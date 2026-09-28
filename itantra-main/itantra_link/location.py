"""
Location encoding. GPS works without internet, so this stays fully offline.

FULL  (WiFi/Bluetooth): float32 lat + float32 lon = 8 bytes, worldwide.
COMPACT (low-bitrate):  lat/lon quantized to 20 bits each inside India's
                        bounding box = 40 bits = 5 bytes, ~3 m precision.
                        Points outside the box are clamped to its edge.
"""
import math
import struct
from typing import Optional, Tuple

LAT_MIN, LAT_MAX = 6.0, 38.0      # India bounding box (with margin)
LON_MIN, LON_MAX = 68.0, 98.0
BITS = 20
STEPS = (1 << BITS) - 1

Loc = Tuple[float, float]


def encode_full(loc: Loc) -> bytes:
    return struct.pack(">ff", loc[0], loc[1])


def decode_full(b: bytes) -> Loc:
    lat, lon = struct.unpack(">ff", b[:8])
    return round(lat, 6), round(lon, 6)


def _q(v, lo, hi) -> int:
    v = min(max(v, lo), hi)
    return round((v - lo) / (hi - lo) * STEPS)


def _dq(q, lo, hi) -> float:
    return lo + q / STEPS * (hi - lo)


def encode_compact(loc: Loc) -> bytes:
    v = (_q(loc[0], LAT_MIN, LAT_MAX) << BITS) | _q(loc[1], LON_MIN, LON_MAX)
    return v.to_bytes(5, "big")


def decode_compact(b: bytes) -> Loc:
    v = int.from_bytes(b[:5], "big")
    return (round(_dq(v >> BITS, LAT_MIN, LAT_MAX), 5),
            round(_dq(v & STEPS, LON_MIN, LON_MAX), 5))


def distance_bearing(frm: Loc, to: Loc) -> Tuple[float, str]:
    """Great-circle distance in metres + 8-point compass direction (offline)."""
    lat1, lon1, lat2, lon2 = map(math.radians, (*frm, *to))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    dist = 2 * 6371000 * math.asin(math.sqrt(a))
    y = math.sin(dlon) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    brg = (math.degrees(math.atan2(y, x)) + 360) % 360
    dirs = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    return dist, dirs[int((brg + 22.5) // 45) % 8]


def describe(loc: Optional[Loc], own: Optional[Loc] = None) -> str:
    if loc is None:
        return "location unknown"
    s = f"{loc[0]:.5f}, {loc[1]:.5f}"
    if own is not None:
        d, dirn = distance_bearing(own, loc)
        s += f" ({d/1000:.2f} km {dirn})" if d >= 1000 else f" ({d:.0f} m {dirn})"
    return s
