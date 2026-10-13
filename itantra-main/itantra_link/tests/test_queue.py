"""
Store-and-forward: a message sent with no link stays queued on disk, survives a restart,
and is delivered once the link comes back.   python -m itantra_link.tests.test_queue
"""
import os
import tempfile
import time

from itantra_link.radio_manager import RadioManager
from itantra_link.transports import UdpWifiTransport


def wait(cond, t):
    end = time.time() + t
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.1)
    return False


def main():
    qf = os.path.join(tempfile.mkdtemp(), "q.json")
    got = []
    rx = RadioManager([UdpWifiTransport(5702, "127.0.0.1", 5701)], on_receive=got.append, log=lambda s: None)
    rx.start()

    w = UdpWifiTransport(5701, "127.0.0.1", 5702)
    w.enabled = False                                         # offline
    tx = RadioManager([w], log=lambda s: None, queue_file=qf)
    tx.start()
    tx.send_message("normal note", "en")
    tx.send_message("emergency, madad bhejo", "hi")
    time.sleep(3)
    assert tx.queued == 2 and not got, "offline: must stay queued"
    assert os.path.exists(qf), "queue must be on disk"
    tx.stop(); w.close(); time.sleep(0.5)
    print("PASS offline -> 2 messages queued and saved")

    w2 = UdpWifiTransport(5701, "127.0.0.1", 5702)            # app restart, network back
    tx2 = RadioManager([w2], log=lambda s: None, queue_file=qf)
    assert tx2.queued == 2, "queue must survive restart"
    tx2.start()
    assert wait(lambda: len(got) == 2, 15), f"not delivered: {got}"
    assert got[0].alert, "alert must be sent first"
    assert wait(lambda: tx2.queued == 0, 3)
    print("PASS restart + link back -> delivered, alert first, queue empty")


if __name__ == "__main__":
    main()
