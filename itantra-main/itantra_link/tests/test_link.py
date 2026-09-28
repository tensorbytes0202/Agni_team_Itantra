"""
End-to-end test: two real nodes over localhost UDP, one process.
Runs the acceptance tests from the Transmission Plan.
    python -m itantra_link.tests.test_link
"""
import time
import threading

from itantra_link.radio_manager import RadioManager
from itantra_link.transports import UdpWifiTransport, EmulatedLowBitrateTransport
from itantra_link import packet as P

received = []
lock = threading.Lock()


def rx(msg):
    with lock:
        received.append(msg)


def wait_for(pred, timeout):
    end = time.time() + timeout
    while time.time() < end:
        with lock:
            if pred():
                return True
        time.sleep(0.1)
    return False


def main():
    quiet = lambda s: print("   ", s)
    wa, wb = UdpWifiTransport(15001, "127.0.0.1", 15002), UdpWifiTransport(15002, "127.0.0.1", 15001)
    la = EmulatedLowBitrateTransport(16001, "127.0.0.1", 16002, bitrate_bps=600, loss=0.1, seed=1)
    lb = EmulatedLowBitrateTransport(16002, "127.0.0.1", 16001, bitrate_bps=600, loss=0.1, seed=2)
    A = RadioManager([wa, la], on_receive=lambda m: None, log=quiet)
    B = RadioManager([wb, lb], on_receive=rx, log=quiet)
    A.set_location(28.669156, 77.453758)   # sender (demo coords)
    A.start(); B.start()
    results = {}

    print("\n[1] Link discovery")
    ok = wait_for(lambda: A.current == "WIFI", 8)
    print("   ", A.status()); results["picks WiFi when healthy"] = ok

    print("\n[2] 10 messages over WiFi")
    for i in range(10):
        A.send_message(f"status update {i}", "en")
    ok = wait_for(lambda: sum(m.kind == "TEXT" for m in received) >= 10, 10)
    texts = [m.text for m in received if m.kind == "TEXT"]
    results["10/10 delivered on WiFi, no duplicates"] = ok and len(texts) == 10 and len(set(texts)) == 10
    results["location on WiFi"] = all(m.location == (28.669155, 77.453758) or
                                      (m.location and abs(m.location[0]-28.669156) < 1e-5)
                                      for m in received if m.kind == "TEXT")
    lats = [m.latency_ms for m in received if m.latency_ms is not None]
    print(f"    delivered={len(texts)}  avg latency={sum(lats)/len(lats):.1f} ms")

    print("\n[3] Kill WiFi -> automatic fallback to low-bitrate")
    t0 = time.time()
    wa.enabled = False
    ok = wait_for(lambda: A.current == "LOWBITRATE", 12)
    print(f"    switched in {time.time()-t0:.1f}s ->", A.status())
    results["fails over to LOWBITRATE"] = ok

    print("\n[4] Emergency on low-bitrate: SUMMARY first, then full text")
    with lock:
        received.clear()
    A.send_message("emergency, madad bhejo, river bridge ke paas", "hi")
    ok = wait_for(lambda: any(m.kind == "TEXT" for m in received), 25)
    kinds = [(m.kind, m.text, m.alert, m.channel) for m in received]
    for k in kinds:
        print("   ", k)
    results["summary arrives before full text"] = ok and len(kinds) >= 2 and kinds[0][0] == "SUMMARY"
    results["alert flag set"] = ok and all(k[2] for k in kinds)
    from itantra_link.location import distance_bearing
    locs = [m.location for m in received]
    print("    locations received:", locs)
    results["location in summary + text (<5 m error)"] = ok and all(
        l is not None and distance_bearing(l, (28.669156, 77.453758))[0] < 5 for l in locs)

    print("\n[5] Store-and-forward: all links down, message queued, delivered on recovery")
    la.enabled = False
    time.sleep(3)
    with lock:
        received.clear()
    A.send_message("water needed at school", "en")
    time.sleep(3)
    queued_ok = not received
    wa.enabled = True; la.enabled = True
    ok = wait_for(lambda: any(m.kind == "TEXT" for m in received), 25)
    results["queued while down, delivered after"] = queued_ok and ok
    print("    delivered via", [m.channel for m in received if m.kind == "TEXT"])

    print("\n[6] WiFi restored -> returns to WiFi (hysteresis)")
    ok = wait_for(lambda: A.current == "WIFI", 25)
    print("   ", A.status()); results["returns to WiFi"] = ok

    print("\n[7] Corrupted packet is rejected by CRC")
    raw = bytearray(P.Packet(P.DATA, 999, payload=b"hello").encode())
    raw[18] ^= 0x01
    try:
        P.decode(bytes(raw)); results["CRC rejects corruption"] = False
    except P.CorruptPacket:
        results["CRC rejects corruption"] = True

    print("\n================ RESULTS ================")
    for k, v in results.items():
        print(f"  {'PASS' if v else 'FAIL'}  {k}")
    A.stop(); B.stop()
    return all(results.values())


if __name__ == "__main__":
    raise SystemExit(0 if main() else 1)
