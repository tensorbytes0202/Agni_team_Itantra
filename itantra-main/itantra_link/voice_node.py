"""
Voice node = STT + Radio Manager in one program.

    speak -> record (push-to-talk OR automatic pause detection)
          -> STTEngine (Vosk / IndicConformer, offline)
          -> RadioManager.send_message(text, lang)   (WiFi / low-bitrate, location, alerts)

The receiving side can be a normal `itantra_link.node` or another voice_node.

One laptop, two terminals:
  python -m itantra_link.voice_node --name A --lang hi --wifi-port 5001 --peer-wifi-port 5002 --lb-port 6001 --peer-lb-port 6002 --lat 28.669156 --lon 77.453758
  python -m itantra_link.node       --name B          --wifi-port 5002 --peer-wifi-port 5001 --lb-port 6002 --peer-lb-port 6001 --lat 28.66 --lon 77.44

Commands:
  (just press Enter)  PUSH-TO-TALK: starts recording, press Enter again to stop and send
  /auto on|off        hands-free mode: sends each sentence automatically when you pause
  /file x.wav         transcribe a 16 kHz mono WAV file and send it
  /lang ta            switch STT language (unloads old model, loads new one)
  any other text      sent as typed text (no STT)
  /wifi off|on  /lb off|on  /loss 0.3  /loc lat lon  /status  /quit   (same as node.py)
"""
import argparse
import gc
import os
import tempfile
import threading
import time
import wave

from itantra_ai.stt.stt_engine import STTEngine

try:                                   # hide Vosk's internal LOG/WARNING spam
    from vosk import SetLogLevel
    SetLogLevel(-1)
except Exception:
    pass

from . import node as N
from .radio_manager import RadioManager
from .transports import EmulatedLowBitrateTransport, UdpWifiTransport

SR = 16000                 # both STT engines expect 16 kHz mono 16-bit
BLOCK_MS = 30
SILENCE_END_MS = 800       # pause length that ends a sentence
MIN_SPEECH_MS = 300        # ignore clicks/coughs shorter than this
MAX_UTTERANCE_S = 15


