import sys, time, wave
from faster_whisper import WhisperModel

def dur(p):
    with wave.open(p) as w: return w.getnframes()/w.getframerate()

files = sys.argv[1:3]
for size in ["small", "large-v3-turbo"]:
    t0 = time.time()
    m = WhisperModel(size, device="cpu", compute_type="int8", cpu_threads=8)
    load = time.time()-t0
    print(f"\n### {size}  (load {load:.1f}s, cpu int8)")
    for f, lang in zip(files, ["en", "pt"]):
        d = dur(f); t = time.time()
        segs, info = m.transcribe(f, language=lang, vad_filter=True, beam_size=1)
        text = " ".join(s.text.strip() for s in segs)
        el = time.time()-t
        print(f"  [{lang}] audio {d:.1f}s | proc {el:.1f}s | RTF {el/d:.2f}")
        print(f"  -> {text}")
    del m
