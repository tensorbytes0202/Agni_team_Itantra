from typing import Dict, Tuple

from itantra_ai.encoder.dictionary import Dictionary


class Decoder:
    """
    Decodes binary bitstream into semantic fields and reconstructs
    a richer receiver-side natural language message.
    """

    @classmethod
    def decode(cls, bit_stream: str) -> Tuple[Dict[str, str], str]:
        """
        Decode:
            4-bit field count
            +
            repeated:
                4-bit field key
                +
                dictionary/fallback encoded value

        Returns:
            (semantic_dictionary, reconstructed_text)
        """

        if not bit_stream:
            return {}, "Invalid or empty bitstream"

        # Remove accidental spaces/newlines
        bit_stream = "".join(bit_stream.split())

        # Validate binary input
        if any(bit not in "01" for bit in bit_stream):
            return {}, "Invalid bitstream: only 0 and 1 are allowed."

        # Need at least 4 bits for field count
        if len(bit_stream) < 4:
            return {}, "Invalid or incomplete bitstream."

        # ------------------------------------------------------
        # Field count
        # ------------------------------------------------------

        field_count = int(bit_stream[0:4], 2)
        idx = 4

        reconstructed_semantic: Dict[str, str] = {}

        # ------------------------------------------------------
        # Decode every field
        # ------------------------------------------------------

        for _ in range(field_count):

            # Need 4 bits for field key
            if idx + 4 > len(bit_stream):
                break

            key_code = bit_stream[idx:idx + 4]
            idx += 4

            key_name = Dictionary.decode_key(key_code)

            if not key_name:
                key_name = f"UNKNOWN_KEY_{key_code}"

            # --------------------------------------------------
            # Decode value
            # --------------------------------------------------

            value_str, next_idx = Dictionary.decode_value(
                bit_stream,
                idx
            )

            # Prevent infinite loop on malformed data
            if next_idx <= idx:
                break

            idx = next_idx

            reconstructed_semantic[key_name] = value_str

        # ------------------------------------------------------
        # Reconstruct natural language
        # ------------------------------------------------------

        reconstructed_text = cls.reconstruct_text(
            reconstructed_semantic
        )

        # Remaining bits can be useful for debugging
        remaining_bits = bit_stream[idx:]

        return reconstructed_semantic, reconstructed_text

    # ==========================================================
    # TEXT RECONSTRUCTION
    # ==========================================================

    @classmethod
    def reconstruct_text(cls, semantic: Dict[str, str]) -> str:
        """
        Converts semantic representation into a richer
        receiver-side natural language message.

        Important:
        This reconstructs the transmitted meaning.
        It cannot guarantee the exact original wording because
        semantic compression intentionally removes stylistic words.
        """

        if not semantic:
            return "No clear meaning extracted."

        parts = []

        # ======================================================
        # 1. URGENCY
        # ======================================================

        urgency = semantic.get("URGENCY")

        if urgency == "CRITICAL":
            parts.append("Critical emergency:")

        elif urgency == "HIGH":
            parts.append("Urgently")

        elif urgency == "MEDIUM":
            parts.append("With medium priority")

        elif urgency == "LOW":
            parts.append("Routinely")

        # ======================================================
        # 2. ACTION
        # ======================================================

        action = semantic.get("ACTION")

        if action:

            action_map = {
                "SEND": "send",
                "EVACUATE": "evacuate",
                "DEPLOY": "deploy",
                "HALT": "halt",
                "SECURE": "secure",
                "REPORT": "report",
            }

            parts.append(
                action_map.get(
                    action,
                    action.replace("_", " ").lower()
                )
            )

        # ======================================================
        # 3. QUANTITY
        # ======================================================

        quantity = semantic.get("QUANTITY")

        if quantity:
            parts.append(quantity)

        # ======================================================
        # 4. OBJECT / TEAM / ACTOR
        # ======================================================

        obj = semantic.get("OBJECT")
        team = semantic.get("TEAM")
        actor = semantic.get("ACTOR")

        if obj:

            object_map = {
                "AMBULANCE": "ambulance",
                "TRUCK": "truck",
                "SUPPLIES": "supplies",
                "WATER": "water",
                "RATIONS": "rations",
                "MEDICINE": "medicine",
                "DRONE": "drone",
            }

            object_text = object_map.get(
                obj,
                obj.replace("_", " ").lower()
            )

            # Pluralize countable objects
            if quantity and quantity != "1":

                if object_text == "ambulance":
                    object_text = "ambulances"

                elif object_text == "truck":
                    object_text = "trucks"

                elif object_text == "drone":
                    object_text = "drones"

            parts.append(object_text)

        elif team:

            team_text = team.replace(
                "_",
                " "
            ).lower()

            parts.append(
                f"the {team_text} team"
            )

        elif actor:

            actor_text = actor.replace(
                "_",
                " "
            ).lower()

            parts.append(
                f"the {actor_text}"
            )

        # ======================================================
        # 5. LOCATION
        # ======================================================

        location = semantic.get("LOCATION")

        if location:

            location_text = location.replace(
                "_",
                " "
            ).title()

            # Avoid awkward "to" with status messages
            if action in {
                "SEND",
                "DEPLOY",
                "EVACUATE",
                "MOVE",
            }:

                parts.append(
                    f"to {location_text}"
                )

            else:

                parts.append(
                    f"at {location_text}"
                )

        # ======================================================
        # 6. REQUIREMENT
        # ======================================================

        requirement = semantic.get("REQUIREMENT")

        if requirement:

            requirement_map = {

                "MEDICAL_ASSISTANCE":
                    "medical assistance",

                "EMERGENCY_MEDICAL_ASSISTANCE":
                    "emergency medical assistance",

                "FOOD_SUPPLIES":
                    "food supplies",

                "WATER_SUPPLIES":
                    "water supplies",

                "REINFORCEMENT":
                    "reinforcements",

                "BACKUP":
                    "backup",

                "SUPPORT":
                    "support",
            }

            requirement_text = requirement_map.get(
                requirement,
                requirement.replace(
                    "_",
                    " "
                ).lower()
            )

            parts.append(
                f"with {requirement_text}"
            )

        # ======================================================
        # 7. STATUS
        # ======================================================

        status = semantic.get("STATUS")

        if status:

            status_map = {

                "DEPLOYED": "deployed",

                "ARRIVED": "arrived",

                "EN_ROUTE": "en route",

                "READY": "ready",

                "STANDBY": "on standby",

                "ENGAGED": "engaged",

                "COMPLETE": "completed",

                "DELAYED": "delayed",

                "SAFE": "safe",
            }

            status_text = status_map.get(
                status,
                status.replace(
                    "_",
                    " "
                ).lower()
            )

            parts.append(
                f"Status: {status_text}"
            )

        # ======================================================
        # 8. TIME
        # ======================================================

        time_value = semantic.get("TIME")

        if time_value:

            time_map = {

                "NOW": "now",

                "IMMEDIATE": "immediately",

                "TODAY": "today",

                "TONIGHT": "tonight",

                "TOMORROW": "tomorrow",

                "ASAP": "as soon as possible",
            }

            time_text = time_map.get(
                time_value,
                time_value.replace(
                    "_",
                    " "
                ).lower()
            )

            parts.append(time_text)

        # ======================================================
        # 9. REASON
        # ======================================================

        reason = semantic.get("REASON")

        if reason:

            reason = reason.strip()

            if reason:

                parts.append(
                    f"because {reason}"
                )

        # ======================================================
        # 10. FALLBACK
        # ======================================================

        if not parts:

            return "No clear meaning extracted."

        # Remove accidental duplicate spaces
        sentence = " ".join(parts)

        sentence = re_clean_sentence(sentence)

        if not sentence.endswith("."):
            sentence += "."

        return sentence


# ==============================================================
# Small helper
# ==============================================================

def re_clean_sentence(text: str) -> str:
    """
    Cleans minor formatting issues in reconstructed text.
    """

    text = " ".join(text.split())

    # Fix common duplicate words
    text = text.replace(
        "the the ",
        "the "
    )

    return text