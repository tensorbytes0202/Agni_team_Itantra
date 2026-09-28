# iTantra — manual test plan

Tick each box. Write the number you see in the "Note" column so it can go straight into the slides.

## 0. Setup (every new terminal)

```
cd /d D:\itantra_10lang\SIH_iTantra
venv\Scripts\activate.bat
chcp 65001
set HF_HOME=D:\hf_cache
set TMP=D:\tmp
set TEMP=D:\tmp
```

Use **headphones** when both windows run on one laptop (otherwise the mic hears the other window's voice).

## 1. Automatic tests (2 minutes)

| # | Do | Expected | ✓ | Note |
|---|---|---|---|---|
| 1.1 | `python -m itantra_ai.tests.test_model_packs` | `9/9 passed` | | |
| 1.2 | `python -m itantra_link.tests.test_link` | 10 × PASS | | |
| 1.2b | `python -m itantra_link.tests.test_channel` | `9/9 passed` (~1.5 min) | | |
| 1.3 | `python -m itantra_ai.model_packs status` | table of 10 languages; en/hi/ml STT+TTS, 6 Indic STT, Odia missing | | zips MB = |

## 2. Language packs (zip → unzip on click)

Start with everything zipped: `python -m itantra_ai.model_packs prune` → "unzipped models: 0 MB".

| # | Do | Expected | ✓ | Note |
|---|---|---|---|---|
| 2.1 | `python -m itantra_link.app --role sender --lat 28.669156 --lon 77.453758` | Window opens; all tiles blue ("in zip"), Odia grey | | |
| 2.2 | Click **हिन्दी** | Log: "unzipping stt-hi.zip…", then "✓ Hindi speech model loaded in X s (unzip Y s)"; tile turns green with orange border | | unzip s = , total s = |
| 2.3 | Click **தமிழ்** | Tamil unzips + loads; Hindi tile goes back to blue ("freed … MB") | | unzip s = |
| 2.4 | Click **ଓଡ଼ିଆ** | Red line "No speech model for Odia yet" — nothing crashes | | |
| 2.5 | Untick "Save disk", click another language | Previous language stays green | | |
| 2.6 | Close app, run `python -m itantra_ai.model_packs status` | Only the languages you used are "ready" | | |
| 2.7 | Task Manager → python.exe memory after loading one Indic language, then after switching 3 times | Memory does not keep growing (one STT model at a time) | | RAM MB = |

## 3. Speech-to-text per language (SENDER window)

Hold **HOLD TO TALK**, speak, release. Check the green bubble text and the "STT … ms, RTF …" line.

| # | Language | Say | Expected text | ✓ | STT ms / RTF |
|---|---|---|---|---|---|
| 3.1 | English | "send medical team north checkpoint" | same words | | |
| 3.2 | Hindi | "मदद भेजो" | मदद भेजो (watch for "मत भेजो") | | |
| 3.3 | Tamil | வணக்கம் | வணக்கம் | | |
| 3.4 | Malayalam | നന്ദി | നന്ദി / നന്നി | | |
| 3.5 | Kannada | ನಮಸ್ಕಾರ | ನಮಸ್ಕಾರ | | |
| 3.6 | Gujarati | નમસ્તે | નમસ્તે | | |
| 3.7 | Marathi | नमस्कार | नमस्कार | | |
| 3.8 | Telugu | నమస్కారం | నమస్కారం | | |
| 3.9 | Bengali | নমস্কার | নমস্কার | | |
| 3.10 | any | tap the button very quickly (< 0.3 s) | "too short, ignored" | | |
| 3.11 | Tamil | hold button in silence for 2 s | ideally "no speech recognized"; note if it outputs "ஆ" | | |
| 3.12 | Hindi | tick **Hands-free**, speak 2 sentences with a pause | each sentence sent by itself after the pause | | |

## 4. Two windows: send → receive → speak

Receiver: `python -m itantra_link.app --role receiver --lat 28.66 --lon 77.44`
Wait until **both** headers show "● connected to …" and `ACTIVE LINK: WIFI` (can take ~10 s).

| # | Do (in SENDER) | Expected in RECEIVER | ✓ | Note |
|---|---|---|---|---|
| 4.1 | Type `team reached north checkpoint`, Send | Blue bubble, "via WIFI", latency ms, 📍 "1.68 km NE"; spoken in English | | latency ms = |
| 4.2 | Hindi PTT: "आग लगी है मदद भेजो" | RED ALERT bubble, siren, then Hindi voice at full volume | | synth ms / RTF = |
| 4.3 | While B speaks a long normal message, send an alert | Alert interrupts; the alert itself is never cut | | |
| 4.4 | Type Tamil text `வணக்கம்` | B unzips Tamil voice ("unzipping Tamil voice…"), speaks it (MMS voice — only if installed, else "no voice installed") | | |
| 4.5 | Type Malayalam text `നന്ദി` | Malayalam Piper voice | | |

## 5. Bad channel demo (Channel conditions card, EMULATED, synced to both laptops)

| # | Do (in SENDER) | Expected | ✓ | Note |
|---|---|---|---|---|
| 5.1 | WiFi interference **Noisy** | Stays on WIFI, messages still arrive (some retries) | | |
| 5.2 | WiFi interference **Bad** | Within ~5 s header turns orange `LOWBITRATE`; RECEIVER card also shows Bad ("changed on the other laptop") | | seconds = |
| 5.3 | WiFi **Dead**, type `emergency madad bhejo` | RECEIVER: red "EMERGENCY - SEND HELP" summary + 📍 first, then full text | | summary bytes = |
| 5.4 | Noise on this freq. **Bad** | Still delivered (retries, CRC-drop counter rises) | | CRC-drop = |
| 5.5 | Noise **Jammed**, send `second floor blocked` | Header red "NONE (queueing)"; nothing arrives; 865.06 MHz turns red | | |
| 5.6 | Click a green frequency, e.g. **865.99 MHz** | Both laptops retune; queued message arrives within ~10 s | | seconds = |
| 5.7 | WiFi **Clean** | Back to green WIFI after ~3 checks | | seconds = |
| 5.8 | Close RECEIVER window, send a message | SENDER: "RECEIVER not heard…"; message waits. Reopen RECEIVER → it is delivered | | |

## 6. Two laptops (real WiFi)

1. Both laptops on the **same WiFi / phone hotspot**.
2. Laptop 1: `python -m itantra_link.app --role sender --lat 28.669156 --lon 77.453758`
3. Laptop 2: `python -m itantra_link.app --role receiver --lat 28.66 --lon 77.44`
4. First run: Windows firewall pop-up → tick **Private and Public** → **Allow**.
5. Header should show "● connected to RECEIVER '<laptop name>' (<IP>)" within ~2 s.
   If it keeps saying "searching": run `ipconfig` on the other laptop, type its IPv4 in **Peer IP** → **Connect**.
6. Repeat section 4 and 5. For the video, turn off mobile data on the hotspot phone to show it is fully offline.
## 7. Known limits to write down honestly

- Low-bitrate link is emulated (600 bps, loss, bit errors).
- Odia STT is missing; MMS voices (ta te kn gu mr bn or) are not downloaded yet — run `python -m itantra_ai.tts.download_models ta te kn gu mr bn or` and repeat 4.4.
- Bluetooth not implemented.
- Sender header can briefly show LOWBITRATE right after loading a model (the model load pauses the network checks for a moment).
