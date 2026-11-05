"""Turn generated green-screen footage into transparent sprite clips.

The video generator hands back opaque MP4, so characters are filmed against the
same flat chroma-key green as the stills and keyed out here, frame by frame,
with the same matte. The result is VP9-with-alpha WebM, which every Chromium
plays with its transparency intact -- the room shows through behind her.

Sources are `assets/clips/{model}-{action}.mp4`; the stage reads
`app/static/anim/cast/{model}/{action}.webm`.

    python scripts/build_clips.py [model-action ...]
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image

from normalize_cast import key_green

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / 'assets' / 'clips'
OUT = ROOT / 'app' / 'static' / 'anim' / 'cast'
MANIFEST = ROOT / 'app' / 'static' / 'anim' / 'stage.json'

FPS = 24
# A hair of margin around the union box: the matte's soft rim is a pixel or two
# wide, and cropping flush to it leaves a hard edge.
MARGIN = 3

# How tall each action reads next to the character's own standing sprite. Clips
# keep their native resolution (upscaling footage to the sprite's height only
# costs bytes and sharpness), so the stage scales them by this instead.
#
# `idle` is the character standing still, so it has to match the standing
# sprite exactly -- 1.0 would make her grow the moment she stopped walking,
# because the footage is not shot at the sprite's height.
ACTION_HEIGHT = {'idle': None, 'sit': 0.90, 'sleep': 0.62}


def run(*args: str) -> None:
    subprocess.run(args, check=True, capture_output=True)


def frames_of(clip: Path, into: Path) -> list[Path]:
    run('ffmpeg', '-y', '-v', 'error', '-i', str(clip), '-map', '0:v:0',
        str(into / 'in_%04d.png'))
    return sorted(into.glob('in_*.png'))


def key_frames(frames: list[Path], into: Path) -> tuple[list[Path], tuple[int, int, int, int]]:
    """Key every frame and return them with the box that holds all of them.

    One box for the whole clip, not one per frame: cropping each frame to its
    own bounding box would make the character jitter as her hair sways.
    """
    cut: list[Path] = []
    box: tuple[int, int, int, int] | None = None
    for frame in frames:
        art = key_green(Image.open(frame).convert('RGB'))
        here = art.getbbox()
        if here:
            box = here if box is None else (
                min(box[0], here[0]), min(box[1], here[1]),
                max(box[2], here[2]), max(box[3], here[3]),
            )
        dst = into / f'cut_{frame.stem[3:]}.png'
        art.save(dst)
        cut.append(dst)
    if box is None:
        raise SystemExit('nothing but green in the footage')
    w, h = Image.open(cut[0]).size
    box = (max(0, box[0] - MARGIN), max(0, box[1] - MARGIN),
           min(w, box[2] + MARGIN), min(h, box[3] + MARGIN))
    return cut, box


def encode(frames: list[Path], box: tuple[int, int, int, int], dst: Path) -> tuple[int, int]:
    work = frames[0].parent
    for i, frame in enumerate(frames, 1):
        Image.open(frame).crop(box).save(work / f'out_{i:04d}.png')
    dst.parent.mkdir(parents=True, exist_ok=True)
    # -auto-alt-ref 0 is required: libvpx's alternate reference frames are
    # encoded without the alpha plane, which shows up as flickering holes.
    run('ffmpeg', '-y', '-v', 'error', '-framerate', str(FPS),
        '-i', str(work / 'out_%04d.png'),
        '-c:v', 'libvpx-vp9', '-pix_fmt', 'yuva420p', '-b:v', '0', '-crf', '30',
        '-row-mt', '1', '-auto-alt-ref', '0', '-an', str(dst))
    return box[2] - box[0], box[3] - box[1]


def stand_scale(model: str, clip_height: int) -> float:
    """How tall a clip must read to match the same model's standing sprite.

    Read from the manifest the stage uses, so the two never drift: the sprite is
    built by `build_stage_art.py` at whatever height it is shipped at, and the
    footage comes back from the video generator at whatever size that gave.
    """
    if not MANIFEST.is_file() or not clip_height:
        return 1.0
    manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))
    poses = manifest.get('cast', {}).get(model, {}).get('poses', {})
    stand = poses.get('stand')
    if not stand or not stand[1]:
        return 1.0
    return round(stand[1] / clip_height, 4)


def build(clip: Path) -> tuple[str, str, dict]:
    model, _, action = clip.stem.partition('-')
    if not action:
        raise SystemExit(f'clip needs a {{model}}-{{action}} name: {clip.name}')
    work = Path(tempfile.mkdtemp(prefix='clip-'))
    try:
        raw = frames_of(clip, work)
        cut, box = key_frames(raw, work)
        dst = OUT / model / f'{action}.webm'
        w, h = encode(cut, box, dst)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    entry = {
        'size': [w, h],
        # A clip of the same pose as a still has to match that still's height.
        'scale': stand_scale(model, h) if action == 'idle' else ACTION_HEIGHT.get(action, 1.0),
        'frames': len(cut),
        'fps': FPS,
    }
    print(f'clip {model}/{action} {w}x{h} {len(cut)}f')
    return model, action, entry


def main(only: list[str]) -> None:
    clips = [SRC / f'{name}.mp4' for name in only] if only else sorted(SRC.glob('*.mp4'))
    if not clips:
        print(f'no clips in {SRC}')
        return
    manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))
    for clip in clips:
        model, action, entry = build(clip)
        cast = manifest.setdefault('cast', {}).setdefault(model, {})
        cast.setdefault('clips', {})[action] = entry
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    import sys
    main(sys.argv[1:])
