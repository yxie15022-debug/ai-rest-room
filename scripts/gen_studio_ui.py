"""Generate the monitor UI textures the Blender studio scene uses."""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parents[1] / 'data' / '_blender_ui'
W, H = 1280, 720
BLUE = (74, 144, 226)
BLUE_D = (58, 124, 204)
INK = (52, 52, 52)


def base(bg_top: tuple, bg_bottom: tuple) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new('RGB', (W, H), bg_top)
    draw = ImageDraw.Draw(img)
    for y in range(H):
        t = y / H
        draw.line([(0, y), (W, y)], fill=tuple(int(bg_top[i] + (bg_bottom[i] - bg_top[i]) * t) for i in range(3)))
    return img, draw


def window(draw: ImageDraw.ImageDraw) -> tuple[int, int, int, int]:
    left, top, right, bottom = 90, 90, W - 90, H - 70
    draw.rounded_rectangle([left, top, right, bottom], radius=16, fill=(252, 252, 251))
    draw.rounded_rectangle([left, top, right, top + 56], radius=16, fill=(240, 240, 237))
    for i in range(3):
        draw.ellipse([left + 28 + i * 34, top + 21, left + 46 + i * 34, top + 39], fill=(205, 205, 202))
    return left, top, right, bottom


def sit() -> Image.Image:
    img, draw = base(BLUE, BLUE_D)
    draw.rounded_rectangle([0, 0, W, 64], radius=0, fill=(52, 110, 186))
    for i in range(3):
        draw.ellipse([28 + i * 40, 26, 46 + i * 40, 44], fill=(255, 255, 255) if i == 0 else (220, 220, 220))
    left, top, right, bottom = window(draw)
    for row in range(16):
        y = top + 84 + row * 34
        icon = (126, 180, 238) if row % 3 == 0 else (206, 206, 203)
        draw.rounded_rectangle([left + 40, y, left + 72, y + 32], radius=6, fill=icon)
        draw.rounded_rectangle([left + 92, y + 8, left + 460 - (row % 4) * 40, y + 24], radius=8, fill=(214, 214, 211))
        draw.rounded_rectangle([right - 300, y + 8, right - 120, y + 24], radius=8, fill=(232, 232, 229))
    return img


def study() -> Image.Image:
    img, draw = base((80, 152, 232), BLUE_D)
    draw.rounded_rectangle([0, 0, W, 64], radius=0, fill=(52, 110, 186))
    left, top, right, bottom = window(draw)
    # sidebar
    draw.rounded_rectangle([left, top + 56, left + 220, bottom], radius=16, fill=(247, 247, 244))
    for row in range(8):
        draw.rounded_rectangle([left + 28, top + 96 + row * 64, left + 190, top + 128 + row * 64], radius=8, fill=(222, 222, 219))
    # line chart
    cx0, cx1 = left + 260, right - 60
    base_y = bottom - 120
    points = []
    for i in range(12):
        x = cx0 + i * (cx1 - cx0) / 11
        y = base_y - 60 - 90 * (0.5 + 0.5 * __import__('math').sin(i * 0.8 + 2.0))
        points.append((x, y))
    draw.line(points, fill=BLUE, width=7, joint='curve')
    for i, (x, y) in enumerate(points):
        draw.ellipse([x - 8, y - 8, x + 8, y + 8], fill=BLUE)
    # bars
    for i in range(8):
        bar_h = 50 + 80 * (0.5 + 0.5 * __import__('math').sin(i * 0.9 + 1.0))
        x = cx0 + 16 + i * 56
        draw.rounded_rectangle([x, bottom - 30 - bar_h, x + 34, bottom - 30], radius=6, fill=(126, 180, 238))
    return img


def chat() -> Image.Image:
    img, draw = base((70, 130, 210), BLUE_D)
    draw.rounded_rectangle([0, 0, W, 64], radius=0, fill=(48, 100, 176))
    left, top, right, bottom = window(draw)
    bubbles = [
        (left + 50, top + 90, left + 520, top + 190, (230, 230, 226)),
        (right - 540, top + 220, right - 80, top + 320, (66, 144, 232)),
        (left + 50, top + 350, left + 560, top + 450, (230, 230, 226)),
    ]
    for x0, y0, x1, y1, color in bubbles:
        draw.rounded_rectangle([x0, y0, x1, y1], radius=26, fill=color)
        for d in range(3):
            draw.ellipse([x0 + 34 + d * 34, (y0 + y1) // 2 - 8, x0 + 46 + d * 34, (y0 + y1) // 2 + 4], fill=(140, 140, 136) if color != (66, 144, 232) else (210, 232, 252))
    return img


def sleep() -> Image.Image:
    img = Image.new('RGB', (W, H), (24, 24, 24))
    draw = ImageDraw.Draw(img)
    draw.ellipse([W - 320, 60, W - 120, 260], fill=(58, 62, 78))
    draw.ellipse([W - 290, 60, W - 120, 260], fill=(24, 24, 24))
    for row in range(6):
        width = 520 - row * 50
        draw.rounded_rectangle([70, 70 + row * 64, 70 + width, 96 + row * 64], radius=10, fill=(52, 54, 64))
    return img


def enter() -> Image.Image:
    img = Image.new('RGB', (W, H), (248, 248, 246))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([W // 2 - 96, 190, W // 2 + 96, 340], radius=36, fill=BLUE)
    draw.ellipse([W // 2 - 46, 228, W // 2 + 46, 320], fill=(248, 248, 246))
    draw.rounded_rectangle([120, H - 150, W - 120, H - 110], radius=18, fill=(231, 231, 228))
    draw.rounded_rectangle([120, H - 150, 120 + int((W - 240) * 0.85), H - 110], radius=18, fill=BLUE)
    return img


SCENES = {'sit': sit, 'study': study, 'chat': chat, 'sleep': sleep, 'enter': enter}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for scene, fn in SCENES.items():
        path = OUT / f'{scene}.png'
        fn().save(path)
        print('wrote', path)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
