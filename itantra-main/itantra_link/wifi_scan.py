"""
WiFi scan + connect for the offline -> online step (stdlib only).
Windows: netsh.  Linux: nmcli.

    scan()                      -> [{ssid, signal, band, auth, secured}] strongest first (5 GHz wins ties)
    current()                   -> (ssid, signal %) or (None, None)
    connect(ssid, password)     -> (ok, message). Open networks need no password; saved ones neither.
"""
import os
import re
import subprocess
import sys
import tempfile
import time
from xml.sax.saxutils import escape

WIN = sys.platform.startswith("win")


def _run(cmd, timeout=15):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, errors="replace")
        return r.returncode, r.stdout + r.stderr
    except (OSError, subprocess.TimeoutExpired) as e:
        return 1, str(e)


def _kv(line):
    k, _, v = line.partition(":")
    return k.strip(), v.strip()


def _win_rescan(settle=4.0):
    """netsh only lists the last background scan; ask every WiFi adapter for a fresh one (wlanapi)."""
    import ctypes
    import ctypes.wintypes as w

    class INFO(ctypes.Structure):
        _fields_ = [("guid", ctypes.c_byte * 16), ("desc", ctypes.c_wchar * 256), ("state", w.DWORD)]

    class LIST(ctypes.Structure):
        _fields_ = [("n", w.DWORD), ("i", w.DWORD), ("info", INFO * 8)]

    try:
        api, h, ver, lst = ctypes.windll.wlanapi, w.HANDLE(), w.DWORD(), ctypes.POINTER(LIST)()
        if api.WlanOpenHandle(2, None, ctypes.byref(ver), ctypes.byref(h)):
            return
        if not api.WlanEnumInterfaces(h, None, ctypes.byref(lst)):
            for k in range(min(lst.contents.n, 8)):
                api.WlanScan(h, ctypes.byref(lst.contents.info[k].guid), None, None, None)
            api.WlanFreeMemory(lst)
        api.WlanCloseHandle(h, None)
        time.sleep(settle)
    except (OSError, AttributeError):
        pass


def scan():
    nets = {}
    if WIN:
        _win_rescan()
        _, out = _run(["netsh", "wlan", "show", "networks", "mode=bssid"])
        ssid, auth, last = "", "", None
        for line in out.splitlines():
            k, v = _kv(line)
            if re.fullmatch(r"SSID \d+", k):
                ssid, auth = v, ""
            elif k == "Authentication":
                auth = v
            elif k == "Signal" and ssid:
                sig = int(v.rstrip("%") or 0)
                n = nets.setdefault(ssid, {"ssid": ssid, "auth": auth, "signal": -1, "band": ""})
                last = n if sig > n["signal"] else None      # strongest BSSID of this SSID wins
                if last:
                    n["signal"] = sig
            elif k == "Band" and last:
                last["band"] = v
    else:
        _, out = _run(["nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY,FREQ", "dev", "wifi", "list", "--rescan", "yes"])
        for line in out.splitlines():
            p = [x.replace("\\:", ":") for x in re.split(r"(?<!\\):", line)]
            if len(p) < 4 or not p[0] or not p[1].isdigit():
                continue
            n = nets.setdefault(p[0], {"ssid": p[0], "auth": p[2], "signal": -1, "band": ""})
            if int(p[1]) > n["signal"]:
                n.update(signal=int(p[1]), band="5 GHz" if p[3].startswith(("5", "6")) else "2.4 GHz")
    res = list(nets.values())
    for n in res:
        n["secured"] = n["auth"].strip().lower() not in ("", "open", "--")
    return sorted(res, key=lambda n: (-n["signal"], "2.4" in n["band"]))


def current():
    if WIN:
        _, out = _run(["netsh", "wlan", "show", "interfaces"], 5)
        kv = dict(_kv(l) for l in out.splitlines() if ":" in l)
        if kv.get("State", "").lower() == "connected" and kv.get("SSID"):
            return kv["SSID"], int(kv.get("Signal", "0%").rstrip("%") or 0)
        return None, None
    _, out = _run(["nmcli", "-t", "-f", "ACTIVE,SSID,SIGNAL", "dev", "wifi"], 5)
    for line in out.splitlines():
        p = line.split(":")
        if p[0] == "yes" and len(p) >= 3:
            return p[1], int(p[-1] or 0)
    return None, None


def _profiles():
    _, out = _run(["netsh", "wlan", "show", "profiles"], 5)
    return {_kv(l)[1] for l in out.splitlines() if "Profile" in l and ":" in l}


def _add_profile(ssid, pw, auth):
    s = escape(ssid)
    if pw:
        a = "WPA3SAE" if "WPA3" in auth and "WPA2" not in auth else "WPA2PSK"
        sec = (f"<authEncryption><authentication>{a}</authentication><encryption>AES</encryption>"
               f"<useOneX>false</useOneX></authEncryption><sharedKey><keyType>passphrase</keyType>"
               f"<protected>false</protected><keyMaterial>{escape(pw)}</keyMaterial></sharedKey>")
    else:
        sec = ("<authEncryption><authentication>open</authentication><encryption>none</encryption>"
               "<useOneX>false</useOneX></authEncryption>")
    xml = ('<?xml version="1.0"?><WLANProfile xmlns="http://www.microsoft.com/networking/WLAN/profile/v1">'
           f"<name>{s}</name><SSIDConfig><SSID><name>{s}</name></SSID></SSIDConfig>"
           f"<connectionType>ESS</connectionType><connectionMode>auto</connectionMode>"
           f"<MSM><security>{sec}</security></MSM></WLANProfile>")
    fd, path = tempfile.mkstemp(suffix=".xml")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(xml)
        _run(["netsh", "wlan", "delete", "profile", f"name={ssid}"], 5)
        rc, out = _run(["netsh", "wlan", "add", "profile", f"filename={path}", "user=current"], 10)
    finally:
        os.remove(path)                                   # file held the password
    return rc == 0, out.strip()


def connect(ssid, password=None, auth="", wait=12):
    # SSIDs come from nearby access points, i.e. anyone: block netsh wildcards ("*" = every
    # saved profile), quotes and option-like names before they reach a command line.
    if not ssid or ssid.strip() == "*" or ssid.startswith("-") or any(c in ssid for c in '"\r\n\0'):
        return False, "refusing unsafe network name"
    if WIN:
        if password or ssid not in _profiles():
            secured = auth.strip().lower() not in ("", "open")
            if secured and not password:
                return False, "this network needs a password"
            ok, msg = _add_profile(ssid, password if secured else None, auth)
            if not ok:
                return False, msg
        rc, out = _run(["netsh", "wlan", "connect", f"name={ssid}"])
    else:
        rc, out = _run(["nmcli", "dev", "wifi", "connect", ssid] + (["password", password] if password else []), 30)
    if rc:
        return False, out.strip()
    for _ in range(wait * 2):
        if current()[0] == ssid:
            return True, f"connected to {ssid}"
        time.sleep(0.5)
    return False, "timed out (wrong password or out of range?)"
