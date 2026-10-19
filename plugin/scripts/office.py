"""Flat office loop. The camera never moves; only the rabbit and the screen do."""

from __future__ import annotations

import math

from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 560, 420
SCALE = 2

WHITE = (255, 255, 255, 255)
DESK = (252, 252, 252, 255)
LINE = (236, 236, 236, 255)
BEZEL = (244, 244, 244, 255)
SCREEN = (78, 164, 232, 255)
SCREEN_DIM = (28, 32, 36, 255)
INK = (22, 22, 22, 255)
SCARF = (235, 96, 88, 255)

SEAT_X = 280
SEAT_Y = 196


def _font(size: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.truetype(r'C:\Windows\Fonts\arial.ttf', size * SCALE)
    except OSError:
        return ImageFont.load_default()


def _ease(phase: float) -> float:
    t = max(0.0, min(1.0, phase))
    return t * t * (3 - 2 * t)


def _sx(value: float) -> float:
    return value * SCALE


def render(*, scene: str, tick: int, phase: float) -> Image.Image:
    canvas = Image.new('RGBA', (W * SCALE, H * SCALE), WHITE)
    _shadow(canvas)
    draw = ImageDraw.Draw(canvas)
    _desk(draw)
    _monitor(draw, scene, tick, phase)
    _chair(draw)
    x = _actor_x(scene, phase)
    drop = 0.0
    if scene == 'enter':
        drop = 34 * (1 - _ease(phase))
    elif scene == 'leave':
        drop = 28 * _ease(phase)
    doze = scene == 'sit'
    _rabbit(draw, x, tick, doze=doze, working=scene not in ('sit', 'leave'), drop=drop)
    if doze:
        _zzz(draw, x, tick)
    if scene == 'leave' and phase > 0.92:
        pass
    out = canvas.resize((W, H), Image.Resampling.LANCZOS)
    return out.convert('RGB')


def _actor_x(scene: str, phase: float) -> float:
    eased = _ease(phase)
    if scene == 'enter':
        return -70 + (SEAT_X + 70) * eased
    if scene == 'leave':
        return SEAT_X + (W + 80 - SEAT_X) * eased
    return SEAT_X


def _shadow(canvas: Image.Image) -> None:
    layer = Image.new('RGBA', canvas.size, (0, 0, 0, 0))
    pen = ImageDraw.Draw(layer)
    pen.ellipse(_box(70, 250, 500, 360), fill=(0, 0, 0, 42))
    pen.ellipse(_box(150, 300, 390, 390), fill=(0, 0, 0, 28))
    canvas.alpha_composite(layer.filter(ImageFilter.GaussianBlur(16 * SCALE // 2)))


def _box(x0: float, y0: float, x1: float, y1: float) -> list[float]:
    return [_sx(x0), _sx(y0), _sx(x1), _sx(y1)]


def _desk(draw: ImageDraw.ImageDraw) -> None:
    draw.rounded_rectangle(_box(36, 158, 524, 200), radius=_sx(10), fill=DESK, outline=LINE, width=SCALE)
    draw.rectangle(_box(64, 190, 108, 286), fill=DESK, outline=LINE)
    draw.rounded_rectangle(_box(400, 192, 496, 312), radius=_sx(8), fill=DESK, outline=LINE, width=SCALE)
    draw.line([_sx(414), _sx(236), _sx(482), _sx(236)], fill=LINE, width=SCALE)
    draw.line([_sx(414), _sx(272), _sx(482), _sx(272)], fill=LINE, width=SCALE)


def _monitor(draw: ImageDraw.ImageDraw, scene: str, tick: int, phase: float) -> None:
    draw.rounded_rectangle(_box(168, 64, 392, 188), radius=_sx(10), fill=BEZEL, outline=LINE, width=SCALE)
    awake = scene not in ('sit', 'leave') and not (scene == 'enter' and phase < 0.55)
    screen = SCREEN if awake else SCREEN_DIM
    draw.rounded_rectangle(_box(180, 76, 380, 172), radius=_sx(4), fill=screen)
    if not awake:
        return
    if scene in ('look', 'film'):
        _picture(draw, scene, tick)
    elif scene in ('go', 'diplomacy'):
        _grid(draw, tick)
    elif scene in ('wall', 'signal', 'name'):
        draw.ellipse(_box(250, 118, 286, 154), fill=(255, 196, 188, 255))
    else:
        _lines(draw, tick)


def _lines(draw: ImageDraw.ImageDraw, tick: int) -> None:
    shift = (tick * 3) % 28
    for index in range(6):
        y = 102 + index * 12 - shift
        if 96 < y < 168:
            width = 70 + (index * 17 + tick) % 80
            draw.rounded_rectangle(
                _box(204, y, 204 + width, y + 5),
                radius=_sx(2),
                fill=(255, 255, 255, 230),
            )
    if (tick // 8) % 2 == 0:
        draw.rectangle(_box(206, 158, 214, 168), fill=(255, 255, 255, 255))


def _picture(draw: ImageDraw.ImageDraw, scene: str, tick: int) -> None:
    draw.rounded_rectangle(_box(206, 102, 354, 164), radius=_sx(3), fill=(255, 248, 236, 255))
    draw.rectangle(_box(206, 102, 354, 132), fill=(186, 214, 232, 255))
    draw.ellipse(_box(300 + math.sin(tick / 10) * 6, 108, 322, 128), fill=(255, 214, 140, 255))
    if scene == 'film' and (tick // 6) % 2 == 0:
        draw.polygon([(_sx(268), _sx(122)), (_sx(268), _sx(148)), (_sx(290), _sx(135))], fill=(78, 164, 232, 255))


def _grid(draw: ImageDraw.ImageDraw, tick: int) -> None:
    for col in range(4):
        for row in range(3):
            x = 210 + col * 36
            y = 104 + row * 22
            hot = (col + row + tick // 10) % 5 == 0
            color = (255, 244, 220, 255) if hot else (255, 255, 255, 180)
            draw.rounded_rectangle(_box(x, y, x + 28, y + 14), radius=_sx(2), fill=color)


def _chair(draw: ImageDraw.ImageDraw) -> None:
    draw.rounded_rectangle(_box(232, 228, 330, 318), radius=_sx(10), fill=WHITE, outline=LINE, width=SCALE)
    draw.line([_sx(281), _sx(318), _sx(281), _sx(352)], fill=(210, 210, 210, 255), width=SCALE * 2)
    for angle in range(0, 360, 72):
        rad = math.radians(angle - 90)
        draw.line(
            [(_sx(281), _sx(352)), (_sx(281 + math.cos(rad) * 28), _sx(352 + math.sin(rad) * 16))],
            fill=(196, 196, 196, 255),
            width=SCALE * 2,
        )


def _rabbit(draw: ImageDraw.ImageDraw, cx: float, tick: int, doze: bool, working: bool, drop: float = 0) -> None:
    breath = math.sin(tick / 5.5) * (1.2 if doze else 3.2)
    ear = math.sin(tick / 7.0) * 5
    cy = SEAT_Y + drop + breath
    if cx < -20 or cx > W + 20:
        return
    # ears
    draw.ellipse(_box(cx - 18 + ear * 0.2, cy - 78, cx - 4, cy - 28), fill=INK)
    draw.ellipse(_box(cx + 4, cy - 84 - ear * 0.15, cx + 18, cy - 30), fill=INK)
    draw.ellipse(_box(cx - 14 + ear * 0.2, cy - 70, cx - 7, cy - 36), fill=(255, 214, 214, 255))
    draw.ellipse(_box(cx + 8, cy - 76 - ear * 0.15, cx + 15, cy - 38), fill=(255, 214, 214, 255))
    # head and body, seen from behind
    draw.ellipse(_box(cx - 26, cy - 46, cx + 26, cy + 2), fill=INK)
    draw.ellipse(_box(cx - 34, cy - 8, cx + 34, cy + 48), fill=INK)
    draw.rounded_rectangle(_box(cx - 30, cy + 2, cx + 30, cy + 22), radius=_sx(10), fill=SCARF)
    # arms on the desk when working, dropped when dozing
    if working:
        lift = math.sin(tick / 3.5) * 3
        draw.ellipse(_box(cx - 48, cy + 8 + lift, cx - 28, cy + 26), fill=INK)
        draw.ellipse(_box(cx + 28, cy + 8 - lift, cx + 48, cy + 26), fill=INK)
    else:
        draw.ellipse(_box(cx - 44, cy + 16, cx - 26, cy + 36), fill=INK)
        draw.ellipse(_box(cx + 26, cy + 16, cx + 44, cy + 36), fill=INK)


def _zzz(draw: ImageDraw.ImageDraw, cx: float, tick: int) -> None:
    rise = (tick * 1.6) % 28
    draw.text((_sx(cx + 34), _sx(SEAT_Y - 36 - rise)), 'z', font=_font(12), fill=(180, 180, 180, 255))
    draw.text((_sx(cx + 48), _sx(SEAT_Y - 58 - rise)), 'Z', font=_font(18), fill=(160, 160, 160, 255))
