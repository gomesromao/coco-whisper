"""Generates the Coconut Whisper icon set from brand tokens."""
from pathlib import Path

from PIL import Image, ImageDraw

NAVY = (11, 30, 63, 255)
GREEN = (80, 176, 128, 255)
AMBER = (244, 196, 48, 255)
CREAM = (250, 246, 238, 255)
WHITE = (255, 255, 255, 255)

ASSETS = Path(__file__).resolve().parent.parent / "assets"
ASSETS.mkdir(exist_ok=True)


def draw_icon(size: int, bg, mic=WHITE) -> Image.Image:
    scale = 8
    s = size * scale
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    radius = int(s * 0.26)
    d.rounded_rectangle([0, 0, s - 1, s - 1], radius=radius, fill=bg)

    # microphone capsule
    cap_w, cap_h = s * 0.26, s * 0.40
    cx, cy = s / 2, s * 0.40
    d.rounded_rectangle(
        [cx - cap_w / 2, cy - cap_h / 2, cx + cap_w / 2, cy + cap_h / 2],
        radius=cap_w / 2, fill=mic,
    )
    # cradle arc
    arc_w = s * 0.42
    arc_top = s * 0.42
    arc_bottom = s * 0.72
    d.arc(
        [cx - arc_w / 2, arc_top, cx + arc_w / 2, arc_bottom],
        start=0, end=180, fill=mic, width=int(s * 0.055),
    )
    # stand
    d.rounded_rectangle(
        [cx - s * 0.028, s * 0.66, cx + s * 0.028, s * 0.82],
        radius=s * 0.028, fill=mic,
    )
    d.rounded_rectangle(
        [cx - s * 0.13, s * 0.80, cx + s * 0.13, s * 0.845],
        radius=s * 0.022, fill=mic,
    )
    return img.resize((size, size), Image.LANCZOS)


def main() -> None:
    sizes = [16, 24, 32, 48, 64, 128, 256]
    frames = [draw_icon(n, NAVY) for n in sizes]
    frames[-1].save(ASSETS / "icon.ico", format="ICO", sizes=[(n, n) for n in sizes])
    draw_icon(256, NAVY).save(ASSETS / "icon.png")

    states = {"idle": NAVY, "recording": GREEN, "busy": AMBER}
    for name, color in states.items():
        mic = NAVY if name != "idle" else CREAM
        draw_icon(64, color, mic).save(ASSETS / f"tray_{name}.png")
    print("icons written to", ASSETS)


if __name__ == "__main__":
    main()
