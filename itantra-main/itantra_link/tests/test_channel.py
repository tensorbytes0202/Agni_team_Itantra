"""
Channel lab test (EMULATED channel): discovery, settings sync, frequency,
interference -> failover, jamming -> queue, frequency change -> recovery.
    python -m itantra_link.tests.test_channel
"""
import threading
import time

from itantra_link import channel_lab as CH
from itantra_link.radio_manager import RadioManager
from itantra_link.transports import EmulatedLowBitrateTransport, UdpWifiTransport

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


def texts():
    return [m.text for m in received if m.kind == "TEXT"]


def main():
    results = []

    def check(name, ok):
        results.append(ok)
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")

    # 1. frequency: only a receiver on the same frequency hears the packet
    a = EmulatedLowBitrateTransport(17001, "127.0.0.1", 17002, bitrate_bps=100000, loss=0, ber=0)
    b = EmulatedLowBitrateTransport(17002, "127.0.0.1", 17001, bitrate_bps=100000, loss=0, ber=0)
    a.freq, b.freq = 0, 1
    a.send(b"hello")
    check("different frequency -> not heard", b.receive(1.0) is None)
    b.freq = 0
    a.send(b"hello")
    check("same frequency -> heard", b.receive(1.0) == b"hello")
    a.close(); b.close()

    # 2. discovery + settings sync
    found = {}
    envs = []
    s = CH.Discovery("sender", "S", 1, 2, on_peer=lambda ip, m: found.update(s=m),
                     on_env=lambda e: None, port_offset=200)
    r = CH.Discovery("receiver", "R", 3, 4, on_peer=lambda ip, m: found.update(r=m),
                     on_env=envs.append, port_offset=200)
    s.start(); r.start()
    ok = wait_for(lambda: "s" in found and "r" in found, 5)
    check("sender and receiver find each other", ok and found["s"]["lb_port"] == 4 and found["r"]["wifi_port"] == 1)
    s.set_env(wifi="Dead", freq=2)
    check("channel change on sender is copied to receiver",
          wait_for(lambda: envs and envs[-1]["wifi"] == "Dead" and envs[-1]["freq"] == 2, 5))
    s.stop(); r.stop()

    # 3. end-to-end with Radio Manager
    quiet = lambda msg: print("   ", msg)
    wa, wb = UdpWifiTransport(17101, "127.0.0.1", 17102), UdpWifiTransport(17102, "127.0.0.1", 17101)
    la = EmulatedLowBitrateTransport(17201, "127.0.0.1", 17202, bitrate_bps=600, seed=1)
    lb = EmulatedLowBitrateTransport(17202, "127.0.0.1", 17201, bitrate_bps=600, seed=2)
    env = CH.default_env()

    def set_env(**kw):
        env.update(kw)
        CH.apply_env(env, wa, la)
        CH.apply_env(env, wb, lb)

    set_env()
    A = RadioManager([wa, la], on_receive=lambda m: None, log=quiet)
    B = RadioManager([wb, lb], on_receive=rx, log=quiet)
    A.start(); B.start()
    time.sleep(5)
    A.send_message("clean channel test", "en")
    check("clean channel -> delivered on WiFi",
          wait_for(lambda: any(m.text == "clean channel test" and m.channel == "WIFI" for m in received), 5))

    set_env(wifi="Bad")
    check("WiFi interference 'Bad' -> fails over to LOWBITRATE", wait_for(lambda: A.current == "LOWBITRATE", 20))
    A.send_message("emergency send help", "en")
    check("message still delivered over the radio link",
          wait_for(lambda: "emergency send help" in texts(), 30))

    set_env(wifi="Dead", noise=["Jammed"] + env["noise"][1:])
    time.sleep(12)
    A.send_message("after jamming", "en")
    time.sleep(6)
    check("WiFi dead + frequency jammed -> nothing gets through (queued)", "after jamming" not in texts())

    set_env(freq=1)                                   # move both radios to a clean frequency
    check("switch to clean frequency -> queued message delivered",
          wait_for(lambda: "after jamming" in texts(), 40))

    A.stop(); B.stop()
    print(f"\n{sum(results)}/{len(results)} passed")
    raise SystemExit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
