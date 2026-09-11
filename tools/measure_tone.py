"""Records the notification tone through the microphone to compare loudness."""
import sys, time
import numpy as np
sys.path.insert(0, ".")
from app import audio
from app.platform_support import play_tone

def capture(label, play):
    r = audio.Recorder(); r.start(None); time.sleep(0.4)
    play(); time.sleep(1.1)
    buf, peak = r.stop()
    rms = float(np.sqrt(np.mean(buf**2))) if buf.size else 0.0
    print(f"{label:26s} peak={peak:.4f}  rms={rms:.5f}")
    return peak

floor = capture("sala em silencio", lambda: time.sleep(0.1))
import winsound
old = capture("winsound antigo", lambda: winsound.Beep(560, 90)) - floor
for vol in (10, 20, 40, 100):
    p = capture(f"stop volume={vol}%", lambda v=vol: (play_tone("stop", v), time.sleep(0.5))) - floor
    print(f"     -> {max(p,0)/old*100:.0f}% do bipe antigo")
