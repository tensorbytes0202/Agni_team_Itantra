from typing import Dict, List


FIELD_PRIORITIES = {
    # P0 - Critical
    "URGENCY": "P0",
    "ACTION": "P0",
    "STATUS": "P0",

    # P1 - Operational
    "TEAM": "P1",
    "LOCATION": "P1",
    "ACTOR": "P1",
    "REQUIREMENT": "P1",

    # P2 - Supporting
    "OBJECT": "P2",
    "QUANTITY": "P2",
    "TIME": "P2",
    "IDENTIFIER": "P2",
    "REASON": "P2",

    # P3 - Optional
    "FILLER": "P3",
}


class PriorityEngine:
    """
    Fixed field-based priority engine.

    P0 = Critical
    P1 = Operational
    P2 = Supporting
    P3 = Optional
    """

    @classmethod
    def get_priority_level(cls, field: str) -> str:
        """
        Returns the priority level of a semantic field.
        Unknown fields are treated as P2.
        """

        return FIELD_PRIORITIES.get(
            field,
            "P2"
        )

    @classmethod
    def assign_priorities(
        cls,
        semantic_dict: Dict[str, str]
    ) -> Dict[str, List[str]]:
        """
        Groups semantic fields according to priority.
        """

        priorities = {
            "P0": [],
            "P1": [],
            "P2": [],
            "P3": [],
        }

        for field in semantic_dict:

            level = cls.get_priority_level(
                field
            )

            priorities[level].append((field, semantic_dict[field]))

        return priorities