"""Turn a generated still/video into the mascot frames the room already plays.

Two kinds of input:
  * a video clip (mp4 / webm / mov / mkv), frames are extracted with ffmpeg
  * a directory of images, used in filename order

Every frame is centre-cropped to a square, resized, and written as
<animal>/<scene>/NNN.png into both app/static/mascot and plugin/frames/mascot,
replacing the old frames for that scene. Optional preview GIF goes to
docs/preview/<animal>-<scene>.gif.

Examples:
    python scripts/ingest_animation.py --input cat-sit.mp4 --scene sit
    python scripts/ingest_animation.py --input frames/sit --scene sit --fps 24
    python scripts/ingest_animation.py --input cat-study.mp4 --scene study --size 512

Requires Pillow (requirements-dev.txt). Videos additionally need ffmpeg on PATH.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
APP_MASCOT = ROOT / 'app' / 'static' / 'mascot'
PLUGIN_MASCOT = ROOT / 'plugin' / 'frames' / 'mascot'
PREVIEW_DIR = ROOT / 'docs' / 'preview'
IMAGE_SUFFIXES = ('.png', '.jpg', '.jpeg', '.webp')
VIDEO_SUFFIXES = ('.mp4', '.webm', '.mov', '.mkv', '.avi')


def fail(message: str) -> None:
    print(f'error: {message}', file=sys.stderr)
    raise SystemExit(1)


def image_paths(source: Path, fps: float):
    if source.is_dir():
        files = sorted(
            path for path in source.iterdir() if path.suffix.lower() in IMAGE_SUFFIXES
        )
        if not files:
            fail(f'no images under {source}')
        return files

    if source.suffix.lower() in IMAGE_SUFFIXES:
        return [source]

    if source.suffix.lower() in VIDEO_SUFFIXES:
        ffmpeg = shutil.which('ffmpeg')
        if not ffmpeg:
            fail('ffmpeg not found on PATH; install it or pass a directory of images instead')
        temp = Path(tempfile.mkdtemp(prefix='rest-room-frames-'))
        command = [
            ffmpeg,
            '-hide_banner',
            '-loglevel',
            'error',
            '-i',
            str(source),
            '-vf',
            f'fps={fps:g}',
            str(temp / 'frame_%04d.png'),
        ]
        try:
            subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except subprocess.CalledProcessError:
            shutil.rmtree(temp, ignore_errors=True)
            fail(f'ffmpeg could not extract frames from {source}')
        files = sorted(temp.glob('frame_*.png'))
        if not files:
            shutil.rmtree(temp, ignore_errors=True)
            fail(f'ffmpeg extracted no frames from {source}')
        return files, temp  # type: ignore[return-value]

    fail(f'unsupported input: {source} (expected a video or image directory)')


def load_frames(paths: list[Path], size: int) -> list[Image.Image]:
    frames: list[Image.Image] = []
    for path in paths:
        image = Image.open(path)
        image = ImageOps.exif_transpose(image).convert('RGB')
        frames.append(ImageOps.fit(image, (size, size), Image.Resampling.LANCZOS))
    return frames


def write_frames(frames: list[Image.Image], animal: str, scene: str, targets: list[Path], preview: bool) -> None:
    for base in targets:
        folder = base / animal / scene
        shutil.rmtree(folder, ignore_errors=True)
        folder.mkdir(parents=True, exist_ok=True)
        for index, frame in enumerate(frames, start=1):
            frame.save(folder / f'{index:03d}.png')
    if preview:
        PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
        gif_frames = [frame.convert('P', palette=Image.Palette.ADAPTIVE, colors=128) for frame in frames]
        gif_frames[0].save(
            PREVIEW_DIR / f'{animal}-{scene}.gif',
            save_all=True,
            append_images=gif_frames[1:],
            duration=70,
            loop=0,
            optimize=True,
        )
    print(f'{animal}/{scene}: wrote {len(frames)} frames to ' + ', '.join(str(base) for base in targets))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Ingest generated animation frames')
    parser.add_argument('--input', required=True, help='video file or directory of images')
    parser.add_argument('--scene', required=True)
    parser.add_argument('--animal', default='cat')
    parser.add_argument('--size', type=int, default=512)
    parser.add_argument('--fps', type=float, default=12.0, help='frame rate for video input')
    parser.add_argument('--targets', choices=('both', 'app', 'plugin'), default='both')
    parser.add_argument('--no-preview', action='store_true')
    args = parser.parse_args(argv)

    source = Path(args.input).expanduser()
    if not source.exists():
        fail(f'input not found: {source}')

    targets = [APP_MASCOT, PLUGIN_MASCOT]
    if args.targets == 'app':
        targets = [APP_MASCOT]
    elif args.targets == 'plugin':
        targets = [PLUGIN_MASCOT]

    result = image_paths(source, args.fps)
    temp: Path | None = None
    if isinstance(result, tuple):
        paths, temp = result
    else:
        paths = result
    try:
        frames = load_frames(paths, args.size)
        if len(frames) < 2:
            fail('need at least two frames for a loop')
        write_frames(frames, args.animal, args.scene, targets, not args.no_preview)
    finally:
        if temp is not None:
            shutil.rmtree(temp, ignore_errors=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
