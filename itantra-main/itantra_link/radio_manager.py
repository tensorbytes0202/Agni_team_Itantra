"""
Radio Manager - picks the best link, adapts the message format to it,
and guarantees delivery with ACK / retry / failover / store-and-forward.

Selection (PS-aligned preference, measured health):
    1. WIFI       if reachable, PER < 10 %, RTT < 300 ms
    2. BLUETOOTH  if reachable, PER < 20 %
    3. LOWBITRATE if reachable
    4. none -> queue until a link comes back
Hysteresis: switch to a *different healthy* channel only after it wins
3 checks in a row. If the current channel becomes unhealthy, fail over
immediately.

Link-adaptive format (the unique part):
    WIFI       -> full UTF-8 text
    BLUETOOTH  -> zlib(6) text
    LOWBITRATE -> SUMMARY first (2 bytes, Hamming FEC), then zlib(9) text
"""
import collections
import itertools
import queue
import threading
import time
import zlib
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from . import packet as P
from .summary import analyze, build_summary, is_alert, parse_summary, summary_to_text
from . import location as L

PREFERENCE = ["WIFI", "BLUETOOTH", "LOWBITRATE"]
PROBE_INTERVAL = 2.0
PROBE_WINDOW = 10
HYSTERESIS_WINS = 3
ACK_TIMEOUT = {"WIFI": 0.5, "BLUETOOTH": 1.0}   # LOWBITRATE computed from airtime
RETRIES = 2


@dataclass
class LinkStats:
    results: collections.deque = field(default_factory=lambda: collections.deque(maxlen=PROBE_WINDOW))
    rtts: collections.deque = field(default_factory=lambda: collections.deque(maxlen=PROBE_WINDOW))

    crc_drops: int = 0

    def record(self, ok: bool, rtt: Optional[float] = None):
        self.results.append(ok)
        if ok and rtt is not None:
            self.rtts.append(rtt)

    @property
    def per(self) -> float:
        # Health uses the most recent 5 probes so a recovered link is
        # recognised in ~10 s instead of waiting for the whole window.
        recent = list(self.results)[-5:]
        return 1.0 - (sum(recent) / len(recent)) if recent else 1.0

    @property
    def rtt_ms(self) -> float:
        return 1000 * sum(self.rtts) / len(self.rtts) if self.rtts else float("inf")

    @property
    def reachable(self) -> bool:
        # A weak radio loses some probes normally; only call it down if
        # most of the last 5 failed. Prevents LOWBITRATE <-> None flapping.
        recent = list(self.results)[-5:]
        return any(recent) and self.per < 0.6


@dataclass
class Received:
    kind: str            # "SUMMARY" or "TEXT"
    text: str
    alert: bool
    lang: str
    channel: str
    latency_ms: Optional[float]
    fec_corrections: int = 0
    location: Optional[tuple] = None     # sender's (lat, lon) if shared


