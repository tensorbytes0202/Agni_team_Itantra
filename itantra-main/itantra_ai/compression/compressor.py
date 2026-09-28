from typing import Dict

from itantra_ai.priority.priority_engine import PriorityEngine


class Compressor:
    """
    Applies semantic compression while preserving important meaning.

    Strategies:
    1. Priority-aware field retention
    2. Context-aware redundancy elimination
    3. Never remove fields that are required to reconstruct
       the operational meaning of the current message.
    """

    # Fields that should never be silently removed because
    # they directly contribute to the meaning of the command.
    CORE_FIELDS = {
        "URGENCY",
        "ACTION",
        "TEAM",
        "ACTOR",
        "OBJECT",
        "QUANTITY",
        "LOCATION",
        "STATUS",
        "REQUIREMENT",
        "TIME",
        "REASON",
        "IDENTIFIER",
    }

    @classmethod
    def compress_semantic(
        cls,
        semantic_dict: Dict[str, str],
        max_priority_allowed: str = "P2"
    ) -> Dict[str, str]:
        """
        Keeps semantic fields up to the requested priority.

        P0:
            Critical fields only

        P1:
            Critical + operational fields

        P2:
            Critical + operational + supporting fields

        P3:
            Everything

        Unknown fields are treated as P2.
        """

        priority_order = [
            "P0",
            "P1",
            "P2",
            "P3"
        ]

        if max_priority_allowed not in priority_order:
            raise ValueError(
                f"Invalid priority: {max_priority_allowed}"
            )

        max_idx = priority_order.index(
            max_priority_allowed
        )

        allowed_priorities = set(
            priority_order[:max_idx + 1]
        )

        compressed_dict = {}

        for field, value in semantic_dict.items():

            field_priority = (
                PriorityEngine.get_priority_level(field)
            )

            if field_priority in allowed_priorities:
                compressed_dict[field] = value

        return compressed_dict

    @classmethod
    def apply_context_compression(
        cls,
        semantic_dict: Dict[str, str],
        active_context: Dict[str, str]
    ) -> Dict[str, str]:
        """
        Removes only genuinely redundant contextual fields.

        Important semantic fields are preserved so that the receiver
        can reconstruct the complete meaning of the current message.

        If a field is identical to the previous context, a REF_PREV
        marker is added, but core command information is not silently
        discarded.
        """

        compressed = {}
        redundant_found = False

        for key, value in semantic_dict.items():

            # --------------------------------------------------
            # Never remove core semantic fields.
            # --------------------------------------------------

            if key in cls.CORE_FIELDS:
                compressed[key] = value
                continue

            # --------------------------------------------------
            # Non-core contextual fields can use REF_PREV.
            # --------------------------------------------------

            if (
                key in active_context
                and active_context[key] == value
            ):
                redundant_found = True
            else:
                compressed[key] = value

        # ------------------------------------------------------
        # Reference marker
        # ------------------------------------------------------

        if redundant_found:
            compressed["REF_PREV"] = "1"

        return compressed