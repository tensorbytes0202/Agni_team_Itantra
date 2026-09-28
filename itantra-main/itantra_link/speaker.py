"""
Receiver-side speech: turns received messages into audio (TTS) and plays them
with alert rules. Runs in its own thread so network receiving never waits on TTS.

SUMMARY packets (critical alert on the low-bitrate link) arrive as a short code,
not a sentence. They are spoken in Hindi if the message language is Hindi,
otherwise in English, together with distance and direction when both
locations are known, e.g. "Emergency. Send help. 1.7 kilometres north east."
"""
import queue
import threading
import time

from itantra_ai.tts.player import AudioPlayer
from itantra_ai.tts.tts_engine import TTSEngine

from . import location as L

HI_HEAD = {"EMERGENCY": "आपातकाल", "URGENT": "तुरंत", "INFO": "सूचना"}
HI_PHRASE = {"SEND HELP": "मदद भेजें", "SEND SUPPORT": "सहायता भेजें", "EVACUATE": "जगह खाली करें",
             "DEPLOY TEAM": "टीम भेजें", "STOP / HALT": "रुकें", "SECURE AREA": "इलाका सुरक्षित करें",
             "REPORT STATUS": "स्थिति बताएं"}
EN_DIR = {"N": "north", "NE": "north east", "E": "east", "SE": "south east",
          "S": "south", "SW": "south west", "W": "west", "NW": "north west"}
HI_DIR = {"N": "उत्तर", "NE": "उत्तर पूर्व", "E": "पूर्व", "SE": "दक्षिण पूर्व",
          "S": "दक्षिण", "SW": "दक्षिण पश्चिम", "W": "पश्चिम", "NW": "उत्तर पश्चिम"}


# Unicode block -> language. Devanagari is shared by Hindi and Marathi, so the
# message's own tag decides between those two.
SCRIPTS = [((0x0900, 0x097F), "hi"), ((0x0980, 0x09FF), "bn"), ((0x0A80, 0x0AFF), "gu"),
           ((0x0B00, 0x0B7F), "or"), ((0x0B80, 0x0BFF), "ta"), ((0x0C00, 0x0C7F), "te"),
           ((0x0C80, 0x0CFF), "kn"), ((0x0D00, 0x0D7F), "ml")]


def voice_for_text(text: str, tagged: str) -> str:
    """Pick the TTS voice from the script actually used in the text, so a wrong
    language tag can never make e.g. an English voice read Devanagari."""
    counts = {}
    for ch in text:
        cp = ord(ch)
        for (lo, hi), lang in SCRIPTS:
            if lo <= cp <= hi:
                counts[lang] = counts.get(lang, 0) + 1
                break
    if not counts:
        return "en" if tagged not in ("en",) and text.isascii() else tagged
    lang = max(counts, key=counts.get)
    if lang == "hi" and tagged == "mr":
        return "mr"
    return lang


class Speaker:
    def __init__(self, get_own_location, save_dir=None, log=None):
        self.engine = TTSEngine(max_loaded=2)
        self.player = AudioPlayer(save_dir=save_dir)
        self.own = get_own_location
        self.log = log or (lambda s: print(f"\n{s}\n> ", end="", flush=True))
        self._q = queue.PriorityQueue()
        self._n = 0
        threading.Thread(target=self._loop, daemon=True).start()

    def say(self, msg):
        self._n += 1
        self._q.put((0 if msg.alert else 1, self._n, msg))

    def _spoken(self, msg):
        """Return (text_to_speak, voice_lang)."""
        if msg.kind != "SUMMARY":
            return msg.text, voice_for_text(msg.text, msg.lang)
        voice = "hi" if msg.lang == "hi" and self.engine.available("hi") else "en"
        parts = [p.strip() for p in msg.text.split(" - ")]
        where = ""
        own = self.own()
        if msg.location and own:
            d, dirn = L.distance_bearing(own, msg.location)
            km = f"{d/1000:.1f}"
            where = (f"{km} किलोमीटर {HI_DIR[dirn]}" if voice == "hi"
                     else f"{km} kilometres {EN_DIR[dirn]}")
        if voice == "hi":
            parts = [HI_HEAD.get(p, HI_PHRASE.get(p, p)) for p in parts]
        return ". ".join(parts + ([where] if where else [])) + ".", voice

    def _loop(self):
        while True:
            _, n, msg = self._q.get()
            text, voice = self._spoken(msg)
            if not self.engine.available(voice):
                self.log(f"[tts] no voice installed for '{voice}' "
                         f"(python -m itantra_ai.tts.download_models {voice})")
                continue
            try:
                samples, sr, synth_s = self.engine.synthesize(text, voice)
            except Exception as e:
                self.log(f"[tts] error: {e}")
                continue
            dur = len(samples) / sr
            self.log(f"[tts:{voice}] \"{text}\"  synth={synth_s*1000:.0f}ms  audio={dur:.1f}s  "
                     f"RTF={synth_s/dur:.2f}{'  ALERT' if msg.alert else ''}")
            self.player.play(samples, sr, msg.alert, label=voice)
