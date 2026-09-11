"""Finds the amplitude that lands near a target share of the old beep."""
import sys, time
import numpy as np
import sounddevice as sd
sys.path.insert(0, ".")
from app import audio

def play_sine(freq, seconds, amp):
    rate = 44100
    t = np.linspace(0, seconds, int(rate * seconds), endpoint=False)
    w = (amp * np.sin(2 * np.pi * freq * t)).astype("float32")
    fade = max(1, int(len(w) * 0.2))
    w[:fade] *= np.linspace(0, 1, fade, dtype="float32")
    w[-fade:] *= np.linspace(1, 0, fade, dtype="float32")
    sd.play(w, rate, blocking=True)

def capture(label, play):
    r = audio.Recorder(); r.start(None); time.sleep(0.35)
    play(); time.sleep(0.9)
    buf, peak = r.stop()
    print(f"  {label:26s} peak={peak:.4f}")
    return peak

floor = capture("silencio", lambda: time.sleep(0.1))
import winsound
old = capture("winsound antigo", lambda: winsound.Beep(560, 90)) - floor
print(f"referencia antiga (acima do ruido): {old:.4f}\n")

for amp in (0.05, 0.15, 0.35, 0.6, 0.9):
    p = capture(f"senoidal amp={amp}", lambda a=amp: play_sine(520, 0.09, a)) - floor
    print(f"     -> {p/old*100:.0f}% do antigo")
