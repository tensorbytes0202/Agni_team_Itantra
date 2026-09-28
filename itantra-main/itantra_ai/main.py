import json
import time
import os
import sys

# Ensure root package import path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from itantra_ai.stt.stt_engine import STTEngine
from itantra_ai.semantic.semantic_extractor import SemanticExtractor
from itantra_ai.priority.priority_engine import PriorityEngine
from itantra_ai.encoder.encoder import Encoder
from itantra_ai.encoder.decoder import Decoder
from itantra_ai.compression.compressor import Compressor
from itantra_ai.context.context_manager import ContextManager
from itantra_ai.channel.simulator import WeakChannelSimulator
from itantra_ai.evaluation.metrics import EvaluationMetrics

def run_pipeline_demo(input_text: str, channel_loss_rate: float = 0.0, context_mgr: ContextManager = None):
    print("=" * 70)
    print(" [iTantra AI Transceiver Prototype Pipeline] ")
    print("=" * 70)
    
    t_start = time.perf_counter()

    # Step 1: Input Speech / Text
    print(f"\n1. INPUT SPEECH / TEXT:\n   \"{input_text}\"")

    # Step 2: Offline STT Transcription
    stt = STTEngine()
    transcribed_text = stt.transcribe_audio(input_text)
    print(f"\n2. OFFLINE STT OUTPUT:\n   \"{transcribed_text}\"")

    # Step 3: Semantic Extraction
    extractor = SemanticExtractor()
    semantic_dict = extractor.extract(transcribed_text)
    print("\n3. SEMANTIC REPRESENTATION:")
    for k, v in semantic_dict.items():
        print(f"   {k:<12} = {v}")

    # Step 4: Priority Tagging
    priorities = PriorityEngine.assign_priorities(semantic_dict)
    print("\n4. PRIORITY ASSIGNMENT:")
    for lvl in ["P0", "P1", "P2", "P3"]:
        fields = priorities[lvl]
        if fields:
            field_str = ", ".join([f"{f}={v}" for f, v in fields])
            print(f"   {lvl} (Critical/Operational): {field_str}")

    # Step 5 & 6: Context & Compression & Encoding
    active_context = context_mgr.get_context() if context_mgr else {}
    compressed_semantic = Compressor.apply_context_compression(semantic_dict, active_context)
    
    encoded_bitstream = Encoder.encode(compressed_semantic)
    print(f"\n5. COMPACT BINARY BITSTREAM (ENCODED & COMPRESSED):")
    print(f"   Bitstream: {encoded_bitstream}")
    print(f"   Length   : {len(encoded_bitstream)} bits")

    # Update context memory
    if context_mgr:
        context_mgr.update_context(semantic_dict)

    # Step 7: Simulated Weak Channel Transmission
    print(f"\n6. SIMULATED WEAK CHANNEL (Loss Rate: {int(channel_loss_rate * 100)}%):")
    sim = WeakChannelSimulator(loss_rate=channel_loss_rate)
    received_bits, delivered = sim.transmit(encoded_bitstream)
    
    if not delivered:
        print("   [DROPPED] [PACKET DROPPED BY CHANNEL LOSS]")
        reconstructed_semantic = {}
        reconstructed_text = "[PACKET LOST - REQUEST RETRANSMISSION]"
    else:
        print("   [OK] Packet Delivered Successfully!")
        # Step 8: Receiver Decoding & Context Resolution
        raw_decoded_semantic, reconstructed_text = Decoder.decode(received_bits)
        
        # Resolve context references if present
        if context_mgr:
            reconstructed_semantic = context_mgr.resolve_context(raw_decoded_semantic)
            reconstructed_text = Decoder.reconstruct_text(reconstructed_semantic)
        else:
            reconstructed_semantic = raw_decoded_semantic

    print("\n7. RECEIVER RECONSTRUCTED SEMANTICS:")
    for k, v in reconstructed_semantic.items():
        print(f"   {k:<12} = {v}")

    print(f"\n8. FINAL RECONSTRUCTED MEANING:\n   \"{reconstructed_text}\"")

    t_end = time.perf_counter()

    # Step 9: Evaluation Metrics
    metrics = EvaluationMetrics.evaluate(
        original_text=input_text,
        original_semantic=semantic_dict,
        encoded_bits=encoded_bitstream,
        compressed_bits=encoded_bitstream,
        reconstructed_semantic=reconstructed_semantic,
        start_time=t_start,
        end_time=t_end
    )

    print("\n" + "-" * 70)
    print(" [EXPERIMENTAL MEASURED METRICS] ")
    print("-" * 70)
    print(f" • Original Text Length   : {metrics['original_text_len']} chars")
    print(f" • Original Estimated Bits: {metrics['original_bits']} bits (8 bits/char)")
    print(f" • Transmitted Bitstream  : {metrics['compressed_bits']} bits")
    print(f" • Compression Ratio      : {metrics['compression_ratio']}x")
    print(f" • Bit Savings %          : {metrics['bit_savings_pct']}%")
    print(f" • Reconstruction Accuracy: {metrics['reconstruction_accuracy_pct']}%")
    print(f" • P0 Critical Recovery   : {metrics['p0_recovery_pct']}%")
    print(f" • Processing Latency     : {metrics['latency_ms']} ms")
    print("=" * 70 + "\n")
    return metrics


def main():
    sample_file = os.path.join(os.path.dirname(__file__), "data", "sample_sentences.json")
    with open(sample_file, "r") as f:
        samples = json.load(f)

    ctx_manager = ContextManager()

    print("\n" + "=" * 70)
    print("       iTantra AI - SEMANTIC TRANSCEIVER DEMO SUITE (ISRO/SIH)")
    print("=" * 70)

    for sample in samples:
        input_sentence = sample["input_text"]
        run_pipeline_demo(input_text=input_sentence, channel_loss_rate=0.0, context_mgr=ctx_manager)

    # Context reuse demonstration
    print("\n" + "=" * 70)
    print(" SPECIAL TEST: CONTEXT REUSE DEMO (MULTI-TURN COMMUNICATION)")
    print("=" * 70)
    ctx_manager.clear()
    
    print("\n--- Turn 1 ---")
    run_pipeline_demo("Medical team is at the north checkpoint.", channel_loss_rate=0.0, context_mgr=ctx_manager)

    print("\n--- Turn 2 (Context Reuse) ---")
    run_pipeline_demo("Send them urgently.", channel_loss_rate=0.0, context_mgr=ctx_manager)

    # Simulated Lossy Channel Demonstration
    print("\n" + "=" * 70)
    print(" SPECIAL TEST: WEAK CHANNEL SIMULATION AT DIFFERENT LOSS RATES")
    print("=" * 70)
    test_sentence = "Urgently send the medical team to the north checkpoint."
    for loss in [0.0, 0.05, 0.10, 0.20, 0.30]:
        print(f"\n--- Channel Loss Rate: {int(loss * 100)}% ---")
        run_pipeline_demo(test_sentence, channel_loss_rate=loss, context_mgr=None)

if __name__ == "__main__":
    main()
