"""Crops and annotates the screenshots used on the how-to pages."""
import os, sys
from pathlib import Path
from PIL import Image, ImageDraw

scratch = Path(os.environ["TEMP"]) / "claude" / "C--Users-Daniel" / "7284d0ee-ea34-43af-9cec-e52e96bafdc3" / "scratchpad"
out = Path("site/img")
out.mkdir(parents=True, exist_ok=True)
GREEN = (80, 176, 128, 255)

def shot(name):
    return Image.open(scratch / name).convert("RGB")

# 1. the icon in the taskbar, zoomed with a ring around it
full = shot("full_desktop.png") if (scratch / "full_desktop.png").exists() else None
tray = shot("tray_zoom.png")
w, h = tray.size
print("tray_zoom:", tray.size)
crop = tray.crop((260, 20, 700, 120)).resize((880, 200), Image.LANCZOS)
d = ImageDraw.Draw(crop)
d.rounded_rectangle([100, 18, 260, 178], radius=18, outline=GREEN, width=6)
crop.save(out / "win-tray-icon.png")

# 2. the listening pill, trimmed
pill = shot("overlay_listening.png")
print("overlay:", pill.size)
pill.crop((330, 30, 700, 150)).save(out / "win-listening.png")

# 3. the settings window
settings = shot("settings3.png")
print("settings:", settings.size)
settings.save(out / "win-settings.png")

for f in sorted(out.iterdir()):
    print(" ", f.name, Image.open(f).size, f.stat().st_size // 1024, "KB")
