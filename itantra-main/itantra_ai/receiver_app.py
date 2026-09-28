import sys
import os
import tempfile

import streamlit as st

# ---------------------------------------------------------
# Ensure root package import path
# ---------------------------------------------------------
sys.path.insert(
    0,
    os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
)

from itantra_ai.encoder.decoder import Decoder
from itantra_ai.encoder.dictionary import Dictionary


# ---------------------------------------------------------
# Page Configuration
# ---------------------------------------------------------
st.set_page_config(
    page_title="iTantra AI - Receiver",
    page_icon="📥",
    layout="wide"
)


# ---------------------------------------------------------
# Styling
# ---------------------------------------------------------
st.markdown("""
<style>
    .main-title {
        font-size: 2.3rem;
        font-weight: 700;
        text-align: center;
        margin-bottom: 5px;
    }

    .sub-title {
        font-size: 1.1rem;
        text-align: center;
        margin-bottom: 25px;
    }

    .bit-box {
        font-family: monospace;
        padding: 12px;
        border-radius: 8px;
        word-break: break-all;
        font-size: 1.05rem;
    }

    .receiver-box {
        padding: 20px;
        border-radius: 12px;
        margin-top: 10px;
    }
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------
# Header
# ---------------------------------------------------------
st.markdown(
    '<div class="main-title">📥 iTantra AI Receiver</div>',
    unsafe_allow_html=True
)

st.markdown(
    '<div class="sub-title">'
    'Receive → Decode → Reconstruct → Text-to-Speech'
    '</div>',
    unsafe_allow_html=True
)


# ---------------------------------------------------------
# Receiver Input
# ---------------------------------------------------------
st.subheader("📡 Step 1: Receive Transmitted Bitstream")

received_input = st.text_area(
    "Paste the received binary bitstream:",
    height=150,
    placeholder="Example: 0100010001101000100001001000111001110001"
)


# ---------------------------------------------------------
# Decode Button
# ---------------------------------------------------------
if st.button("📥 Receive & Decode Packet", type="primary"):

    # -----------------------------------------------------
    # Clean received bits
    # -----------------------------------------------------
    received_bits = (
        received_input
        .replace(" ", "")
        .replace("\n", "")
        .replace("\r", "")
        .strip()
    )

    # -----------------------------------------------------
    # Validate input
    # -----------------------------------------------------
    if not received_bits:
        st.warning("⚠️ Please enter the received bitstream.")

    elif any(bit not in "01" for bit in received_bits):
        st.error(
            "❌ Invalid bitstream. "
            "Only 0 and 1 are allowed."
        )

    else:

        # -------------------------------------------------
        # Show received data
        # -------------------------------------------------
        st.markdown("---")
        st.subheader("📡 Received Data")

        st.markdown(
            f'<div class="bit-box">{received_bits}</div>',
            unsafe_allow_html=True
        )

        st.write(
            f"**Received Bits:** {len(received_bits)} bits"
        )

        # -------------------------------------------------
        # Decode Binary → Semantic Representation
        # -------------------------------------------------
        try:

            raw_decoded, remaining_bits = Decoder.decode(
                received_bits
            )

            # ---------------------------------------------
            # Semantic Data
            # ---------------------------------------------
            st.markdown("---")
            st.subheader("🧠 Step 2: Decoded Semantic Information")

            if raw_decoded:

                st.json(raw_decoded)

            else:
                st.warning(
                    "⚠️ No semantic information could be decoded."
                )

            # -------------------------------------------------
            # Dictionary Version
            # -------------------------------------------------
            st.write(
                f"**Dictionary Version:** "
                f"{getattr(Dictionary, 'VERSION', '1')}"
            )

            # -------------------------------------------------
            # Reconstruct Text
            # -------------------------------------------------
            if raw_decoded:

                reconstructed_text = Decoder.reconstruct_text(
                    raw_decoded
                )

                st.markdown("---")
                st.subheader(
                    "📝 Step 3: Reconstructed Message"
                )

                st.success(reconstructed_text)

                # -------------------------------------------------
                # Text → Voice
                # -------------------------------------------------
                st.markdown("---")
                st.subheader(
                    "🔊 Step 4: Receiver Text-to-Speech"
                )

                try:

                    # Import TTS library only when required
                    import pyttsx3

                    # Temporary WAV file
                    temp_audio = tempfile.NamedTemporaryFile(
                        delete=False,
                        suffix=".wav"
                    )

                    temp_audio_path = temp_audio.name
                    temp_audio.close()

                    # Create TTS engine
                    engine = pyttsx3.init()

                    # Optional speech settings
                    engine.setProperty("rate", 150)
                    engine.setProperty("volume", 1.0)

                    # Generate speech
                    engine.save_to_file(
                        reconstructed_text,
                        temp_audio_path
                    )

                    engine.runAndWait()

                    # Read generated audio
                    with open(
                        temp_audio_path,
                        "rb"
                    ) as audio_file:

                        audio_bytes = audio_file.read()

                    # Display audio player
                    st.audio(
                        audio_bytes,
                        format="audio/wav"
                    )

                    st.success(
                        "🔊 Decoded message converted to voice successfully."
                    )

                    # Cleanup
                    try:
                        os.remove(temp_audio_path)
                    except OSError:
                        pass

                except ImportError:

                    st.error(
                        "❌ pyttsx3 is not installed."
                    )

                    st.info(
                        "Install it using: pip install pyttsx3"
                    )

                except Exception as e:

                    st.error(
                        f"❌ Text-to-Speech failed: {e}"
                    )

            else:

                st.warning(
                    "⚠️ Voice generation skipped because "
                    "no message was reconstructed."
                )

            # -------------------------------------------------
            # Remaining Bits
            # -------------------------------------------------
            if remaining_bits:

                st.markdown("---")
                st.subheader("ℹ️ Remaining Bits")

                st.code(
                    remaining_bits,
                    language="text"
                )

                st.caption(
                    f"{len(remaining_bits)} bits remained "
                    "after decoding."
                )

            # -------------------------------------------------
            # Receiver Summary
            # -------------------------------------------------
            st.markdown("---")
            st.subheader("📊 Receiver Summary")

            col1, col2, col3 = st.columns(3)

            with col1:
                st.metric(
                    "Received Bits",
                    len(received_bits)
                )

            with col2:
                st.metric(
                    "Fields Recovered",
                    len(raw_decoded)
                    if raw_decoded else 0
                )

            with col3:
                st.metric(
                    "Dictionary",
                    getattr(
                        Dictionary,
                        "VERSION",
                        "1"
                    )
                )

        except Exception as e:

            st.error(
                f"❌ Decoding failed: {e}"
            )