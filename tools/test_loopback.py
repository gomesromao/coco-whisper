import subprocess, sys, time
import numpy as np
from app import audio

wav = sys.argv[1]
dev = int(sys.argv[2])
r = audio.Recorder()
try:
    r.start(dev)
except audio.RecordingError as e:
    print("CANNOT OPEN DEVICE:", e); sys.exit(1)
subprocess.Popen(["powershell", "-c",
    f"(New-Object Media.SoundPlayer '{wav}').PlaySync()"])
time.sleep(13)
buf, peak = r.stop()
print(f"captured {buf.size/16000:.1f}s peak={peak:.4f}")
np.save("captured.npy", buf)
