# Vosk Model Folder

This folder is intentionally empty in the repo (model weights are too large
to bundle, and can't be auto-downloaded in a network-restricted environment).

## To enable real offline speech-to-text:

1. `pip install vosk`
2. Download a small model from https://alphacephei.com/vosk/models
   - Hindi: `vosk-model-small-hi-0.22` (~42 MB)
   - English: `vosk-model-small-en-us-0.15` (~40 MB)
3. Unzip it directly into this folder, so you end up with:
   `itantra_ai/stt/models/vosk-model-small-hi-0.22/`
4. Test it:
   `python3 itantra_ai/stt/stt_engine.py path/to/some_16khz_mono.wav`

Once the model folder is present, `STTEngine().transcribe_audio(path)` will
transcribe real audio - no code changes needed.
