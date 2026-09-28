# iTantra — offline multilingual STT ↔ radio ↔ TTS (SIH PS 26173, Team Agni)

Speak in one of 10 Indian languages → offline speech-to-text → sent as text over WiFi or a
low-bitrate radio link (with alerts, FEC summary and location) → offline text-to-speech on the receiver.
Everything runs offline with open-source models. This repo is the laptop prototype; the Android app
follows the same design.

## Setup (Windows)

```
python -m venv venv
venv\Scripts\activate.bat
python -m pip install -r requirements.txt
chcp 65001
```

## Models (not in git — too large)

Models are kept as LZMA zips in `language_packs/` (`stt-<lang>.zip`, `tts-<lang>.zip`, ~900 MB total)
and unzipped automatically when a language is selected. Get them from the team drive / release and put
them in `language_packs/`, or download the originals:

| Part | Languages | Source |
|---|---|---|
| STT Vosk | en, hi | https://alphacephei.com/vosk/models (`vosk-model-small-en-us-0.15`, `vosk-model-small-hi-0.22`) → `itantra_ai/stt/models/` |
| STT IndicConformer INT8 | gu mr kn ml ta te bn | HF `mobilebytesensei/betterflow-indicconformer-ctc` → `itantra_ai/stt/models/indicconformer/<lang>/` |
| TTS | all | `python -m itantra_ai.tts.download_models en hi ml` (Piper) / `ta te kn gu mr bn or` (MMS, CC-BY-NC) |

Then `python -m itantra_ai.model_packs build` makes the zips and `... prune` removes the unzipped copies.
Odia STT is not available yet.

## Run

```
python -m itantra_link.app --role sender   --lat 28.669156 --lon 77.453758
python -m itantra_link.app --role receiver --lat 28.66 --lon 77.44
```

Same WiFi: the two apps find each other automatically. Otherwise add `--peer-ip <other IP>`.
Details: [itantra_link/README.md](itantra_link/README.md). Manual test steps: [TEST_PLAN.md](TEST_PLAN.md).

## Tests

```
python -m itantra_link.tests.test_link        # 10 transmission tests
python -m itantra_link.tests.test_channel     # 9 channel lab tests
python -m itantra_ai.tests.test_model_packs   # 9 language pack tests
```

## Real vs emulated

WiFi transmission, STT (9 languages), TTS (en/hi/ml tested), alerts, location logic: real.
Low-bitrate radio and channel conditions: **emulated** (LoRa-ready interface). Bluetooth: not yet.
