from typing import Dict, Optional

class ContextManager:
    """
    Manages session context state across multi-turn communications.
    Enables context reuse so redundant fields (like known locations or active teams)
    don't need to be re-transmitted over low-bitrate links.
    """

    def __init__(self):
        self.context_memory: Dict[str, str] = {}

    def update_context(self, semantic_dict: Dict[str, str]):
        """Stores or updates persistent fields in session context memory."""
        for k, v in semantic_dict.items():
            if k in ["TEAM", "LOCATION", "ACTOR", "OBJECT"]:
                self.context_memory[k] = v

    def resolve_context(self, incoming_semantic: Dict[str, str]) -> Dict[str, str]:
        """
        If incoming message contains a reference flag (REF_PREV),
        merges fields stored in context memory with the new incoming semantic fields.
        """
        full_semantic = dict(incoming_semantic)
        
        if "REF_PREV" in incoming_semantic or "them" in str(incoming_semantic.values()).lower():
            # Inject remembered context fields that aren't explicitly overridden
            for k, v in self.context_memory.items():
                if k not in full_semantic:
                    full_semantic[k] = v
                    
        return full_semantic

    def get_context(self) -> Dict[str, str]:
        return dict(self.context_memory)

    def conceal(self, field: str) -> Optional[str]:
        """
        Packet Loss Concealment (PLC) - inspired by Glaris (arXiv:2512.08203),
        which uses a generative model to estimate lost speech content from
        prior context. We can't run a generative model on edge hardware, so
        this is a lightweight, rule-based analog: substitute the last known
        value for a field from context memory instead of leaving it blank.

        Only ever used for non-critical (P1-P3) fields - P0 fields (ACTION,
        URGENCY, STATUS) are never concealed, since guessing what happened
        or how urgent it was would be actively dangerous. Concealment is a
        best-effort estimate, not a substitute for the real data, and
        callers MUST flag it to the operator as estimated, not confirmed.
        """
        return self.context_memory.get(field)

    def clear(self):
        self.context_memory.clear()
