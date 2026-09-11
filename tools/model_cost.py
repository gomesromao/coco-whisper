"""How long each model takes and how hard it pushes the processor."""
import os, sys, time
import numpy as np
sys.path.insert(0, ".")
from app.transcribe import Engine

buf = np.load("captured.npy") if os.path.exists("captured.npy") else None
if buf is None:
    print("sem audio de teste"); raise SystemExit
secs = buf.size / 16000
print(f"audio de teste: {secs:.1f}s   threads: {max(2, min(6, (os.cpu_count() or 4)//2))}\n")

for model in ("small", "large-v3-turbo"):
    e = Engine()
    e.load(model, "cpu")
    t0 = time.time(); e.transcribe(buf, "auto", model, "cpu"); el = time.time() - t0
    print(f"{model:16s} {el:5.1f}s para {secs:.0f}s de fala   (RTF {el/secs:.2f})")
    del e
