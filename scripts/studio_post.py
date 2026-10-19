"""Copy Blender-rendered studio frames into both frame dirs and rebuild previews."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'data' / '_studio_render'
APP = ROOT / 'app' / 'static' / 'mascot' / 'studio'
PLUGIN = ROOT / 'plugin' / 'frames' / 'mascot' / 'studio'
PREVIEW = ROOT / 'docs' / 'preview'
SCENES = ['enter', 'sit', 'study', 'chat', 'sleep']


def publish() -> None:
    for scene in SCENES:
        frames = sorted((SRC / scene).glob('*.png'))
        if not frames:
            print(f'skip {scene}: no frames')
            continue
        for base in (APP, PLUGIN):
            target = base / scene
            shutil.rmtree(target, ignore_errors=True)
            target.mkdir(parents=True, exist_ok=True)
            for index, frame in enumerate(frames, start=1):
                shutil.copy2(frame, target / f'{index:03d}.png')
        print(f'{scene}: {len(frames)} frames')


def previews() -> None:
    PREVIEW.mkdir(parents=True, exist_ok=True)
    tiles = []
    for scene in SCENES:
        frames = sorted((APP / scene).glob('*.png'))
        if not frames:
            continue
        images = [Image.open(f).convert('RGB') for f in frames]
        gif = [im.convert('P', palette=Image.Palette.ADAPTIVE, colors=128) for im in images]
        gif[0].save(PREVIEW / f'studio-{scene}.gif', save_all=True, append_images=gif[1:], duration=55, loop=0, optimize=True)
        pick_index = {'chat': 6, 'enter': max(0, len(images) - 7), 'sleep': 6, 'study': 2, 'sit': 2}.get(scene, 2)
        tiles.append((scene, images[min(pick_index, len(images) - 1)].resize((480, 480), Image.Resampling.LANCZOS)))
    cell = 520
    sheet = Image.new('RGB', (cell * 2 + 20, cell * 2 + 20), (255, 255, 255))
    draw = ImageDraw.Draw(sheet)
    for index, (scene, tile) in enumerate(tiles[:4]):
        x = 10 + (index % 2) * cell + 20
        y = 10 + (index // 2) * cell + 20
        sheet.paste(tile, (x, y))
        draw.text((x + 8, y + 440), scene, fill=(90, 90, 86))
    sheet.save(PREVIEW / 'studio-contact.png')
    print('previews rebuilt')


def main() -> int:
    if '--previews-only' in sys.argv:
        previews()
        return 0
    publish()
    previews()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
