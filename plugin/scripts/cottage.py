"""Soft illustrated cottage, drawn at 2x so the window is not a pile of flat shapes."""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from mascot import SPECIES, pose_of

W, H = 520, 400
SCALE = 2
RADIUS = 36

PLASTER = (255, 248, 242)
INK = (92, 74, 64)
MUTED = (176, 146, 132)

SPECS = {
    'cat': {'body': (236, 176, 132), 'edge': (196, 132, 96), 'belly': (255, 232, 214), 'ear': 'point', 'tail': 'curl', 'face': 'short'},
    'dog': {'body': (224, 176, 112), 'edge': (184, 136, 78), 'belly': (255, 236, 210), 'ear': 'flop', 'tail': 'wag', 'face': 'long'},
    'rabbit': {'body': (246, 240, 232), 'edge': (214, 200, 188), 'belly': (255, 252, 248), 'ear': 'long', 'tail': 'puff', 'face': 'short'},
    'bird': {'body': (242, 196, 96), 'edge': (206, 156, 64), 'belly': (255, 236, 196), 'ear': 'crest', 'tail': 'fan', 'face': 'beak'},
}


def _font(size: int) -> ImageFont.ImageFont:
    for path in (r'C:\Windows\Fonts\msyh.ttc', r'C:\Windows\Fonts\msyh.ttc'):
        if Path(path).is_file():
            return ImageFont.truetype(path, size * SCALE)
    return ImageFont.load_default()


def _ease(phase: float) -> float:
    t = max(0.0, min(1.0, phase))
    return t * t * (3 - 2 * t)


def _lerp(a: int, b: int, t: float) -> int:
    return int(a + (b - a) * t)


