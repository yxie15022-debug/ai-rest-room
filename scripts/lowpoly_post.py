"""Publish per-model low-poly frames and gif previews.

Usage: python scripts/lowpoly_post.py [--src data/_lowpoly_render]
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'app' / 'static' / 'mascot' / 'lowpoly'
PLUGIN = ROOT / 'plugin' / 'frames' / 'mascot' / 'lowpoly'
PREVIEW = ROOT / 'docs' / 'preview'
REGISTRY = ROOT / 'data' / 'characters' / 'registry.json'
SCENES = ['enter', 'sit', 'sleep', 'study', 'chat']


def _models() -> list[str]:
    if REGISTRY.is_file():
        return list(json.loads(REGISTRY.read_text(encoding='utf-8')).keys())
    return ['default']


def _copy_frames(src_dir: Path, dst_dir: Path) -> int:
    frames = sorted(src_dir.glob('*.png'))
    if not frames:
        return 0
    if dst_dir.exists():
        shutil.rmtree(dst_dir)
    dst_dir.mkdir(parents=True, exist_ok=True)
    for frame in frames:
        shutil.copy2(frame, dst_dir / frame.name)
    return len(frames)


def _gif(frames: list[Path], out: Path) -> None:
    imgs = [Image.open(f).convert('RGB') for f in frames]
    gif = [im.convert('P', palette=Image.Palette.ADAPTIVE, colors=64) for im in imgs]
    out.parent.mkdir(parents=True, exist_ok=True)
    gif[0].save(out, save_all=True, append_images=gif[1:], duration=100, loop=0, optimize=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--src', default='data/_lowpoly_render')
    args = parser.parse_args()
    src = (ROOT / args.src).resolve()
    models = _models()
    # drop the flat scene folders and the old shared sit from the cat render
    for base in (APP, PLUGIN):
        if not base.is_dir():
            continue
        for child in list(base.iterdir()):
            if child.is_dir() and child.name not in models:
                shutil.rmtree(child)
    for model in models:
        for scene in SCENES:
            src_dir = src / model / scene
            n = _copy_frames(src_dir, APP / model / scene)
            _copy_frames(src_dir, PLUGIN / model / scene)
            frames = sorted(src_dir.glob('*.png'))
            if frames:
                _gif(frames, PREVIEW / f'lowpoly-{model}-{scene}.gif')
            print('published', model, scene, n)

    tile = 128
    sheet = Image.new(
        'RGB',
        (len(SCENES) * (tile + 8) + 8, len(models) * (tile + 22) + 8),
        (255, 255, 255),
    )
    draw = ImageDraw.Draw(sheet)
    for ri, model in enumerate(models):
        for ci, scene in enumerate(SCENES):
            frames = sorted((APP / model / scene).glob('*.png'))
            x = 8 + ci * (tile + 8)
            y = 8 + ri * (tile + 22)
            if frames:
                im = Image.open(frames[min(6, len(frames) - 1)]).convert('RGB')
                sheet.paste(im.resize((tile, tile), Image.Resampling.NEAREST), (x, y))
            draw.text((x + 2, y + tile + 2), f'{model}/{scene}', fill=(80, 76, 70))
    PREVIEW.mkdir(parents=True, exist_ok=True)
    sheet.save(PREVIEW / 'lowpoly-contact.png')
    print('contact sheet saved')


if __name__ == '__main__':
    main()
