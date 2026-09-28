import unittest
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from itantra_ai.preprocessing.text_cleaner import TextCleaner
from itantra_ai.semantic.semantic_extractor import SemanticExtractor
from itantra_ai.priority.priority_engine import PriorityEngine
from itantra_ai.encoder.dictionary import Dictionary
from itantra_ai.encoder.encoder import Encoder
from itantra_ai.encoder.decoder import Decoder
from itantra_ai.context.context_manager import ContextManager

class TestITantraPipeline(unittest.TestCase):

    def test_text_cleaner(self):
        cleaned = TextCleaner.clean_text("Turant medical team ko north checkpoint bhejo.")
        self.assertIn("urgently", cleaned)
        self.assertIn("send", cleaned)

    def test_semantic_extractor(self):
        extractor = SemanticExtractor()
        res = extractor.extract("Urgently send the medical team to the north checkpoint.")
        self.assertEqual(res.get("ACTION"), "SEND")
        self.assertEqual(res.get("TEAM"), "MEDICAL")
        self.assertEqual(res.get("LOCATION"), "NORTH_CHECKPOINT")
        self.assertEqual(res.get("URGENCY"), "HIGH")

    def test_priority_engine(self):
        priorities = PriorityEngine.assign_priorities({"ACTION": "SEND", "TEAM": "MEDICAL", "URGENCY": "HIGH"})
        p0_keys = [k for k, v in priorities["P0"]]
        self.assertIn("ACTION", p0_keys)
        self.assertIn("URGENCY", p0_keys)

    def test_encoder_decoder_roundtrip(self):
        semantic = {"ACTION": "SEND", "TEAM": "MEDICAL", "LOCATION": "NORTH_CHECKPOINT", "URGENCY": "HIGH"}
        encoded = Encoder.encode(semantic)
        decoded_semantic, text = Decoder.decode(encoded)
        self.assertEqual(decoded_semantic["ACTION"], "SEND")
        self.assertEqual(decoded_semantic["TEAM"], "MEDICAL")
        self.assertEqual(decoded_semantic["LOCATION"], "NORTH_CHECKPOINT")
        self.assertEqual(decoded_semantic["URGENCY"], "HIGH")

    def test_dynamic_fallback(self):
        # Testing out-of-dictionary location term
        semantic = {"ACTION": "SEND", "LOCATION": "UNMAPPED_OUTPOST_X"}
        encoded = Encoder.encode(semantic)
        decoded_semantic, text = Decoder.decode(encoded)
        self.assertEqual(decoded_semantic["LOCATION"], "UNMAPPED_OUTPOST_X")

    def test_context_manager(self):
        ctx = ContextManager()
        ctx.update_context({"TEAM": "MEDICAL", "LOCATION": "NORTH_CHECKPOINT"})
        resolved = ctx.resolve_context({"ACTION": "SEND", "URGENCY": "HIGH", "REF_PREV": "1"})
        self.assertEqual(resolved["TEAM"], "MEDICAL")
        self.assertEqual(resolved["LOCATION"], "NORTH_CHECKPOINT")
        self.assertEqual(resolved["ACTION"], "SEND")

if __name__ == "__main__":
    unittest.main()
