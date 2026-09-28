"""
End-to-end demonstration/test of the 3 Round-2 additions:
  1. Hamming(7,4) FEC on P0 fields
  2. Priority-based packet splitting
  3. Dictionary versioning (mismatch detection)

Run directly: python3 itantra_ai/tests/test_reliability_features.py
"""
import random
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from itantra_ai.transport.packetizer import Packetizer
from itantra_ai.encoder.dictionary import Dictionary
from itantra_ai.channel.simulator import WeakChannelSimulator


SAMPLE = {
    "ACTION": "SEND",
    "URGENCY": "HIGH",
    "TEAM": "MEDICAL",
    "LOCATION": "NORTH_CHECKPOINT",
    "QUANTITY": "2",
}


def run_scenario(loss_rate: float, seed: int):
    print(f"\n=== Scenario: loss_rate={loss_rate}, seed={seed} ===")
    packets = Packetizer.build_packets(SAMPLE, protect_priorities=("P0",))
    channel = WeakChannelSimulator(loss_rate=loss_rate, seed=seed)

    received = []
    for pkt in packets:
        # header is short and sent alongside payload; we run both through the
        # same lossy channel independently (each packet is one radio burst)
        recv_header, header_ok = channel.transmit(pkt["header_bits"])
        recv_payload, payload_ok = channel.transmit(pkt["payload_bits"])

        if not header_ok or not payload_ok:
            print(f"  [{pkt['priority']}] packet DROPPED entirely on the channel")
            continue

        parsed = Packetizer.parse_packet(recv_header, recv_payload)
        received.append(parsed)
        status = "OK" if parsed["ok"] else f"FAILED ({parsed['reason']})"
        corr = parsed["corrections_made"]
        print(f"  [{parsed['priority']}] {status}  fields={parsed['fields']}  "
              f"bit-errors corrected={corr}")

    merged = Packetizer.reassemble(received)
    print(f"  --> Reassembled message: {merged}")
    p0_survived = any(p["priority"] == "P0" and p["ok"] for p in received)
    print(f"  --> P0 (critical) fields survived: {p0_survived}")
    return merged, p0_survived


def scenario_version_mismatch():
    from itantra_ai.reliability.hamming import encode_bits as _enc
    from itantra_ai.transport.packetizer import PRIORITY_CODE, HEADER_LEN

    print("\n=== Scenario: dictionary version mismatch ===")
    packets = Packetizer.build_packets(SAMPLE, protect_priorities=("P0",))
    p0 = packets[0]

    # Simulate a SENDER on a newer dictionary version than this receiver
    real_version = Dictionary.DICT_VERSION
    fake_sender_version = real_version + 1
    field_count = len(p0["fields"])
    raw_header = (
        PRIORITY_CODE["P0"]
        + format(fake_sender_version, "04b")
        + "1"
        + format(field_count, "08b")
        + format(p0["original_payload_len"], "016b")
    )
    assert len(raw_header) == HEADER_LEN
    tampered_header = _enc(raw_header)

    parsed = Packetizer.parse_packet(tampered_header, p0["payload_bits"])
    print(f"  Sender used v{fake_sender_version}, receiver expects v{real_version}")
    print(f"  Result: ok={parsed['ok']}, reason='{parsed['reason']}'")
    assert parsed["version_mismatch"] is True
    assert parsed["ok"] is False
    print("  --> PASS: mismatch correctly detected, no silent mis-decode")


if __name__ == "__main__":
    print("Sample message:", SAMPLE)

    # 1) Clean channel - sanity check
    merged, _ = run_scenario(loss_rate=0.0, seed=1)
    assert merged == SAMPLE, "clean channel should reconstruct exactly"
    print("PASS: clean channel reconstructs message exactly")

    # 2) Moderate loss - show P0 survives even when others may not
    survived_count = 0
    trials = 15
    for seed in range(trials):
        _, p0_ok = run_scenario(loss_rate=0.35, seed=seed)
        survived_count += int(p0_ok)
    print(f"\nP0 survival rate over {trials} trials at 35% loss: "
          f"{survived_count}/{trials} = {100*survived_count/trials:.0f}%")

    # 3) Dictionary version mismatch handling
    scenario_version_mismatch()

    print("\nAll reliability feature checks complete.")
