"""
Download offline TTS voices (one time; after that everything runs offline).

    python -m itantra_ai.tts.download_models en hi ml          # Piper voices (GitHub)
    python -m itantra_ai.tts.download_models ta te kn gu mr bn or   # MMS voices (HuggingFace)
    python -m itantra_ai.tts.download_models all
Set HF_HOME to a drive with space before running (e.g. set HF_HOME=D:\\hf_cache).
"""
import os
import shutil
import sys
import tarfile
import urllib.request

from .tts_engine import MODELS_DIR, VOICES

PIPER_URL = "https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/{}.tar.bz2"
MMS_REPO = "willwade/mms-tts-multilingual-models-onnx"


def get(lang: str):
    kind, folder, onnx = VOICES[lang]
    target = os.path.join(MODELS_DIR, folder)
    from itantra_ai import model_packs
    if model_packs.available("tts", lang):
        print(f"[{lang}] already present"); return
    os.makedirs(MODELS_DIR, exist_ok=True)
    if kind == "piper":
        url = PIPER_URL.format(folder)
        tmp = os.path.join(MODELS_DIR, folder + ".tar.bz2")
        print(f"[{lang}] downloading {url}")
        urllib.request.urlretrieve(url, tmp)
        with tarfile.open(tmp, "r:bz2") as tf:
            tf.extractall(MODELS_DIR)
        os.remove(tmp)
    else:
        from huggingface_hub import hf_hub_download
        iso = folder.split("/")[1]
        os.makedirs(target, exist_ok=True)
        for f in ("model.onnx", "tokens.txt"):
            print(f"[{lang}] downloading {MMS_REPO}/{iso}/{f}")
            p = hf_hub_download(MMS_REPO, f"{iso}/{f}")
            shutil.copy(p, os.path.join(target, f))
    print(f"[{lang}] OK -> {target}")
    from itantra_ai import model_packs
    model_packs.build("tts", lang)                     # also store it as a language pack zip


if __name__ == "__main__":
    langs = sys.argv[1:] or ["en", "hi"]
    if langs == ["all"]:
        langs = list(VOICES)
    for l in langs:
        try:
            get(l)
        except Exception as e:
            print(f"[{l}] FAILED: {e}")
