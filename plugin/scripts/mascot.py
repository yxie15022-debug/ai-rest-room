"""Original little animals for the scene window.

One body, four species (ears, tail, colors). Poses follow the room scene.
"""

from __future__ import annotations

import math
from pathlib import Path

MASCOT_PATH = Path.home() / '.ai-rest-room-mascot'

ROOM_W = 380
ROOM_H = 220
FLOOR_Y = 158
SEAT_X = 176
DOOR_X = 58
WALL_X = 262

SPECIES_IDS = ('cat', 'dog', 'rabbit', 'bird')

SPECIES: dict[str, dict[str, str]] = {
    'cat': {
        'label': '猫',
        'body': '#c9956b',
        'belly': '#f6e6d2',
        'line': '#8d6848',
        'ear': 'point',
        'tail': 'curl',
        'face': 'short',
    },
    'dog': {
        'label': '狗',
        'body': '#d4a574',
        'belly': '#f8ead8',
        'line': '#8f6a42',
        'ear': 'flop',
        'tail': 'wag',
        'face': 'long',
    },
    'rabbit': {
        'label': '兔',
        'body': '#f3ece4',
        'belly': '#fffaf4',
        'line': '#c4b6a6',
        'ear': 'long',
        'tail': 'puff',
        'face': 'short',
    },
    'bird': {
        'label': '鸟',
        'body': '#e8b86d',
        'belly': '#fff4dc',
        'line': '#b5833d',
        'ear': 'crest',
        'tail': 'fan',
        'face': 'beak',
    },
}

POSE = {
    'enter': 'enter',
    'sit': 'sit',
    'read': 'read',
    'look': 'watch',
    'film': 'watch',
    'wall': 'mark',
    'signal': 'mark',
    'name': 'mark',
    'go': 'play',
    'diplomacy': 'play',
    'leave': 'leave',
}

WALL = '#f6f1e7'
FLOOR = '#e7d7c3'
WOOD = '#d7b89a'
INK = '#3d3a33'
GLASS = '#d5e4ee'


def pose_of(scene: str) -> str:
    return POSE.get(scene, 'sit')


def load_species() -> str | None:
    try:
        value = MASCOT_PATH.read_text(encoding='utf-8').strip()
    except OSError:
        return None
    if value in SPECIES:
        return value
    return None


def save_species(species_id: str) -> None:
    if species_id not in SPECIES:
        raise ValueError(species_id)
    MASCOT_PATH.write_text(species_id + '\n', encoding='utf-8')


def _ease(phase: float) -> float:
    t = max(0.0, min(1.0, phase))
    return t * t * (3 - 2 * t)


def _anchor(pose: str, phase: float) -> tuple[float, float]:
    eased = _ease(phase)
    if pose == 'enter':
        return DOOR_X + (SEAT_X - DOOR_X) * eased, FLOOR_Y
    if pose == 'leave':
        return SEAT_X + (DOOR_X - 36 - SEAT_X) * eased, FLOOR_Y
    if pose == 'mark':
        return WALL_X, FLOOR_Y
    return SEAT_X, FLOOR_Y


def draw(canvas, *, species: str, scene: str, tick: int, phase: float = 1.0, scale: float = 1.0) -> None:
    """Paint the standalone room. The house window uses draw_occupant instead."""
    canvas.delete('all')
    canvas.configure(bg=WALL, highlightthickness=0, bd=0)

    def sx(value: float) -> float:
        return value * scale

    def sy(value: float) -> float:
        return value * scale

    canvas.configure(width=int(sx(ROOM_W)), height=int(sy(ROOM_H)))
    canvas.create_rectangle(0, 0, sx(ROOM_W), sy(ROOM_H), fill=WALL, outline='')
    canvas.create_rectangle(0, sy(FLOOR_Y), sx(ROOM_W), sy(ROOM_H), fill=FLOOR, outline='')
    _window(canvas, sx, sy)
    _door(canvas, sx, sy)
    _plant(canvas, sx, sy)
    draw_occupant(canvas, species=species, scene=scene, tick=tick, phase=phase, left=0, top=0, scale=scale)


