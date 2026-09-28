import sys
import os
import time
import tempfile
import streamlit as st

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
from itantra_ai.transport.packetizer import Packetizer
from itantra_ai.encoder.dictionary import Dictionary
from itantra_ai.priority.adaptive_priority_engine import AdaptivePriorityEngine


# Page configuration
st.set_page_config(
    page_title="iTantra AI - Semantic Transceiver Prototype",
    page_icon="📡",
    layout="wide"
)


# Styling
st.markdown("""
<style>
    .main-title {
        font-size: 2.3rem;
        font-weight: 700;
        color: #1E88E5;
        text-align: center;
        margin-bottom: 0px;
    }

    .sub-title {
        font-size: 1.1rem;
        text-align: center;
        color: #555;
        margin-bottom: 25px;
    }

    .metric-card {
        background-color: #f8f9fa;
        border-radius: 10px;
        padding: 15px;
        border-left: 5px solid #1E88E5;
        box-shadow: 0 2px 5px rgba(0,0,0,0.05);
    }

    .bit-box {
        font-family: monospace;
        background-color: #0E1117;
        color: #00FF66;
        padding: 12px;
        border-radius: 8px;
        word-break: break-all;
        font-size: 1.1rem;
    }

    .step-header {
        font-weight: 600;
        font-size: 1.1rem;
        color: #0F52BA;
        margin-top: 10px;
    }
</style>
""", unsafe_allow_html=True)


st.markdown(
    '<div class="main-title">📡 iTantra AI Transceiver</div>',
    unsafe_allow_html=True
)

st.markdown(
    '<div class="sub-title">Indian Multilingual Low-Bitrate Semantic Speech Compression & Priority Transceiver</div>',
    unsafe_allow_html=True
)


# Sidebar
st.sidebar.header("🎛️ Simulation Parameters")

channel_loss = st.sidebar.slider(
    "Radio Packet Loss Rate (%)",
    min_value=0,
    max_value=50,
    value=0,
    step=5,
    help="Simulates weak, noisy HF/VHF or satellite channel packet drops."
) / 100.0


use_context = st.sidebar.checkbox(
    "Enable Session Context Memory Reuse",
    value=True,
    help="Remembers active location and team from previous messages to avoid redundant transmission."
)


use_reliability_engine = st.sidebar.checkbox(
    "🛡️ Enable Reliability Engine (Priority Packet Splitting + Hamming FEC)",
    value=True,
    help="Splits the message into per-priority packets, protects P0 (critical) "
         "fields with Hamming(7,4) error correction, and tags every packet with "
         "the dictionary version so a mismatched receiver never silently mis-decodes."
)


use_adaptive_priority = st.sidebar.checkbox(
    "🧠 Use Adaptive (context-sensitive) Priority Engine",
    value=True,
    help="Instead of a fixed field→priority table (e.g. LOCATION is always P1), "
         "scores each field using its base importance + the specific value + "
         "the rest of the message. e.g. LOCATION becomes P0 during an EVACUATE "
         "order, but stays low priority in a routine status check-in."
)


st.sidebar.markdown("---")
st.sidebar.subheader("💡 Quick Sample Commands")

sample_choice = st.sidebar.radio(
    "Select a pre-configured operational command:",
    [
        "Custom Input",
        "Urgently send the medical team to the north checkpoint.",
        "Evacuate 5 civilians from sector 4.",
        "Deploy 2 ambulances to south bridge immediately.",
        "Engineering squad reached power plant."
    ]
)


# Context Manager initialization in session state
if "context_mgr" not in st.session_state:
    st.session_state.context_mgr = ContextManager()


if st.sidebar.button("🧹 Clear Session Context Memory"):
    st.session_state.context_mgr.clear()
    st.sidebar.success("Context memory cleared!")


# ============================================================
# Input Section
# ============================================================

st.subheader("🎙️ Step 1: Speech / Text Command Input")


input_mode = st.radio(
    "Choose input method:",
    ["🎙️ Voice", "⌨️ Text"],
    horizontal=True
)


voice_input = None
input_text = ""


if input_mode == "🎙️ Voice":

    voice_input = st.audio_input(
        "Record your operational command",
        sample_rate=16000
    )

    if voice_input:
        st.audio(voice_input, format="audio/wav")


else:

    default_text = "Urgently send the medical team to the north checkpoint."

    if sample_choice != "Custom Input":
        default_text = sample_choice

    input_text = st.text_input(
        "Enter Operational Command:",
        value=default_text
    )


# ============================================================
# Process Command
# ============================================================

