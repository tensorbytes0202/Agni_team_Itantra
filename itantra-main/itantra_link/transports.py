"""
Transports. All share one interface so Radio Manager doesn't care which is which:

    send(raw_bytes)          -> None (best effort, may be dropped)
    receive(timeout)         -> bytes | None
    enabled (bool)           -> kill switch for demos
    compact (bool)           -> use compact packet encoding on this link
    name                     -> "WIFI" / "BLUETOOTH" / "LOWBITRATE"

Implemented now:
    UdpWifiTransport          - REAL UDP socket over the local WiFi network
    EmulatedLowBitrateTransport - UDP underneath, but throttled to N bps with
                                  random packet loss + bit errors, so it behaves
                                  like a weak long-range radio (LoRa-class).
Next:
    Bluetooth RFCOMM (same interface), LoRa serial (same interface).
"""
import queue
import random
import socket
import threading
import time
from typing import Optional


class UdpWifiTransport:
    name = "WIFI"
    compact = False

    def __init__(self, local_port: int, peer_ip: str, peer_port: int, bind_ip: str = "0.0.0.0"):
        self.peer = (peer_ip, peer_port)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((bind_ip, local_port))
        self.sock.settimeout(0.2)
        self.enabled = True  # kill switch
        # EMULATED interference for demos (channel_lab.py); 0 = real WiFi untouched
        self.loss = 0.0      # probability an outgoing packet is dropped
        self.delay = 0.0     # extra seconds before an outgoing packet leaves
        self._rng = random.Random()

    def send(self, raw: bytes):
        if not self.enabled:
            return
        if self.loss and self._rng.random() < self.loss:
            return
        if self.delay:
            threading.Timer(self.delay, self._sendto, (raw,)).start()
        else:
            self._sendto(raw)

    def _sendto(self, raw: bytes):
        try:
            self.sock.sendto(raw, self.peer)
        except OSError:
            pass  # network down -> treated as loss

    def receive(self, timeout: float = 0.2) -> Optional[bytes]:
        self.sock.settimeout(timeout)
        try:
            data, _ = self.sock.recvfrom(65535)
        except (socket.timeout, OSError):
            return None
        if not self.enabled:
            return None  # link "down": ignore anything that arrives
        return data

    def close(self):
        self.sock.close()


class EmulatedLowBitrateTransport:
    """
    Weak long-range radio emulation.
      bitrate_bps : air data rate (default 600 bps)
      loss        : probability a whole packet is lost
      ber         : probability each bit is flipped (CRC catches it)
    Packets are sent one after another, each occupying the channel for
    len(bits)/bitrate seconds, exactly like a half-duplex radio.
    """
    name = "LOWBITRATE"
    compact = True

    def __init__(self, local_port: int, peer_ip: str, peer_port: int,
                 bitrate_bps: int = 600, loss: float = 0.1, ber: float = 0.0002,
                 bind_ip: str = "0.0.0.0", seed: Optional[int] = None):
        self.peer = (peer_ip, peer_port)
        self.bitrate_bps = bitrate_bps
        self.loss = loss
        self.ber = ber
        self.enabled = True
        # EMULATED radio frequency (channel index). None = off. When set, a packet
        # is only heard by a receiver tuned to the same channel, like a real radio.
        self.freq: Optional[int] = None
        self._rng = random.Random(seed)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((bind_ip, local_port))
        self._tx = queue.Queue()
        self._stop = False
        threading.Thread(target=self._air_loop, daemon=True).start()

    def airtime(self, nbytes: int) -> float:
        return nbytes * 8 / self.bitrate_bps

    def send(self, raw: bytes):
        if self.enabled:
            self._tx.put(raw)

    def _air_loop(self):
        while not self._stop:
            try:
                raw = self._tx.get(timeout=0.2)
            except queue.Empty:
                continue
            time.sleep(self.airtime(len(raw)))          # channel busy for the airtime
            if self._rng.random() < self.loss:
                continue                                  # whole packet lost
            data = bytearray(raw)
            if self.ber > 0:
                for i in range(len(data)):
                    for b in range(8):
                        if self._rng.random() < self.ber:
                            data[i] ^= (1 << b)
            if self.freq is not None:                     # emulator tag, not sent over the air
                data = bytes([self.freq]) + data
            try:
                self.sock.sendto(bytes(data), self.peer)
            except OSError:
                pass

    def receive(self, timeout: float = 0.2) -> Optional[bytes]:
        self.sock.settimeout(timeout)
        try:
            data, _ = self.sock.recvfrom(65535)
        except (socket.timeout, OSError):
            return None
        if not self.enabled:
            return None
        if self.freq is not None:                         # tuned to another frequency -> not heard
            if not data or data[0] != self.freq:
                return None
            data = data[1:]
        return data

    def close(self):
        self._stop = True
        self.sock.close()
