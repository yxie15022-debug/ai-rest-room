"""Pixel room built from real hand-drawn asset packs (Stardew-grade detail).

Room: Cozy Farm Interiors (Spaceyyy) tiles/walls/furniture pasted onto a
512x512 canvas (16 tiles of 32px, 2x set; the bed comes from the 4x set
scaled to 96px so a cat actually fits in it). Cat: hand-placed black cat
sprites drawn here (pointy ears, scene-coloured scarf) — the asset-pack cat
looked like a bear cub. Code also draws the desk monitor, speech bubbles,
Zs, night dimming and the fireplace loop.

Asset packs live in assets/ (git-ignored). Output: room/<scene>/NNN.png in
app/static/mascot and plugin/frames/mascot, previews in docs/preview/.

Usage:
    python scripts/render_pixel_room.py --scenes enter,sit,sleep,study,chat --frames 20
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
APP_MASCOT = ROOT / 'app' / 'static' / 'mascot'
PLUGIN_MASCOT = ROOT / 'plugin' / 'frames' / 'mascot'
PREVIEW_DIR = ROOT / 'docs' / 'preview'
ASSETS = ROOT / 'assets'
INTERIOR = ASSETS / 'cozy-farm-interiors'
CAT_SHEET_PATH = ASSETS / 'cat-pack' / 'Free_Cat_Pack_By_Glem' / 'Cat_Sprite_Sheet_Black.png'

W = 512
SCALE = 1
SCENES = ['enter', 'sit', 'sleep', 'study', 'chat']

BLACK = (26, 24, 26)
BLACK_SOFT = (48, 45, 49)
EYE_GREEN = (126, 222, 146)
EYE_SHINE = (240, 250, 240)
SCARF = {
    'enter': (240, 196, 84),
    'sit': (74, 190, 140),
    'study': (86, 140, 230),
    'chat': (226, 86, 80),
    'sleep': (110, 110, 220),
}

NIGHT_TINT = (18, 22, 52)
NIGHT_ALPHA = 0.40
SCREEN = (58, 116, 198)
SCREEN_DARK = (44, 92, 162)
CODE_GREEN = (142, 230, 152)
CODE_DIM = (110, 180, 220)
MONITOR = (44, 46, 56)

_cache: dict[str, Image.Image] = {}


def piece(kind: str, name: str, scale: str = '2x') -> Image.Image:
    key = f'{kind}/{name}/{scale}'
    if key not in _cache:
        _cache[key] = Image.open(INTERIOR / kind / scale / f'{name}.png').convert('RGBA')
    return _cache[key]


def big_bed() -> Image.Image:
    """The 2x bed is a tiny single; downscale the 4x one to a proper 96px bed."""
    if 'bigbed' not in _cache:
        src = Image.open(INTERIOR / 'furniture' / '4x' / 'bed.png').convert('RGBA')
        _cache['bigbed'] = src.resize((96, 96), Image.Resampling.LANCZOS)
    return _cache['bigbed']


def paste(img: Image.Image, spr: Image.Image, x: int, y: int) -> None:
    img.paste(spr, (x, y), spr)


# ------------------------------------------------------ hand-placed cat sprites
# Drawn on the 512 canvas (~76px tall standing): pointy ears, belly shading,
# a scarf that takes the scene colour.

def _scarf(d, x, y, w, color):
    fold = tuple(int(c * 0.72) for c in color)
    d.rectangle([x, y, x + w, y + 8], fill=color)
    d.rectangle([x, y + 6, x + w, y + 8], fill=fold)


def cat_back(d, x, y, walk, scarf):
    """From behind (facing the desk). (x, y) = centre of feet."""
    bob = (walk % 2) * 2
    d.line([(x + 16, y - 16), (x + 26, y - 26 - bob)], fill=BLACK, width=6)
    d.ellipse([x - 20, y - 40 + bob, x + 20, y - 4], fill=BLACK)
    lx, rx = (-12, 10) if bob else (-14, 12)
    d.rectangle([x + lx, y - 8, x + lx + 8, y], fill=BLACK)
    d.rectangle([x + rx, y - 8, x + rx + 8, y], fill=BLACK)
    d.ellipse([x - 18, y - 68 + bob, x + 18, y - 34 + bob], fill=BLACK)
    d.polygon([(x - 18, y - 58 + bob), (x - 12, y - 78 + bob), (x - 4, y - 60 + bob)], fill=BLACK)
    d.polygon([(x + 4, y - 60 + bob), (x + 12, y - 78 + bob), (x + 18, y - 58 + bob)], fill=BLACK)
    _scarf(d, x - 14, y - 38 + bob, 28, scarf)


def cat_front(d, x, y, blink, scarf, breath=0, walk=None):
    """Facing the camera, sitting (walk=None) or walking toward us."""
    by = breath * 2
    d.line([(x + 18, y - 8), (x + 30, y - 6), (x + 32, y - 14)], fill=BLACK, width=6)
    if walk is None:
        d.ellipse([x - 24, y - 26, x + 24, y], fill=BLACK)
        d.ellipse([x - 18, y - 44 - by, x + 18, y - 14], fill=BLACK)
        d.ellipse([x - 12, y - 28 - by, x + 12, y - 16], fill=BLACK_SOFT)
        d.rectangle([x - 14, y - 8, x - 6, y], fill=BLACK_SOFT)
        d.rectangle([x + 6, y - 8, x + 14, y], fill=BLACK_SOFT)
        hy = y - 78 - by
    else:
        step = walk % 2
        d.ellipse([x - 20, y - 48 + step * 2, x + 20, y - 12], fill=BLACK)
        d.ellipse([x - 14, y - 32 + step * 2, x + 14, y - 16], fill=BLACK_SOFT)
        d.rectangle([x - 16, y - 12 - step * 4, x - 6, y], fill=BLACK)
        d.rectangle([x + 6, y - 12 + step * 4 - 4, x + 16, y - step * 4], fill=BLACK)
        hy = y - 84 + step * 2
    d.ellipse([x - 20, hy, x + 20, hy + 36], fill=BLACK)
    d.polygon([(x - 20, hy + 8), (x - 14, hy - 10), (x - 6, hy + 2)], fill=BLACK)
    d.polygon([(x + 6, hy + 2), (x + 14, hy - 10), (x + 20, hy + 8)], fill=BLACK)
    d.polygon([(x - 14, hy + 4), (x - 12, hy - 4), (x - 8, hy + 4)], fill=BLACK_SOFT)
    d.polygon([(x + 8, hy + 4), (x + 12, hy - 4), (x + 14, hy + 4)], fill=BLACK_SOFT)
    if blink:
        d.rectangle([x - 14, hy + 18, x - 6, hy + 20], fill=EYE_GREEN)
        d.rectangle([x + 6, hy + 18, x + 14, hy + 20], fill=EYE_GREEN)
    else:
        d.ellipse([x - 14, hy + 14, x - 6, hy + 24], fill=EYE_GREEN)
        d.ellipse([x + 6, hy + 14, x + 14, hy + 24], fill=EYE_GREEN)
        d.rectangle([x - 12, hy + 16, x - 10, hy + 18], fill=EYE_SHINE)
        d.rectangle([x + 8, hy + 16, x + 10, hy + 18], fill=EYE_SHINE)
    d.rectangle([x - 2, hy + 26, x + 2, hy + 28], fill=BLACK_SOFT)
    sy = y - 32 - by if walk is None else y - 52 + (walk % 2) * 2
    _scarf(d, x - 16, sy, 32, scarf)


def cat_side(d, x, y, flip, walk, scarf):
    """Sideways. flip=True faces left."""
    bob = (walk % 2) * 2
    xm = -1 if flip else 1
    d.ellipse([x - 22, y - 30 + bob, x + 22, y - 4], fill=BLACK)
    d.ellipse([x - 16, y - 20 + bob, x + 16, y - 6], fill=BLACK_SOFT)
    hx = x - 30 if flip else x + 8
    d.ellipse([hx, y - 52 + bob, hx + 26, y - 22 + bob], fill=BLACK)
    ear_x = hx + 4 if flip else hx + 14
    d.polygon([(ear_x, y - 44 + bob), (ear_x + 6, y - 60 + bob), (ear_x + 12, y - 42 + bob)], fill=BLACK)
    d.polygon([(ear_x + 2, y - 44 + bob), (ear_x + 6, y - 54 + bob), (ear_x + 10, y - 44 + bob)], fill=BLACK_SOFT)
    ex = hx + 4 if flip else hx + 18
    d.ellipse([ex, y - 42 + bob, ex + 6, y - 34 + bob], fill=EYE_GREEN)
    tx0 = x - 22 * xm
    d.line([(tx0, y - 20), (tx0 - 12 * xm, y - 32 - bob)], fill=BLACK, width=6)
    for i, off in enumerate((-14, 6)):
        leg_h = 8 if (i + walk) % 2 == 0 else 10
        d.rectangle([x + off, y - leg_h, x + off + 8, y], fill=BLACK)
    _scarf(d, hx + 2, y - 28 + bob, 22, scarf)


def cat_sleeping(d, x, y, breath, scarf):
    """Curled up asleep. (x, y) = centre."""
    by = breath * 2
    d.ellipse([x - 34, y - 20 - by, x + 34, y + 20], fill=BLACK)
    d.ellipse([x - 22, y - 12 - by, x + 22, y + 14], fill=BLACK_SOFT)
    d.ellipse([x - 44, y - 16 - by, x - 8, y + 12], fill=BLACK)
    d.polygon([(x - 42, y - 8 - by), (x - 36, y - 24 - by), (x - 24, y - 10 - by)], fill=BLACK)
    d.line([(x - 32, y - 2 - by), (x - 24, y - 2 - by)], fill=(200, 198, 192), width=2)
    d.line([(x + 32, y + 8), (x + 42, y + 16), (x + 26, y + 22)], fill=BLACK, width=6)
    _scarf(d, x - 12, y - 20 - by, 24, scarf)


# --------------------------------------------------------------- room build

def build_room(f: int, fire_frame: int | None) -> Image.Image:
    img = Image.new('RGB', (W, W), (0, 0, 0))

    floor_img = piece('tiles', 'floor-wood-honey')
    for ty in range(14):
        for tx in range(16):
            paste(img, floor_img, tx * 32, 64 + ty * 32)

    # back wall: sage wallpaper, two windows, one door
    for tx in range(16):
        if tx in (3, 4, 8, 9):
            wall = piece('walls', 'wall-sage-window')
        elif tx == 12:
            wall = piece('walls', 'wall-sage-door')
        else:
            wall = piece('walls', 'wall-sage')
        paste(img, wall, tx * 32, 0)

    # frame strip on the very top edge gives the wall its thickness
    for tx in range(16):
        paste(img, piece('frame', 'frame-n'), tx * 32, 0)
    paste(img, piece('frame', 'frame-nw'), 0, 0)
    paste(img, piece('frame', 'frame-ne'), 480, 0)

    # wall decorations
    paste(img, piece('furniture', 'painting'), 192, 28)
    paste(img, piece('furniture', 'wall-clock'), 320, 16)

    # furniture (each sits on the bottom edge of its own canvas)
    paste(img, big_bed(), 24, 76)
    paste(img, piece('furniture', 'floor-lamp'), 132, 112)
    if fire_frame is None:
        paste(img, piece('furniture', 'bookshelf'), 160, 80)
    else:
        paste(img, piece('furniture', f'fireplace-frame{fire_frame + 1}'), 160, 80)
    paste(img, piece('furniture', 'table'), 400, 104)
    paste(img, piece('furniture', 'chair'), 420, 148)
    paste(img, piece('furniture', 'cupboard'), 468, 80)
    paste(img, piece('furniture', 'sofa'), 408, 256)
    paste(img, piece('furniture', 'rug-round'), 216, 264)
    paste(img, piece('furniture', 'cat-bed'), 88, 312)
    paste(img, piece('furniture', 'potted-plant'), 28, 432)
    paste(img, piece('furniture', 'flower-vase'), 480, 200)
    return img


def apply_night(img: Image.Image) -> Image.Image:
    return Image.blend(img, Image.new('RGB', img.size, NIGHT_TINT), NIGHT_ALPHA)


# --------------------------------------------------- dynamic drawn elements

def draw_monitor(img: Image.Image, f: int) -> None:
    """Little monitor on the desk, screen facing the camera, code scrolling."""
    d = ImageDraw.Draw(img)
    x0, y0 = 416, 80
    d.rectangle([x0, y0, x0 + 35, y0 + 25], fill=MONITOR, outline=(26, 27, 34))
    d.rectangle([x0 + 3, y0 + 3, x0 + 32, y0 + 22], fill=SCREEN)
    d.rectangle([x0 + 3, y0 + 3, x0 + 32, y0 + 7], fill=SCREEN_DARK)
    for i in range(4):
        length = 8 + (i * 5 + f * 2) % 16
        color = CODE_GREEN if i % 2 == 0 else CODE_DIM
        d.rectangle([x0 + 5, y0 + 10 + i * 3, x0 + 5 + length, y0 + 11 + i * 3], fill=color)


def draw_bubbles(d: ImageDraw.ImageDraw, f: int) -> None:
    def bubble(x, y, w, h, kind):
        d.rectangle([x, y, x + w, y + h], fill=(252, 252, 250), outline=(120, 118, 116))
        d.polygon([(x + w - 10, y + h), (x + w, y + h), (x + w + 6, y + h + 8)], fill=(252, 252, 250))
        if kind == 'dots':
            for i in range(3):
                d.ellipse([x + 8 + i * 10, y + h // 2 - 2, x + 12 + i * 10, y + h // 2 + 2], fill=(150, 148, 144))
        elif kind == 'heart':
            hx, hy = x + w // 2, y + h // 2
            d.rectangle([hx - 6, hy - 3, hx - 1, hy + 2], fill=(226, 86, 80))
            d.rectangle([hx + 1, hy - 3, hx + 6, hy + 2], fill=(226, 86, 80))
            d.rectangle([hx - 4, hy + 2, hx + 4, hy + 5], fill=(226, 86, 80))
            d.rectangle([hx - 2, hy + 5, hx + 2, hy + 8], fill=(226, 86, 80))
        else:
            for i in range(2):
                d.rectangle([x + 6, y + 6 + i * 8, x + w - 8 - i * 8, y + 8 + i * 8], fill=(170, 168, 164))

    if f >= 2:
        bubble(320, 216, 52, 20, 'lines')
    if f >= 5:
        bubble(348, 188, 44, 20, 'dots')
    if f >= 8:
        bubble(316, 160, 48, 24, 'heart')


def draw_zzz(d: ImageDraw.ImageDraw, f: int, x: int, y: int) -> None:
    color = (226, 222, 214)
    for i in range(3):
        t = (f + i * 5) % 15
        zx, zy = x + i * 12 + t // 4, y - t * 4
        size = 6 + i * 2
        d.line([(zx, zy), (zx + size, zy)], fill=color, width=2)
        d.line([(zx + size, zy), (zx, zy + size)], fill=color, width=2)
        d.line([(zx, zy + size), (zx + size, zy + size)], fill=color, width=2)


# ------------------------------------------------------------- scene frames

def frame_enter(f: int) -> Image.Image:
    img = build_room(f, fire_frame=None)
    draw_monitor(img, f)
    d = ImageDraw.Draw(img)
    if f < 2:
        return img
    if f < 8:
        t = (f - 2) / 5.0
        x = int(384 - 140 * t)
        y = int(104 + 168 * t)
        cat_front(d, x, y, blink=False, scarf=SCARF['enter'], walk=f)
    else:
        cat_front(d, 248, 296, blink=(f == 9), scarf=SCARF['enter'], breath=(f % 2))
    return img


def frame_sit(f: int) -> Image.Image:
    img = build_room(f, fire_frame=None)
    draw_monitor(img, f)
    d = ImageDraw.Draw(img)
    breath = 1 if (f // 5) % 2 == 0 else 0
    cat_front(d, 122, 332, blink=(f == 8), scarf=SCARF['sit'], breath=breath)
    return img


def frame_sleep(f: int) -> Image.Image:
    img = build_room(f, fire_frame=f % 3)
    img = apply_night(img)
    d = ImageDraw.Draw(img)
    breath = 1 if (f // 5) % 2 == 0 else 0
    cat_sleeping(d, 74, 122, breath, SCARF['sleep'])
    draw_zzz(d, f, 108, 74)
    return img


def frame_study(f: int) -> Image.Image:
    img = build_room(f, fire_frame=None)
    draw_monitor(img, f)
    d = ImageDraw.Draw(img)
    breath = 1 if (f // 5) % 2 == 0 else 0
    cat_back(d, 420, 178, walk=0 if breath else 0, scarf=SCARF['study'])
    return img


def frame_chat(f: int) -> Image.Image:
    img = build_room(f, fire_frame=None)
    draw_monitor(img, f)
    d = ImageDraw.Draw(img)
    cat_side(d, 424, 296, flip=True, walk=0, scarf=SCARF['chat'])
    draw_bubbles(d, f)
    return img


FRAME_FN = {
    'enter': frame_enter,
    'sit': frame_sit,
    'sleep': frame_sleep,
    'study': frame_study,
    'chat': frame_chat,
}


# -------------------------------------------------------------------- driver

def save_previews(scene, frames):
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    gif = [im.convert('P', palette=Image.Palette.ADAPTIVE, colors=64) for im in frames]
    gif[0].save(
        PREVIEW_DIR / f'room-{scene}.gif',
        save_all=True,
        append_images=gif[1:],
        duration=100,
        loop=0,
        optimize=True,
    )


def contact():
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    tiles = []
    for scene in SCENES:
        frames = sorted((APP_MASCOT / 'room' / scene).glob('*.png'))
        if not frames:
            continue
        pick = frames[min(14, len(frames) - 1)]
        tiles.append((scene, Image.open(pick).convert('RGB')))
    cols = 3
    rows = (len(tiles) + cols - 1) // cols
    sheet = Image.new('RGB', (cols * 300 + 20, rows * 320 + 20), (255, 255, 255))
    d = ImageDraw.Draw(sheet)
    for i, (scene, tile) in enumerate(tiles):
        x = 10 + (i % cols) * 300
        y = 10 + (i // cols) * 320
        sheet.paste(tile.resize((280, 280), Image.Resampling.NEAREST), (x, y))
        d.text((x + 6, y + 284), scene, fill=(80, 76, 70))
    sheet.save(PREVIEW_DIR / 'room-contact.png')


def render(scenes, frames, outdir):
    targets = [outdir] if outdir else [APP_MASCOT / 'room', PLUGIN_MASCOT / 'room']
    for scene in scenes:
        for base in targets:
            shutil.rmtree(base / scene, ignore_errors=True)
            (base / scene).mkdir(parents=True, exist_ok=True)
        rendered = []
        for f in range(frames):
            logic = f // 2 if frames > 10 else f
            im = FRAME_FN[scene](logic)
            if SCALE != 1:
                im = im.resize((W * SCALE, W * SCALE), Image.Resampling.NEAREST)
            rendered.append(im)
            for base in targets:
                im.save(base / scene / f'{f + 1:03d}.png')
        if not outdir:
            save_previews(scene, rendered)
    if not outdir:
        contact()


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--scenes', default=','.join(SCENES))
    parser.add_argument('--frames', type=int, default=20)
    parser.add_argument('--outdir', default=None)
    args = parser.parse_args(argv)
    scenes = [s for s in args.scenes.split(',') if s]
    render(scenes, args.frames, Path(args.outdir) if args.outdir else None)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
