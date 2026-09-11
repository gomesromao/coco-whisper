"""Checks whether a trailing pad of silence is what the output stream needs."""
import sys, time
import numpy as np
import sounddevice as sd
sys.path.insert(0, ".")
from app import audio

print("dispositivo de saida padrao:", sd.query_devices(kind="output")["name"])

def tone(freq, seconds, amp, pad):
    rate = 44100
    t = np.linspace(0, seconds, int(rate * seconds), endpoint=False)
    w = (amp * np.sin(2 * np.pi * freq * t)).astype("float32")
    fade = max(1, int(len(w) * 0.2))
    w[:fade] *= np.linspace(0, 1, fade, dtype="float32")
    w[-fade:] *= np.linspace(1, 0, fade, dtype="float32")
    if pad:
        w = np.concatenate([w, np.zeros(int(rate * pad), dtype="float32")])
    return w, rate

def capture(label, play):
    r = audio.Recorder(); r.start(None); time.sleep(0.35)
    play(); time.sleep(0.9)
    buf, peak = r.stop()
    print(f"  {label:34s} peak={peak:.4f}")
    return peak

floor = capture("silencio", lambda: time.sleep(0.1))
for pad in (0.0, 0.25):
    for amp in (0.15, 0.5):
        w, rate = tone(520, 0.09, amp, pad)
        capture(f"amp={amp} pad={pad}s", lambda w=w, rate=rate: sd.play(w, rate, blocking=True))
