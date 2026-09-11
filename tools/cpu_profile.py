"""How many cores each model actually pulls during a transcription."""
import os, sys, time
import numpy as np
sys.path.insert(0, ".")
from faster_whisper import WhisperModel
from app.config import models_dir

buf = np.load("captured.npy")
secs = buf.size / 16000
print(f"audio: {secs:.1f}s\n")
print(f"{'modelo':16s} {'threads':>7s} {'tempo':>7s} {'nucleos usados':>15s}")

for model, threads in (("large-v3-turbo", 8), ("large-v3-turbo", 6),
                       ("small", 6), ("small", 4), ("base", 4)):
    m = WhisperModel(model, device="cpu", compute_type="int8",
                     cpu_threads=threads, download_root=str(models_dir()))
    t0, c0 = time.time(), time.process_time()
    segs, _ = m.transcribe(buf, language="en", vad_filter=True, beam_size=1)
    list(segs)
    wall, cpu = time.time() - t0, time.process_time() - c0
    print(f"{model:16s} {threads:7d} {wall:6.1f}s {cpu/wall:14.1f}x")
    del m
