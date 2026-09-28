"""
Packetizer — splits an encoded message into separate packets by priority
level, instead of sending the whole message as one blob.

Why this exists:
  In the original single-blob encoding, a single dropped packet or a run of
  bit-flips could take the ENTIRE message down with it, regardless of which
  fields mattered most. By splitting P0/P1/P2/P3 fields into independent
  packets, a P0 packet (ACTION, URGENCY, STATUS) can survive and be decoded
  correctly even if the P2/P3 packets are lost outright on a bad link.

  Each packet also carries a small header with:
    - which priority tier it is (2 bits)
    - the dictionary version it was encoded with (4 bits) -> lets a
      receiver on a mismatched codebook detect the mismatch instead of
      silently decoding garbage
    - whether Hamming(7,4) FEC protection was applied to its payload
    - field count + original (pre-FEC) payload bit length, so the receiver
      knows exactly how many bits to read back out
"""

from typing import Dict, List
from itantra_ai.encoder.dictionary import Dictionary
from itantra_ai.priority.priority_engine import PriorityEngine
from itantra_ai.priority.adaptive_priority_engine import AdaptivePriorityEngine
from itantra_ai.reliability.hamming import encode_bits, decode_bits

PRIORITY_ORDER = ["P0", "P1", "P2", "P3"]
PRIORITY_CODE = {"P0": "00", "P1": "01", "P2": "10", "P3": "11"}
CODE_PRIORITY = {v: k for k, v in PRIORITY_CODE.items()}

# Header layout (all fields fixed-width so parsing is unambiguous):
#   2 bits  priority code
#   4 bits  dictionary version
#   1 bit   FEC-protected flag
#   8 bits  field count in this packet
#  16 bits  original (pre-FEC) payload bit length
HEADER_LEN = 2 + 4 + 1 + 8 + 16

# The header carries priority/version/length metadata that everything else
# depends on to parse correctly - a corrupted header byte is catastrophic
# (wrong priority read, wrong length read, spurious "version mismatch").
# So unlike the payload (protected only for P0 to save bandwidth), the
# header is ALWAYS Hamming-protected: it's tiny (31 bits -> 56 bits), so
# the overhead is cheap insurance against exactly the kind of silent
# misparse a bit-flip would otherwise cause.


