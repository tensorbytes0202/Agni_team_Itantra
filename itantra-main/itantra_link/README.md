# itantra_link — Transmission layer (Radio Manager)

Copy this `itantra_link` folder into `SIH_iTantra/` (next to `itantra_ai/`).
No new pip packages needed (standard library only; reuses itantra_ai modules).

## What is real and what is emulated

| Part | Status |
|---|---|
| WiFi link | REAL UDP over your local network |
| Low-bitrate link | EMULATED (600 bps default, packet loss, bit errors). Same interface will drive a LoRa radio later |
| Bluetooth | Not yet (next task, same interface) |
| Packet format, CRC, ACK/retry, failover, store-and-forward | Real |
| Probing (PER, RTT), hysteresis switching | Real |
| Link-adaptive format (full / zlib / summary+FEC) | Real |
| Alert detection (10 languages, keyword based) | Real |
| Location sharing + distance/direction at receiver | Real (laptop: `--lat/--lon` or `/loc`; phone: GPS, works offline) |
| TTS playback | Real, offline (sherpa-onnx: Piper en/hi/ml, MMS for other Indic). Alerts: siren + full scale, not interruptible |

## Run the automated tests (~1.5 min)

    python -m itantra_link.tests.test_link
    python -m itantra_ai.tests.test_model_packs

Expect 10 x PASS and 9 x PASS.

## Desktop app (everything in one window) — use this for the demo

    laptop 1:  python -m itantra_link.app --role sender   --lat 28.669156 --lon 77.453758
    laptop 2:  python -m itantra_link.app --role receiver --lat 28.66 --lon 77.44

- Same WiFi: the two apps find each other automatically (UDP hello on ports 5901/5902) and show
  "● connected to …". Until then messages wait in the queue. If the WiFi blocks broadcast, type the
  other laptop's IP in **Peer IP**. Both commands also work on one laptop.
- **Channel conditions** card (EMULATED, copied to the other laptop): WiFi interference
  Clean/Noisy/Bad/Dead, radio frequency 865.06–866.95 MHz, noise per frequency Clean/Noisy/Bad/Jammed.
  Bad WiFi -> failover to radio; jammed frequency -> queue; switch frequency -> queued message delivered.
  Test: `python -m itantra_link.tests.test_channel`.

- **Language buttons**: click one -> its zip in `language_packs/` is unzipped, the STT model is loaded
  (the old one is freed first). Green = unzipped, blue = only in zip, grey = no model.
- "Save disk" (on by default): after switching, other unzipped languages are deleted again
  (only if their zip is verified). Turn off with `--keep-unzipped`.
- **HOLD TO TALK**: press and hold, speak, release -> STT -> sent. "Hands-free" sends on each pause.
- Typed text box, WiFi / low-bitrate switches, loss / BER, location — same as the terminal commands.
- Received messages appear (alerts in red) and are spoken; the voice for that language is unzipped on first use.

## Language packs (smaller prototype)

All models are stored as LZMA zips in `SIH_iTantra/language_packs/` (`stt-<lang>.zip`, `tts-<lang>.zip`)
and unzipped only when needed.

    python -m itantra_ai.model_packs status          # zipped / unzipped per language, total sizes
    python -m itantra_ai.model_packs build           # zip every unzipped model (keeps the originals)
    python -m itantra_ai.model_packs prune           # delete all unzipped models that have a good zip
    python -m itantra_ai.model_packs prune hi en     # same, but keep hi and en unzipped
    python -m itantra_ai.model_packs extract ta      # unzip a language by hand

`STTEngine.load_model()` and `TTSEngine` unzip automatically, so the terminal nodes also work with only zips.
New TTS voices from `download_models` are zipped automatically.

## Demo on ONE laptop (two terminals)

Terminal 1 (receiver, rescue team):

    python -m itantra_link.node --name B --wifi-port 5002 --peer-wifi-port 5001 --lb-port 6002 --peer-lb-port 6001 --lat 28.6600 --lon 77.4400

Terminal 2 (sender, person needing help):

    python -m itantra_link.node --name A --wifi-port 5001 --peer-wifi-port 5002 --lb-port 6001 --peer-lb-port 6002 --lat 28.669156 --lon 77.453758

Receiver shows e.g. `LOCATION: 28.66915, 77.45374 (1.68 km NE)`.

## Demo on TWO laptops (same WiFi)

1. Find each laptop's IP: `ipconfig` -> "IPv4 Address".
2. Windows may show a firewall popup the first time: click **Allow** (private network).
3. On both laptops use the same ports, and point `--peer-ip` at the other laptop:

       python -m itantra_link.node --name A --peer-ip <other-IP> --wifi-port 5001 --peer-wifi-port 5001 --lb-port 6001 --peer-lb-port 6001

Add `--verbose` to any node to print every CRC-dropped packet.

## Commands inside a node

| Command | Effect |
|---|---|
| any text | send it |
| `/lang hi` | set language (en hi gu mr kn ml ta te or bn) |
| `/wifi off` / `/wifi on` | WiFi kill switch (forces fallback to low-bitrate) |
| `/lb off` / `/lb on` | low-bitrate kill switch |
| `/loss 0.3` | set low-bitrate packet loss |
| `/ber 0.0005` | set low-bitrate bit error rate (corrupt packets are dropped by CRC and counted in `/status`) |
| `/loc 28.66 77.45` | set own location (phone: from GPS) |
| `/status` | link health (PER, RTT, active channel) |
| `/quit` | exit |

