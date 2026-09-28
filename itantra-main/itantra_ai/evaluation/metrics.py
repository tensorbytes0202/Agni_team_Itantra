import time
from typing import Dict, Any

class EvaluationMetrics:
    """
    Computes precise, experimentally measured evaluation metrics for the semantic transceiver:
    - Bit counts (Original vs Encoded vs Compressed)
    - Compression Ratio
    - Bit Savings %
    - Semantic match accuracy
    - P0 Critical field recovery rate
    - Processing latency
    """

    @classmethod
    def evaluate(
        cls,
        original_text: str,
        original_semantic: Dict[str, str],
        encoded_bits: str,
        compressed_bits: str,
        reconstructed_semantic: Dict[str, str],
        start_time: float,
        end_time: float
    ) -> Dict[str, Any]:
        
        orig_len = len(original_text)
        orig_bits = orig_len * 8  # Standard ASCII/UTF-8 byte-based bit count
        
        enc_bit_len = len(encoded_bits)
        comp_bit_len = len(compressed_bits) if compressed_bits else enc_bit_len
        
        compression_ratio = round(orig_bits / comp_bit_len, 2) if comp_bit_len > 0 else 0.0
        bit_savings_pct = round((1.0 - (comp_bit_len / orig_bits)) * 100.0, 2) if orig_bits > 0 else 0.0
        
        # Calculate semantic slot accuracy
        total_slots = len(original_semantic)
        matched_slots = 0
        p0_total = 0
        p0_recovered = 0
        
        for key, val in original_semantic.items():
            if key in ["ACTION", "URGENCY", "STATUS"]:
                p0_total += 1
                if key in reconstructed_semantic and reconstructed_semantic[key] == val:
                    p0_recovered += 1
                    
            if key in reconstructed_semantic and reconstructed_semantic[key] == val:
                matched_slots += 1
                
        accuracy_pct = round((matched_slots / total_slots) * 100.0, 2) if total_slots > 0 else 0.0
        p0_recovery_pct = round((p0_recovered / p0_total) * 100.0, 2) if p0_total > 0 else 100.0
        
        latency_ms = round((end_time - start_time) * 1000.0, 3)
        
        return {
            "original_text_len": orig_len,
            "original_bits": orig_bits,
            "semantic_fields_count": total_slots,
            "encoded_bits": enc_bit_len,
            "compressed_bits": comp_bit_len,
            "compression_ratio": compression_ratio,
            "bit_savings_pct": bit_savings_pct,
            "reconstruction_accuracy_pct": accuracy_pct,
            "p0_recovery_pct": p0_recovery_pct,
            "latency_ms": latency_ms
        }
