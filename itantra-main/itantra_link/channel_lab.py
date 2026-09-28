"""
Channel lab (EMULATED) + auto-discovery for the two-laptop demo.

1. Discovery: each app says "hello" on the LAN every second (UDP broadcast +
   unicast to 127.0.0.1 and any typed peer IP). When the other role answers,
   both apps point their links at it. Until then nothing can be delivered and
   messages wait in the queue (store-and-forward), so transmission starts only
   once sender and receiver have found each other.

2. Channel conditions, shared by both laptops:
     WiFi interference      Clean / Noisy / Bad / Dead      (loss + delay on the WiFi link)
     Radio frequency        865-867 MHz channels            (both sides must be on the same one)
     Noise per frequency    Clean / Noisy / Bad / Jammed    (loss + bit errors on that frequency)
   A change on either laptop is copied to the other through the hello messages,
   so both sides always see the same "air". Everything here is EMULATED: on real
   LoRa hardware the frequency is set on the radio module, and both radios
   follow a pre-agreed channel plan instead of this LAN sync.
"""
import json
import os
import socket
import threading
import time
from typing import Callable, Dict, List, Optional

FREQS_MHZ = [865.0625, 865.4025, 865.9850, 866.5500, 866.9500]    # India 865-867 MHz licence-free band

WIFI_LEVELS = ["Clean", "Noisy", "Bad", "Dead"]
WIFI_EFFECT = {"Clean": (0.0, 0.0), "Noisy": (0.05, 0.05), "Bad": (0.4, 0.35), "Dead": (1.0, 0.0)}  # loss, delay s

RADIO_LEVELS = ["Clean", "Noisy", "Bad", "Jammed"]
RADIO_EFFECT = {"Clean": (0.02, 0.0), "Noisy": (0.1, 0.0002), "Bad": (0.3, 0.0008), "Jammed": (1.0, 0.0)}  # loss, BER

DISCOVERY_PORT = {"sender": 5901, "receiver": 5902}      # each role listens on its own port
OTHER = {"sender": "receiver", "receiver": "sender"}
PEER_TIMEOUT = 5.0


def default_env() -> Dict:
    return {"wifi": "Clean", "freq": 0, "noise": ["Noisy"] + ["Clean"] * (len(FREQS_MHZ) - 1), "ver": 0}


def apply_env(env: Dict, wifi, lb):
    """Push the shared channel conditions into the two transports."""
    wifi.loss, wifi.delay = WIFI_EFFECT[env["wifi"]]
    lb.freq = env["freq"]
    lb.loss, lb.ber = RADIO_EFFECT[env["noise"][env["freq"]]]


def _broadcast_addrs() -> List[str]:
    addrs = {"255.255.255.255", "127.0.0.1"}
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith("127."):
                addrs.add(ip.rsplit(".", 1)[0] + ".255")          # /24 subnet broadcast
    except OSError:
        pass
    return sorted(addrs)


class Discovery:
    """
    Finds the other laptop and keeps the channel conditions in sync.
      on_peer(ip, info)   called when a peer appears or its address changes
      on_env(env)         called when the peer changed the channel conditions
    """

    def __init__(self, role: str, name: str, wifi_port: int, lb_port: int,
                 on_peer: Callable[[str, Dict], None], on_env: Callable[[Dict], None],
                 manual_ip: Optional[str] = None, port_offset: int = 0):
        self.role, self.name = role, name
        self.ports = {"wifi_port": wifi_port, "lb_port": lb_port}
        self.on_peer, self.on_env = on_peer, on_env
        self.manual_ip = manual_ip
        self.id = os.urandom(4).hex()
        self.env = default_env()
        self.peer_ip: Optional[str] = None
        self.peer: Dict = {}
        self.last_seen = 0.0
        self._addr_seen = 0.0            # last hello heard on the chosen peer address
        self._lock = threading.Lock()
        self._stop = False
        self._listen = DISCOVERY_PORT[role] + port_offset
        self._target = DISCOVERY_PORT[OTHER[role]] + port_offset
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self.sock.bind(("0.0.0.0", self._listen))
        self.sock.settimeout(0.5)
        self._addrs = _broadcast_addrs()

    @property
    def connected(self) -> bool:
        return self.peer_ip is not None and time.time() - self.last_seen < PEER_TIMEOUT

    def start(self):
        threading.Thread(target=self._rx, daemon=True).start()
        threading.Thread(target=self._tx, daemon=True).start()

    def stop(self):
        self._stop = True

    def set_env(self, **changes):
        """Local change (from the UI): bump the version so the peer adopts it."""
        with self._lock:
            self.env.update(changes)
            self.env["ver"] += 1
            env = json.loads(json.dumps(self.env))
        self._hello()                                   # tell the peer right away
        return env

    def _hello(self):
        with self._lock:
            msg = json.dumps({"app": "itantra", "id": self.id, "role": self.role, "name": self.name,
                              **self.ports, "env": self.env}).encode()
        targets = list(self._addrs)
        if self.manual_ip:
            targets.append(self.manual_ip)
        if self.peer_ip:
            targets.append(self.peer_ip)
        for ip in set(targets):
            try:
                self.sock.sendto(msg, (ip, self._target))
            except OSError:
                pass

    def _tx(self):
        while not self._stop:
            self._hello()
            time.sleep(1.0)

    def _rx(self):
        while not self._stop:
            try:
                raw, (ip, _) = self.sock.recvfrom(4096)
                m = json.loads(raw)
            except (socket.timeout, OSError, ValueError):
                continue
            if m.get("app") != "itantra" or m.get("id") == self.id or m.get("role") != OTHER[self.role]:
                continue
            # The same peer is often heard on several addresses (loopback, WiFi,
            # virtual adapters). Stick to one; move only if it goes quiet.
            now = time.time()
            same_peer = m.get("id") == self.peer.get("id")
            if ip == self.peer_ip:
                self._addr_seen = now
            move = not same_peer or (ip != self.peer_ip and now - self._addr_seen > 3.0)
            self.peer, self.last_seen = m, now
            if move:
                self.peer_ip, self._addr_seen = ip, now
                self.on_peer(ip, m)
            env = m.get("env") or {}
            with self._lock:
                mine = self.env["ver"]
                theirs = env.get("ver", -1)
                # newer version wins; on a tie the sender's settings win
                adopt = theirs > mine or (theirs == mine and self.role == "receiver" and env != self.env)
                if adopt:
                    self.env = env
            if adopt:
                self.on_env(json.loads(json.dumps(env)))
