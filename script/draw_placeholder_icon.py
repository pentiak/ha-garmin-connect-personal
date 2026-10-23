"""Draw the placeholder brand icon: a generic watch, not Garmin's logo.

Run from the repository root, with the brand folder as the argument:
    .venv/bin/python -I script/draw_placeholder_icon.py \
        custom_components/garmin_connect_personal/brand
"""

import math
from pathlib import Path
import sys

from PIL import Image, ImageDraw

STRAP = (84, 110, 122, 255)  # blue grey
STRAP_EDGE = (55, 71, 79, 255)
CASE = (0, 137, 123, 255)  # teal
FACE = (250, 250, 250, 255)
HANDS = (38, 50, 56, 255)
TICKS = (96, 125, 139, 255)


def draw(size: int) -> Image.Image:
    """Return the icon at `size` pixels square, on a transparent background."""
    # Drawn at 4x and downscaled, for anti-aliased edges.
    s = size * 4
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    u = s / 256
    cx = cy = s / 2

    strap_w = 92 * u
    d.rounded_rectangle(
        (cx - strap_w / 2, 4 * u, cx + strap_w / 2, 252 * u), radius=22 * u, fill=STRAP
    )
    for y in (34 * u, 222 * u):
        d.line(
            (cx - strap_w / 2 + 14 * u, y, cx + strap_w / 2 - 14 * u, y),
            fill=STRAP_EDGE,
            width=round(6 * u),
        )

    # crown and buttons
    d.rounded_rectangle(
        (cx + 84 * u, cy - 14 * u, cx + 104 * u, cy + 14 * u), radius=5 * u, fill=CASE
    )
    for dy in (-46, 46):
        d.rounded_rectangle(
            (cx + 72 * u, cy + dy * u - 9 * u, cx + 92 * u, cy + dy * u + 9 * u),
            radius=4 * u,
            fill=CASE,
        )

    r_case, r_face = 90 * u, 72 * u
    d.ellipse((cx - r_case, cy - r_case, cx + r_case, cy + r_case), fill=CASE)
    d.ellipse((cx - r_face, cy - r_face, cx + r_face, cy + r_face), fill=FACE)

    for i in range(12):
        a = math.radians(i * 30)
        r1 = r_face - (16 if i % 3 == 0 else 10) * u
        r2 = r_face - 5 * u
        d.line(
            (
                cx + r1 * math.sin(a),
                cy - r1 * math.cos(a),
                cx + r2 * math.sin(a),
                cy - r2 * math.cos(a),
            ),
            fill=TICKS if i % 3 else HANDS,
            width=round((7 if i % 3 == 0 else 4) * u),
        )

    def hand(angle_deg: float, length: float, width: float) -> None:
        a = math.radians(angle_deg)
        d.line(
            (cx, cy, cx + length * math.sin(a), cy - length * math.cos(a)),
            fill=HANDS,
            width=round(width),
        )
        d.ellipse(
            (cx - width / 2, cy - width / 2, cx + width / 2, cy + width / 2), fill=HANDS
        )
        ex, ey = cx + length * math.sin(a), cy - length * math.cos(a)
        d.ellipse(
            (ex - width / 2, ey - width / 2, ex + width / 2, ey + width / 2), fill=HANDS
        )

    hand(300, 38 * u, 12 * u)  # hour hand at ten
    hand(60, 54 * u, 8 * u)  # minute hand at ten past
    d.ellipse((cx - 9 * u, cy - 9 * u, cx + 9 * u, cy + 9 * u), fill=CASE)

    return img.resize((size, size), Image.Resampling.LANCZOS)


def main() -> None:
    """Write `icon.png` and `icon@2x.png` into the folder given as the argument."""
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    draw(256).save(out / "icon.png", optimize=True)
    draw(512).save(out / "icon@2x.png", optimize=True)


if __name__ == "__main__":
    main()
