
"""Studio-cat frames: a black cat at a white studio desk.

The look: pure white seamless studio, white desk / monitor / chair / cabinet,
a soft grey contact shadow, and a black cat silhouette with a coloured scarf,
seen from behind at a fixed three-quarter camera. The monitor is a small UI
screen that changes with the scene (file list / chart / chat / locked / boot).

Output matches what the room already plays: <animal>/<scene>/NNN.png under
both app/static/mascot and plugin/frames/mascot, plus docs/preview previews.

Usage:
    python scripts/render_studio.py --scenes all --size 512
    python scripts/render_studio.py --scenes sleep --frames 1 --outdir data/_preview
"""

from __future__ import annotations

import argparse
import math
import shutil
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
APP_MASCOT = ROOT / 'app' / 'static' / 'mascot'
PLUGIN_MASCOT = ROOT / 'plugin' / 'frames' / 'mascot'
PREVIEW_DIR = ROOT / 'docs' / 'preview'
WORK = 1024

BLACK = (16, 16, 16)
WHITE = (255, 255, 255)
SHELL = (250, 250, 248)
SHELL_EDGE = (231, 231, 228)
SHELL_SHADE = (241, 241, 238)
SCREEN_BLUE = (74, 144, 226)
INK = (56, 56, 56)
SCARF = {
    'enter': (240, 190, 72),
    'sit': (66, 186, 140),
    'study': (62, 144, 232),
    'chat': (228, 82, 78),
    'sleep': (86, 122, 224),
}
FONT_PATHS = (r'C:\Windows\Fonts\arialbd.ttf', r'C:\Windows\Fonts\msyhbd.ttc')
FONT_CACHE: dict[int, ImageFont.ImageFont] = {}


def font(size: int):
    if size not in FONT_CACHE:
        loaded = None
        for path in FONT_PATHS:
            try:
                loaded = ImageFont.truetype(path, size)
                break
            except OSError:
                continue
        FONT_CACHE[size] = loaded or ImageFont.load_default()
    return FONT_CACHE[size]


def ease(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)


def lerp_color(a, b, t: float):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def background() -> Image.Image:
    img = Image.new('RGB', (WORK, WORK), WHITE)
    draw = ImageDraw.Draw(img)
    for y in range(WORK):
        t = y / WORK
        if t < 0.55:
            continue
        k = (t - 0.55) / 0.45
        draw.line([(0, y), (WORK, y)], fill=lerp_color(WHITE, (247, 247, 244), k * 0.9))
    return img


