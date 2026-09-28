"""
Offline Speech-to-Text engine — dual backend, auto-routed by language.

WHY TWO BACKENDS INSTEAD OF ONE:
  Vosk only has reliable, well-tested small models for a handful of Indian
  languages (English, Hindi confirmed good quality; a few others exist but
  are inconsistent). It does NOT reliably cover all 10 languages this PS
  requires. AI4Bharat's IndicConformer DOES cover all of them (it's a
  22-language Indic ASR model, government-backed, purpose-built for Indian
  languages) - but the full model needs NeMo + PyTorch, which is far too
  heavy for a low/mid-range phone.

  The fix: run IndicConformer through `sherpa-onnx` instead of NeMo/PyTorch.
  sherpa-onnx is a lightweight C++ ONNX Runtime wrapper (no Python/PyTorch
  needed at inference) that loads INT8-quantized per-language ONNX exports
  of IndicConformer at ~130-190MB each. This is a real, proven deployment
  path - see e.g. the open-source "Uktam.ai" Android app, which already
  ships exactly this combination on real phones.

SPLIT USED HERE:
  - Vosk:          English, Hindi        (small, well-tested, already working)
  - IndicConformer: Gujarati, Marathi, Kannada, Malayalam, Tamil, Telugu,
                    Odia, Bengali         (via sherpa-onnx, INT8 quantized)

Both backends are real integrations, not stubs - each raises a clear,
actionable error if its model files aren't present locally, instead of
silently returning fake output. Neither backend's model weights are
bundled in this repo except the English Vosk model (already downloaded);
see MODEL SETUP below for how to get the rest.

MODEL SETUP
-----------
Vosk (English, Hindi):
    pip install vosk
    Download from https://alphacephei.com/vosk/models :
        vosk-model-small-en-us-0.15   (~40MB)  -> already bundled
        vosk-model-small-hi-0.22      (~42MB)
    Unzip each into itantra_ai/stt/models/<folder-name>/

IndicConformer via sherpa-onnx (Gujarati, Marathi, Kannada, Malayalam,
Tamil, Telugu, Odia, Bengali):
    pip install sherpa-onnx
    Download the INT8-quantized per-language ONNX pack for each language
    (encoder.int8.onnx / model.int8.onnx + tokens.txt) from a sherpa-onnx-
    format IndicConformer export on HuggingFace (search "indicconformer
    sherpa-onnx <language>"; several community-maintained exports exist,
    e.g. under the AI4Bharat / Next-Gen Kaldi ecosystem).
    Place each language's files into:
        itantra_ai/stt/models/indicconformer/<lang_code>/model.int8.onnx
        itantra_ai/stt/models/indicconformer/<lang_code>/tokens.txt
    lang_code uses ISO codes: gu, mr, kn, ml, ta, te, or, bn
"""

import os
import json
import wave
from typing import Optional, Any, List

MODELS_DIR = os.path.join(os.path.dirname(__file__), "models")
INDIC_MODELS_DIR = os.path.join(MODELS_DIR, "indicconformer")

# Which backend + model identifier handles each language.
LANGUAGE_ROUTING = {
    "en": ("vosk", "vosk-model-small-en-us-0.15"),
    "hi": ("vosk", "vosk-model-small-hi-0.22"),
    "gu": ("indicconformer", "gu"),
    "mr": ("indicconformer", "mr"),
    "kn": ("indicconformer", "kn"),
    "ml": ("indicconformer", "ml"),
    "ta": ("indicconformer", "ta"),
    "te": ("indicconformer", "te"),
    "or": ("indicconformer", "or"),
    "bn": ("indicconformer", "bn"),
}


def build_grammar_from_vocabulary() -> List[str]:
    """
    Auto-builds a closed-vocabulary grammar list for Vosk's constrained
    decoding, pulled directly from SemanticExtractor's known keyword
    tables. (IndicConformer/sherpa-onnx does not support grammar
    constraints the same way, so this only applies to the Vosk backend.)
    """
    from itantra_ai.semantic.semantic_extractor import SemanticExtractor

    words = set()
    for vocab in (SemanticExtractor.ACTIONS, SemanticExtractor.TEAMS,
                  SemanticExtractor.ACTORS, SemanticExtractor.OBJECTS,
                  SemanticExtractor.URGENCIES, SemanticExtractor.STATUSES):
        for phrase in vocab.keys():
            words.update(phrase.split())
    for phrase in SemanticExtractor.KNOWN_LOCATIONS.keys():
        words.update(phrase.split())

    words.update([
        "the", "to", "at", "a", "an", "and", "team", "from", "please",
        "now", "of", "with", "for",
    ])
    return sorted(words)


