"""Locates our navy icon in the taskbar so the crop is not guesswork."""
import os
from pathlib import Path
from PIL import Image

scratch = Path(os.environ["TEMP"]) / "claude" / "C--Users-Daniel" / "7284d0ee-ea34-43af-9cec-e52e96bafdc3" / "scratchpad"
img = Image.open(scratch / "full_desktop.png").convert("RGB")
band = img.crop((1200, 1030, 1920, 1075))
px = band.load()
# our icon is the brand navy #0B1E3F
hits = {}
for x in range(band.width):
    for y in range(band.height):
        r, g, b = px[x, y]
        if abs(r - 11) < 18 and abs(g - 30) < 18 and abs(b - 63) < 22:
            hits[x] = hits.get(x, 0) + 1
cols = sorted(k for k, v in hits.items() if v >= 4)
if cols:
    groups, current = [], [cols[0]]
    for c in cols[1:]:
        if c - current[-1] <= 3:
            current.append(c)
        else:
            groups.append(current); current = [c]
    groups.append(current)
    for grp in groups:
        print(f"faixa navy em x={1200+grp[0]}..{1200+grp[-1]} (largura {grp[-1]-grp[0]})")
else:
    print("nao encontrei a cor da marca nessa faixa")
