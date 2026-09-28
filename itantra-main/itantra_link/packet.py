"""
Packet format shared by every transport.

Two encodings, auto-detected on decode:

FULL (WiFi / Bluetooth) - 16 byte header + payload + CRC32
    version(1) type(1) seq(2) flags(1) lang(1) timestamp_ms(4) payload_len(2)
    reserved(4) payload(N) crc32(4)

COMPACT (low-bitrate link) - 5 byte header + payload + CRC16
    marker|type(1) seq(2) flags+lang(1) payload_len(1) payload(N) crc16(2)
    Language id packed into the high 4 bits of the flags byte.
    No timestamp: every bit costs airtime on a slow link.
"""
import struct
import time
import zlib
import binascii
from dataclasses import dataclass

VERSION = 1
COMPACT_MARKER = 0xC0

# packet types
DATA, SUMMARY, ACK, PROBE, PROBE_REPLY = 1, 2, 3, 4, 5
TYPE_NAMES = {DATA: "DATA", SUMMARY: "SUMMARY", ACK: "ACK", PROBE: "PROBE", PROBE_REPLY: "PROBE_REPLY"}

# flag bits
F_ALERT = 0x01
F_COMPRESSED = 0x02
F_FEC = 0x04
F_LOC = 0x08          # payload ends with a location block

LANG_CODES = ["en", "hi", "gu", "mr", "kn", "ml", "ta", "te", "or", "bn"]

_FULL_HDR = struct.Struct(">BBHBBIH4x")   # 16 bytes
_COMPACT_HDR = struct.Struct(">BHBB")     # 5 bytes


@dataclass
class Packet:
    type: int
    seq: int
    flags: int = 0
    lang: str = "en"
    timestamp_ms: int = 0
    payload: bytes = b""

    @property
    def alert(self) -> bool:
        return bool(self.flags & F_ALERT)

    def encode(self, compact: bool = False) -> bytes:
        if compact:
            if len(self.payload) > 255:
                raise ValueError("compact packet payload must be <= 255 bytes")
            # flags uses the low 3 bits; language id rides in the high 4 bits
            lang_id = LANG_CODES.index(self.lang) if self.lang in LANG_CODES else 0
            flags_byte = (self.flags & 0x0F) | (lang_id << 4)
            body = _COMPACT_HDR.pack(COMPACT_MARKER | self.type, self.seq & 0xFFFF,
                                     flags_byte, len(self.payload)) + self.payload
            return body + struct.pack(">H", binascii.crc_hqx(body, 0xFFFF))
        ts = self.timestamp_ms or now_ms()
        lang_id = LANG_CODES.index(self.lang) if self.lang in LANG_CODES else 0
        body = _FULL_HDR.pack(VERSION, self.type, self.seq & 0xFFFF, self.flags,
                              lang_id, ts & 0xFFFFFFFF, len(self.payload)) + self.payload
        return body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)


class CorruptPacket(Exception):
    pass


def decode(raw: bytes) -> Packet:
    """Decode either format. Raises CorruptPacket on CRC mismatch / bad length."""
    if not raw:
        raise CorruptPacket("empty")
    if raw[0] & 0xF0 == COMPACT_MARKER:
        if len(raw) < _COMPACT_HDR.size + 2:
            raise CorruptPacket("short compact packet")
        body, crc = raw[:-2], struct.unpack(">H", raw[-2:])[0]
        if binascii.crc_hqx(body, 0xFFFF) != crc:
            raise CorruptPacket("crc16 mismatch")
        marker_type, seq, flags, plen = _COMPACT_HDR.unpack(body[:_COMPACT_HDR.size])
        payload = body[_COMPACT_HDR.size:]
        if len(payload) != plen:
            raise CorruptPacket("length mismatch")
        lang_id = flags >> 4
        lang = LANG_CODES[lang_id] if lang_id < len(LANG_CODES) else "en"
        return Packet(type=marker_type & 0x0F, seq=seq, flags=flags & 0x0F, lang=lang, payload=payload)

    if len(raw) < _FULL_HDR.size + 4:
        raise CorruptPacket("short full packet")
    body, crc = raw[:-4], struct.unpack(">I", raw[-4:])[0]
    if zlib.crc32(body) & 0xFFFFFFFF != crc:
        raise CorruptPacket("crc32 mismatch")
    ver, ptype, seq, flags, lang_id, ts, plen = _FULL_HDR.unpack(body[:_FULL_HDR.size])
    if ver != VERSION:
        raise CorruptPacket(f"unknown version {ver}")
    payload = body[_FULL_HDR.size:]
    if len(payload) != plen:
        raise CorruptPacket("length mismatch")
    lang = LANG_CODES[lang_id] if lang_id < len(LANG_CODES) else "en"
    return Packet(type=ptype, seq=seq, flags=flags, lang=lang, timestamp_ms=ts, payload=payload)


def now_ms() -> int:
    return int(time.time() * 1000) & 0xFFFFFFFF