class Packetizer:

    @classmethod
    def build_packets(cls, semantic_dict: Dict[str, str],
                       protect_priorities=("P0",),
                       use_adaptive_priority: bool = True) -> List[dict]:
        """
        Splits a semantic dict into one packet per non-empty priority tier.
        `protect_priorities` controls which tiers get Hamming(7,4) FEC —
        by default only P0, matching the "protection bits on P0 fields
        only" design in the Feasibility slide.

        `use_adaptive_priority` selects which priority engine decides the
        tiers: the original PriorityEngine (fixed by field name only) or
        AdaptivePriorityEngine (scores by field + value + message context -
        e.g. LOCATION becomes P0 during an EVACUATE order but stays P2 in
        a routine check-in, instead of always being a fixed P1).
        """
        engine = AdaptivePriorityEngine if use_adaptive_priority else PriorityEngine
        grouped = engine.assign_priorities(semantic_dict)
        packets = []

        for priority in PRIORITY_ORDER:
            fields = grouped[priority]
            if not fields:
                continue

            payload_bits = "".join(
                Dictionary.encode_key(key) + Dictionary.encode_value(str(val))
                for key, val in fields
            )
            protect = priority in protect_priorities
            tx_payload = encode_bits(payload_bits) if protect else payload_bits

            raw_header_bits = (
                PRIORITY_CODE[priority]
                + format(Dictionary.DICT_VERSION, "04b")
                + ("1" if protect else "0")
                + format(len(fields), "08b")
                + format(len(payload_bits), "016b")
            )
            tx_header = encode_bits(raw_header_bits)  # header always protected

            packets.append({
                "priority": priority,
                "fields": fields,
                "header_bits": tx_header,
                "payload_bits": tx_payload,
                "protected": protect,
                "original_payload_len": len(payload_bits),
                "total_bits": len(tx_header) + len(tx_payload),
            })

        return packets

    @classmethod
    def parse_packet(cls, header_bits: str, payload_bits: str) -> dict:
        """
        Parses a received (possibly corrupted/truncated) packet.
        Returns a dict describing what was recovered, including whether the
        dictionary version matched and how many bit-errors FEC corrected.
        """
        # header is always Hamming-protected -> decode it first
        raw_header, header_corrections = decode_bits(header_bits, HEADER_LEN)
        if len(raw_header) < HEADER_LEN:
            return {"priority": None, "ok": False, "reason": "header truncated",
                    "fields": {}, "version_mismatch": None, "corrections_made": 0}

        priority = CODE_PRIORITY.get(raw_header[0:2], "UNKNOWN")
        version = int(raw_header[2:6], 2)
        protected = raw_header[6] == "1"
        field_count = int(raw_header[7:15], 2)
        original_len = int(raw_header[15:31], 2)
        version_mismatch = version != Dictionary.DICT_VERSION

        if version_mismatch:
            # Don't attempt to decode against a codebook we know is wrong -
            # this is exactly the silent-mis-decode failure mode versioning
            # is meant to catch.
            return {
                "priority": priority, "ok": False,
                "reason": f"dictionary version mismatch (packet=v{version}, "
                          f"local=v{Dictionary.DICT_VERSION})",
                "fields": {}, "version_mismatch": True,
                "corrections_made": header_corrections,
            }

        if protected:
            decoded_payload, payload_corrections = decode_bits(payload_bits, original_len)
        else:
            decoded_payload, payload_corrections = payload_bits[:original_len], 0
        corrections = header_corrections + payload_corrections

        fields = {}
        idx = 0
        for _ in range(field_count):
            if idx >= len(decoded_payload):
                break
            key_code = decoded_payload[idx:idx + 4]
            key_name = Dictionary.decode_key(key_code) or f"UNKNOWN_KEY_{key_code}"
            idx += 4
            value_str, next_idx = Dictionary.decode_value(decoded_payload, idx)
            idx = next_idx
            fields[key_name] = value_str

        complete = len(fields) == field_count
        return {
            "priority": priority, "ok": complete,
            "reason": None if complete else "packet truncated/corrupted beyond recovery",
            "fields": fields, "version_mismatch": False,
            "corrections_made": corrections,
        }

    @classmethod
    def reassemble(cls, parsed_packets: List[dict]) -> Dict[str, str]:
        """Merge whatever fields survived across all received packets."""
        merged = {}
        for pkt in parsed_packets:
            merged.update(pkt.get("fields", {}))
        return merged

    @classmethod
    def conceal_dropped_packets(cls, all_priorities_sent: List[str],
                                 received_priorities: List[str],
                                 context_manager,
                                 concealable_fields=("TEAM", "LOCATION", "ACTOR", "OBJECT")) -> dict:
        """
        Packet Loss Concealment (PLC), inspired by Glaris (arXiv:2512.08203).
        Their approach uses a generative model to estimate lost speech content
        from context. This is the rule-based analog we can actually run on
        edge hardware: for a NON-P0 packet that was dropped entirely, look up
        the last known value for its fields in session context memory instead
        of leaving them blank.

        Deliberately never applied to P0 - concealing "what happened" or "how
        urgent" would be actively dangerous, not helpful. Concealed fields are
        returned separately from confirmed ones so the caller can clearly mark
        them "estimated" rather than "received" to the operator.
        """
        dropped = set(all_priorities_sent) - set(received_priorities)
        dropped -= {"P0"}  # never conceal critical fields

        concealed = {}
        for field in concealable_fields:
            if any(p in dropped for p in ("P1", "P2", "P3")):
                value = context_manager.conceal(field)
                if value is not None:
                    concealed[field] = value
        return concealed