def draw_occupant(canvas, *, species: str, scene: str, tick: int, phase: float, left: float, top: float, scale: float) -> None:
    """Animal and the prop for this scene. Does not clear the canvas."""
    spec = SPECIES.get(species) or SPECIES['cat']
    pose = pose_of(scene)

    def sx(value: float) -> float:
        return left + value * scale

    def sy(value: float) -> float:
        return top + value * scale

    if pose in ('sit', 'read', 'watch', 'play') or (pose == 'enter' and phase > 0.72):
        _cushion(canvas, sx, sy, SEAT_X)
    if pose == 'watch':
        if scene == 'film':
            _screen(canvas, sx, sy, tick)
        else:
            _painting(canvas, sx, sy)
    if pose == 'mark':
        _mark(canvas, sx, sy, scene, tick)
    if pose == 'play':
        _table(canvas, sx, sy, scene)
    if pose == 'leave' and phase >= 0.98:
        return

    cx, foot = _anchor(pose, phase if pose in ('enter', 'leave') else 1.0)
    bob = math.sin(tick / 5.5) * (2.4 if pose in ('enter', 'leave') else 0.7)
    _creature(
        canvas,
        sx,
        sy,
        spec,
        cx,
        foot - bob,
        tick,
        pose,
        look_up=pose == 'watch',
        paw_up=pose == 'mark',
    )
    if pose == 'read':
        _book(canvas, sx, sy, cx, foot)
    if pose == 'play':
        _board(canvas, sx, sy, scene, tick)


def _window(canvas, sx, sy) -> None:
    canvas.create_rectangle(sx(248), sy(28), sx(332), sy(96), fill='#f3e2c4', outline='')
    canvas.create_rectangle(sx(254), sy(34), sx(326), sy(90), fill=GLASS, outline='')
    canvas.create_line(sx(290), sy(34), sx(290), sy(90), fill='#f6f1e7', width=2)
    canvas.create_line(sx(254), sy(62), sx(326), sy(62), fill='#f6f1e7', width=2)
    canvas.create_oval(sx(300), sy(42), sx(314), sy(56), fill='#f6e7a8', outline='')


def _door(canvas, sx, sy) -> None:
    canvas.create_rectangle(sx(16), sy(72), sx(62), sy(FLOOR_Y), fill='#e4d0b4', outline='')
    canvas.create_oval(sx(48), sy(112), sx(54), sy(118), fill='#c4a574', outline='')


def _plant(canvas, sx, sy) -> None:
    canvas.create_rectangle(sx(336), sy(132), sx(358), sy(FLOOR_Y), fill='#d7b89a', outline='')
    canvas.create_oval(sx(328), sy(108), sx(366), sy(140), fill='#b7c7a3', outline='')
    canvas.create_oval(sx(340), sy(100), sx(370), sy(132), fill='#c9d4b4', outline='')


def _cushion(canvas, sx, sy, cx: float) -> None:
    canvas.create_oval(sx(cx - 34), sy(FLOOR_Y - 10), sx(cx + 34), sy(FLOOR_Y + 10), fill='#e7c2b2', outline='')


def _painting(canvas, sx, sy) -> None:
    canvas.create_rectangle(sx(118), sy(36), sx(176), sy(86), fill='#efe6d6', outline='')
    canvas.create_rectangle(sx(124), sy(42), sx(170), sy(80), fill='#f7f1e4', outline='')
    canvas.create_oval(sx(132), sy(50), sx(148), sy(66), fill='#e7b86a', outline='')
    canvas.create_rectangle(sx(128), sy(66), sx(166), sy(76), fill='#c9d4b4', outline='')


def _screen(canvas, sx, sy, tick: int) -> None:
    canvas.create_rectangle(sx(112), sy(40), sx(186), sy(92), fill='#4a463f', outline='')
    canvas.create_rectangle(sx(118), sy(46), sx(180), sy(80), fill='#2c3338', outline='')
    bar = 118 + (tick % 28)
    canvas.create_rectangle(sx(bar), sy(58), sx(bar + 16), sy(66), fill='#e7b86a', outline='')
    canvas.create_rectangle(sx(140), sy(86), sx(158), sy(96), fill=WOOD, outline='')


def _mark(canvas, sx, sy, scene: str, tick: int) -> None:
    if scene == 'name':
        canvas.create_rectangle(sx(318), sy(78), sx(352), sy(108), fill='#f7f1e4', outline='')
        canvas.create_line(sx(335), sy(70), sx(335), sy(78), fill='#c4a574', width=2)
        canvas.create_oval(sx(328), sy(88), sx(342), sy(98), fill='#e7b7b0', outline='')
        return
    if scene == 'signal':
        canvas.create_oval(sx(324), sy(84), sx(346), sy(106), fill='#e7b7b0', outline='')
        return
    canvas.create_line(sx(322), sy(96), sx(348), sy(84), fill='#c9956b', width=2)
    canvas.create_line(sx(326), sy(104), sx(350), sy(96), fill='#c9956b', width=2)