## 60-second video demo

1. `/status` -> active=WIFI. Send a Hindi sentence -> arrives instantly.
2. `/wifi off` on sender -> within ~4 s log shows `failover: WIFI -> LOWBITRATE`.
3. Send `emergency, madad bhejo` -> receiver first shows ALERT SUMMARY "EMERGENCY - SEND HELP", then full text.
4. `/wifi on` -> after ~10-16 s log shows `switch: LOWBITRATE -> WIFI`.

Say in the video: "The low-bitrate link is emulated at 600 bps with packet loss; the same code will drive a LoRa radio."

## Voice mode (STT connected)

`voice_node.py` = microphone -> STT -> Radio Manager. Needs `sounddevice`
(`python -m pip install sounddevice`) and the STT models from itantra_ai.

Sender (speaks):

    python -m itantra_link.voice_node --name A --lang hi --wifi-port 5001 --peer-wifi-port 5002 --lb-port 6001 --peer-lb-port 6002 --lat 28.669156 --lon 77.453758

Receiver:

    python -m itantra_link.node --name B --wifi-port 5002 --peer-wifi-port 5001 --lb-port 6002 --peer-lb-port 6001 --lat 28.66 --lon 77.44

| In voice_node | Effect |
|---|---|
| press Enter | push-to-talk: speak, press Enter again to send |
| `/auto on` / `/auto off` | hands-free: each sentence is sent automatically after an 0.8 s pause |
| `/file x.wav` | transcribe a 16 kHz mono WAV and send |
| `/lang ta` | switch STT language (old model is unloaded first) |

Each utterance prints STT time and RTF (Real Time Factor), which the PS scores.
Tested: English speech file -> "send medical team north checkpoint", STT 113 ms, RTF 0.03.

## TTS on the receiver

Any node now speaks what it receives. First download voices (see `itantra_ai/tts/README.md`):

    python -m itantra_ai.tts.download_models en hi ml

- Voice is picked from the script of the text (Devanagari -> Hindi voice, Tamil script -> Tamil voice...), so a wrong language tag cannot make an English voice read Hindi.
- Low-bitrate alert SUMMARY is spoken in Hindi (for Hindi messages) or English, with distance and direction:
  "आपातकाल. मदद भेजें. 1.7 किलोमीटर उत्तर पूर्व." / "Emergency. Send help. 1.7 kilometres north east."
- Alerts: two-tone siren, then the message at full scale; interrupts normal playback and cannot itself be interrupted.
- `--no-tts` prints instead of speaking; `--save-wav folder` writes WAV files instead of playing.
- Each spoken message prints synth time and RTF.

Verified: received English audio fed back into our own STT was recognised correctly
("emergency send help one point seven kilometers northeast").

## Plugging in STT and TTS

- STT side: after `STTEngine(language=lang).transcribe_audio(wav)`, call
  `radio_manager.send_message(text, lang)`.
- Location: on Android call `radio_manager.set_location(lat, lon)` from the GPS
  provider (`LocationManager.GPS_PROVIDER` works without internet; use last
  known fix if indoors). The `geo:lat,lon` string opens in any offline map app.
- TTS side: replace `tts_play()` in `node.py`. Use `msg.lang` for the voice and
  `msg.alert` for max-volume, non-interruptible playback.

## Key numbers in this build

| Setting | Value |
|---|---|
| Probe interval | 2 s |
| WiFi healthy if | PER < 10 %, RTT < 300 ms (last 5 probes) |
| Switch to better link | after 3 consecutive wins |
| ACK timeout | WiFi 0.5 s, low-bitrate = 2 x airtime + 1 s |
| Retries | 2, then fail over to next link |
| Full header | 16 B + CRC32 |
| Compact header (low-bitrate) | 5 B + CRC16 |
| Summary payload | 1 byte -> Hamming(7,4) -> 2 bytes (no location) |
| Summary + location | 6 bytes -> Hamming(7,4) -> 11 bytes |
| Location, WiFi/BT | float32 lat/lon, 8 bytes, worldwide |
| Location, low-bitrate | 20+20 bits in India bounding box, 5 bytes, ~2 m error |

## Files

| File | Purpose |
|---|---|
| packet.py | Packet format, CRC, full + compact encoding |
| transports.py | Real WiFi UDP, emulated low-bitrate link |
| summary.py | Alert detection (10 languages) + critical summary (+ location) with FEC |
| location.py | Location encoding (full / compact) + distance & direction |
| radio_manager.py | Probing, selection, hysteresis, failover, ACK/retry, queue, adaptive format |
| app.py | Desktop app: role, language buttons, hold-to-talk, links, channel conditions, received messages + TTS |
| channel_lab.py | Auto-discovery of the other laptop + EMULATED channel conditions (interference, frequency, noise) |
| node.py | Interactive text node for demos (receiver side) |
| voice_node.py | Mic -> STT -> Radio Manager (push-to-talk + auto pause detection) |
| speaker.py | Receiver TTS worker: voice choice, alert priority, spoken summaries with distance |
| tests/test_link.py | Acceptance tests |
