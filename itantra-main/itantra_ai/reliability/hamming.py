"""
Hamming(7,4) Single-Error-Correcting code.

Protects a bitstream against random bit-flips introduced by a lossy radio
channel. Every 4 data bits are expanded into a 7-bit codeword using 3 parity
bits. On the receive side, any single-bit flip inside a 7-bit block is
detected AND automatically corrected before the data bits are recovered.

This is deliberately applied only to P0 (critical) fields in the packetizer,
since protecting every field would eat into the compression gains that are
the core of this project (see FEC-overhead tradeoff in Feasibility slide).
"""

from typing import Tuple


def _encode_nibble(nibble: str) -> str:
    """Encode 4 data bits -> 7-bit Hamming codeword."""
    d1, d2, d3, d4 = (int(b) for b in nibble)
    p1 = d1 ^ d2 ^ d4
    p2 = d1 ^ d3 ^ d4
    p4 = d2 ^ d3 ^ d4
    # Standard bit ordering: p1 p2 d1 p4 d2 d3 d4
    return f"{p1}{p2}{d1}{p4}{d2}{d3}{d4}"


def _decode_block(block: str) -> Tuple[str, bool]:
    """
    Decode a 7-bit Hamming codeword -> (original 4 data bits, error_detected).
    Corrects any single-bit error automatically.
    """
    bits = [int(b) for b in block]
    p1, p2, d1, p4, d2, d3, d4 = bits

    c1 = p1 ^ d1 ^ d2 ^ d4
    c2 = p2 ^ d1 ^ d3 ^ d4
    c4 = p4 ^ d2 ^ d3 ^ d4
    syndrome = c4 * 4 + c2 * 2 + c1  # 0 = no error, 1-7 = faulty bit position

    error_detected = syndrome != 0
    if error_detected:
        idx = syndrome - 1
        bits[idx] ^= 1  # flip the faulty bit back

    p1, p2, d1, p4, d2, d3, d4 = bits
    return f"{d1}{d2}{d3}{d4}", error_detected


def encode_bits(bit_string: str) -> str:
    """
    Encode an arbitrary-length bitstring by protecting it 4 bits at a time.
    Pads with zeros to a multiple of 4 (padding length is NOT stored here;
    the caller must remember the original length to trim after decoding).
    """
    padded = bit_string + "0" * ((-len(bit_string)) % 4)
    return "".join(_encode_nibble(padded[i:i + 4]) for i in range(0, len(padded), 4))


def decode_bits(protected_bits: str, original_length: int) -> Tuple[str, int]:
    """
    Decode a Hamming-protected bitstring back to the original data.
    Returns (recovered_bits trimmed to original_length, number_of_corrections_made).
    """
    corrections = 0
    data_chunks = []
    for i in range(0, len(protected_bits), 7):
        block = protected_bits[i:i + 7]
        if len(block) < 7:
            break  # truncated/dropped tail - nothing more we can recover
        nibble, corrected = _decode_block(block)
        if corrected:
            corrections += 1
        data_chunks.append(nibble)

    recovered = "".join(data_chunks)[:original_length]
    return recovered, corrections