# ---------------------------------------------------------------------
# Backend 1: Vosk (English, Hindi)
# ---------------------------------------------------------------------
class _VoskBackend:
    def __init__(self, model_name: str, use_grammar: bool = True):
        self.model_name = model_name
        self.model_path = os.path.join(MODELS_DIR, model_name)
        self.use_grammar = use_grammar
        self._model = None
        self._grammar_json = None

    def load(self):
        try:
            from vosk import Model
        except ImportError:
            raise RuntimeError("Run: pip install vosk")
        if not os.path.isdir(self.model_path):
            raise FileNotFoundError(
                f"Vosk model not found at '{self.model_path}'.\n"
                f"Download from https://alphacephei.com/vosk/models and "
                f"unzip into {MODELS_DIR}/"
            )
        self._model = Model(self.model_path)
        if self.use_grammar:
            self._grammar_json = json.dumps(build_grammar_from_vocabulary())

    def transcribe(self, wav_path: str) -> str:
        from vosk import KaldiRecognizer
        wf = wave.open(wav_path, "rb")
        if wf.getnchannels() != 1 or wf.getsampwidth() != 2:
            raise ValueError("Audio must be 16-bit mono WAV.")

        if self.use_grammar and self._grammar_json:
            recognizer = KaldiRecognizer(self._model, wf.getframerate(), self._grammar_json)
        else:
            recognizer = KaldiRecognizer(self._model, wf.getframerate())
        recognizer.SetWords(True)

        results = []
        while True:
            data = wf.readframes(4000)
            if len(data) == 0:
                break
            if recognizer.AcceptWaveform(data):
                res = json.loads(recognizer.Result())
                if res.get("text"):
                    results.append(res["text"])
        final = json.loads(recognizer.FinalResult())
        if final.get("text"):
            results.append(final["text"])
        return " ".join(results).strip()


# ---------------------------------------------------------------------
# Backend 2: AI4Bharat IndicConformer via sherpa-onnx
# (Gujarati, Marathi, Kannada, Malayalam, Tamil, Telugu, Odia, Bengali)
# ---------------------------------------------------------------------
class _IndicConformerBackend:
    def __init__(self, lang_code: str):
        self.lang_code = lang_code
        self.lang_dir = os.path.join(INDIC_MODELS_DIR, lang_code)
        self._recognizer = None

    def load(self):
        try:
            import sherpa_onnx
        except ImportError:
            raise RuntimeError("Run: pip install sherpa-onnx")

        model_path = os.path.join(self.lang_dir, "model.int8.onnx")
        tokens_path = os.path.join(self.lang_dir, "tokens.txt")
        if not (os.path.isfile(model_path) and os.path.isfile(tokens_path)):
            raise FileNotFoundError(
                f"IndicConformer model for language '{self.lang_code}' not found "
                f"at '{self.lang_dir}'.\n"
                f"Expected files: model.int8.onnx, tokens.txt\n"
                f"Download an INT8-quantized sherpa-onnx export of AI4Bharat "
                f"IndicConformer for this language and place both files there."
            )

        # CTC-style offline recognizer - matches how these community ONNX
        # exports of IndicConformer are typically packaged.
        self._recognizer = sherpa_onnx.OfflineRecognizer.from_nemo_ctc(
            model=model_path,
            tokens=tokens_path,
            num_threads=2,
            decoding_method="greedy_search",
        )

    def transcribe(self, wav_path: str) -> str:
        import sherpa_onnx
        wf = wave.open(wav_path, "rb")
        if wf.getnchannels() != 1 or wf.getsampwidth() != 2:
            raise ValueError("Audio must be 16-bit mono WAV.")

        num_frames = wf.getnframes()
        raw = wf.readframes(num_frames)
        import array
        samples = array.array("h", raw)
        # sherpa-onnx expects float32 samples in [-1, 1]
        float_samples = [s / 32768.0 for s in samples]

        stream = self._recognizer.create_stream()
        stream.accept_waveform(wf.getframerate(), float_samples)
        self._recognizer.decode_stream(stream)
        return stream.result.text.strip()


# ---------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------
class STTEngine:
    """
    Usage:
        engine = STTEngine(language="hi")   # routes to Vosk
        engine = STTEngine(language="ta")   # routes to IndicConformer/sherpa-onnx
        text = engine.transcribe_audio("path/to/audio.wav")

    Passing plain text (not a real file path) instead of an audio file makes
    this a no-op passthrough, so the rest of the pipeline (semantic
    extraction, priority tagging, compression) stays demoable from typed
    text without requiring any model to be downloaded.
    """

    def __init__(self, language: str = "en", use_grammar: bool = True):
        if language not in LANGUAGE_ROUTING:
            raise ValueError(
                f"Unsupported language '{language}'. Supported: "
                f"{sorted(LANGUAGE_ROUTING.keys())}"
            )
        self.language = language
        backend_type, model_id = LANGUAGE_ROUTING[language]
        self.backend_type = backend_type

        if backend_type == "vosk":
            self._backend = _VoskBackend(model_id, use_grammar=use_grammar and language == "en")
        else:
            self._backend = _IndicConformerBackend(model_id)

        self.is_loaded = False

    def load_model(self):
        from itantra_ai import model_packs
        model_packs.ensure("stt", self.language)     # unzip the language pack if needed
        self._backend.load()
        self.is_loaded = True
        return True

    def transcribe_audio(self, audio_path_or_stream: Any) -> str:
        if not isinstance(audio_path_or_stream, str) or not os.path.isfile(audio_path_or_stream):
            return str(audio_path_or_stream)  # text passthrough for the demo path

        if not self.is_loaded:
            self.load_model()

        return self._backend.transcribe(audio_path_or_stream)


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python3 stt_engine.py <path-to-16khz-mono-wav> [language_code]")
        print(f"Supported languages: {sorted(LANGUAGE_ROUTING.keys())}")
        sys.exit(0)

    lang = sys.argv[2] if len(sys.argv) > 2 else "en"
    engine = STTEngine(language=lang)
    try:
        print("Transcribed text:", engine.transcribe_audio(sys.argv[1]))
    except (FileNotFoundError, RuntimeError, ValueError) as e:
        print(f"Could not transcribe: {e}")