def shadow_layer() -> Image.Image:
    layer = Image.new('RGBA', (WORK, WORK), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    # floor contact: chair, desk, cabinet
    draw.ellipse([320, 840, 730, 1010], fill=(96, 96, 92, 52))
    draw.polygon([(120, 700), (924, 686), (986, 800), (54, 820)], fill=(96, 96, 92, 28))
    draw.ellipse([630, 790, 1020, 970], fill=(96, 96, 92, 30))
    # on the desk: monitor + cat
    draw.ellipse([400, 470, 720, 560], fill=(96, 96, 92, 34))
    draw.ellipse([330, 600, 740, 780], fill=(80, 80, 78, 32))
    layer = layer.filter(ImageFilter.GaussianBlur(30))
    return layer


def draw_desk(draw: ImageDraw.ImageDraw) -> None:
    # desk top
    top = [(148, 512), (884, 500), (920, 674), (116, 690)]
    draw.polygon(top, fill=(254, 254, 252), outline=(238, 238, 235))
    # front edge
    draw.polygon([(116, 690), (920, 674), (920, 706), (116, 724)], fill=(247, 247, 244))
    draw.line([(116, 690), (920, 674)], fill=(235, 235, 232), width=3)
    # legs
    draw.rounded_rectangle([176, 700, 206, 930], radius=10, fill=SHELL, outline=SHELL_EDGE)
    draw.rounded_rectangle([872, 690, 900, 900], radius=10, fill=SHELL, outline=SHELL_EDGE)
    # side cabinet
    draw.polygon([(772, 588), (916, 594), (890, 610), (748, 604)], fill=WHITE, outline=SHELL_EDGE)
    draw.rounded_rectangle([752, 604, 906, 858], radius=12, fill=SHELL, outline=SHELL_EDGE)
    for y in (676, 752):
        draw.line([(762, y), (896, y)], fill=(232, 232, 229), width=3)
    draw.rounded_rectangle([818, 638, 842, 644], radius=3, fill=(226, 226, 222))
    draw.rounded_rectangle([818, 714, 842, 720], radius=3, fill=(226, 226, 222))


def draw_monitor(draw: ImageDraw.ImageDraw) -> tuple[int, int, int, int]:
    # stand
    draw.ellipse([470, 498, 596, 528], fill=(246, 246, 243), outline=SHELL_EDGE)
    draw.rounded_rectangle([500, 442, 562, 508], radius=6, fill=SHELL_SHADE)
    # bezel
    draw.rounded_rectangle([376, 184, 740, 456], radius=18, fill=(248, 248, 246), outline=(229, 229, 226), width=3)
    draw.rounded_rectangle([392, 200, 724, 440], radius=10, fill=(233, 233, 230))
    return (402, 210, 714, 430)


def ui_image(scene: str, t: float, size: tuple[int, int]) -> Image.Image:
    w, h = size
    img = Image.new('RGB', (w, h), SCREEN_BLUE)
    draw = ImageDraw.Draw(img)
    if scene == 'sleep':
        img.paste((24, 24, 24), (0, 0, w, h))
        draw = ImageDraw.Draw(img)
        # asleep screen: dim moon and a few short lines
        draw.ellipse([w - 96, 24, w - 40, 80], fill=(58, 62, 78))
        draw.ellipse([w - 86, 24, w - 30, 80], fill=(24, 24, 24))
        for row in range(3):
            draw.rounded_rectangle([28, 40 + row * 26, 28 + (90 - row * 12), 47 + row * 26], radius=3, fill=(52, 54, 64))
        return img

    if scene == 'enter':
        boot = Image.new('RGB', (w, h), (248, 248, 246))
        bd = ImageDraw.Draw(boot)
        bd.rounded_rectangle([w // 2 - 34, 34, w // 2 + 34, 102], radius=16, fill=SCREEN_BLUE)
        bd.ellipse([w // 2 - 16, 52, w // 2 + 16, 84], fill=(248, 248, 246))
        progress = 0.15 + 0.8 * ease(t)
        bd.rounded_rectangle([38, h - 54, w - 38, h - 40], radius=7, fill=(231, 231, 228))
        bd.rounded_rectangle([38, h - 54, 38 + int((w - 76) * progress), h - 40], radius=7, fill=SCREEN_BLUE)
        return boot

    # blue desktop
    for y in range(h):
        draw.line([(0, y), (w, y)], fill=lerp_color((80, 152, 232), (58, 124, 204), y / h))
    # top bar
    draw.rounded_rectangle([0, 0, w, 18], radius=0, fill=(52, 110, 186))
    draw.ellipse([8, 6, 14, 12], fill=(255, 255, 255))
    draw.ellipse([19, 6, 25, 12], fill=(235, 235, 235))
    draw.ellipse([30, 6, 36, 12], fill=(200, 200, 200))
    # window
    left, top, right, bottom = 18, 28, w - 18, h - 20
    draw.rounded_rectangle([left, top, right, bottom], radius=6, fill=(252, 252, 251))
    draw.rounded_rectangle([left, top, right, top + 18], radius=6, fill=(240, 240, 237))
    for i in range(3):
        draw.ellipse([left + 8 + i * 10, top + 7, left + 13 + i * 10, top + 12], fill=(205, 205, 202))

    if scene == 'study':
        # line chart + bars
        base_y = top + 118
        points = []
        for i in range(9):
            x = left + 16 + i * (right - left - 32) / 8
            y = base_y - 34 - 26 * math.sin(i * 0.85 + t * 2.0 * math.pi)
            points.append((x, y))
        draw.line(points, fill=(62, 144, 232), width=4, joint='curve')
        for i, (x, y) in enumerate(points):
            draw.ellipse([x - 4, y - 4, x + 4, y + 4], fill=(62, 144, 232))
        for i in range(6):
            bar_h = 18 + 16 * abs(math.sin(i * 0.7 + t * 2.0 * math.pi))
            x = left + 22 + i * 20
            draw.rounded_rectangle([x, bottom - 16 - bar_h, x + 12, bottom - 16], radius=3, fill=(126, 180, 238))
        for row in range(3):
            draw.rounded_rectangle([left + 14, top + 34 + row * 12, left + 68, top + 40 + row * 12], radius=3, fill=(206, 206, 203))
    elif scene == 'chat':
        bubbles = [
            (left + 14, top + 36, left + 130, top + 62, (230, 230, 226)),
            (right - 132, top + 72, right - 18, top + 98, (66, 144, 232)),
            (left + 26, top + 108, left + 144, top + 134, (230, 230, 226)),
        ]
        for index, (x0, y0, x1, y1, color) in enumerate(bubbles):
            visible = t * len(bubbles) >= index + 0.1
            if not visible:
                continue
            draw.rounded_rectangle([x0, y0, x1, y1], radius=10, fill=color)
            for dot in range(3):
                draw.ellipse([x0 + 12 + dot * 12, (y0 + y1) // 2 - 3, x0 + 18 + dot * 12, (y0 + y1) // 2 + 3], fill=(120, 120, 116) if color != (66, 144, 232) else (220, 236, 252))
        # typing dots
        for dot in range(3):
            alpha = 0.35 + 0.65 * abs(math.sin(t * 2.0 * math.pi - dot * 0.7))
            shade = int(120 + 80 * alpha)
            draw.ellipse([left + 20 + dot * 12, bottom - 40, left + 26 + dot * 12, bottom - 34], fill=(shade, shade, shade))
    else:  # sit / idle: file list
        for row in range(7):
            y = top + 30 + row * 20
            icon = (206, 206, 203) if row % 3 else (126, 180, 238)
            draw.rounded_rectangle([left + 12, y, left + 22, y + 10], radius=2, fill=icon)
            draw.rounded_rectangle([left + 30, y + 2, left + 108 - (row % 3) * 12, y + 8], radius=3, fill=(214, 214, 211))
            draw.rounded_rectangle([right - 70, y + 2, right - 16, y + 8], radius=3, fill=(232, 232, 229))
    return img


def paste_screen(frame: Image.Image, scene: str, t: float, rect: tuple[int, int, int, int], pulse: float) -> None:
    x0, y0, x1, y1 = rect
    ui = ui_image(scene, t, (x1 - x0, y1 - y0))
    mask = Image.new('L', ui.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, ui.width - 1, ui.height - 1], radius=8, fill=255)
    frame.paste(ui, (x0, y0), mask)
    # subtle glass reflection
    glass = Image.new('RGBA', ui.size, (255, 255, 255, 0))
    gd = ImageDraw.Draw(glass)
    gd.polygon([(0, 0), (ui.width * 0.55, 0), (0, ui.height * 0.62)], fill=(255, 255, 255, 14))
    frame.paste(glass, (x0, y0), glass)


def draw_cat(scene: str, t: float, phase: float, opacity: float) -> Image.Image:
    layer = Image.new('RGBA', (WORK, WORK), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    breathe = math.sin(phase) * 0.012
    bob = math.sin(phase) * 3.0
    asleep = scene == 'sleep'
    head_shift = (-52, 26) if asleep else (0, 0)
    head_angle = -14 if asleep else 0

    # arms resting on the desk (elbows out)
    arm_y = 606 + bob
    for sign in (-1, 1):
        shoulder = (520 + sign * 88, 566 + bob)
        elbow = (520 + sign * 158, 616 + bob * 0.6)
        paw = (520 + sign * 194, arm_y)
        draw.line([shoulder, elbow, paw], fill=BLACK, width=52, joint='curve')
        draw.ellipse([paw[0] - 28, paw[1] - 22, paw[0] + 28, paw[1] + 22], fill=BLACK)

    # body
    body = [352, 494 + bob, 696, 742 + bob]
    draw.ellipse(body, fill=BLACK)

    # head (drawn on a separate layer so it can tilt)
    head = Image.new('RGBA', (WORK, WORK), (0, 0, 0, 0))
    hd = ImageDraw.Draw(head)
    cx, cy = 524 + head_shift[0], 420 + head_shift[1] + bob
    radius = 84
    hd.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], fill=BLACK)
    # ears (same black so they merge with the head)
    hd.polygon([(cx - 84, cy - 44), (cx - 66, cy - 150), (cx - 6, cy - 70)], fill=BLACK)
    hd.polygon([(cx + 6, cy - 70), (cx + 66, cy - 150), (cx + 84, cy - 44)], fill=BLACK)
    if asleep:
        # half-turned face: closed eyes and a small nose on the visible side
        hd.arc([cx - 72, cy - 12, cx - 20, cy + 22], start=200, end=340, fill=(238, 238, 234), width=7)
        hd.arc([cx + 12, cy - 10, cx + 58, cy + 18], start=200, end=340, fill=(238, 238, 234), width=7)
        hd.ellipse([cx - 16, cy + 12, cx + 2, cy + 26], fill=(58, 58, 56))
    if head_angle:
        head = head.rotate(head_angle, resample=Image.Resampling.BICUBIC, center=(cx, cy))
    layer = Image.alpha_composite(layer, head)
    draw = ImageDraw.Draw(layer)

    # scarf: thick band around the neck
    scarf_color = SCARF.get(scene, SCARF['sit'])
    fold = lerp_color(scarf_color, (0, 0, 0), 0.18)
    band_top = 492 + bob * 0.6
    band = [
        (438, band_top - 4), (524, band_top - 12), (610, band_top - 4),
        (664, band_top + 28), (650, band_top + 56),
        (590, band_top + 78), (524, band_top + 90), (458, band_top + 78),
        (398, band_top + 56), (384, band_top + 28),
    ]
    draw.polygon(band, fill=scarf_color)
    draw.line(
        [(406, band_top + 48), (466, band_top + 72), (524, band_top + 82),
         (582, band_top + 72), (642, band_top + 48)],
        fill=fold, width=6, joint='curve',
    )
    draw.line(
        [(446, band_top - 4), (524, band_top - 13), (602, band_top - 4)],
        fill=lerp_color(scarf_color, WHITE, 0.38), width=5, joint='curve',
    )

    if opacity < 1.0:
        alpha = layer.getchannel('A').point(lambda value: int(value * opacity))
        layer.putalpha(alpha)
    return layer


def draw_chair(draw: ImageDraw.ImageDraw) -> None:
    # chair back in front of the cat's lower body
    draw.rounded_rectangle([392, 654, 648, 900], radius=44, fill=(252, 252, 250), outline=(234, 234, 231), width=3)
    draw.rounded_rectangle([410, 672, 630, 700], radius=14, fill=(247, 247, 244))
    draw.rounded_rectangle([506, 892, 546, 952], radius=8, fill=SHELL_SHADE)
    # five-star base
    hub = (526, 966)
    for angle in (200, 235, 270, 305, 340):
        rad = math.radians(angle)
        end = (hub[0] + 118 * math.cos(rad), hub[1] + 40 * math.sin(rad) + 20)
        draw.line([hub, end], fill=(238, 238, 235), width=9)
        draw.ellipse([end[0] - 10, end[1] - 8, end[0] + 10, end[1] + 10], fill=(232, 232, 229))
    draw.ellipse([hub[0] - 18, hub[1] - 12, hub[0] + 18, hub[1] + 14], fill=(240, 240, 237))


def draw_sleep_zs(frame: Image.Image, t: float) -> None:
    draw = ImageDraw.Draw(frame)
    for index in range(3):
        local = (t + index / 3.0) % 1.0
        alpha = int(210 * math.sin(math.pi * local))
        if alpha <= 0:
            continue
        size = int(30 + 22 * (1.0 - local))
        text_font = font(size)
        x = 700 + local * 92 + index * 14
        y = 300 - local * 120 + index * 10
        overlay = Image.new('RGBA', (size * 2, size * 2), (0, 0, 0, 0))
        od = ImageDraw.Draw(overlay)
        od.text((size * 0.3, size * 0.2), 'Z', font=text_font, fill=(70, 70, 70, alpha))
        frame.alpha_composite(overlay, (int(x), int(y)))


def render_frame(scene: str, frame: int, frames: int) -> Image.Image:
    t = frame / float(frames)
    phase = 2.0 * math.pi * t
    base = background().convert('RGBA')
    base = Image.alpha_composite(base, shadow_layer())
    overlay = Image.new('RGBA', (WORK, WORK), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    draw_desk(draw)
    screen_rect = draw_monitor(draw)
    base = Image.alpha_composite(base, overlay)
    base = base.convert('RGB')
    paste_screen(base, scene, t, screen_rect, 1.0)
    base = base.convert('RGBA')

    opacity = 1.0
    if scene == 'enter':
        opacity = ease(min(1.0, frame / max(1.0, frames * 0.45)))
    cat = draw_cat(scene, t, phase, opacity)
    base = Image.alpha_composite(base, cat)

    chair = Image.new('RGBA', (WORK, WORK), (0, 0, 0, 0))
    draw_chair(ImageDraw.Draw(chair))
    base = Image.alpha_composite(base, chair)

    if scene == 'sleep':
        draw_sleep_zs(base, t)
    return base.convert('RGB').resize((512, 512), Image.Resampling.LANCZOS)


def _font(size: int):
    return font(size)


def save_previews(scene: str, frames: list[Image.Image], base: Path) -> None:
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    gif_frames = [frame.convert('P', palette=Image.Palette.ADAPTIVE, colors=128) for frame in frames]
    gif_frames[0].save(PREVIEW_DIR / f'studio-{scene}.gif', save_all=True, append_images=gif_frames[1:], duration=55, loop=0, optimize=True)


def contact_sheet(scenes: list[str], base: Path) -> None:
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    tiles = []
    for scene in scenes:
        frames = sorted((base / scene).glob('*.png'))
        if not frames:
            continue
        pick_index = {'chat': 6, 'enter': max(0, len(frames) - 7), 'sleep': 6, 'study': 2, 'sit': 2}.get(scene, 2)
        pick = frames[min(pick_index, len(frames) - 1)]
        tiles.append((scene, Image.open(pick).convert('RGB').resize((480, 480), Image.Resampling.LANCZOS)))
    cell = 520
    sheet = Image.new('RGB', (cell * 2 + 20, cell * 2 + 20), WHITE)
    draw = ImageDraw.Draw(sheet)
    label = font(28)
    for index, (scene, tile) in enumerate(tiles[:4]):
        x = 10 + (index % 2) * cell + 20
        y = 10 + (index // 2) * cell + 20
        sheet.paste(tile, (x, y))
        draw.text((x + 8, y + 440), scene, font=label, fill=(90, 90, 86))
    sheet.save(PREVIEW_DIR / 'studio-contact.png')


def render(scenes: list[str], frames: int, outdir: Path | None, preview: bool, animal: str) -> None:
    targets = [outdir] if outdir else [APP_MASCOT / animal, PLUGIN_MASCOT / animal]
    for scene in scenes:
        for base in targets:
            shutil.rmtree(base / scene, ignore_errors=True)
            (base / scene).mkdir(parents=True, exist_ok=True)
        rendered: list[Image.Image] = []
        for frame in range(frames):
            image = render_frame(scene, frame, frames)
            rendered.append(image)
            for base in targets:
                image.save(base / scene / f'{frame + 1:03d}.png')
        if preview:
            save_previews(scene, rendered, targets[0])
    if preview:
        contact_sheet(scenes, targets[0])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Render the studio black-cat frames')
    parser.add_argument('--scenes', default='sleep,sit,study,chat,enter')
    parser.add_argument('--frames', type=int, default=20)
    parser.add_argument('--outdir', default=None)
    parser.add_argument('--animal', default='studio')
    parser.add_argument('--no-preview', action='store_true')
    args = parser.parse_args(argv)
    scenes = [item.strip() for item in args.scenes.split(',') if item.strip()]
    outdir = Path(args.outdir) if args.outdir else None
    render(scenes, args.frames, outdir, not args.no_preview, args.animal)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
