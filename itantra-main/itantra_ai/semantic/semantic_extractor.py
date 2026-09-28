import re

from typing import Dict

from itantra_ai.preprocessing.text_cleaner import TextCleaner


class SemanticExtractor:
    """
    Extracts structured operational intent from raw text.

    Core semantic fields:
        ACTION, TEAM, ACTOR, OBJECT, QUANTITY,
        LOCATION, URGENCY, STATUS

    Additional detail fields:
        REQUIREMENT, REASON, TIME

    The extractor remains deterministic and rule-based.
    """

    # ==========================================================
    # ACTIONS
    # ==========================================================

    ACTIONS = {
        "send": "SEND",
        "dispatch": "SEND",
        "move": "SEND",
        "transport": "SEND",
        "bring": "SEND",
        "deliver": "SEND",
        "evacuate": "EVACUATE",
        "evacuation": "EVACUATE",
        "extract": "EVACUATE",
        "withdraw": "EVACUATE",
        "deploy": "DEPLOY",
        "position": "DEPLOY",
        "station": "DEPLOY",
        "halt": "HALT",
        "stop": "HALT",
        "hold": "HALT",
        "pause": "HALT",
        "secure": "SECURE",
        "protect": "SECURE",
        "guard": "SECURE",
        "defend": "SECURE",
        "report": "REPORT",
        "update": "REPORT",
        "confirm": "REPORT",
        "advise": "REPORT",
        "assist": "SEND",
        "help": "SEND",
        "escort": "SEND",
        "clear": "SECURE",
        "search": "REPORT",
    }

    # ==========================================================
    # TEAMS
    # ==========================================================

    TEAMS = {
        "medical": "MEDICAL",
        "medic": "MEDICAL",
        "medics": "MEDICAL",
        "paramedic": "MEDICAL",
        "paramedics": "MEDICAL",
        "ambulance crew": "MEDICAL",

        "engineer": "ENGINEER",
        "engineers": "ENGINEER",
        "engineering": "ENGINEER",

        "rescue": "RESCUE",
        "rescue team": "RESCUE",
        "search and rescue": "RESCUE",

        "recon": "RECON",
        "reconnaissance": "RECON",
        "scout": "RECON",
        "scouts": "RECON",

        "fire": "FIRE",
        "firefighter": "FIRE",
        "firefighters": "FIRE",
        "fire brigade": "FIRE",

        "security": "SECURITY",
        "police": "SECURITY",
        "guards": "SECURITY",
        "swat": "SECURITY",

        "logistics": "LOGISTICS",
        "supply team": "LOGISTICS",

        "command": "COMMAND",
        "hq team": "COMMAND",
    }

    # ==========================================================
    # ACTORS
    # ==========================================================

    ACTORS = {
        "civilian": "CIVILIAN",
        "civilians": "CIVILIAN",
        "resident": "CIVILIAN",
        "residents": "CIVILIAN",

        "refugee": "REFUGEE",
        "refugees": "REFUGEE",
        "displaced": "REFUGEE",

        "hostage": "HOSTAGE",
        "hostages": "HOSTAGE",

        "squad": "SQUAD",
        "unit": "SQUAD",

        "victim": "CIVILIAN",
        "victims": "CIVILIAN",
        "wounded": "CIVILIAN",
        "injured": "CIVILIAN",
        "patient": "CIVILIAN",
        "patients": "CIVILIAN",

        "personnel": "SQUAD",
        "officer": "SQUAD",
        "officers": "SQUAD",
    }

    # ==========================================================
    # OBJECTS
    # ==========================================================

    OBJECTS = {
        "ambulance": "AMBULANCE",
        "ambulances": "AMBULANCE",

        "truck": "TRUCK",
        "trucks": "TRUCK",
        "vehicle": "TRUCK",
        "vehicles": "TRUCK",

        "helicopter": "DRONE",
        "drone": "DRONE",

        "boat": "TRUCK",

        "supplies": "SUPPLIES",
        "equipment": "SUPPLIES",
        "gear": "SUPPLIES",

        "water": "WATER",

        "rations": "RATIONS",
        "food": "RATIONS",

        "medicine": "MEDICINE",
        "medicines": "MEDICINE",

        "fuel": "SUPPLIES",
        "stretcher": "SUPPLIES",
        "radio": "SUPPLIES",
        "generator": "SUPPLIES",
        "tent": "SUPPLIES",
    }

    # ==========================================================
    # URGENCY
    # ==========================================================

    URGENCIES = {
        "urgently": "HIGH",
        "urgent": "HIGH",
        "immediate": "HIGH",
        "immediately": "HIGH",
        "asap": "HIGH",
        "priority": "HIGH",

        "critical": "CRITICAL",
        "emergency": "CRITICAL",
        "life threatening": "CRITICAL",

        "routine": "LOW",
        "low priority": "LOW",
        "non-urgent": "LOW",
        "whenever possible": "LOW",

        "moderate": "MEDIUM",
        "moderate priority": "MEDIUM",
    }

    # ==========================================================
    # STATUS
    # ==========================================================

    STATUSES = {
        "is at": "DEPLOYED",
        "deployed": "DEPLOYED",

        "reached": "ARRIVED",
        "arrived": "ARRIVED",
        "on site": "ARRIVED",

        "departed": "EN_ROUTE",
        "en route": "EN_ROUTE",
        "enroute": "EN_ROUTE",
        "on the way": "EN_ROUTE",

        "ready": "READY",
        "standby": "STANDBY",
        "standing by": "STANDBY",

        "engaged": "ENGAGED",
        "in progress": "ENGAGED",

        "completed": "COMPLETE",
        "complete": "COMPLETE",
        "done": "COMPLETE",

        "delayed": "DELAYED",
        "stuck": "DELAYED",
        "blocked": "DELAYED",

        "safe": "SAFE",
        "secured": "SAFE",
    }

    # ==========================================================
    # LOCATIONS
    # ==========================================================

    KNOWN_LOCATIONS = {
        "north checkpoint": "NORTH_CHECKPOINT",
        "northern checkpoint": "NORTH_CHECKPOINT",

        "south bridge": "SOUTH_BRIDGE",
        "east gate": "EAST_GATE",
        "west gate": "WEST_GATE",

        "power plant": "POWER_PLANT",

        "sector 4": "SECTOR_4",
        "sector four": "SECTOR_4",

        "sector 7b": "SECTOR_7B",

        "base camp": "BASE_CAMP",
        "headquarters": "HQ",
        "hq": "HQ",

        "main road": "MAIN_ROAD",
        "river bank": "RIVER_BANK",

        "hospital": "HOSPITAL",
        "school": "SCHOOL",
        "market": "MARKET",
        "village": "VILLAGE",
        "border": "BORDER",
        "airport": "AIRPORT",
        "station": "STATION",
        "warehouse": "WAREHOUSE",
    }

    # ==========================================================
    # REQUIREMENTS
    # ==========================================================

    REQUIREMENTS = {
        "medical assistance": "MEDICAL_ASSISTANCE",
        "medical help": "MEDICAL_ASSISTANCE",
        "medical support": "MEDICAL_ASSISTANCE",

        "emergency medical assistance": "EMERGENCY_MEDICAL_ASSISTANCE",

        "food supplies": "FOOD_SUPPLIES",
        "water supplies": "WATER_SUPPLIES",

        "reinforcement": "REINFORCEMENT",
        "reinforcements": "REINFORCEMENT",

        "backup": "BACKUP",
        "support": "SUPPORT",
    }

    # ==========================================================
    # TIME EXPRESSIONS
    # ==========================================================

    TIMES = {
        "now": "NOW",
        "immediately": "IMMEDIATE",
        "right now": "NOW",
        "today": "TODAY",
        "tonight": "TONIGHT",
        "tomorrow": "TOMORROW",
        "asap": "ASAP",
    }

    def __init__(self):
        pass

    # ==========================================================
    # Helper
    # ==========================================================

    @staticmethod
    def _contains_phrase(text: str, phrase: str) -> bool:
        """
        Safe phrase matching.
        """
        return re.search(
            r"\b" + re.escape(phrase) + r"\b",
            text
        ) is not None

    # ==========================================================
    # MAIN EXTRACTION
    # ==========================================================

    def extract(self, raw_text: str) -> Dict[str, str]:

        cleaned = TextCleaner.clean_text(raw_text)

        semantic: Dict[str, str] = {}

        # ------------------------------------------------------
        # 1. URGENCY
        # ------------------------------------------------------

        for keyword, code in self.URGENCIES.items():

            if self._contains_phrase(cleaned, keyword):

                semantic["URGENCY"] = code
                break

        # ------------------------------------------------------
        # 2. ACTION
        # ------------------------------------------------------

        for keyword, code in self.ACTIONS.items():

            if self._contains_phrase(cleaned, keyword):

                semantic["ACTION"] = code
                break

        # ------------------------------------------------------
        # 3. TEAM
        # ------------------------------------------------------

        for keyword, code in self.TEAMS.items():

            if self._contains_phrase(cleaned, keyword):

                semantic["TEAM"] = code
                break

        # ------------------------------------------------------
        # 4. ACTOR
        # ------------------------------------------------------

        for keyword, code in self.ACTORS.items():

            if self._contains_phrase(cleaned, keyword):

                semantic["ACTOR"] = code
                break

        # ------------------------------------------------------
        # 5. OBJECT
        # ------------------------------------------------------

        for keyword, code in self.OBJECTS.items():

            if self._contains_phrase(cleaned, keyword):

                semantic["OBJECT"] = code
                break

        # ------------------------------------------------------
        # 6. QUANTITY
        # ------------------------------------------------------

        qty_match = re.search(
            r"\b("
            r"\d+|"
            r"one|two|three|four|five|"
            r"six|seven|eight|nine|ten"
            r")\b",
            cleaned
        )

        if qty_match:

            value = qty_match.group(1)

            num_map = {
                "one": "1",
                "two": "2",
                "three": "3",
                "four": "4",
                "five": "5",
                "six": "6",
                "seven": "7",
                "eight": "8",
                "nine": "9",
                "ten": "10",
            }

            semantic["QUANTITY"] = num_map.get(
                value,
                value
            )

        # ------------------------------------------------------
        # 7. LOCATION
        # ------------------------------------------------------

        for phrase, code in self.KNOWN_LOCATIONS.items():

            if self._contains_phrase(cleaned, phrase):

                semantic["LOCATION"] = code
                break

        # Generic location fallback

        if "LOCATION" not in semantic:

            generic_location = re.search(
                r"(sector\s+\w+|"
                r"checkpoint\s+\w+|"
                r"bridge\s+\w+|"
                r"hill\s+\d+)",
                cleaned
            )

            if generic_location:

                loc = generic_location.group(1)

                semantic["LOCATION"] = (
                    loc.upper()
                    .replace(" ", "_")
                )

        # ------------------------------------------------------
        # 8. REQUIREMENT
        # ------------------------------------------------------

        for phrase, code in self.REQUIREMENTS.items():

            if self._contains_phrase(cleaned, phrase):

                semantic["REQUIREMENT"] = code
                break

        # ------------------------------------------------------
        # 9. TIME
        # ------------------------------------------------------

        for phrase, code in self.TIMES.items():

            if self._contains_phrase(cleaned, phrase):

                semantic["TIME"] = code
                break

        # ------------------------------------------------------
        # 10. STATUS
        # ------------------------------------------------------

        for phrase, code in self.STATUSES.items():

            if self._contains_phrase(cleaned, phrase):

                semantic["STATUS"] = code
                break

        # ------------------------------------------------------
        # 11. REASON
        # ------------------------------------------------------

        reason_patterns = [
            r"because (.+)",
            r"as (.+)",
            r"since (.+)",
            r"due to (.+)",
        ]

        for pattern in reason_patterns:

            reason_match = re.search(
                pattern,
                cleaned
            )

            if reason_match:

                reason = reason_match.group(1).strip()

                if reason:

                    semantic["REASON"] = reason

                break

        return semantic