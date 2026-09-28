import sounddevice as sd
import wave
import sys

seconds = 5
filename = sys.argv[1] if len(sys.argv) > 1 else "sample.wav"

print(f"Recording {seconds} seconds... ab bolo!")
audio = sd.rec(int(seconds * 16000), samplerate=16000, channels=1, dtype="int16")
sd.wait()
print(f"Done. Saved to {filename}")

with wave.open(filename, "wb") as wf:
    wf.setnchannels(1)
    wf.setsampwidth(2)
    wf.setframerate(16000)
    wf.writeframes(audio.tobytes())