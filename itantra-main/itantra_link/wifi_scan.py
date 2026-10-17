"""
WiFi scan + connect for the offline -> online step (stdlib only).
Windows: netsh.  macOS: networksetup / system_profiler.  Linux: nmcli.

    scan()                      -> [{ssid, signal, band, auth, secured}] strongest first (5 GHz wins ties)
    current()                   -> (ssid, signal %) or (None, None)
    connect(ssid, password)     -> (ok, message). Open networks need no password; saved ones neither.
"""
import functools
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from xml.sax.saxutils import escape

WIN = sys.platform.startswith("win")
MAC = sys.platform == "darwin"
HIDDEN = "Connected (name hidden by macOS)"   # newer macOS hides the SSID without Location permission


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


@functools.lru_cache(maxsize=1)
def _mac_iface():
    _, out = _run(["networksetup", "-listallhardwareports"], 5)
    m = re.search(r"Hardware Port: (?:Wi-Fi|AirPort)\s*\nDevice: (\S+)", out)
    return m.group(1) if m else "en0"


def _mac_scan(nets):
    _, out = _run(["system_profiler", "SPAirPortDataType", "-json"], 30)
    try:
        ifaces = json.loads(out)["SPAirPortDataType"][0]["spairport_airport_interfaces"]
    except (ValueError, KeyError, IndexError, TypeError):
        return
    for ifc in ifaces:
        cur = ifc.get("spairport_current_network_information")
        for net in ifc.get("spairport_airport_other_local_wireless_networks", []) + ([cur] if cur else []):
            name = net.get("_name", "")
            m = re.match(r"\s*(-?\d+)", str(net.get("spairport_signal_noise", "")))
            if not name or name.startswith("<") or not m:            # "<redacted>": name hidden by macOS
                continue
            sig = max(0, min(100, 2 * (int(m.group(1)) + 100)))      # dBm -> % (-50 dBm = 100 %, -100 = 0 %)
            ch, sec = str(net.get("spairport_network_channel", "")), str(net.get("spairport_security_mode", ""))
            auth = "Open" if not sec or sec.endswith("none") else \
                sec.replace("spairport_security_mode_", "").replace("_", " ").upper()
            n = nets.setdefault(name, {"ssid": name, "auth": auth, "signal": -1, "band": ""})
            if sec:                                           # some entries omit the security mode
                n["auth"] = auth
            if sig > n["signal"]:
                n.update(signal=sig, band="6 GHz" if "6GHz" in ch else "5 GHz" if "5GHz" in ch else "2.4 GHz" if ch else "")


def scan():
    nets = {}
    if MAC:
        _mac_scan(nets)
    elif WIN:
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
    if MAC:                                               # signal % has no fast source on macOS
        iface = _mac_iface()
        _, out = _run(["networksetup", "-getairportnetwork", iface], 5)
        m = re.search(r"Current Wi-Fi Network: (.+)", out)
        if m:
            return m.group(1).strip(), None
        _, out = _run(["ipconfig", "getsummary", iface], 5)
        m = re.search(r"^\s*SSID : (.+)$", out, re.M)
        if m and not m.group(1).startswith("<"):
            return m.group(1).strip(), None
        rc, ip = _run(["ipconfig", "getifaddr", iface], 5)
        return (HIDDEN, None) if rc == 0 and ip.strip() else (None, None)
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
    elif MAC:                                             # saved networks use the keychain password
        rc, out = _run(["networksetup", "-setairportnetwork", _mac_iface(), ssid] + ([password] if password else []), 40)
        if re.search(r"error|could not|failed", out, re.I):
            rc = rc or 1
    else:
        rc, out = _run(["nmcli", "dev", "wifi", "connect", ssid] + (["password", password] if password else []), 30)
    if rc:
        return False, out.strip()
    for _ in range(wait * 2):
        if current()[0] in (ssid, HIDDEN if MAC else None):
            return True, f"connected to {ssid}"
        time.sleep(0.5)
    return False, "timed out (wrong password or out of range?)"
