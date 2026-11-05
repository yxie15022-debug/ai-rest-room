"""Assemble the 2D stage art from generated source images.

Sources live in `assets/` (local only, like the other raster sources in this
repo); the stage reads the output under `app/static/anim/`.

The room is one still cutaway box -- an isometric dollhouse with a floor and
two walls -- and it is the desktop pet itself, not a backdrop behind one. The
pet window is clipped to the shape baked here, so the cut-out has to be the
room's real outline and its alpha has to be hard: a half-transparent rim would
read as a grey fringe against whatever is behind the window.

    python scripts/build_stage_art.py
"""

from __future__ import annotations

import json
from collections import deque
from pathlib import Path

from PIL import Image

from normalize_cast import HEIGHT, normalize

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / 'assets'
OUT = ROOT / 'app' / 'static' / 'anim'

# Every pose is drawn filling its own square, so a seated girl comes back as
# tall as a standing one. Scale each pose against the standing sprite instead.
#
# Kneeling tucks the legs under the body, so a real seiza pose is markedly
# shorter than standing -- not a tenth, which is what this said while the art
# was still a standing figure. The sprite is anchored by its feet, so the
# number has to match how she actually sits on the cushion.
POSE_HEIGHT = {'sit': 0.74}
# A lying pose has no height to match -- her body runs across the frame -- so
# these are fitted by how long she is instead. The bed's own top surface is
# about 240 room pixels long (the art is drawn smaller than a standing chibi),
# so the pose is fitted to that with a little margin, not to her standing size.
POSE_WIDTH = {'sleep': 230}

# What still counts as the white page the room was drawn on: bright, and with
# almost no colour in it. Loose enough for JPEG mottling, tight enough to stop
# at the pale window frame and the cream throw on the sofa.
PAGE_LIGHT = 206
PAGE_TINT = 20


def _page_mask(img: Image.Image) -> Image.Image:
    """Alpha that is 0 on the white page around the room and 255 on the room.

    A flood from the border rather than a test on every pixel: the room has
    white things of its own -- the desk, the window frame, the pillows -- and
    only what the page actually reaches is page.
    """
    w, h = img.size
    px = img.convert('RGB').load()
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
        r, g, b = px[x, y]
        if min(r, g, b) < PAGE_LIGHT or max(r, g, b) - min(r, g, b) > PAGE_TINT:
            continue
        ap[x, y] = 0
        queue.extend(((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)))
    return alpha


def build_room() -> dict:
    """Cut the room box off its page and keep it as the pet's own shape."""
    room = Image.open(SRC / 'room' / 'iso.jpg').convert('RGBA')
    room.putalpha(_page_mask(room))
    room = room.crop(room.getbbox())

    (OUT / 'room').mkdir(parents=True, exist_ok=True)
    room.save(OUT / 'room' / 'bg.png')
    (OUT / 'room' / 'door.png').unlink(missing_ok=True)
    return {'size': [room.width, room.height]}


def _leg_gap(alpha, w: int, y: int) -> tuple[float, float] | None:
    """The clear channel between the two legs on one row, if there is one.

    Only an interior gap near the middle counts: side hair and skirt frills
    also break the row into runs, but never down the centre of the body.
    """
    opaque = [x for x in range(w) if alpha[x, y] > 128]
    if len(opaque) < 2:
        return None
    best = None
    for a, b in zip(opaque, opaque[1:]):
        if b - a <= 1:
            continue
        mid = (a + b) / 2
        if abs(mid / w - 0.5) > 0.12:
            continue
        if best is None or b - a > best[1]:
            best = (mid, b - a)
    return best


def measure_rig(sprite: Path) -> dict:
    """Find where the skirt ends and where to split the two legs.

    The stage cuts the standing sprite into three bands with clip-path: the
    upper body (which includes the skirt) and one band per leg. The cut sits
    just under the hem, so the skirt hides it and the legs read as swinging out
    from under it.

    Both numbers come from the same feature: the clear channel between the two
    legs. Walk up from the soles while that channel stays open, and the row it
    closes at is the hem; its centre is the split. Reading a drop in silhouette
    width instead gets fooled by whatever else the character has going on -- a
    drop at the end of a pair of hair buns is sharper than the one at the hem --
    and starting from the top finds the slot beside a hanging twin-tail first.
    """
    img = Image.open(sprite)
    w, h = img.size
    alpha = img.getchannel('A').load()
    cover = [sum(1 for x in range(w) if alpha[x, y] > 128) for y in range(h)]

    floor = max(0.012 * w, 3)
    slack = max(int(h * 0.012), 6)
    gaps = {y: _leg_gap(alpha, w, y) for y in range(int(h * 0.35), h)}
    is_open = lambda y: bool(gaps.get(y)) and gaps[y][1] >= floor  # noqa: E731

    sole = next((y for y in range(h - 1, int(h * 0.35), -1) if is_open(y)), None)
    hem = None
    if sole is not None:
        hem = sole
        miss = 0
        for y in range(sole, int(h * 0.35), -1):
            if is_open(y):
                hem, miss = y, 0
            else:
                miss += 1
                if miss > slack:
                    break

    if hem is None:
        # No channel at all (feet together, skirt to the ankles): fall back to
        # the sharpest narrowing of the silhouette.
        reach = 10
        hem = max(
            range(int(h * 0.40), int(h * 0.88)),
            key=lambda y: (cover[y - reach] - cover[y + reach]) / max(1, cover[y - reach]),
        )
        row = [x for x in range(w) if alpha[x, min(h - 1, hem + int(h * 0.03))] > 128]
        split = (row[0] + row[-1]) / 2 if row else w / 2
    else:
        mids = [gaps[y][0] for y in range(hem, sole + 1) if gaps.get(y)]
        split = sum(mids) / len(mids)

    head = next((y for y in range(h) if cover[y] > 0), 0)
    return {
        'size': [w, h],
        'hem': round(hem / h, 4),
        'split': round(split / w, 4),
        'head': round(head / h, 4),
    }


def build_cast() -> dict:
    cast: dict[str, dict] = {}
    for art in sorted((SRC / 'cast').glob('*.jpg')):
        model, _, pose = art.stem.partition('-')
        if not pose:
            continue
        dst = OUT / 'cast' / model / f'{pose}.png'
        w, h = normalize(
            art, dst,
            round(HEIGHT * POSE_HEIGHT.get(pose, 1.0)),
            POSE_WIDTH.get(pose, 0),
        )
        entry = cast.setdefault(model, {'poses': {}})
        entry['poses'][pose] = [w, h]
        if pose == 'stand':
            # Measured on the sprite as shipped. The build's height is the one
            # the browser actually draws at, so measuring here rather than on
            # the 1024 source keeps the rig honest about the art it describes.
            entry['rig'] = measure_rig(dst)
        print(f'cast {model}/{pose} {w}x{h}')
    return cast


def main() -> None:
    manifest = {'room': build_room(), 'cast': build_cast()}
    (OUT / 'stage.json').write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8'
    )
    print('room', manifest['room'])


if __name__ == '__main__':
    main()
