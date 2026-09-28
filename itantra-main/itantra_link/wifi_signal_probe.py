"""
Real WiFi signal-strength + packet-loss probe (Windows only, standalone).

Independent of the rest of itantra_link: run it alongside node.py's
--log-status on both laptops while you physically weaken the WiFi signal
(walk away, add obstacles, lower the router's TX power). It logs, once per
--interval:

    real signal strength (netsh wlan)  +  real network-level ping loss/RTT

to a CSV, timestamped so you can line it up against node.py's
--log-status CSV (which shows the app's own PER/RTT and WIFI->LOWBITRATE
failover) and see exactly what signal level makes the app switch links.

Usage (run on ONE of the two laptops, pointed at the other's IP):

    python -m itantra_link.wifi_signal_probe --peer 192.168.1.23 --out signal_log.csv
"""
import argparse
import csv
import os
import re
import subprocess
import time

SIGNAL_RE = re.compile(r"^\s*Signal\s*:\s*(\d+)%", re.MULTILINE)
RX_RATE_RE = re.compile(r"^\s*Receive rate \(Mbps\)\s*:\s*([\d.]+)", re.MULTILINE)
TX_RATE_RE = re.compile(r"^\s*Transmit rate \(Mbps\)\s*:\s*([\d.]+)", re.MULTILINE)
CHANNEL_RE = re.compile(r"^\s*Channel\s*:\s*(\d+)", re.MULTILINE)


def wifi_info():
    """(signal_pct, tx_mbps, rx_mbps, channel) from `netsh wlan show interfaces`; Nones if unavailable."""
    try:
        out = subprocess.run(["netsh", "wlan", "show", "interfaces"],
                              capture_output=True, text=True, timeout=3).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None, None, None, None
    sig, tx, rx, ch = SIGNAL_RE.search(out), TX_RATE_RE.search(out), RX_RATE_RE.search(out), CHANNEL_RE.search(out)
    return (int(sig.group(1)) if sig else None,
            float(tx.group(1)) if tx else None,
            float(rx.group(1)) if rx else None,
            int(ch.group(1)) if ch else None)


def ping_once(peer: str, timeout_ms: int = 1000):
    """One ICMP ping. Returns RTT in ms, or None if it timed out / failed."""
    try:
        out = subprocess.run(["ping", "-n", "1", "-w", str(timeout_ms), peer],
                              capture_output=True, text=True, timeout=timeout_ms / 1000 + 2).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None
    m = re.search(r"time[=<](\d+)ms", out)
    if not m or "Request timed out" in out or "could not find host" in out.lower():
        return None
    return int(m.group(1))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--peer", required=True, help="other laptop's IP (same one used as --peer-ip for node.py)")
    ap.add_argument("--out", default="signal_log.csv")
    ap.add_argument("--interval", type=float, default=1.0, help="seconds between samples")
    ap.add_argument("--window", type=int, default=10, help="rolling window size for loss %% (default: 10 pings)")
    a = ap.parse_args()

    is_new = not os.path.exists(a.out)
    recent = []  # rolling ping outcomes: True = reply, False = loss
    with open(a.out, "a", newline="") as f:
        w = csv.writer(f)
        if is_new:
            w.writerow(["timestamp", "wifi_signal_pct", "tx_mbps", "rx_mbps", "channel",
                        "ping_rtt_ms", "ping_lost", f"loss_pct_last_{a.window}"])
            f.flush()
        print(f"Logging to {a.out} every {a.interval}s. Ctrl+C to stop.")
        try:
            while True:
                sig, tx, rx, ch = wifi_info()
                rtt = ping_once(a.peer)
                recent.append(rtt is not None)
                del recent[:-a.window]
                loss_pct = round(100 * (1 - sum(recent) / len(recent)), 1)
                w.writerow([time.strftime("%Y-%m-%d %H:%M:%S"), sig, tx, rx, ch,
                            rtt if rtt is not None else "", rtt is None, loss_pct])
                f.flush()
                print(f"signal={sig}%  rtt={rtt}ms  loss(last {len(recent)})={loss_pct}%")
                time.sleep(max(0.0, a.interval))
        except KeyboardInterrupt:
            print("\nstopped")


if __name__ == "__main__":
    main()
