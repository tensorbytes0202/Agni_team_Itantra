from typing import Tuple, Dict, Optional


class Dictionary:
    """
    Dictionary-based binary codebook mapper.

    Supports:
    - Compact 4-bit field keys
    - Compact 5-bit common values
    - OOV fallback using 7-bit ASCII
    - Versioning for sender/receiver compatibility
    """

    # ==========================================================
    # DICTIONARY VERSION
    # ==========================================================

    # Changed because new semantic fields were added.
    DICT_VERSION = 2

    # ==========================================================
    # FIELD KEY MAPPINGS
    # ==========================================================

    KEY_TO_CODE = {

        "ACTION":     "0001",
        "TEAM":       "0010",
        "LOCATION":   "0011",
        "URGENCY":    "0100",
        "ACTOR":      "0101",
        "OBJECT":     "0110",
        "QUANTITY":   "0111",
        "STATUS":     "1000",
        "TIME":       "1001",
        "IDENTIFIER": "1010",

        # Existing context reuse
        "REF_PREV":   "1011",

        # NEW semantic detail fields
        "REQUIREMENT": "1100",
        "REASON":      "1101",

    }

    CODE_TO_KEY = {
        value: key
        for key, value in KEY_TO_CODE.items()
    }

    # ==========================================================
    # COMMON DOMAIN VALUES
    # ==========================================================

    VALUE_TO_CODE = {

        # ------------------------------------------------------
        # ACTIONS
        # ------------------------------------------------------

        "SEND":       "00001",
        "EVACUATE":   "00010",
        "DEPLOY":     "00011",
        "HALT":       "00100",
        "SECURE":     "00101",
        "REPORT":     "00110",

        # ------------------------------------------------------
        # TEAMS
        # ------------------------------------------------------

        "MEDICAL":    "00111",
        "ENGINEER":   "01000",
        "RESCUE":     "01001",
        "RECON":      "01010",
        "FIRE":       "01011",
        "SECURITY":   "01100",

        # ------------------------------------------------------
        # URGENCY
        # ------------------------------------------------------

        "HIGH":       "01101",
        "CRITICAL":   "01110",
        "LOW":        "01111",
        "MEDIUM":     "10000",

        # ------------------------------------------------------
        # LOCATIONS
        # ------------------------------------------------------

        "NORTH_CHECKPOINT": "10001",
        "SOUTH_BRIDGE":     "10010",
        "POWER_PLANT":      "10011",
        "SECTOR_4":         "10100",
        "BASE_CAMP":        "10101",
        "HQ":               "10110",

        # ------------------------------------------------------
        # ACTORS
        # ------------------------------------------------------

        "CIVILIAN":   "10111",
        "REFUGEE":    "11000",

        # ------------------------------------------------------
        # OBJECTS
        # ------------------------------------------------------

        "AMBULANCE":  "11001",
        "TRUCK":      "11010",
        "SUPPLIES":   "11011",

        # ------------------------------------------------------
        # STATUS
        # ------------------------------------------------------

        "DEPLOYED":   "11100",
        "ARRIVED":    "11101",
        "READY":      "11110",

        # IMPORTANT:
        # 11111 is reserved for FALLBACK_SENTINEL.
        # Therefore new/unseen values such as MEDICINE,
        # REQUIREMENT values and REASON values use fallback.
    }

    CODE_TO_VALUE = {
        value: key
        for key, value in VALUE_TO_CODE.items()
    }

    # ==========================================================
    # FALLBACK
    # ==========================================================

    # 11111 means:
    # "The value is not in the compact dictionary.
    # Read the length and then read 7-bit ASCII characters."

    FALLBACK_SENTINEL = "11111"

    # ==========================================================
    # KEY ENCODING
    # ==========================================================

    @classmethod
    def encode_key(cls, key: str) -> str:
        """
        Converts semantic field name into 4-bit key.

        Example:
            ACTION -> 0001
            LOCATION -> 0011
            REQUIREMENT -> 1100
            REASON -> 1101
        """

        key = str(key).upper()

        if key not in cls.KEY_TO_CODE:
            raise ValueError(
                f"Unknown semantic field: {key}"
            )

        return cls.KEY_TO_CODE[key]

    # ==========================================================
    # KEY DECODING
    # ==========================================================

    @classmethod
    def decode_key(cls, bit_str: str) -> Optional[str]:
        """
        Converts 4-bit key back to semantic field name.
        """

        return cls.CODE_TO_KEY.get(bit_str)

    # ==========================================================
    # VALUE ENCODING
    # ==========================================================

    @classmethod
    def encode_value(cls, value: str) -> str:
        """
        Encodes a semantic value.

        Known value:
            5 bits

        Unknown value:
            5-bit sentinel
            + 8-bit string length
            + 7-bit ASCII characters
        """

        value = str(value)

        value_upper = value.upper()

        # ------------------------------------------------------
        # Known compact value
        # ------------------------------------------------------

        if value_upper in cls.VALUE_TO_CODE:

            return cls.VALUE_TO_CODE[value_upper]

        # ------------------------------------------------------
        # OOV fallback
        # ------------------------------------------------------

        try:

            ascii_bits = "".join(
                format(ord(char), "07b")
                for char in value
            )

        except Exception:

            raise ValueError(
                f"Unable to encode value: {value}"
            )

        string_length = len(value)

        if string_length > 255:
            raise ValueError(
                "Fallback value is too long. "
                "Maximum supported length is 255 characters."
            )

        length_bits = format(
            string_length,
            "08b"
        )

        return (
            cls.FALLBACK_SENTINEL
            + length_bits
            + ascii_bits
        )

    # ==========================================================
    # VALUE DECODING
    # ==========================================================

    @classmethod
    def decode_value(
        cls,
        bit_stream: str,
        start_index: int
    ) -> Tuple[str, int]:
        """
        Decodes one value from the binary stream.

        Returns:
            (decoded_value, next_read_index)
        """

        # ------------------------------------------------------
        # Safety check
        # ------------------------------------------------------

        if start_index + 5 > len(bit_stream):

            return (
                "INVALID_VALUE",
                len(bit_stream)
            )

        code_5bit = bit_stream[
            start_index:start_index + 5
        ]

        # ------------------------------------------------------
        # Known dictionary value
        # ------------------------------------------------------

        if code_5bit in cls.CODE_TO_VALUE:

            return (
                cls.CODE_TO_VALUE[code_5bit],
                start_index + 5
            )

        # ------------------------------------------------------
        # Fallback value
        # ------------------------------------------------------

        if code_5bit == cls.FALLBACK_SENTINEL:

            length_start = start_index + 5
            length_end = start_index + 13

            if length_end > len(bit_stream):

                return (
                    "INVALID_FALLBACK",
                    len(bit_stream)
                )

            length_bits = bit_stream[
                length_start:length_end
            ]

            string_length = int(
                length_bits,
                2
            )

            current_index = length_end

            chars = []

            # --------------------------------------------------
            # Read 7-bit ASCII characters
            # --------------------------------------------------

            for _ in range(string_length):

                if current_index + 7 > len(bit_stream):

                    return (
                        "".join(chars),
                        len(bit_stream)
                    )

                char_bits = bit_stream[
                    current_index:current_index + 7
                ]

                char_code = int(
                    char_bits,
                    2
                )

                chars.append(
                    chr(char_code)
                )

                current_index += 7

            return (
                "".join(chars),
                current_index
            )

        # ------------------------------------------------------
        # Unknown 5-bit sequence
        # ------------------------------------------------------

        return (
            f"UNKNOWN({code_5bit})",
            start_index + 5
        )