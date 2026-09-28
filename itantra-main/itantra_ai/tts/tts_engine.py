"""
Offline Text-to-Speech for the 10 PS languages, via sherpa-onnx (same runtime as STT).

    Piper (VITS)     : en, hi, ml      natural voices, ~61 MB model each, espeak-ng phonemizer bundled
    Meta MMS (VITS)  : ta, te, kn, gu, mr, bn, or   ~114 MB each, character input

Measured on laptop (Piper hi): load 0.9 s, ~90 MB RAM, synth 290 ms for 2.1 s audio (RTF 0.14).

Memory: keeps at most `max_loaded` models (default 2: the current language +
English, which is the fallback voice for alert summaries).

LICENSE NOTE: MMS-TTS weights are CC-BY-NC-4.0 (non-commercial). Fine for the
hackathon; for commercial deployment replace with AI4Bharat Indic-TTS or
Piper voices with permissive licenses.

Get models:  python -m itantra_ai.tts.download_models en hi ml ta te kn gu mr bn or
"""
import collections
import os
import time
from typing import Tuple

import numpy as np

MODELS_DIR = os.path.join(os.path.dirname(__file__), "models")

# lang -> (kind, folder, onnx filename)
VOICES = {
    "en": ("piper", "vits-piper-en_US-lessac-medium", "en_US-lessac-medium.onnx"),
    "hi": ("piper", "vits-piper-hi_IN-priyamvada-medium", "hi_IN-priyamvada-medium.onnx"),
    "ml": ("piper", "vits-piper-ml_IN-meera-medium", "ml_IN-meera-medium.onnx"),
    "ta": ("mms", "mms/tam", "model.onnx"),
    "te": ("mms", "mms/tel", "model.onnx"),
    "kn": ("mms", "mms/kan", "model.onnx"),
    "gu": ("mms", "mms/guj", "model.onnx"),
    "mr": ("mms", "mms/mar", "model.onnx"),
    "bn": ("mms", "mms/ben", "model.onnx"),
    "or": ("mms", "mms/ory", "model.onnx"),
}


class TTSEngine:
    def __init__(self, max_loaded: int = 2, num_threads: int = 2):
        self.max_loaded = max_loaded
        self.num_threads = num_threads
        self._loaded = collections.OrderedDict()     # lang -> OfflineTts (LRU)

    def available(self, lang: str) -> bool:
        """True if the voice is unzipped or its language pack zip exists."""
        from itantra_ai import model_packs
        return lang in VOICES and model_packs.available("tts", lang)

    def _load(self, lang: str):
        import sherpa_onnx
        from itantra_ai import model_packs
        if lang in self._loaded:
            self._loaded.move_to_end(lang)
            return self._loaded[lang]
        if not model_packs.ensure("tts", lang):          # unzip the language pack if needed
            raise FileNotFoundError(
                f"TTS voice for '{lang}' not found in {MODELS_DIR}. "
                f"Run: python -m itantra_ai.tts.download_models {lang}")
        kind, folder, onnx = VOICES[lang]
        d = os.path.join(MODELS_DIR, folder)
        vits = sherpa_onnx.OfflineTtsVitsModelConfig(
            model=os.path.join(d, onnx),
            tokens=os.path.join(d, "tokens.txt"),
            data_dir=os.path.join(d, "espeak-ng-data") if kind == "piper" else "",
        )
        cfg = sherpa_onnx.OfflineTtsConfig(
            model=sherpa_onnx.OfflineTtsModelConfig(vits=vits, num_threads=self.num_threads,
                                                    provider="cpu"),
            max_num_sentences=1,
        )
        while len(self._loaded) >= self.max_loaded:   # free the least recently used first
            self._loaded.popitem(last=False)
        tts = sherpa_onnx.OfflineTts(cfg)
        self._loaded[lang] = tts
        return tts

    def synthesize(self, text: str, lang: str, speed: float = 1.0) -> Tuple[np.ndarray, int, float]:
        """Returns (float32 samples in [-1,1], sample_rate, synthesis_seconds)."""
        tts = self._load(lang)
        t = time.time()
        audio = tts.generate(text, sid=0, speed=speed)
        return np.asarray(audio.samples, dtype=np.float32), audio.sample_rate, time.time() - t
