from typing import Dict

from itantra_ai.encoder.dictionary import Dictionary


class Encoder:
    """
    Converts structured semantic key-value dictionaries
    into compact binary bitstreams.
    """

    @classmethod
    def encode(cls, semantic_dict: Dict[str, str]) -> str:
        """
        Bitstream format:

        [4-bit field count]
        [4-bit key][encoded value]
        [4-bit key][encoded value]
        ...

        Example:

        semantic_dict = {
            "URGENCY": "HIGH",
            "ACTION": "SEND",
            "TEAM": "MEDICAL"
        }

        The dictionary decides whether a value gets a
        compact 5-bit code or fallback encoding.
        """

        if not semantic_dict:
            return "0000"

        # ------------------------------------------------------
        # Validate number of fields
        # ------------------------------------------------------

        field_count = len(semantic_dict)

        # 4-bit header can represent 0-15 fields
        if field_count > 15:
            raise ValueError(
                f"Too many semantic fields: {field_count}. "
                "Maximum supported fields = 15."
            )

        # ------------------------------------------------------
        # Header
        # ------------------------------------------------------

        header_bits = format(field_count, "04b")

        bit_chunks = [header_bits]

        # ------------------------------------------------------
        # Encode each semantic field
        # ------------------------------------------------------

        for key, value in semantic_dict.items():

            # 4-bit field key
            key_bits = Dictionary.encode_key(key)

            # Dictionary / fallback value encoding
            value_bits = Dictionary.encode_value(
                str(value)
            )

            bit_chunks.append(
                key_bits + value_bits
            )

        # ------------------------------------------------------
        # Final binary stream
        # ------------------------------------------------------

        return "".join(bit_chunks)

    @classmethod
    def get_bit_length(cls, bit_stream: str) -> int:
        """
        Returns total number of bits in encoded stream.
        """

        if not bit_stream:
            return 0

        return len(bit_stream)