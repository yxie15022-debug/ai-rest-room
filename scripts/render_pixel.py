
"""Pixel-art rest-room mascot frames.

A 128x128 logical canvas, limited palette, hard pixel edges (nearest-neighbour
x4 -> 512), ten-frame loops. Scenes: sit, study, chat, sleep, enter.
Output: <animal>/<scene>/NNN.png in app/static and plugin/frames + previews.

Usage:
    python scripts/render_pixel.py --scenes sleep,sit,study,chat,enter --frames 10
"""

from __future__ import annotations

import argparse
import math
import shutil
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
APP_MASCOT = ROOT / 'app' / 'static' / 'mascot'
PLUGIN_MASCOT = ROOT / 'plugin' / 'frames' / 'mascot'
PREVIEW_DIR = ROOT / 'docs' / 'preview'

W = 128
SCALE = 4

BG = (246, 242, 234)
BG_DARK = (238, 233, 223)
WHITE = (252, 250, 245)
WHITE_SHADE = (236, 231, 220)
WHITE_EDGE = (222, 216, 204)
SHADOW = (210, 204, 192)
BLACK = (22, 20, 22)
BLACK_EDGE = (12, 11, 13)
INK = (54, 52, 56)
SCREEN_BLUE = (74, 144, 226)
SCREEN_BLUE_D = (56, 118, 190)
SCREEN_LIGHT = (214, 233, 252)
DARK_SCREEN = (30, 34, 46)
DARK_LINE = (56, 62, 78)
SCARF = {
    'enter': (240, 196, 84),
    'sit': (74, 190, 140),
    'study': (86, 140, 230),
    'chat': (226, 86, 80),
    'sleep': (110, 110, 220),
}
SCENES = ['enter', 'sit', 'study', 'chat', 'sleep']


def rect(draw, x0, y0, x1, y1, fill, outline=None):
    draw.rectangle([x0, y0, x1, y1], fill=fill, outline=outline)


def ell(draw, x0, y0, x1, y1, fill, outline=None):
    draw.ellipse([x0, y0, x1, y1], fill=fill, outline=outline)


def line(draw, points, fill, width=1):
    draw.line(points, fill=fill, width=width)


# ---------------------------------------------------------------- environment

def background(draw):
    rect(draw, 0, 0, W - 1, W - 1, BG)
    # a barely-there floor line so the chair has somewhere to stand
    rect(draw, 0, 112, W - 1, W - 1, BG)


def shadow(draw):
    for y in range(104, 116):
        for x in range(40, 88):
            if (x + y) % 3 == 0:
                draw.point((x, y), fill=SHADOW)
    rect(draw, 30, 116, 100, 117, SHADOW)
    for x in range(38, 92, 4):
        draw.point((x, 118), fill=SHADOW)


def desk(draw):
    # legs
    rect(draw, 24, 84, 29, 116, WHITE_SHADE)
    rect(draw, 99, 84, 104, 116, WHITE_SHADE)
    rect(draw, 24, 84, 25, 116, WHITE_EDGE)
    rect(draw, 99, 84, 100, 116, WHITE_EDGE)
    # cabinet
    rect(draw, 98, 70, 114, 112, WHITE)
    rect(draw, 98, 70, 114, 112, WHITE_EDGE)
    rect(draw, 100, 72, 112, 90, WHITE)
    rect(draw, 100, 94, 112, 110, WHITE)
    rect(draw, 100, 90, 112, 91, WHITE_EDGE)
    rect(draw, 106, 78, 108, 79, WHITE_EDGE)
    rect(draw, 106, 100, 108, 101, WHITE_EDGE)
    # top
    rect(draw, 18, 76, 110, 85, WHITE)
    rect(draw, 18, 76, 110, 77, (255, 255, 255))
    rect(draw, 18, 85, 110, 86, WHITE_EDGE)
    rect(draw, 18, 76, 19, 86, WHITE_EDGE)
    rect(draw, 109, 76, 110, 86, WHITE_EDGE)


def monitor(draw, scene, f):
    # stand + base
    rect(draw, 72, 54, 78, 75, WHITE_SHADE)
    rect(draw, 64, 74, 86, 77, WHITE)
    rect(draw, 64, 77, 86, 78, WHITE_EDGE)
    # bezel
    rect(draw, 46, 14, 104, 54, WHITE)
    rect(draw, 46, 14, 104, 54, WHITE_EDGE)
    rect(draw, 47, 15, 103, 53, WHITE)
    rect(draw, 49, 17, 101, 51, (232, 232, 230))
    screen(draw, 50, 18, 100, 50, scene, f)


