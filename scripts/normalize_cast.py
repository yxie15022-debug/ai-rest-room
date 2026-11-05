"""Turn generated character art into stage-ready sprites.

The image generator hands back JPEGs, so "transparent background" never
survives. Characters are therefore generated against a flat chroma-key green
and keyed out here: a green-dominance matte gives clean anti-aliased edges even
through JPEG ringing, and white costume parts survive (a flood fill by colour
does not -- white stockings connect to the border and get eaten).

    python scripts/normalize_cast.py --src assets/cast-deepseek-stand.jpg \
        --out app/static/anim/cast/deepseek/stand.png
"""

from __future__ import annotations

import argparse
from collections import deque
from pathlib import Path

from PIL import Image, ImageChops, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
# Sprites are drawn about 120-190 px tall on the desktop, so building them at
# 1024 only to have the browser throw 90% of the pixels away is what made the
# characters look soft: a 5-9x downscale in the compositor is a box filter, not
# a resample. This keeps a little over 2x the drawn height for sharpness on a
# high-DPI screen, and the shrink is done here, once, with Lanczos.
HEIGHT = 384
# Green dominance (g above the brighter of r/b) that counts as fully opaque /
# fully background. Everything between is the anti-aliased rim.
KEY_SOLID = 12
KEY_CLEAR = 46


def _greenness(img: Image.Image) -> Image.Image:
    r, g, b = img.split()
    return ImageChops.subtract(g, ImageChops.lighter(r, b))


def _is_chroma(img: Image.Image) -> bool:
    w, h = img.size
    green = _greenness(img)
    corners = [green.getpixel(p) for p in ((2, 2), (w - 3, 2), (2, h - 3), (w - 3, h - 3))]
    return min(corners) > KEY_CLEAR


def key_green(img: Image.Image) -> Image.Image:
    """Matte out a flat green backdrop and pull the green spill off the rim."""
    span = KEY_CLEAR - KEY_SOLID
    alpha = _greenness(img).point(
        lambda v: 255 if v <= KEY_SOLID else max(0, 255 - round((v - KEY_SOLID) * 255 / span))
    )
    r, g, b = img.split()
    # Despill: no pixel of the artwork should be greener than its own red/blue.
    ceiling = ImageChops.lighter(r, b).point(lambda v: min(255, v + KEY_SOLID))
    out = Image.merge('RGB', (r, ImageChops.darker(g, ceiling), b)).convert('RGBA')
    out.putalpha(alpha)
    return out


def _is_backdrop(px: tuple[int, int, int]) -> bool:
    r, g, b = px[:3]
    return min(r, g, b) >= 176 and max(r, g, b) - min(r, g, b) <= 26


def flood_backdrop(img: Image.Image) -> Image.Image:
    """Fallback for art drawn on the pale transparency checkerboard."""
    w, h = img.size
    px = img.load()
    alpha = Image.new('L', (w, h), 255)
    ap = alpha.load()
    seen = bytearray(w * h)
    queue: deque[tuple[int, int]] = deque()
    for x in range(w):
        queue.extend(((x, 0), (x, h - 1)))
    for y in range(h):
        queue.extend(((0, y), (w - 1, y)))
    while queue:
        x, y = queue.popleft()
        if not (0 <= x < w and 0 <= y < h):
            continue
        i = y * w + x
        if seen[i]:
            continue
        seen[i] = 1
        if not _is_backdrop(px[x, y]):
            continue
        ap[x, y] = 0
        queue.extend(((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)))
    alpha = alpha.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(0.7))
    out = img.convert('RGBA')
    out.putalpha(alpha)
    return out


def cut_out(img: Image.Image) -> Image.Image:
    img = img.convert('RGB')
    return key_green(img) if _is_chroma(img) else flood_backdrop(img)


def normalize(src: Path, dst: Path, height: int = HEIGHT,
              width: int = 0) -> tuple[int, int]:
    art = cut_out(Image.open(src))
    box = art.getbbox()
    if box:
        art = art.crop(box)
    # A lying sprite has no meaningful height -- her body runs across the
    # frame, not up it -- so those are fitted by length instead, or a pose
    # drawn loosely would come back a head taller than a tight one.
    if width and art.width != width:
        art = art.resize(
            (width, max(1, round(art.height * width / art.width))),
            Image.Resampling.LANCZOS,
        )
    elif height and art.height != height:
        w = max(1, round(art.width * height / art.height))
        art = art.resize((w, height), Image.Resampling.LANCZOS)
    dst.parent.mkdir(parents=True, exist_ok=True)
    art.save(dst)
    return art.size


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--src', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--height', type=int, default=HEIGHT, help='0 keeps the source height')
    args = parser.parse_args()
    dst = Path(args.out)
    if not dst.is_absolute():
        dst = ROOT / dst
    size = normalize(Path(args.src), dst, args.height)
    print(f'{dst} {size[0]}x{size[1]}')


if __name__ == '__main__':
    main()