class RadioManager:
    def __init__(self, transports: List, on_receive: Callable[[Received], None] = print,
                 log: Callable[[str], None] = print, verbose: bool = False):
        self.verbose = verbose
        self.t: Dict[str, object] = {tr.name: tr for tr in transports}
        self.stats: Dict[str, LinkStats] = {n: LinkStats() for n in self.t}
        self.on_receive = on_receive
        self.log = log
        self.current: Optional[str] = None
        self._challenger: Optional[str] = None
        self._wins = 0
        self._seq = itertools.count(1)
        self._acks: Dict[int, threading.Event] = {}
        self._probes: Dict[int, float] = {}
        self._seen = collections.deque(maxlen=500)
        self._outbox = queue.Queue()
        self._stop = False
        self._lock = threading.Lock()
        self.location: Optional[tuple] = None   # own (lat, lon); set from GPS

    def set_location(self, lat: float, lon: float):
        """Call whenever GPS gives a fix (GPS works offline)."""
        self.location = (lat, lon)

    # ------------------------------------------------------------ lifecycle
    def start(self):
        for name in self.t:
            threading.Thread(target=self._rx_loop, args=(name,), daemon=True).start()
        threading.Thread(target=self._probe_loop, daemon=True).start()
        threading.Thread(target=self._send_loop, daemon=True).start()

    def stop(self):
        self._stop = True

    def next_seq(self) -> int:
        return next(self._seq) & 0xFFFF

    # ------------------------------------------------------------ health
    def healthy(self, name: str) -> bool:
        tr, st = self.t[name], self.stats[name]
        if not tr.enabled or not st.reachable:
            return False
        if name == "WIFI":
            return st.per < 0.10 and st.rtt_ms < 300
        if name == "BLUETOOTH":
            return st.per < 0.20
        return True

    def _best(self) -> Optional[str]:
        for name in PREFERENCE:
            if name in self.t and self.healthy(name):
                return name
        return None

    def _reselect(self):
        best = self._best()
        with self._lock:
            if self.current is None or not self.healthy(self.current):
                if best != self.current:
                    self.log(f"[radio] failover: {self.current} -> {best}")
                self.current, self._challenger, self._wins = best, None, 0
                return
            if best is None or best == self.current:
                self._challenger, self._wins = None, 0
                return
            if best == self._challenger:
                self._wins += 1
            else:
                self._challenger, self._wins = best, 1
            if self._wins >= HYSTERESIS_WINS:
                self.log(f"[radio] switch: {self.current} -> {best} (won {self._wins} checks)")
                self.current, self._challenger, self._wins = best, None, 0

    def status(self) -> str:
        parts = []
        for n in self.t:
            st = self.stats[n]
            rtt = "-" if st.rtt_ms == float("inf") else f"{st.rtt_ms:.0f}ms"
            flag = "UP" if self.healthy(n) else "DOWN"
            parts.append(f"{n}:{flag} PER={st.per*100:.0f}% RTT={rtt} CRC-dropped={st.crc_drops}")
        return f"active={self.current} | " + " | ".join(parts)

    # ------------------------------------------------------------ probing
    def _probe_loop(self):
        while not self._stop:
            for name, tr in self.t.items():
                if not tr.enabled:
                    self.stats[name].record(False)
                    continue
                seq = self.next_seq()
                self._probes[seq] = time.time()
                pkt = P.Packet(P.PROBE, seq)
                tr.send(pkt.encode(compact=tr.compact))
                threading.Thread(target=self._probe_timeout, args=(name, seq, tr), daemon=True).start()
            time.sleep(PROBE_INTERVAL)
            self._reselect()

    def _probe_timeout(self, name, seq, tr):
        wait = ACK_TIMEOUT.get(name) or self._lb_timeout(tr, 8)
        time.sleep(wait)
        if self._probes.pop(seq, None) is not None:
            self.stats[name].record(False)

    def _lb_timeout(self, tr, nbytes: int) -> float:
        return 2 * tr.airtime(nbytes + 8) + 1.0

    # ------------------------------------------------------------ receiving
    def _rx_loop(self, name: str):
        tr = self.t[name]
        while not self._stop:
            raw = tr.receive(0.2)
            if raw is None:
                continue
            try:
                pkt = P.decode(raw)
            except P.CorruptPacket as e:
                self.stats[name].crc_drops += 1          # counted, shown in /status
                if self.verbose:
                    self.log(f"[rx {name}] dropped corrupt packet ({e})")
                continue
            self._handle(name, tr, pkt)

    def _handle(self, name, tr, pkt: P.Packet):
        if pkt.type == P.PROBE:
            tr.send(P.Packet(P.PROBE_REPLY, pkt.seq).encode(compact=tr.compact))
        elif pkt.type == P.PROBE_REPLY:
            sent = self._probes.pop(pkt.seq, None)
            if sent is not None:
                self.stats[name].record(True, time.time() - sent)
        elif pkt.type == P.ACK:
            ev = self._acks.get(pkt.seq)
            if ev:
                ev.set()
        elif pkt.type in (P.DATA, P.SUMMARY):
            tr.send(P.Packet(P.ACK, pkt.seq).encode(compact=tr.compact))
            key = (pkt.type, pkt.seq)
            if key in self._seen:
                return                                   # duplicate from a retry
            self._seen.append(key)
            latency = None
            if not tr.compact and pkt.timestamp_ms:
                latency = (P.now_ms() - pkt.timestamp_ms) & 0xFFFFFFFF
            if pkt.type == P.SUMMARY:
                urg, act, alert, corr, loc = parse_summary(pkt.payload)
                self.on_receive(Received("SUMMARY", summary_to_text(urg, act), alert,
                                         pkt.lang, name, latency, corr, loc))
            else:
                payload, loc = pkt.payload, None
                if pkt.flags & P.F_LOC:
                    n = 5 if tr.compact else 8
                    payload, lb = payload[:-n], payload[-n:]
                    loc = L.decode_compact(lb) if tr.compact else L.decode_full(lb)
                body = zlib.decompress(payload) if pkt.flags & P.F_COMPRESSED else payload
                self.on_receive(Received("TEXT", body.decode("utf-8", "replace"),
                                         pkt.alert, pkt.lang, name, latency, 0, loc))

    # ------------------------------------------------------------ sending
    def send_message(self, text: str, lang: str = "en"):
        """Non-blocking. Alerts jump the queue."""
        urgency, _ = analyze(text)
        self._outbox.put((0 if is_alert(urgency) else 1, time.time(), text, lang))

    def _send_loop(self):
        pending = []
        while not self._stop:
            try:
                while True:
                    pending.append(self._outbox.get_nowait())
            except queue.Empty:
                pass
            if not pending:
                time.sleep(0.05)
                continue
            pending.sort()                                # alerts first, then FIFO
            if self._best() is None and self.current is None:
                time.sleep(0.5)                           # store-and-forward: wait for a link
                continue
            item = pending.pop(0)
            if not self._deliver(item[2], item[3]):
                self.log("[radio] no link delivered it, queued for retry")
                pending.append(item)
                time.sleep(1.0)

    def _build(self, channel: str, text: str, lang: str) -> List[P.Packet]:
        urgency, _ = analyze(text)
        flags = P.F_ALERT if is_alert(urgency) else 0
        raw = text.encode("utf-8")
        loc = self.location
        if loc is not None:
            flags |= P.F_LOC
        if channel == "WIFI":
            tail = L.encode_full(loc) if loc else b""
            return [P.Packet(P.DATA, self.next_seq(), flags, lang, payload=raw + tail)]
        if channel == "BLUETOOTH":
            tail = L.encode_full(loc) if loc else b""
            return [P.Packet(P.DATA, self.next_seq(), flags | P.F_COMPRESSED, lang,
                             payload=zlib.compress(raw, 6) + tail)]
        pkts = []
        summ = build_summary(text, loc)
        if summ is not None:
            pkts.append(P.Packet(P.SUMMARY, self.next_seq(), (flags & ~P.F_LOC) | P.F_FEC,
                                 lang, payload=summ))
        tail = L.encode_compact(loc) if loc else b""
        pkts.append(P.Packet(P.DATA, self.next_seq(), flags | P.F_COMPRESSED, lang,
                             payload=zlib.compress(raw, 9) + tail))
        return pkts

    def _deliver(self, text: str, lang: str) -> bool:
        tried = []
        order = [self.current] + [c for c in PREFERENCE if c != self.current]
        for ch in order:
            if ch is None or ch not in self.t or ch in tried:
                continue
            if ch != self.current and not self.healthy(ch):
                continue
            tried.append(ch)
            tr = self.t[ch]
            ok = all(self._send_reliable(ch, tr, pkt) for pkt in self._build(ch, text, lang))
            if ok:
                return True
            self.log(f"[radio] {ch} failed after retries, failing over")
        return False

    def _send_reliable(self, ch, tr, pkt: P.Packet) -> bool:
        raw = pkt.encode(compact=tr.compact)
        timeout = ACK_TIMEOUT.get(ch) or self._lb_timeout(tr, len(raw))
        ev = threading.Event()
        self._acks[pkt.seq] = ev
        try:
            for attempt in range(1 + RETRIES):
                tr.send(raw)
                if ev.wait(timeout):
                    kind = P.TYPE_NAMES[pkt.type]
                    self.log(f"[tx {ch}] {kind} seq={pkt.seq} {len(raw)}B delivered"
                             + (f" (retry {attempt})" if attempt else ""))
                    return True
            return False
        finally:
            self._acks.pop(pkt.seq, None)