def _mix(c0: tuple[int, int, int], c1: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return tuple(_lerp(c0[i], c1[i], t) for i in range(3))  # type: ignore[return-value]


def _s(box: tuple[float, float, float, float]) -> list[float]:
    return [value * SCALE for value in box]


class Cottage:
    def __init__(self) -> None:
        self.image = Image.new('RGBA', (W * SCALE, H * SCALE), (0, 0, 0, 0))
        self.draw = ImageDraw.Draw(self.image)
        self.font = _font(15)
        self.small = _font(11)

    def rounded(self, box: tuple[float, float, float, float], radius: float, fill: tuple[int, ...]) -> None:
        self.draw.rounded_rectangle(_s(box), radius=radius * SCALE, fill=fill)

    def ellipse(self, box: tuple[float, float, float, float], fill: tuple[int, ...]) -> None:
        self.draw.ellipse(_s(box), fill=fill)

    def polygon(self, points: list[tuple[float, float]], fill: tuple[int, ...]) -> None:
        self.draw.polygon([(x * SCALE, y * SCALE) for x, y in points], fill=fill)

    def line(self, a: tuple[float, float], b: tuple[float, float], fill: tuple[int, ...], width: float = 2) -> None:
        self.draw.line(
            [(a[0] * SCALE, a[1] * SCALE), (b[0] * SCALE, b[1] * SCALE)],
            fill=fill,
            width=max(1, int(width * SCALE)),
        )

    def text(self, xy: tuple[float, float], content: str, font: ImageFont.ImageFont, fill: tuple[int, ...]) -> None:
        self.draw.text((xy[0] * SCALE, xy[1] * SCALE), content, font=font, fill=fill, anchor='mm')

    def layer(self) -> ImageDraw.ImageDraw:
        plate = Image.new('RGBA', self.image.size, (0, 0, 0, 0))
        pen = ImageDraw.Draw(plate)
        self._plate = plate
        self._pen = pen
        return pen

    def commit(self) -> None:
        self.image = Image.alpha_composite(self.image, self._plate)
        self.draw = ImageDraw.Draw(self.image)

    def finish(self) -> Image.Image:
        return self.image.resize((W, H), Image.Resampling.LANCZOS)


def _room(art: Cottage) -> None:
    art.rounded((8, 8, W - 8, H - 8), RADIUS, PLASTER)
    # warm light from the window, painted as a soft oval behind the glass
    glow = art.layer()
    glow.ellipse(_s((150, 40, 390, 250)), fill=(255, 220, 180, 70))
    art.commit()

    # sky window
    art.rounded((168, 58, 352, 168), 18, (255, 252, 248))
    for row in range(64, 162):
        t = (row - 64) / 98
        color = _mix((255, 206, 156), (186, 214, 232), t)
        art.line((176, row), (344, row), color, 1.2)
    cloud = 214 + math.sin(art.tick / 18) * 10
    art.ellipse((cloud, 96, cloud + 36, 114), (255, 252, 248))
    art.ellipse((cloud + 16, 88, cloud + 52, 112), (255, 252, 248))
    art.ellipse((292, 78, 310, 96), (255, 214, 140))

    # floor
    art.polygon([(28, 286), (492, 286), (508, 384), (12, 384)], (236, 204, 166))
    for y in range(300, 376, 16):
        art.line((20, y), (500, y), (224, 186, 146), 1)
    art.ellipse((176, 312, 360, 368), (242, 176, 156))
    art.ellipse((196, 324, 340, 358), (248, 196, 176))

    # plant
    art.rounded((414, 248, 446, 292), 6, (232, 196, 160))
    art.ellipse((408, 214, 452, 258), (156, 186, 140))
    art.ellipse((424, 204, 460, 246), (186, 206, 160))


def _blob(art: Cottage, box: tuple[float, float, float, float], fill: tuple[int, int, int], edge: tuple[int, int, int]) -> None:
    x0, y0, x1, y1 = box
    art.ellipse((x0 - 2, y0 - 2, x1 + 2, y1 + 2), edge)
    art.ellipse(box, fill)


def _character(art: Cottage, spec: dict, cx: float, foot: float, tick: int, pose: str, look_up: bool) -> None:
    bob = math.sin(tick / 6.0) * 1.6
    foot -= bob
    body = spec['body']
    edge = spec['edge']
    belly = spec['belly']
    blink = (tick % 70) < 5
    swing = math.sin(tick / 5.0) * 14

    shadow = art.layer()
    shadow.ellipse(_s((cx - 32, foot - 14, cx + 32, foot + 2)), fill=(186, 140, 120, 45))
    art.commit()
    _tail(art, spec, cx - 40, foot - 58, swing)

    _blob(art, (cx - 42, foot - 96, cx + 42, foot - 20), body, edge)
    art.ellipse((cx - 20, foot - 72, cx + 24, foot - 30), belly)

    hy = foot - 112
    if spec['face'] == 'beak':
        flap = math.sin(tick / 4.0) * 4
        _blob(art, (cx - 8, hy + 18, cx + 26, foot - 36 + flap), edge, edge)
    _blob(art, (cx - 34, hy - 32, cx + 38, hy + 36), body, edge)
    _ears(art, spec, cx, hy)
    # cheek and shine
    art.ellipse((cx - 18, hy + 6, cx - 6, hy + 14), (242, 176, 166))
    art.ellipse((cx + 12, hy + 6, cx + 24, hy + 14), (242, 176, 166))
    shine = art.layer()
    shine.ellipse(_s((cx - 16, hy - 16, cx + 2, hy - 4)), fill=(255, 255, 255, 90))
    art.commit()
    _eyes(art, cx, hy, blink, look_up, spec['face'])

    if pose == 'mark':
        _blob(art, (cx + 16, foot - 70, cx + 34, foot - 52), body, edge)
        _blob(art, (cx - 24, foot - 28, cx - 8, foot - 14), body, edge)
    else:
        _blob(art, (cx - 28, foot - 30, cx - 10, foot - 14), body, edge)
        _blob(art, (cx + 12, foot - 30, cx + 30, foot - 14), body, edge)


def _ears(art: Cottage, spec: dict, cx: float, hy: float) -> None:
    body, edge = spec['body'], spec['edge']
    kind = spec['ear']
    if kind == 'point':
        art.polygon([(cx - 16, hy - 8), (cx - 6, hy - 40), (cx + 2, hy - 6)], body)
        art.polygon([(cx + 6, hy - 10), (cx + 18, hy - 42), (cx + 26, hy - 8)], body)
        art.polygon([(cx - 12, hy - 12), (cx - 6, hy - 30), (cx - 2, hy - 12)], (242, 186, 176))
        art.polygon([(cx + 10, hy - 14), (cx + 16, hy - 32), (cx + 22, hy - 12)], (242, 186, 176))
    elif kind == 'flop':
        _blob(art, (cx - 40, hy - 4, cx - 16, hy + 28), body, edge)
        _blob(art, (cx + 18, hy - 6, cx + 42, hy + 26), body, edge)
    elif kind == 'long':
        _blob(art, (cx - 18, hy - 62, cx - 2, hy - 6), body, edge)
        _blob(art, (cx + 8, hy - 68, cx + 24, hy - 8), body, edge)
        art.ellipse((cx - 14, hy - 52, cx - 6, hy - 16), (242, 196, 190))
        art.ellipse((cx + 12, hy - 56, cx + 20, hy - 18), (242, 196, 190))
    else:
        art.polygon([(cx + 2, hy - 22), (cx + 12, hy - 40), (cx + 20, hy - 18)], edge)


def _eyes(art: Cottage, cx: float, hy: float, blink: bool, look_up: bool, face: str) -> None:
    dy = -4 if look_up else 2
    for dx in (-12, 8):
        ex = cx + dx
        if blink:
            art.line((ex - 7, hy + 2), (ex + 7, hy + 2), INK, 2)
        else:
            art.ellipse((ex - 7, hy - 6, ex + 7, hy + 10), (255, 252, 248))
            art.ellipse((ex - 3, hy + dy - 2, ex + 3, hy + dy + 4), INK)
            art.ellipse((ex - 1, hy + dy - 1, ex + 2, hy + dy + 1), (255, 255, 255))
    if face == 'beak':
        art.polygon([(cx + 2, hy + 10), (cx + 16, hy + 14), (cx + 2, hy + 18)], (224, 122, 64))
    elif face == 'long':
        art.ellipse((cx + 8, hy + 8, cx + 28, hy + 20), (255, 236, 214))
        art.ellipse((cx + 20, hy + 12, cx + 26, hy + 17), (196, 120, 112))
    else:
        art.ellipse((cx - 2, hy + 10, cx + 6, hy + 16), (206, 128, 120))


def _tail(art: Cottage, spec: dict, x: float, y: float, swing: float) -> None:
    kind = spec['tail']
    if kind == 'curl':
        art.draw.arc(_s((x - 10, y - 18, x + 26, y + 22)), start=40 + swing, end=250 + swing, fill=spec['body'], width=6 * SCALE)
    elif kind == 'wag':
        ang = math.radians(-40 + swing)
        art.line((x + 8, y), (x + 8 + math.cos(ang) * 28, y + math.sin(ang) * 16), spec['body'], 7)
    elif kind == 'puff':
        art.ellipse((x - 8, y - 8, x + 12, y + 10), spec['belly'])
    else:
        for tilt in (-16, 0, 14):
            ang = math.radians(180 + tilt + swing * 0.25)
            art.line((x + 8, y), (x + 8 + math.cos(ang) * 18, y + math.sin(ang) * 8), spec['edge'], 3)


def _props(art: Cottage, scene: str, pose: str, cx: float, foot: float, tick: int) -> None:
    if pose == 'read':
        art.polygon([(cx - 28, foot - 20), (cx - 2, foot - 32), (cx - 2, foot - 8), (cx - 28, foot - 2)], (255, 250, 244))
        art.polygon([(cx + 2, foot - 32), (cx + 30, foot - 20), (cx + 30, foot - 2), (cx + 2, foot - 8)], (255, 252, 248))
        art.line((cx, foot - 32), (cx, foot - 6), (214, 156, 120), 3)
    elif pose == 'watch' and scene == 'film':
        art.rounded((188, 78, 332, 150), 8, (64, 72, 78))
        bar = 200 + (tick % 40)
        art.rounded((bar, 108, bar + 28, 122), 4, (255, 206, 140))
    elif pose == 'watch':
        art.rounded((392, 96, 458, 160), 8, (255, 248, 240))
        art.ellipse((408, 110, 432, 134), (242, 196, 120))
        art.polygon([(400, 146), (450, 146), (430, 128)], (176, 196, 160))
    elif pose == 'mark':
        art.ellipse((430, 150, 462, 182), (242, 170, 164))
    elif pose == 'play':
        art.rounded((cx - 46, foot - 28, cx + 50, foot - 6), 8, (232, 196, 150))
        art.rounded((cx - 36, foot - 46, cx + 40, foot - 22), 6, (255, 244, 224))
        for step in range(1, 3):
            art.line((cx - 36 + step * 24, foot - 46), (cx - 36 + step * 24, foot - 22), (226, 196, 164), 1)
        stone = cx - 24 + (tick // 14 % 3) * 16
        art.ellipse((stone, foot - 40, stone + 10, foot - 30), INK)


def _actor_x(pose: str, phase: float) -> float:
    eased = _ease(phase)
    if pose == 'enter':
        return 120 + (268 - 120) * eased
    if pose == 'leave':
        return 268 + (70 - 268) * eased
    if pose == 'mark':
        return 360
    return 268


def render(*, species: str, scene: str, tick: int, phase: float, line: str, choosing: bool) -> Image.Image:
    art = Cottage()
    art.tick = tick
    _room(art)
    if choosing:
        art.text((W / 2, 196), '选一只陪你待着的动物', art.font, INK)
        spots = {
            'cat': (110, 250),
            'dog': (230, 250),
            'rabbit': (350, 250),
            'bird': (450, 250),
        }
        for name, (cx, foot) in spots.items():
            _character(art, SPECS[name], cx, foot, tick=8, pose='sit', look_up=False)
            art.text((cx, 292), SPECIES[name]['label'], art.small, MUTED)
    else:
        pose = pose_of(scene)
        if not (pose == 'leave' and phase >= 0.98):
            cx = _actor_x(pose, phase if pose in ('enter', 'leave') else 1)
            _props(art, scene, pose, cx, 348, tick)
            _character(art, SPECS.get(species) or SPECS['cat'], cx, 348, tick, pose, look_up=pose == 'watch')
        caption = '此刻 · ' + line if line else '此刻'
        art.text((W / 2, 40), caption, art.font, INK)
    art.text((92, 372), '换一只', art.small, MUTED)
    art.text((430, 372), '双击关闭', art.small, MUTED)
    return art.finish().convert('RGB')


def choice_at(x: int, y: int) -> str | None:
    spots = (('cat', 110), ('dog', 230), ('rabbit', 350), ('bird', 450))
    if not 200 <= y <= 310:
        return None
    for name, cx in spots:
        if abs(x - cx) <= 48:
            return name
    return None
