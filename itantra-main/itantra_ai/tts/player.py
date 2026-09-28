"""
Audio playback with the PS alert rules:
  - normal messages  : played as voice notes, one after another
  - ALERT messages   : a short siren tone, then the message at full scale,
                       interrupt anything that is playing, and cannot be
                       interrupted themselves (they finish before anything else).

Laptop demo: full-scale audio (peak-normalised). On Android use the ALARM
audio stream + audio focus so alerts play at max volume even if media is muted.
If no audio device is available, set save_dir to write WAV files instead.
"""
import os
import queue
import threading
import time
import wave

import numpy as np


def _siren(sr: int, seconds: float = 0.6) -> np.ndarray:
    t = np.arange(int(sr * seconds)) / sr
    freq = np.where((t * 4).astype(int) % 2 == 0, 880.0, 660.0)   # two-tone alert
    return (0.9 * np.sin(2 * np.pi * freq * t)).astype(np.float32)


class AudioPlayer:
    def __init__(self, save_dir: str = None):
        self.save_dir = save_dir
        self._q = queue.PriorityQueue()
        self._n = 0
        self._playing_alert = False
        self._lock = threading.Lock()
        threading.Thread(target=self._loop, daemon=True).start()

    def play(self, samples: np.ndarray, sr: int, alert: bool, label: str = ""):
        with self._lock:
            self._n += 1
            n = self._n
        if alert:
            peak = float(np.max(np.abs(samples))) or 1.0
            samples = np.concatenate([_siren(sr), np.zeros(int(sr * 0.15), np.float32),
                                      samples / peak * 0.99])
            if not self._playing_alert:
                self._stop_current()                   # alert interrupts normal playback
        self._q.put((0 if alert else 1, n, samples, sr, alert, label))

    def _stop_current(self):
        try:
            import sounddevice as sd
            sd.stop()
        except Exception:
            pass

    def _loop(self):
        while True:
            _, n, samples, sr, alert, label = self._q.get()
            if self.save_dir:
                os.makedirs(self.save_dir, exist_ok=True)
                path = os.path.join(self.save_dir, f"{n:03d}_{'ALERT' if alert else 'msg'}_{label}.wav")
                with wave.open(path, "wb") as w:
                    w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
                    w.writeframes((np.clip(samples, -1, 1) * 32767).astype(np.int16).tobytes())
                continue
            try:
                import sounddevice as sd
                self._playing_alert = alert
                sd.play(samples, sr)
                sd.wait()                              # alerts are never stopped mid-way
            except Exception as e:
                print(f"[tts] playback failed ({e}); use --save-wav to write files instead")
            finally:
                self._playing_alert = False