# --------------------------------------------------------------------- STT
class Speech:
    """Holds exactly ONE loaded STT model (low RAM). Switching language unloads first."""

    def __init__(self, lang: str):
        self.lang = None
        self.engine = None
        self.set_lang(lang)

    def set_lang(self, lang: str):
        if lang == self.lang:
            return
        self.engine = None
        gc.collect()                                   # free the old model before loading
        t = time.time()
        eng = STTEngine(language=lang)
        eng.load_model()
        self.engine, self.lang = eng, lang
        print(f"[stt] '{lang}' model loaded in {time.time() - t:.1f}s")

    def transcribe_pcm(self, pcm: bytes):
        """pcm = 16 kHz mono int16 bytes. Returns (text, stt_seconds, audio_seconds)."""
        fd, path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        try:
            with wave.open(path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(SR)
                wf.writeframes(pcm)
            t = time.time()
            text = self.engine.transcribe_audio(path)
            return text.strip(), time.time() - t, len(pcm) / 2 / SR
        finally:
            os.remove(path)

    def transcribe_file(self, path: str):
        with wave.open(path, "rb") as wf:
            if wf.getframerate() != SR or wf.getnchannels() != 1 or wf.getsampwidth() != 2:
                raise ValueError("WAV must be 16 kHz, mono, 16-bit")
            return self.transcribe_pcm(wf.readframes(wf.getnframes()))


def speak_and_send(speech: Speech, rm: RadioManager, pcm: bytes, source: str):
    if len(pcm) < SR * 2 * MIN_SPEECH_MS / 1000:
        print("[stt] too short, ignored")
        return
    text, stt_s, audio_s = speech.transcribe_pcm(pcm)
    rtf = stt_s / audio_s if audio_s else 0
    if not text:
        print(f"[stt] no speech recognized ({audio_s:.1f}s audio), nothing sent")
        return
    print(f"[stt:{source}] \"{text}\"   audio={audio_s:.1f}s  STT={stt_s*1000:.0f}ms  RTF={rtf:.2f}")
    rm.send_message(text, speech.lang)
    print(f"[send] queued on {rm.current}")


# --------------------------------------------------------------------- recording
def record_push_to_talk() -> bytes:
    import sounddevice as sd
    frames = []

    def cb(indata, n, t, status):
        frames.append(bytes(indata))

    with sd.RawInputStream(samplerate=SR, channels=1, dtype="int16", callback=cb):
        input("  REC... speak now, press Enter to stop ")
    return b"".join(frames)


class AutoListener(threading.Thread):
    """
    Hands-free mode (PS: 'STT activated after detecting pauses').
    Simple energy VAD: calibrates to room noise, starts a sentence when the
    voice gets louder than noise, ends it after SILENCE_END_MS of quiet.
    """

    def __init__(self, speech: Speech, rm: RadioManager, on_speech=None, log=None):
        super().__init__(daemon=True)
        self.speech, self.rm = speech, rm
        self.running = True
        # the GUI passes its own handlers; the terminal keeps the old prints
        self.on_speech = on_speech or self._terminal_send
        self.log = log or (lambda s: print(s, flush=True))

    def run(self):
        import numpy as np
        import sounddevice as sd
        block = int(SR * BLOCK_MS / 1000)
        with sd.RawInputStream(samplerate=SR, channels=1, dtype="int16", blocksize=block) as st:
            noise = []
            for _ in range(int(1000 / BLOCK_MS)):          # 1 s calibration
                data, _ = st.read(block)
                noise.append(self._rms(np, data))
            thr = max(300.0, sorted(noise)[len(noise) // 2] * 3)
            self.log(f"\n[auto] listening (noise={sorted(noise)[len(noise)//2]:.0f}, threshold={thr:.0f}). Speak, then pause.")

            buf, speaking, loud, quiet = [], False, 0, 0
            while self.running:
                data, _ = st.read(block)
                data = bytes(data)
                rms = self._rms(np, data)
                if not speaking:
                    loud = loud + 1 if rms > thr else 0
                    buf = (buf + [data])[-10:]              # keep 300 ms of lead-in
                    if loud >= 3:
                        speaking, quiet = True, 0
                        self.log("\n[auto] speech started...")
                    continue
                buf.append(data)
                quiet = quiet + 1 if rms < thr else 0
                too_long = len(buf) * BLOCK_MS / 1000 > MAX_UTTERANCE_S
                if quiet * BLOCK_MS >= SILENCE_END_MS or too_long:
                    self.log("[auto] pause detected, transcribing...")
                    self.on_speech(b"".join(buf))
                    buf, speaking, loud = [], False, 0

    def _terminal_send(self, pcm: bytes):
        speak_and_send(self.speech, self.rm, pcm, "auto")
        print("> ", end="", flush=True)

    @staticmethod
    def _rms(np, data) -> float:
        a = np.frombuffer(data, dtype=np.int16).astype(np.float32)
        return float(np.sqrt(np.mean(a * a))) if a.size else 0.0


# --------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="A")
    ap.add_argument("--lang", default="hi")
    ap.add_argument("--peer-ip", default="127.0.0.1")
    ap.add_argument("--wifi-port", type=int, required=True)
    ap.add_argument("--peer-wifi-port", type=int, required=True)
    ap.add_argument("--lb-port", type=int, required=True)
    ap.add_argument("--peer-lb-port", type=int, required=True)
    ap.add_argument("--lb-bps", type=int, default=600)
    ap.add_argument("--lb-loss", type=float, default=0.1)
    ap.add_argument("--verbose", action="store_true", help="print every dropped corrupt packet")
    ap.add_argument("--no-tts", action="store_true", help="print received messages instead of speaking")
    ap.add_argument("--save-wav", default=None, help="write received audio to this folder instead of playing")
    ap.add_argument("--lat", type=float, default=None)
    ap.add_argument("--lon", type=float, default=None)
    a = ap.parse_args()

    speech = Speech(a.lang)

    wifi = UdpWifiTransport(a.wifi_port, a.peer_ip, a.peer_wifi_port)
    lb = EmulatedLowBitrateTransport(a.lb_port, a.peer_ip, a.peer_lb_port,
                                     bitrate_bps=a.lb_bps, loss=a.lb_loss)
    rm = RadioManager([wifi, lb], on_receive=N.on_receive,
                      log=lambda s: print(f"\n{s}\n> ", end="", flush=True),
                      verbose=a.verbose)
    N.RM = rm
    if not a.no_tts:
        from .speaker import Speaker
        N.SPEAKER = Speaker(lambda: rm.location, save_dir=a.save_wav)
    if a.lat is not None and a.lon is not None:
        rm.set_location(a.lat, a.lon)
    rm.start()

    print(f"Voice node {a.name} ready. STT language = {speech.lang}. "
          f"Press Enter to talk, /auto on for hands-free, /status for links.")
    auto = None
    while True:
        try:
            line = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        try:
            if line == "":
                speak_and_send(speech, rm, record_push_to_talk(), "ptt")
            elif line == "/quit":
                break
            elif line == "/status":
                print(rm.status())
            elif line.startswith("/auto "):
                if line.endswith("on") and auto is None:
                    auto = AutoListener(speech, rm); auto.start()
                elif line.endswith("off") and auto is not None:
                    auto.running = False; auto = None; print("[auto] stopped")
            elif line.startswith("/file "):
                path = line.split(maxsplit=1)[1]
                text, stt_s, audio_s = speech.transcribe_file(path)
                if text:
                    print(f"[stt:file] \"{text}\"  STT={stt_s*1000:.0f}ms  RTF={stt_s/audio_s:.2f}")
                    rm.send_message(text, speech.lang)
                else:
                    print("[stt] no speech recognized, nothing sent")
            elif line.startswith("/lang "):
                speech.set_lang(line.split()[1])
            elif line.startswith("/wifi "):
                wifi.enabled = line.endswith("on"); print(f"WiFi enabled = {wifi.enabled}")
            elif line.startswith("/lb "):
                lb.enabled = line.endswith("on"); print(f"Low-bitrate enabled = {lb.enabled}")
            elif line.startswith("/ber "):
                lb.ber = float(line.split()[1]); print(f"low-bitrate bit error rate = {lb.ber}")
            elif line.startswith("/loss "):
                lb.loss = float(line.split()[1]); print(f"low-bitrate loss = {lb.loss}")
            elif line.startswith("/loc "):
                _, la, lo = line.split(); rm.set_location(float(la), float(lo)); print("location set")
            else:
                rm.send_message(line, speech.lang)
                print(f"[send] typed text queued on {rm.current}")
        except Exception as e:                      # keep the node alive on any single error
            print(f"[error] {type(e).__name__}: {e}")
    if auto:
        auto.running = False
    rm.stop()


if __name__ == "__main__":
    main()
