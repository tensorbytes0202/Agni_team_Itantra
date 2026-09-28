"""
Run one iTantra node. Start two nodes (two laptops on same WiFi, or two
terminals on one laptop) and type messages.

One laptop, two terminals:
  python -m itantra_link.node --name A --wifi-port 5001 --peer-wifi-port 5002 --lb-port 6001 --peer-lb-port 6002
  python -m itantra_link.node --name B --wifi-port 5002 --peer-wifi-port 5001 --lb-port 6002 --peer-lb-port 6001

Two laptops (same WiFi): add --peer-ip <other laptop IP> on both, use the same ports on both.

Commands while running:
  <text>          send text (current language)
  /lang hi        set language code (en hi gu mr kn ml ta te or bn)
  /wifi off|on    WiFi kill switch (demo: forces fallback to low-bitrate)
  /lb off|on      low-bitrate link kill switch
  /loss 0.3       set low-bitrate packet loss
  /loc 28.66 77.45  set own location (on a phone this comes from GPS, offline)
  /status         show link health
  /quit

--log-status FILE.csv logs active channel + per-link PER/RTT/CRC-drops every
--log-interval seconds (default 1s), so you can correlate WiFi signal-strength
tests (see wifi_signal_probe.py) against real app-level behaviour over time.
"""
import argparse
import csv
import os
import sys
import threading
import time

from .radio_manager import RadioManager, Received
from .transports import EmulatedLowBitrateTransport, UdpWifiTransport
from . import location as L

RM = None  # set in main(), used to show distance from our own location


SPEAKER = None  # set in main() unless --no-tts


def _status_logger(rm: RadioManager, path: str, interval: float):
    names = list(rm.t)
    is_new = not os.path.exists(path)
    with open(path, "a", newline="") as f:
        w = csv.writer(f)
        if is_new:
            header = ["timestamp", "active_channel"]
            for n in names:
                header += [f"{n}_up", f"{n}_per_pct", f"{n}_rtt_ms", f"{n}_crc_drops"]
            w.writerow(header)
            f.flush()
        while True:
            row = [time.strftime("%Y-%m-%d %H:%M:%S"), rm.current or ""]
            for n in names:
                st = rm.stats[n]
                rtt = "" if st.rtt_ms == float("inf") else round(st.rtt_ms, 1)
                row += [rm.healthy(n), round(st.per * 100, 1), rtt, st.crc_drops]
            w.writerow(row)
            f.flush()
            time.sleep(interval)


def tts_play(msg: Received):
    """Speak the received message (offline TTS). Alerts: siren + full volume, not interruptible."""
    if SPEAKER is not None:
        SPEAKER.say(msg)
    elif msg.alert:
        print(f"\n  [TTS ALERT - MAX VOLUME, NON-INTERRUPTIBLE] {msg.text}")
    else:
        print(f"\n  [TTS voice note] {msg.text}")


def on_receive(msg: Received):
    lat = f"{msg.latency_ms:.0f} ms" if msg.latency_ms is not None else "n/a (compact link)"
    tag = "!!! ALERT !!!" if msg.alert else "message"
    extra = f", FEC fixed {msg.fec_corrections} bit(s)" if msg.fec_corrections else ""
    print(f"\n<<< {tag} [{msg.kind}] via {msg.channel} lang={msg.lang} latency={lat}{extra}")
    print(f"    {msg.text}")
    if msg.location:
        own = RM.location if RM else None
        print(f"    LOCATION: {L.describe(msg.location, own)}   geo:{msg.location[0]},{msg.location[1]}")
    tts_play(msg)
    print("> ", end="", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="A")
    ap.add_argument("--peer-ip", default="127.0.0.1")
    ap.add_argument("--wifi-port", type=int, required=True)
    ap.add_argument("--peer-wifi-port", type=int, required=True)
    ap.add_argument("--lb-port", type=int, required=True)
    ap.add_argument("--peer-lb-port", type=int, required=True)
    ap.add_argument("--lb-bps", type=int, default=600)
    ap.add_argument("--lb-loss", type=float, default=0.1)
    ap.add_argument("--verbose", action="store_true", help="print every dropped corrupt packet")
    ap.add_argument("--no-tts", action="store_true", help="print instead of speaking")
    ap.add_argument("--save-wav", default=None, help="write spoken audio to this folder instead of playing")
    ap.add_argument("--lat", type=float, default=None, help="demo location (phone uses GPS)")
    ap.add_argument("--lon", type=float, default=None)
    ap.add_argument("--log-status", default=None,
                     help="CSV file to append active channel + per-link PER/RTT/CRC-drops to, every --log-interval s")
    ap.add_argument("--log-interval", type=float, default=1.0, help="seconds between --log-status rows")
    a = ap.parse_args()

    wifi = UdpWifiTransport(a.wifi_port, a.peer_ip, a.peer_wifi_port)
    lb = EmulatedLowBitrateTransport(a.lb_port, a.peer_ip, a.peer_lb_port,
                                     bitrate_bps=a.lb_bps, loss=a.lb_loss)
    rm = RadioManager([wifi, lb], on_receive=on_receive,
                      log=lambda s: print(f"\n{s}\n> ", end="", flush=True),
                      verbose=a.verbose)
    global RM, SPEAKER
    RM = rm
    if not a.no_tts:
        from .speaker import Speaker
        SPEAKER = Speaker(lambda: rm.location, save_dir=a.save_wav)
    if a.lat is not None and a.lon is not None:
        rm.set_location(a.lat, a.lon)
    rm.start()
    if a.log_status:
        threading.Thread(target=_status_logger, args=(rm, a.log_status, a.log_interval), daemon=True).start()
        print(f"Logging link status to {a.log_status} every {a.log_interval}s.")
    lang = "en"
    print(f"Node {a.name} running. Low-bitrate link = EMULATED {a.lb_bps} bps. Type /status.")
    while True:
        try:
            line = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not line:
            continue
        if line == "/quit":
            break
        if line == "/status":
            print(rm.status()); continue
        if line.startswith("/lang "):
            lang = line.split()[1]; print(f"language = {lang}"); continue
        if line.startswith("/wifi "):
            wifi.enabled = line.endswith("on"); print(f"WiFi enabled = {wifi.enabled}"); continue
        if line.startswith("/lb "):
            lb.enabled = line.endswith("on"); print(f"Low-bitrate enabled = {lb.enabled}"); continue
        if line.startswith("/loc "):
            _, la, lo = line.split()
            rm.set_location(float(la), float(lo)); print(f"location = {la}, {lo}"); continue
        if line.startswith("/ber "):
            lb.ber = float(line.split()[1]); print(f"low-bitrate bit error rate = {lb.ber}"); continue
        if line.startswith("/loss "):
            lb.loss = float(line.split()[1]); print(f"low-bitrate loss = {lb.loss}"); continue
        rm.send_message(line, lang)
        print(f"(queued, active channel = {rm.current})")
    rm.stop()


if __name__ == "__main__":
    main()