if st.button("🚀 Process & Transmit Command", type="primary"):

    t_start = time.perf_counter()


    # ========================================================
    # Step 1: STT Transcription
    # ========================================================

    stt = STTEngine()


    if input_mode == "🎙️ Voice":

        if voice_input is None:
            st.warning("🎙️ Please record a voice command first.")
            st.stop()


        temp_audio_path = None


        try:

            with tempfile.NamedTemporaryFile(
                delete=False,
                suffix=".wav"
            ) as temp_audio:

                temp_audio.write(voice_input.getvalue())
                temp_audio_path = temp_audio.name


            # REAL VOSK STT
            transcribed_text = stt.transcribe_audio(temp_audio_path)


        finally:

            if temp_audio_path and os.path.exists(temp_audio_path):
                os.remove(temp_audio_path)


    else:

        # Text mode — existing behavior
        transcribed_text = stt.transcribe_audio(input_text)


    # Show transcription
    st.write("**🎤 Transcribed Command:**")
    st.info(transcribed_text)


    # ========================================================
    # Step 2: Semantic NLU Extraction
    # ========================================================

    extractor = SemanticExtractor()
    semantic_dict = extractor.extract(transcribed_text)


    # ========================================================
    # Step 3: Priority Assignment
    # ========================================================

    priorities = PriorityEngine.assign_priorities(semantic_dict)


    # ========================================================
    # Step 4: Context & Compression
    # ========================================================

    active_ctx = (
        st.session_state.context_mgr.get_context()
        if use_context
        else {}
    )


    compressed_semantic = Compressor.apply_context_compression(
        semantic_dict,
        active_ctx
    )


    encoded_bitstream = Encoder.encode(
        compressed_semantic
    )


    # Update context memory
    if use_context:
        st.session_state.context_mgr.update_context(
            semantic_dict
        )


    # ========================================================
    # Step 5: Channel Transmission
    # ========================================================

    simulator = WeakChannelSimulator(
        loss_rate=channel_loss
    )


    received_bits, delivered = simulator.transmit(
        encoded_bitstream
    )


    # ========================================================
    # Step 6: Receiver Decoding
    # ========================================================

    if not delivered:

        reconstructed_semantic = {}

        reconstructed_text = (
            "❌ [PACKET LOST - REQUEST RETRANSMISSION]"
        )

    else:

        raw_decoded, _ = Decoder.decode(
            received_bits
        )


        if use_context:

            reconstructed_semantic = (
                st.session_state.context_mgr.resolve_context(
                    raw_decoded
                )
            )

            reconstructed_text = (
                Decoder.reconstruct_text(
                    reconstructed_semantic
                )
            )

        else:

            reconstructed_semantic = raw_decoded

            reconstructed_text = (
                Decoder.reconstruct_text(
                    raw_decoded
                )
            )


    t_end = time.perf_counter()


    # ========================================================
    # Evaluation Metrics
    # ========================================================

    metrics = EvaluationMetrics.evaluate(
        original_text=transcribed_text,
        original_semantic=semantic_dict,
        encoded_bits=encoded_bitstream,
        compressed_bits=encoded_bitstream,
        reconstructed_semantic=reconstructed_semantic,
        start_time=t_start,
        end_time=t_end
    )


    st.markdown("---")


    # ========================================================
    # Display Measured Metrics Cards
    # ========================================================

    st.subheader("📊 Key Measured AI & Compression Metrics")

    m1, m2, m3, m4, m5 = st.columns(5)


    with m1:

        st.metric(
            "Original Text Size",
            f"{metrics['original_bits']} bits",
            f"{metrics['original_text_len']} chars"
        )


    with m2:

        st.metric(
            "AI Transmitted Stream",
            f"{metrics['compressed_bits']} bits",
            f"-{metrics['bit_savings_pct']}% bits"
        )


    with m3:

        st.metric(
            "Compression Ratio",
            f"{metrics['compression_ratio']}x",
            "Speedup"
        )


    with m4:

        st.metric(
            "Intent Recovery",
            f"{metrics['reconstruction_accuracy_pct']}%",
            f"P0: {metrics['p0_recovery_pct']}%"
        )


    with m5:

        st.metric(
            "AI Latency",
            f"{metrics['latency_ms']} ms",
            "Sub-millisecond"
        )


    st.markdown("---")


    # ========================================================
    # Detailed Step-by-Step AI Breakdown
    # ========================================================

    col_sender, col_receiver = st.columns(2)


    # ========================================================
    # Sender End
    # ========================================================

    with col_sender:

        st.markdown(
            '<div class="step-header">📤 SENDER END (AI Extraction & Bit Framing)</div>',
            unsafe_allow_html=True
        )


        st.write("**🎤 Speech-to-Text Output:**")
        st.info(transcribed_text)


        st.write("**1. NLU Extracted Intent (Slots):**")
        st.json(semantic_dict)


        st.write("**2. Priority Engine Tagging:**")
        st.write(
            f"• **P0 Critical:** {priorities['P0']}"
        )

        st.write(
            f"• **P1 Operational:** {priorities['P1']}"
        )


        st.write("**3. Compact Binary Bitstream (Transmitted over Radio):**")

        st.markdown(
            f'<div class="bit-box">{encoded_bitstream}</div>',
            unsafe_allow_html=True
        )


        st.caption(
            f"Bit length: {len(encoded_bitstream)} bits "
            f"(vs 440 bits standard ASCII)"
        )


    # ========================================================
    # Receiver End
    # ========================================================

    with col_receiver:

        st.markdown(
            '<div class="step-header">📥 RECEIVER END (Channel & AI Reconstruction)</div>',
            unsafe_allow_html=True
        )


        if delivered:

            st.success(
                f"✅ Radio Packet Delivered Successfully "
                f"(Channel Loss: {int(channel_loss*100)}%)"
            )


            st.write("**1. Decoded Semantic Representation:**")
            st.json(reconstructed_semantic)


            st.write("**2. Synthesized Speech & Text Command:**")

            st.info(
                f"🗣️ **Reconstructed Meaning:** "
                f"\"{reconstructed_text}\""
            )


        else:

            st.error(
                f"⚠️ Packet Dropped by Lossy Channel "
                f"(Loss Rate: {int(channel_loss*100)}%)"
            )

            st.warning(
                "Requesting Retransmission (ARQ Protocol)..."
            )


    # ========================================================
    # Reliability Engine
    # ========================================================

    if use_reliability_engine:

        st.markdown("---")

        st.subheader(
            "🛡️ Reliability Engine — Priority-Split Packets + Hamming FEC"
        )


        st.caption(
            "Instead of sending the whole message as one blob, each priority "
            "tier becomes its own packet. P0 (critical) fields get Hamming(7,4) "
            "error correction; every packet carries the dictionary version so a "
            "mismatch is detected, never silently mis-decoded."
        )


        packets = Packetizer.build_packets(
            compressed_semantic,
            protect_priorities=("P0",),
            use_adaptive_priority=use_adaptive_priority,
        )


        rel_channel = WeakChannelSimulator(
            loss_rate=channel_loss
        )


        if use_adaptive_priority:

            with st.expander(
                "🔍 Why each field got its priority tier (adaptive scoring)"
            ):

                st.caption(
                    "Score = base importance of the field type + a modifier for "
                    "this specific value + a modifier from the rest of the "
                    "message (e.g. an EVACUATE action boosts LOCATION's score). "
                    "Compare this to the old engine, where LOCATION was always "
                    "a fixed P1 no matter what."
                )


                explain_rows = AdaptivePriorityEngine.explain(
                    compressed_semantic
                )

                st.table(explain_rows)


        pkt_cols = (
            st.columns(len(packets))
            if packets
            else []
        )


        received_packets = []


        for pcol, pkt in zip(pkt_cols, packets):

            with pcol:

                st.markdown(
                    f"**[{pkt['priority']}] packet**  "
                    f"({'FEC protected' if pkt['protected'] else 'unprotected'})"
                )


                recv_header, header_ok = (
                    rel_channel.transmit(
                        pkt["header_bits"]
                    )
                )


                recv_payload, payload_ok = (
                    rel_channel.transmit(
                        pkt["payload_bits"]
                    )
                )


                if not header_ok or not payload_ok:

                    st.error(
                        "Packet dropped by channel"
                    )

                    continue


                parsed = Packetizer.parse_packet(
                    recv_header,
                    recv_payload
                )


                received_packets.append(parsed)


                if parsed["ok"]:

                    st.success(
                        f"Recovered: {parsed['fields']}"
                    )


                    if parsed["corrections_made"] > 0:

                        st.caption(
                            f"🔧 Hamming FEC auto-corrected "
                            f"{parsed['corrections_made']} bit-flip(s)"
                        )


                elif parsed["version_mismatch"]:

                    st.warning(
                        f"⚠️ {parsed['reason']}"
                    )

                else:

                    st.error(
                        f"Failed: {parsed['reason']}"
                    )


        merged = Packetizer.reassemble(
            received_packets
        )


        # Packet Loss Concealment
        sent_priorities = [
            p["priority"]
            for p in packets
        ]


        received_priorities = [
            p["priority"]
            for p in received_packets
        ]


        concealed = Packetizer.conceal_dropped_packets(
            all_priorities_sent=sent_priorities,
            received_priorities=received_priorities,
            context_manager=st.session_state.context_mgr,
        )


        if concealed:

            st.warning(
                f"🔶 Packet Loss Concealment: {concealed} — these fields' packets "
                f"were dropped, so their values are ESTIMATED from prior context, "
                f"not actually received this transmission."
            )


            merged = {
                **concealed,
                **merged
            }


        p0_ok = any(
            p["priority"] == "P0"
            and p["ok"]
            for p in received_packets
        )


        st.markdown(
            f"**Reassembled message:** `{merged}`  \n"
            f"**Critical (P0) fields survived:** "
            f"{'✅ Yes' if p0_ok else '❌ No'}  \n"
            f"**Dictionary version:** v{Dictionary.DICT_VERSION}"
        )


        st.info(
            "Compare this to the single-blob result above: with plain encoding, "
            "one corrupted or dropped packet can take the whole message down. "
            "Here, P0 is isolated and protected, so it can survive even when "
            "other fields don't. Measured over 200 trials at 35% loss, this "
            "raises critical-field survival from ~26% to ~47% "
            "(see itantra_ai/tests/test_before_after_comparison.py)."
        )


st.markdown("---")

st.caption(
    "iTantra AI Transceiver Prototype | Designed for ISRO & SIH Low-Bitrate Tactical Communications"
)