"""Generate the app icon (.icns) from a procedurally drawn design.

The icon follows the app's UI theme (the macOS "system blue" accent color
used throughout style.py) and depicts a simple, modern server tower with a
status light - readable at every size from 16px to 1024px.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
SIZE = 1024


def _rounded_mask(size: int, radius: int) -> Image.Image:
    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle((0, 0, size - 1, size - 1), radius=radius, fill=255)
    return mask


def _vertical_gradient(size: int, top: tuple[int, int, int], bottom: tuple[int, int, int]) -> Image.Image:
    gradient = Image.new("RGB", (1, size))
    for y in range(size):
        t = y / (size - 1)
        color = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
        gradient.putpixel((0, y), color)
    return gradient.resize((size, size))


def build_icon() -> Image.Image:
    # Same accent blue as style.py, fading to a deeper blue for depth.
    background = _vertical_gradient(SIZE, (64, 156, 255), (10, 90, 230))
    icon = Image.new("RGBA", (SIZE, SIZE))
    icon.paste(background, (0, 0))
    icon.putalpha(_rounded_mask(SIZE, radius=int(SIZE * 0.22)))

    draw = ImageDraw.Draw(icon)

    # Server tower: three stacked rack units, centered.
    tower_w = int(SIZE * 0.46)
    tower_h = int(SIZE * 0.56)
    tower_x = (SIZE - tower_w) // 2
    tower_y = (SIZE - tower_h) // 2
    unit_gap = int(SIZE * 0.025)
    unit_h = (tower_h - 2 * unit_gap) // 3
    corner = int(SIZE * 0.045)

    for i in range(3):
        unit_y = tower_y + i * (unit_h + unit_gap)
        draw.rounded_rectangle(
            (tower_x, unit_y, tower_x + tower_w, unit_y + unit_h),
            radius=corner,
            fill=(255, 255, 255, 235),
        )
        # Status light on each unit - the top one is "active" (green).
        light_r = int(unit_h * 0.16)
        light_cx = tower_x + tower_w - int(tower_w * 0.13)
        light_cy = unit_y + unit_h // 2
        light_color = (48, 209, 88, 255) if i == 0 else (180, 196, 220, 255)
        draw.ellipse(
            (light_cx - light_r, light_cy - light_r, light_cx + light_r, light_cy + light_r),
            fill=light_color,
        )
        # Two small indicator bars on the left of each unit.
        bar_w = int(tower_w * 0.09)
        bar_h = int(unit_h * 0.16)
        bar_x = tower_x + int(tower_w * 0.10)
        for b in range(2):
            bar_y = unit_y + int(unit_h * 0.28) + b * int(unit_h * 0.30)
            draw.rounded_rectangle(
                (bar_x, bar_y, bar_x + int(tower_w * 0.32), bar_y + bar_h),
                radius=bar_h // 2,
                fill=(64, 156, 255, 255),
            )

    return icon


def export_iconset(icon: Image.Image, iconset_dir: Path) -> None:
    iconset_dir.mkdir(parents=True, exist_ok=True)
    # Canonical macOS iconset sizes (iconutil rejects anything else).
    for size in (16, 32, 128, 256, 512):
        icon.resize((size, size), Image.LANCZOS).save(iconset_dir / f"icon_{size}x{size}.png")
        icon.resize((size * 2, size * 2), Image.LANCZOS).save(iconset_dir / f"icon_{size}x{size}@2x.png")


def export_ico(icon: Image.Image, ico_path: Path) -> None:
    sizes = [16, 32, 48, 64, 128, 256]
    icon.save(ico_path, format="ICO", sizes=[(size, size) for size in sizes])


def main() -> None:
    ASSETS.mkdir(exist_ok=True)
    icon = build_icon()
    png_path = ASSETS / "app_icon.png"
    icon.save(png_path)

    iconset_dir = ASSETS / "AppIcon.iconset"
    export_iconset(icon, iconset_dir)

    icns_path = ASSETS / "AppIcon.icns"
    subprocess.run(["iconutil", "-c", "icns", str(iconset_dir), "-o", str(icns_path)], check=True)
    print(f"Icone generee: {icns_path}")

    ico_path = ASSETS / "AppIcon.ico"
    export_ico(icon, ico_path)
    print(f"Icone generee: {ico_path}")


if __name__ == "__main__":
    main()