def screen(draw, x0, y0, x1, y1, scene, f):
    w, h = x1 - x0, y1 - y0
    if scene == 'sleep':
        rect(draw, x0, y0, x1, y1, DARK_SCREEN)
        ell(draw, x1 - 14, y0 + 4, x1 - 6, y0 + 12, DARK_LINE)
        ell(draw, x1 - 12, y0 + 3, x1 - 4, y0 + 11, DARK_SCREEN)
        for i in range(4):
            rect(draw, x0 + 4, y0 + 6 + i * 5, x0 + 14 + i * 4, y0 + 7 + i * 5, DARK_LINE)
        return
    if scene == 'enter':
        rect(draw, x0, y0, x1, y1, WHITE_SHADE)
        rect(draw, x0 + 18, y0 + 8, x0 + 32, y0 + 22, SCREEN_BLUE)
        rect(draw, x0 + 22, y0 + 12, x0 + 28, y0 + 18, WHITE)
        rect(draw, x0 + 6, y1 - 8, x1 - 6, y1 - 4, (226, 226, 222))
        fill = 8 + int((w - 24) * min(1.0, f / 6.0))
        rect(draw, x0 + 6, y1 - 8, x0 + 6 + fill, y1 - 4, SCREEN_BLUE)
        return
    # blue desktop UI
    rect(draw, x0, y0, x1, y1, SCREEN_BLUE)
    rect(draw, x0, y0, x1, y0 + 4, SCREEN_BLUE_D)
    for i in range(3):
        rect(draw, x0 + 3 + i * 4, y0 + 1, x0 + 3 + i * 4, y0 + 1, (240, 246, 255))
    rect(draw, x0 + 4, y0 + 6, x1 - 4, y1 - 3, (250, 250, 248))
    rect(draw, x0 + 4, y0 + 6, x1 - 4, y0 + 9, (236, 236, 232))
    if scene == 'study':
        pts = []
        for i in range(8):
            px = x0 + 6 + i * ((w - 14) / 7)
            py = y0 + 26 - (4 if (i + f // 3) % 3 == 0 else 0)
            pts.append((px, py))
        line(draw, pts, SCREEN_BLUE)
        for i in range(4):
            bh = 3 + (i * 2 + f) % 5
            rect(draw, x0 + 7 + i * 6, y1 - 5 - bh, x0 + 10 + i * 6, y1 - 5, SCREEN_LIGHT)
    elif scene == 'chat':
        bubbles = [(x0 + 6, y0 + 12, x0 + 30, y0 + 19, (228, 228, 224)),
                   (x1 - 26, y0 + 22, x1 - 6, y0 + 29, SCREEN_BLUE),
                   (x0 + 8, y0 + 32, x0 + 24, y0 + 39, (228, 228, 224))]
        for i, (a, b, c, d, col) in enumerate(bubbles):
            if f >= 1 + i * 2:
                rect(draw, a, b, c, d, col)
                for dot in range(3):
                    rect(draw, a + 3 + dot * 4, b + 3, a + 4 + dot * 4, b + 4, (150, 150, 146))
    else:  # sit / idle: file list
        for row in range(5):
            y = y0 + 12 + row * 5
            rect(draw, x0 + 6, y, x0 + 8, y + 1, SCREEN_BLUE if row % 2 == 0 else SCREEN_LIGHT)
            rect(draw, x0 + 10, y, x0 + 22 + (row % 3) * 4, y + 1, (216, 216, 212))
            rect(draw, x1 - 18, y, x1 - 6, y + 1, (230, 230, 226))


# ---------------------------------------------------------------- character

def cat(draw, scene, f, visible=True):
    if not visible:
        return
    t = f / 10.0
    bob = 1 if scene != 'sleep' and 3 <= f <= 6 else 0
    head_drop = 3 if scene == 'sleep' else 0
    black = BLACK

    # tail
    line(draw, [(80, 86), (86, 80), (90, 82)], black, 3)
    # arms resting on the desk top
    ell(draw, 33, 70, 49, 80, black)
    ell(draw, 79, 70, 95, 80, black)
    rect(draw, 33, 77, 95, 80, BLACK_EDGE)
    # body
    ell(draw, 48, 58 + bob, 80, 94 + bob, black)
    rect(draw, 48, 78 + bob, 80, 88 + bob, black)
    # scarf: solid cloth band with a fold
    scarf_color = SCARF.get(scene, SCARF['sit'])
    fold = tuple(int(c * 0.72) for c in scarf_color)
    shine = tuple(min(255, int(c * 1.18)) for c in scarf_color)
    top = 61 + bob + head_drop
    rect(draw, 49, top, 79, top + 6, scarf_color)
    rect(draw, 49, top + 5, 79, top + 6, fold)
    rect(draw, 49, top, 79, top, shine)
    rect(draw, 60, top + 2, 61, top + 5, fold)
    # head (drawn after the scarf so it sits above the collar)
    ell(draw, 53, 42 + bob + head_drop, 75, 64 + bob + head_drop, black)
    # solid ears
    off = bob + head_drop
    draw.polygon([(54, 47 + off), (56, 33 + off), (63, 44 + off)], fill=black)
    draw.polygon([(65, 44 + off), (72, 33 + off), (74, 47 + off)], fill=black)
    # notch between the ears shows whatever is behind (screen colour)
    back = {'sleep': DARK_SCREEN, 'enter': WHITE_SHADE}.get(scene, SCREEN_BLUE)
    draw.polygon([(62, 44 + off), (64, 37 + off), (66, 44 + off)], fill=back)
    # sleeping closed eye hint on the side
    if scene == 'sleep':
        rect(draw, 54, 54, 58, 55, (238, 236, 230))
        rect(draw, 61, 55, 65, 56, (238, 236, 230))
        # pixel Zs floating over the dark screen
        zcolor = (224, 220, 212)
        for i in range(3):
            zy = 44 - i * 7 - (f * 2 + i * 3) % 8
            zx = 76 + i * 6 + (f + i) % 3
            if zy < 20:
                zy += 20
            rect(draw, zx, zy, zx + 5, zy + 1, zcolor)
            rect(draw, zx + 3, zy + 1, zx + 4, zy + 2, zcolor)
            rect(draw, zx + 2, zy + 2, zx + 3, zy + 3, zcolor)
            rect(draw, zx, zy + 3, zx + 5, zy + 4, zcolor)


def chair(draw, scene):
    # seat in front of the cat's lower body
    rect(draw, 46, 92, 82, 100, WHITE)
    rect(draw, 46, 92, 82, 93, (255, 255, 255))
    rect(draw, 46, 99, 82, 100, WHITE_EDGE)
    rect(draw, 46, 92, 47, 100, WHITE_EDGE)
    rect(draw, 81, 92, 82, 100, WHITE_EDGE)
    # post and star base
    rect(draw, 62, 100, 66, 108, WHITE_SHADE)
    rect(draw, 62, 100, 63, 108, WHITE_EDGE)
    rect(draw, 52, 108, 76, 110, WHITE)
    rect(draw, 52, 110, 76, 111, WHITE_EDGE)
    for x in (50, 58, 70, 78):
        rect(draw, x, 111, x + 2, 114, WHITE_SHADE)
        rect(draw, x, 114, x + 3, 115, WHITE_EDGE)


def frame(scene, f):
    img = Image.new('RGB', (W, W), BG)
    draw = ImageDraw.Draw(img)
    background(draw)
    shadow(draw)
    desk(draw)
    monitor(draw, scene, f)
    visible = scene != 'enter' or f >= 2
    cat(draw, scene, f, visible)
    chair(draw, scene)
    return img.resize((W * SCALE, W * SCALE), Image.Resampling.NEAREST)


def save_previews(scene, frames, base):
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    gif = [im.convert('P', palette=Image.Palette.ADAPTIVE, colors=64) for im in frames]
    gif[0].save(PREVIEW_DIR / f'pixel-{scene}.gif', save_all=True, append_images=gif[1:], duration=120, loop=0, optimize=True)


def contact():
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    tiles = []
    for scene in SCENES:
        frames = sorted((APP_MASCOT / 'pixel' / scene).glob('*.png'))
        if not frames:
            continue
        pick_index = {'enter': 12, 'chat': 6, 'sleep': 6, 'study': 2, 'sit': 2}.get(scene, 2)
        pick = frames[min(pick_index, len(frames) - 1)]
        tiles.append((scene, Image.open(pick).convert('RGB').resize((480, 480), Image.Resampling.NEAREST)))
    sheet = Image.new('RGB', (1060, 1060), (255, 255, 255))
    draw = ImageDraw.Draw(sheet)
    for i, (scene, tile) in enumerate(tiles[:4]):
        x = 20 + (i % 2) * 520
        y = 20 + (i // 2) * 520
        sheet.paste(tile, (x, y))
        draw.text((x + 6, y + 450), scene, fill=(80, 76, 70))
    sheet.save(PREVIEW_DIR / 'pixel-contact.png')


def render(scenes, frames, outdir):
    targets = [outdir] if outdir else [APP_MASCOT / 'pixel', PLUGIN_MASCOT / 'pixel']
    for scene in scenes:
        for base in targets:
            shutil.rmtree(base / scene, ignore_errors=True)
            (base / scene).mkdir(parents=True, exist_ok=True)
        rendered = []
        for f in range(frames):
            logic = f // 2 if frames > 10 else f
            im = frame(scene, logic)
            rendered.append(im)
            for base in targets:
                im.save(base / scene / f'{f + 1:03d}.png')
        if not outdir:
            save_previews(scene, rendered, targets[0])
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
