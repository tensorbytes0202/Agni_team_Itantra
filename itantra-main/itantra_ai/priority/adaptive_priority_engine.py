"""
Adaptive Priority Engine

Priority is calculated using three layers:

1. BASE SCORE
2. VALUE MODIFIER
3. CONTEXT MODIFIER

Final score is converted into P0-P3.
"""

from typing import Dict, List, Tuple


# ==============================================================
# Layer 1: Base importance
# ==============================================================

BASE_SCORE = {

    # P0 - Critical
    "URGENCY": 95,
    "ACTION": 90,
    "STATUS": 80,

    # P1 - Operational
    "TEAM": 55,
    "LOCATION": 50,
    "ACTOR": 50,
    "REQUIREMENT": 60,

    # P2 - Supporting information
    "OBJECT": 30,
    "QUANTITY": 25,
    "TIME": 20,
    "IDENTIFIER": 20,
    "REASON": 25,

    # P3 - Optional
    "FILLER": 5,
}


DEFAULT_BASE_SCORE = 30


# ==============================================================
# Layer 2: Value-specific modifiers
# ==============================================================

VALUE_MODIFIER = {

    # Urgency
    ("URGENCY", "CRITICAL"): +10,
    ("URGENCY", "HIGH"): +5,
    ("URGENCY", "LOW"): -15,

    # Actions
    ("ACTION", "EVACUATE"): +10,
    ("ACTION", "HALT"): +8,
    ("ACTION", "SECURE"): +5,
    ("ACTION", "REPORT"): -10,

    # Status
    ("STATUS", "ARRIVED"): -10,
    ("STATUS", "DEPLOYED"): -5,

    # Important locations
    ("LOCATION", "POWER_PLANT"): +15,
    ("LOCATION", "HQ"): -10,
    ("LOCATION", "BASE_CAMP"): -10,

    # Requirements
    ("REQUIREMENT", "EMERGENCY_MEDICAL_ASSISTANCE"): +15,
    ("REQUIREMENT", "MEDICAL_ASSISTANCE"): +10,
    ("REQUIREMENT", "REINFORCEMENT"): +10,
    ("REQUIREMENT", "BACKUP"): +8,
}


# ==============================================================
# Layer 3: Context modifiers
# ==============================================================

def _context_modifiers(
    semantic_dict: Dict[str, str]
) -> Dict[str, int]:
    """
    Calculates score changes based on the complete message.
    """

    mods: Dict[str, int] = {}

    action = semantic_dict.get(
        "ACTION",
        ""
    ).upper()

    urgency = semantic_dict.get(
        "URGENCY",
        ""
    ).upper()

    status = semantic_dict.get(
        "STATUS",
        ""
    ).upper()

    # ----------------------------------------------------------
    # Rule A:
    # EVACUATE / HALT / SECURE makes location and actor critical
    # ----------------------------------------------------------

    if action in {
        "EVACUATE",
        "HALT",
        "SECURE"
    }:

        mods["LOCATION"] = (
            mods.get("LOCATION", 0) + 25
        )

        mods["ACTOR"] = (
            mods.get("ACTOR", 0) + 15
        )

        # Quantity becomes more important during evacuation
        mods["QUANTITY"] = (
            mods.get("QUANTITY", 0) + 10
        )

    # ----------------------------------------------------------
    # Rule B:
    # Critical urgency escalates every transmitted field
    # ----------------------------------------------------------

    if urgency == "CRITICAL":

        for field in semantic_dict:

            mods[field] = (
                mods.get(field, 0) + 10
            )

    # ----------------------------------------------------------
    # Rule C:
    # Routine status updates reduce supporting information
    # ----------------------------------------------------------

    if status in {
        "ARRIVED",
        "READY"
    } and not urgency:

        for field in (
            "OBJECT",
            "QUANTITY",
            "TIME",
            "REASON"
        ):

            mods[field] = (
                mods.get(field, 0) - 5
            )

    # ----------------------------------------------------------
    # Rule D:
    # Medical assistance requirement increases importance
    # of the operational details around it.
    # ----------------------------------------------------------

    requirement = semantic_dict.get(
        "REQUIREMENT",
        ""
    ).upper()

    if requirement in {
        "MEDICAL_ASSISTANCE",
        "EMERGENCY_MEDICAL_ASSISTANCE"
    }:

        mods["OBJECT"] = (
            mods.get("OBJECT", 0) + 5
        )

        mods["TEAM"] = (
            mods.get("TEAM", 0) + 5
        )

        mods["ACTOR"] = (
            mods.get("ACTOR", 0) + 5
        )

    return mods


# ==============================================================
# Score -> Priority tier
# ==============================================================

def _score_to_tier(score: int) -> str:

    if score >= 80:
        return "P0"

    if score >= 55:
        return "P1"

    if score >= 30:
        return "P2"

    return "P3"


# ==============================================================
# Adaptive Priority Engine
# ==============================================================

class AdaptivePriorityEngine:
    """
    Context-sensitive priority engine.

    The return format remains compatible with the
    original PriorityEngine.
    """

    @classmethod
    def score_fields(
        cls,
        semantic_dict: Dict[str, str]
    ) -> Dict[str, int]:
        """
        Returns the final numeric score for every field.
        """

        ctx_mods = _context_modifiers(
            semantic_dict
        )

        scores = {}

        for field, value in semantic_dict.items():

            # Base score
            base = BASE_SCORE.get(
                field,
                DEFAULT_BASE_SCORE
            )

            # Value-specific modifier
            value_key = (
                field,
                str(value).upper()
            )

            value_modifier = VALUE_MODIFIER.get(
                value_key,
                0
            )

            # Message-context modifier
            context_modifier = ctx_mods.get(
                field,
                0
            )

            # Final bounded score
            score = max(
                0,
                min(
                    100,
                    base
                    + value_modifier
                    + context_modifier
                )
            )

            scores[field] = score

        return scores

    @classmethod
    def assign_priorities(
        cls,
        semantic_dict: Dict[str, str]
    ) -> Dict[str, List[Tuple[str, str]]]:
        """
        Groups fields into P0/P1/P2/P3.
        """

        scores = cls.score_fields(
            semantic_dict
        )

        prioritized = {
            "P0": [],
            "P1": [],
            "P2": [],
            "P3": [],
        }

        for field, value in semantic_dict.items():

            tier = _score_to_tier(
                scores[field]
            )

            prioritized[tier].append(
                (field, value)
            )

        return prioritized

    @classmethod
    def explain(
        cls,
        semantic_dict: Dict[str, str]
    ) -> List[dict]:
        """
        Returns a human-readable explanation
        of the priority calculation.
        """

        ctx_mods = _context_modifiers(
            semantic_dict
        )

        rows = []

        for field, value in semantic_dict.items():

            base = BASE_SCORE.get(
                field,
                DEFAULT_BASE_SCORE
            )

            value_modifier = VALUE_MODIFIER.get(
                (
                    field,
                    str(value).upper()
                ),
                0
            )

            context_modifier = ctx_mods.get(
                field,
                0
            )

            final_score = max(
                0,
                min(
                    100,
                    base
                    + value_modifier
                    + context_modifier
                )
            )

            rows.append({
                "field": field,
                "value": value,
                "base_score": base,
                "value_modifier": value_modifier,
                "context_modifier": context_modifier,
                "final_score": final_score,
                "tier": _score_to_tier(
                    final_score
                ),
            })

        return rows