def _table(canvas, sx, sy, scene: str) -> None:
    canvas.create_rectangle(sx(118), sy(132), sx(246), sy(150), fill=WOOD, outline='')
    canvas.create_rectangle(sx(128), sy(150), sx(138), sy(FLOOR_Y), fill='#c4a574', outline='')
    canvas.create_rectangle(sx(226), sy(150), sx(236), sy(FLOOR_Y), fill='#c4a574', outline='')


def _board(canvas, sx, sy, scene: str, tick: int) -> None:
    if scene == 'diplomacy':
        canvas.create_oval(sx(148), sy(112), sx(216), sy(146), fill='#f3e6c8', outline='')
        colors = ('#d27b6a', '#7f97b2', '#c4a574', '#8fa67a')
        for index, color in enumerate(colors):
            ox = 160 + (index % 2) * 28
            oy = 118 + (index // 2) * 14
            canvas.create_oval(sx(ox), sy(oy), sx(ox + 10), sy(oy + 10), fill=color, outline='')
        return
    canvas.create_rectangle(sx(146), sy(108), sx(220), sy(148), fill='#f3e6c8', outline='')
    for step in range(1, 4):
        canvas.create_line(sx(146 + step * 18), sy(108), sx(146 + step * 18), sy(148), fill='#d7c4a4')
        canvas.create_line(sx(146), sy(108 + step * 10), sx(220), sy(108 + step * 10), fill='#d7c4a4')
    stone = 158 + (tick // 12 % 3) * 16
    canvas.create_oval(sx(stone), sy(118), sx(stone + 8), sy(126), fill=INK, outline='')


def _book(canvas, sx, sy, cx: float, foot: float) -> None:
    canvas.create_polygon(
        sx(cx - 22), sy(foot - 18),
        sx(cx - 2), sy(foot - 26),
        sx(cx - 2), sy(foot - 8),
        sx(cx - 22), sy(foot - 4),
        fill='#f7f1e4', outline='',
    )
    canvas.create_polygon(
        sx(cx + 2), sy(foot - 26),
        sx(cx + 24), sy(foot - 18),
        sx(cx + 24), sy(foot - 4),
        sx(cx + 2), sy(foot - 8),
        fill='#fffaf4', outline='',
    )
    canvas.create_line(sx(cx - 2), sy(foot - 26), sx(cx + 2), sy(foot - 26), sx(cx), sy(foot - 6), fill='#c9956b', width=2)


def _creature(canvas, sx, sy, spec: dict[str, str], cx: float, foot: float, tick: int, pose: str, look_up: bool, paw_up: bool) -> None:
    body = spec['body']
    belly = spec['belly']
    line = spec['line']
    blink = (tick % 52) < 4
    tail_swing = math.sin(tick / 5.0) * (16 if pose == 'sit' else 8)

    canvas.create_oval(sx(cx - 22), sy(foot - 8), sx(cx + 22), sy(foot + 4), fill='#ddcbb6', outline='')
    _tail(canvas, sx, sy, spec, cx - 24, foot - 28, tail_swing)

    canvas.create_oval(sx(cx - 28), sy(foot - 54), sx(cx + 28), sy(foot - 8), fill=body, outline='')
    canvas.create_oval(sx(cx - 14), sy(foot - 38), sx(cx + 16), sy(foot - 12), fill=belly, outline='')

    hy = foot - 64
    canvas.create_oval(sx(cx - 18), sy(hy - 18), sx(cx + 22), sy(hy + 18), fill=body, outline='')
    _ears(canvas, sx, sy, spec, cx, hy)
    _face(canvas, sx, sy, spec, cx, hy, blink, look_up)
    if spec['face'] == 'beak':
        flap = math.sin(tick / 4.0) * 5
        canvas.create_oval(sx(cx - 8), sy(hy + 8), sx(cx + 16), sy(foot - 20 + flap), fill=line, outline='')

    if paw_up:
        canvas.create_oval(sx(cx + 8), sy(foot - 46), sx(cx + 22), sy(foot - 32), fill=body, outline='')
        canvas.create_oval(sx(cx - 16), sy(foot - 16), sx(cx - 2), sy(foot - 6), fill=body, outline='')
    else:
        canvas.create_oval(sx(cx - 16), sy(foot - 16), sx(cx - 2), sy(foot - 6), fill=body, outline='')
        canvas.create_oval(sx(cx + 6), sy(foot - 16), sx(cx + 20), sy(foot - 6), fill=body, outline='')


def _ears(canvas, sx, sy, spec: dict[str, str], cx: float, hy: float) -> None:
    body = spec['body']
    kind = spec['ear']
    if kind == 'point':
        canvas.create_polygon(sx(cx - 12), sy(hy - 8), sx(cx - 4), sy(hy - 28), sx(cx + 2), sy(hy - 6), fill=body, outline='')
        canvas.create_polygon(sx(cx + 4), sy(hy - 10), sx(cx + 12), sy(hy - 30), sx(cx + 18), sy(hy - 8), fill=body, outline='')
    elif kind == 'flop':
        canvas.create_oval(sx(cx - 24), sy(hy - 6), sx(cx - 8), sy(hy + 18), fill=body, outline='')
        canvas.create_oval(sx(cx + 14), sy(hy - 8), sx(cx + 30), sy(hy + 16), fill=body, outline='')
    elif kind == 'long':
        canvas.create_oval(sx(cx - 12), sy(hy - 42), sx(cx - 1), sy(hy - 4), fill=body, outline='')
        canvas.create_oval(sx(cx + 6), sy(hy - 46), sx(cx + 17), sy(hy - 6), fill=body, outline='')
        canvas.create_oval(sx(cx - 9), sy(hy - 36), sx(cx - 3), sy(hy - 10), fill='#f3c9c4', outline='')
        canvas.create_oval(sx(cx + 9), sy(hy - 40), sx(cx + 15), sy(hy - 12), fill='#f3c9c4', outline='')
    else:
        canvas.create_polygon(sx(cx + 2), sy(hy - 16), sx(cx + 8), sy(hy - 28), sx(cx + 14), sy(hy - 14), fill=spec['line'], outline='')


def _face(canvas, sx, sy, spec: dict[str, str], cx: float, hy: float, blink: bool, look_up: bool) -> None:
    pupil_dy = -3 if look_up else 1
    for dx in (-6, 8):
        ex = cx + dx
        if blink:
            canvas.create_line(sx(ex - 4), sy(hy + 1), sx(ex + 4), sy(hy + 1), fill=INK, width=2)
        else:
            canvas.create_oval(sx(ex - 4), sy(hy - 3), sx(ex + 4), sy(hy + 5), fill='#f7f3ea', outline='')
            canvas.create_oval(sx(ex - 1.5), sy(hy + pupil_dy - 1.5), sx(ex + 1.5), sy(hy + pupil_dy + 1.5), fill=INK, outline='')
    kind = spec['face']
    if kind == 'beak':
        canvas.create_polygon(sx(cx + 2), sy(hy + 6), sx(cx + 14), sy(hy + 9), sx(cx + 2), sy(hy + 13), fill='#e07a3d', outline='')
    elif kind == 'long':
        canvas.create_oval(sx(cx + 6), sy(hy + 4), sx(cx + 22), sy(hy + 14), fill=spec['belly'], outline='')
        canvas.create_oval(sx(cx + 16), sy(hy + 8), sx(cx + 20), sy(hy + 12), fill='#c47b73', outline='')
    else:
        canvas.create_oval(sx(cx + 1), sy(hy + 6), sx(cx + 7), sy(hy + 11), fill='#c47b73', outline='')


def _tail(canvas, sx, sy, spec: dict[str, str], x: float, y: float, swing: float) -> None:
    kind = spec['tail']
    if kind == 'curl':
        canvas.create_arc(
            sx(x - 8), sy(y - 16), sx(x + 20), sy(y + 16),
            start=30 + swing, extent=230, style='arc', outline=spec['body'], width=4,
        )
    elif kind == 'wag':
        ang = math.radians(-50 + swing)
        canvas.create_line(
            sx(x + 6), sy(y),
            sx(x + 6 + math.cos(ang) * 26), sy(y + math.sin(ang) * 18),
            fill=spec['body'], width=5, capstyle='round',
        )
    elif kind == 'puff':
        canvas.create_oval(sx(x - 6), sy(y - 8), sx(x + 10), sy(y + 8), fill=spec['belly'], outline='')
    else:
        for index, tilt in enumerate((-18, 0, 16)):
            ang = math.radians(180 + tilt + swing * 0.3)
            canvas.create_line(
                sx(x + 8), sy(y),
                sx(x + 8 + math.cos(ang) * (16 + index * 2)), sy(y + math.sin(ang) * 10),
                fill=spec['line'], width=2, capstyle='round',
            )
