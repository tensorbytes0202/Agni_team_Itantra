# itantra_ai/tts — Offline TTS (10 languages)

Runtime: sherpa-onnx (already installed for STT). No internet after the one-time download.

| Language | Voice | Size | Source / license |
|---|---|---|---|
| English | Piper en_US lessac (medium) | ~61 MB + 19 MB phonemizer data | sherpa-onnx releases |
| Hindi | Piper hi_IN priyamvada (medium) | ~61 MB + 19 MB | sherpa-onnx releases |
| Malayalam | Piper ml_IN meera (medium) | ~61 MB + 19 MB | sherpa-onnx releases |
| Tamil, Telugu, Kannada, Gujarati, Marathi, Bengali, Odia | Meta MMS-TTS (VITS) | ~114 MB each | HF willwade/mms-tts-multilingual-models-onnx, **CC-BY-NC-4.0** |

Measured (laptop, Hindi Piper): load 0.9 s, ~90 MB RAM, RTF ~0.15 (2 s of speech in ~0.3 s).
At most 2 voices stay loaded (current language + English).

## Download voices (one time, needs internet)

    set HF_HOME=D:\hf_cache
    python -m itantra_ai.tts.download_models en hi ml
    python -m itantra_ai.tts.download_models ta te kn gu mr bn or

## Quick check

    python -c "from itantra_ai.tts.tts_engine import TTSEngine; import sounddevice as sd; s,sr,t=TTSEngine().synthesize('मदद भेजो','hi'); print(t); sd.play(s,sr); sd.wait()"

## Notes
- MMS voices have not been tested in this build environment (HuggingFace not reachable here). If a language plays silence or garbled audio, that voice may need romanised input; report it.
- MMS license is non-commercial. For commercial use swap in AI4Bharat Indic-TTS or permissively licensed voices; the engine only needs model.onnx + tokens.txt.
- Android: play alerts on the ALARM stream with audio focus so they are loud even if media volume is low.
