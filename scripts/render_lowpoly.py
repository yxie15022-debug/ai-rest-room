
"""Render Marvis-style low-poly mascot frames.

The look: a cream low-poly cat with a coral collar on a white seamless floor,
fixed camera, matte flat shading, soft contact shadow. Output is the same
<headscene>/NN.png layout the Tk window and room page already play.

Usage:
    python scripts/render_lowpoly.py --scenes all --size 512
    python scripts/render_lowpoly.py --scenes sleep --frames 1 --outdir data/_preview
"""

from __future__ import annotations

import argparse
import math
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
APP_MASCOT = ROOT / 'app' / 'static' / 'mascot'
PLUGIN_MASCOT = ROOT / 'plugin' / 'frames' / 'mascot'
PREVIEW_DIR = ROOT / 'docs' / 'preview'

Vec = tuple[float, float, float]
Color = tuple[int, int, int]

CREAM = (243, 233, 218)
CREAM_SHADE = (226, 212, 192)
COLLAR = (232, 106, 96)
COLLAR_DARK = (198, 82, 76)
INK = (54, 48, 43)
WHITE = (255, 255, 255)
WORK_SIZE = 1024

CAMERA = (0.0, 2.95, 7.8)
TARGET = (0.0, 0.55, 0.0)
LIGHT = (-0.38, 0.82, 0.55)
LIGHT2 = (0.55, 0.22, 0.68)
FOV = math.radians(33.0)


def v_add(a: Vec, b: Vec) -> Vec:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def v_sub(a: Vec, b: Vec) -> Vec:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def v_mul(a: Vec, k: float) -> Vec:
    return (a[0] * k, a[1] * k, a[2] * k)


def v_dot(a: Vec, b: Vec) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def v_cross(a: Vec, b: Vec) -> Vec:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def v_norm(a: Vec) -> Vec:
    length = math.sqrt(v_dot(a, a)) or 1.0
    return (a[0] / length, a[1] / length, a[2] / length)


def v_lerp(a: Vec, b: Vec, t: float) -> Vec:
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t)


LIGHT = v_norm(LIGHT)
LIGHT2 = v_norm(LIGHT2)
_F = v_norm(v_sub(TARGET, CAMERA))
_R = v_norm(v_cross(_F, (0.0, 1.0, 0.0)))
_U = v_cross(_R, _F)


@dataclass
class Part:
    verts: list[Vec]
    faces: list[tuple[int, ...]]
    color: Color
    emissive: bool = False


def ellipsoid(center: Vec, radii: Vec, u: int = 8, v: int = 5, color: Color = CREAM) -> Part:
    cx, cy, cz = center
    rx, ry, rz = radii
    verts: list[Vec] = [(cx, cy + ry, cz)]
    for j in range(1, v):
        phi = math.pi * j / v
        sr, sy = math.sin(phi), math.cos(phi)
        for i in range(u):
            th = 2.0 * math.pi * i / u
            verts.append((cx + rx * sr * math.cos(th), cy + ry * sy, cz + rz * sr * math.sin(th)))
    verts.append((cx, cy - ry, cz))
    bottom = len(verts) - 1
    faces: list[tuple[int, ...]] = []
    for i in range(u):
        faces.append((0, 1 + i, 1 + (i + 1) % u))
    for j in range(v - 2):
        a = 1 + j * u
        b = a + u
        for i in range(u):
            i2 = (i + 1) % u
            faces.append((a + i, b + i, b + i2, a + i2))
    last = 1 + (v - 2) * u
    for i in range(u):
        faces.append((bottom, last + (i + 1) % u, last + i))
    return Part(verts, faces, color)


def box(center: Vec, size: Vec, color: Color, taper: float = 1.0) -> Part:
    cx, cy, cz = center
    sx, sy, sz = size
    hx, hy, hz = sx / 2.0, sy / 2.0, sz / 2.0
    tx, tz = hx * taper, hz * taper
    verts = [
        (cx - hx, cy - hy, cz - hz),
        (cx + hx, cy - hy, cz - hz),
        (cx + hx, cy - hy, cz + hz),
        (cx - hx, cy - hy, cz + hz),
        (cx - tx, cy + hy, cz - tz),
        (cx + tx, cy + hy, cz - tz),
        (cx + tx, cy + hy, cz + tz),
        (cx - tx, cy + hy, cz + tz),
    ]
    faces = [
        (0, 1, 2, 3),
        (7, 6, 5, 4),
        (0, 4, 5, 1),
        (1, 5, 6, 2),
        (2, 6, 7, 3),
        (3, 7, 4, 0),
    ]
    return Part(verts, faces, color)


def tube(points: list[Vec], radii: list[float], sides: int = 6, color: Color = CREAM) -> Part:
    ring_ids: list[list[int]] = []
    verts: list[Vec] = []
    for index, (point, radius) in enumerate(zip(points, radii)):
        if index == 0:
            direction = v_sub(points[1], points[0])
        elif index == len(points) - 1:
            direction = v_sub(points[-1], points[-2])
        else:
            direction = v_sub(points[index + 1], points[index - 1])
        direction = v_norm(direction)
        up = (0.0, 1.0, 0.0) if abs(direction[1]) < 0.9 else (1.0, 0.0, 0.0)
        a = v_norm(v_cross(direction, up))
        b = v_norm(v_cross(direction, a))
        ring: list[int] = []
        for i in range(sides):
            th = 2.0 * math.pi * i / sides
            vert = v_add(point, v_add(v_mul(a, radius * math.cos(th)), v_mul(b, radius * math.sin(th))))
            verts.append(vert)
            ring.append(len(verts) - 1)
        ring_ids.append(ring)
    faces: list[tuple[int, ...]] = []
    for k in range(len(ring_ids) - 1):
        r0, r1 = ring_ids[k], ring_ids[k + 1]
        for i in range(sides):
            i2 = (i + 1) % sides
            faces.append((r0[i], r0[i2], r1[i2], r1[i]))
    faces.append(tuple(reversed(ring_ids[0])))
    faces.append(tuple(ring_ids[-1]))
    return Part(verts, faces, color)


def cone(base: Vec, tip: Vec, radius: float, sides: int = 4, color: Color = CREAM) -> Part:
    direction = v_norm(v_sub(tip, base))
    up = (0.0, 1.0, 0.0) if abs(direction[1]) < 0.9 else (1.0, 0.0, 0.0)
    a = v_norm(v_cross(direction, up))
    b = v_norm(v_cross(direction, a))
    verts: list[Vec] = []
    for i in range(sides):
        th = 2.0 * math.pi * i / sides
        verts.append(v_add(base, v_add(v_mul(a, radius * math.cos(th)), v_mul(b, radius * math.sin(th)))))
    verts.append(tip)
    faces = []
    for i in range(sides):
        faces.append((i, (i + 1) % sides, sides))
    faces.append(tuple(reversed(range(sides))))
    return Part(verts, faces, color)


def band(center: Vec, radius: float, width: float, sides: int = 8, color: Color = COLLAR) -> Part:
    cx, cy, cz = center
    verts: list[Vec] = []
    for x in (cx - width / 2.0, cx + width / 2.0):
        for i in range(sides):
            th = 2.0 * math.pi * i / sides
            verts.append((x, cy + radius * math.cos(th), cz + radius * math.sin(th)))
    faces = []
    for i in range(sides):
        i2 = (i + 1) % sides
        faces.append((i, i2, sides + i2, sides + i))
    return Part(verts, faces, color)


def patch(center: Vec, facing: Vec, width: float, height: float, color: Color = INK, sides: int = 4) -> Part:
    direction = v_norm(facing)
    up = (0.0, 1.0, 0.0) if abs(direction[1]) < 0.9 else (1.0, 0.0, 0.0)
    a = v_norm(v_cross(direction, up))
    b = v_norm(v_cross(direction, a))
    verts: list[Vec] = []
    for i in range(sides):
        th = 2.0 * math.pi * i / sides + math.pi / 2.0
        verts.append(v_add(center, v_add(v_mul(a, width * math.cos(th)), v_mul(b, height * math.sin(th)))))
    return Part(verts, [tuple(range(sides))], color)


def transform_parts(parts: list[Part], yaw: float, offset: Vec) -> list[Part]:
    cy, sy = math.cos(yaw), math.sin(yaw)
    moved: list[Part] = []
    for part in parts:
        verts = []
        for x, y, z in part.verts:
            verts.append((x * cy + z * sy + offset[0], y + offset[1], -x * sy + z * cy + offset[2]))
        moved.append(Part(verts, part.faces, part.color, part.emissive))
    return moved


def transform_point(point: Vec, yaw: float, offset: Vec) -> Vec:
    cy, sy = math.cos(yaw), math.sin(yaw)
    x, y, z = point
    return (x * cy + z * sy + offset[0], y + offset[1], -x * sy + z * cy + offset[2])


def project(point: Vec, size: int) -> tuple[float, float, float] | None:
    rel = v_sub(point, CAMERA)
    depth = v_dot(rel, _F)
    if depth < 0.25:
        return None
    focal = (size / 2.0) / math.tan(FOV / 2.0)
    x = size / 2.0 + v_dot(rel, _R) / depth * focal
    y = size / 2.0 - v_dot(rel, _U) / depth * focal
    return (x, y, depth)


def face_normal(points: list[Vec]) -> Vec:
    nx = ny = nz = 0.0
    for index, point in enumerate(points):
        nxt = points[(index + 1) % len(points)]
        nx += (point[1] - nxt[1]) * (point[2] + nxt[2])
        ny += (point[2] - nxt[2]) * (point[0] + nxt[0])
        nz += (point[0] - nxt[0]) * (point[1] + nxt[1])
    return v_norm((nx, ny, nz))


def shade(color: Color, normal: Vec, centroid: Vec) -> Color:
    to_cam = v_norm(v_sub(CAMERA, centroid))
    n = normal if v_dot(normal, to_cam) >= 0 else v_mul(normal, -1.0)
    key = max(0.0, v_dot(n, LIGHT))
    fill = max(0.0, v_dot(n, LIGHT2))
    ground = 0.88 + 0.12 * min(1.0, centroid[1] / 1.4)
    k = (0.47 + 0.53 * key + 0.06 * fill) * ground
    warm = (1.0, 0.985, 0.965)
    return tuple(max(0, min(255, int(color[i] * k * warm[i]))) for i in range(3))


def shadow_point(point: Vec) -> Vec:
    k = max(0.0, point[1]) / LIGHT[1]
    return (point[0] - LIGHT[0] * k, 0.0, point[2] - LIGHT[2] * k)


def convex_hull(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    pts = sorted(set(points))
    if len(pts) <= 2:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def background(size: int) -> Image.Image:
    img = Image.new('RGB', (size, size), WHITE)
    draw = ImageDraw.Draw(img)
    horizon = int(size * 0.70)
    for y in range(horizon, size):
        t = (y - horizon) / max(1, size - horizon)
        color = (
            int(255 - 6 * t),
            int(255 - 9 * t),
            int(255 - 15 * t),
        )
        draw.line([(0, y), (size, y)], fill=color)
    return img


def draw_shadow(img: Image.Image, groups: list[list[Vec]], size: int) -> Image.Image:
    hulls = []
    for group in groups:
        pts = []
        for vertex in group:
            projected = project(shadow_point(vertex), size)
            if projected is not None:
                pts.append((projected[0], projected[1]))
        hull = convex_hull(pts)
        if len(hull) >= 3:
            hulls.append(hull)
    result = img.convert('RGBA')
    for alpha, blur in ((62, 0.026), (58, 0.009)):
        layer = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(layer)
        for hull in hulls:
            draw.polygon(hull, fill=(118, 106, 90, alpha))
        layer = layer.filter(ImageFilter.GaussianBlur(int(size * blur)))
        result = Image.alpha_composite(result, layer)
    return result.convert('RGB')


def draw_parts(img: Image.Image, parts: list[Part], size: int) -> Image.Image:
    draw = ImageDraw.Draw(img)
    faces: list[tuple[float, list[tuple[float, float]], Color]] = []
    for part in parts:
        for face in part.faces:
            world = [part.verts[i] for i in face]
            projected = [project(p, size) for p in world]
            if any(p is None for p in projected):
                continue
            pts = [(p[0], p[1]) for p in projected if p is not None]
            depth = sum(p[2] for p in projected if p is not None) / len(pts)
            centroid = (
                sum(p[0] for p in world) / len(world),
                sum(p[1] for p in world) / len(world),
                sum(p[2] for p in world) / len(world),
            )
            color = part.color if part.emissive else shade(part.color, face_normal(world), centroid)
            faces.append((depth, pts, color))
    faces.sort(key=lambda item: item[0], reverse=True)
    for _, pts, color in faces:
        draw.polygon(pts, fill=color)
    return img


# ---------------------------------------------------------------- cat poses

def sleep_cat(phase: float) -> tuple[list[Part], dict]:
    breathe = 1.0 + 0.018 * math.sin(phase)
    parts: list[Part] = []
    parts.append(ellipsoid((0.10, 0.62 * breathe, 0.0), (0.96, 0.62 * breathe, 0.64), 8, 5))
    parts.append(ellipsoid((0.64, 0.66 * breathe, 0.0), (0.58, 0.56 * breathe, 0.60), 7, 4))
    parts.append(ellipsoid((-0.92, 0.80, 0.04), (0.62, 0.58, 0.60), 8, 5))
    head = (-0.92, 0.80, 0.04)
    for sign in (-1.0, 1.0):
        base = (-0.82, 1.16, 0.04 + 0.40 * sign)
        tip = (-0.86, 1.58, 0.04 + 0.52 * sign)
        parts.append(cone(base, tip, 0.27, 4))
    parts.append(band((-0.52, 0.84, 0.03), 0.50, 0.16, 8))
    for sign in (-1.0, 1.0):
        parts.append(tube([(-0.94, 0.34, 0.17 * sign), (-1.14, 0.16, 0.16 * sign), (-1.24, 0.13, 0.16 * sign)], [0.17, 0.14, 0.11], 6))
        parts.append(ellipsoid((-1.30, 0.12, 0.16 * sign), (0.21, 0.12, 0.15), 6, 3))
    for sign in (-1.0, 1.0):
        parts.append(ellipsoid((0.62, 0.38, 0.36 * sign), (0.30, 0.20, 0.19), 6, 4))
    tail_points = [
        (0.86, 0.64, 0.40),
        (1.24, 0.46, 0.50),
        (1.44, 0.26, 0.18),
        (1.18, 0.14, -0.18),
        (0.88, 0.11, -0.34),
    ]
    sway = math.sin(phase) * 0.04
    tail_points = [(p[0], p[1] + sway * i * 0.3, p[2] + sway * (i + 1)) for i, p in enumerate(tail_points)]
    parts.append(tube(tail_points, [0.16, 0.14, 0.11, 0.09, 0.07], 6))
    return parts, {'head': (-0.92, 1.34, 0.04), 'face': (-1.46, 0.86, 0.04), 'right': (-1.42, 0.86, 0.34), 'up': (-1.46, 1.12, 0.04), 'groups': 2}


def sit_cat(phase: float, blink: bool = True, walk: float | None = None) -> tuple[list[Part], dict]:
    breathe = 1.0 + 0.014 * math.sin(phase)
    parts: list[Part] = []
    parts.append(ellipsoid((0.16, 0.98 * breathe, 0.0), (0.74, 0.82 * breathe, 0.66), 8, 5))
    parts.append(ellipsoid((0.70, 0.58, 0.0), (0.56, 0.46, 0.56), 7, 4))
    head = (-0.38, 1.72, 0.02)
    parts.append(ellipsoid(head, (0.58, 0.54, 0.58), 8, 5))
    for sign in (-1.0, 1.0):
        base = (-0.30, 2.16, 0.02 + 0.35 * sign)
        tip = (-0.24, 2.58, 0.02 + 0.44 * sign)
        parts.append(cone(base, tip, 0.23, 4))
    parts.append(band((0.05, 1.38, 0.02), 0.52, 0.16, 8))
    swing = 0.10 * math.sin(phase) if walk is not None else 0.0
    for sign in (-1.0, 1.0):
        foot_z = 0.27 * sign
        leg_points = [
            (-0.12, 0.90, 0.27 * sign),
            (-0.18 + swing * 0.6, 0.48, foot_z),
            (-0.24 - swing * 0.6, 0.15, foot_z),
        ]
        parts.append(tube(leg_points, [0.18, 0.15, 0.12], 6))
        parts.append(ellipsoid((-0.32 - swing * 0.6, 0.12, foot_z), (0.20, 0.12, 0.15), 6, 3))
        parts.append(ellipsoid((0.62, 0.60, 0.40 * sign), (0.40, 0.38, 0.26), 6, 4))
        parts.append(tube([(0.84, 0.50, 0.42 * sign), (0.92, 0.15, 0.41 * sign)], [0.17, 0.12], 5))
    tail_points = [(0.74, 0.58, 0.44), (1.10, 0.44, 0.54), (1.32, 0.24, 0.22), (1.04, 0.13, -0.10), (0.84, 0.12, -0.28)]
    sway = math.sin(phase + 0.6) * 0.045
    tail_points = [(p[0], p[1] + sway * i * 0.4, p[2] + sway * (i + 1)) for i, p in enumerate(tail_points)]
    parts.append(tube(tail_points, [0.15, 0.13, 0.11, 0.08, 0.06], 6))
    return parts, {'head': (-0.38, 2.30, 0.02), 'face': (-0.94, 1.76, 0.02), 'right': (-0.90, 1.76, 0.30), 'up': (-0.94, 2.02, 0.02), 'groups': 2}


# ---------------------------------------------------------------- scenes

def scene_parts(scene: str, t: float) -> tuple[list[Part], dict]:
    phase = 2.0 * math.pi * t
    overlays: dict = {}
    if scene == 'sleep':
        parts, meta = sleep_cat(phase)
        yaw, offset = 0.85, (0.25, 0.0, 0.0)
    else:
        walk = math.sin(phase * 2.0) if scene == 'enter' else None
        blink = scene in ('sit', 'study', 'chat', 'enter')
        parts, meta = sit_cat(phase, blink=blink, walk=walk)
        if scene in ('study', 'chat'):
            desk_parts, anchors = desk(phase, chat=scene == 'chat')
            parts += desk_parts
            meta.update(anchors)
            yaw, offset = -2.35, (-0.35, 0.0, 0.0)
        elif scene == 'enter':
            ease = t * t * (3.0 - 2.0 * t)
            yaw, offset = 0.55, (-3.2 * (1.0 - ease), 0.0, 0.0)
        else:
            yaw, offset = 0.72, (0.15, 0.0, 0.0)
    parts = transform_parts(parts, yaw, offset)
    meta = {k: (transform_point(v, yaw, offset) if isinstance(v, tuple) and len(v) == 3 else v) for k, v in meta.items()}
    return parts, {'meta': meta}


def desk(phase: float, chat: bool) -> tuple[list[Part], dict]:
    parts: list[Part] = []
    top = box((-1.95, 0.98, 0.0), (1.5, 0.10, 2.5), (247, 242, 232))
    parts.append(top)
    for x in (-2.55, -1.35):
        for z in (-0.92, 0.92):
            parts.append(box((x, 0.46, z), (0.09, 0.94, 0.09), (233, 225, 211)))
    parts.append(box((-1.60, 0.99, 0.0), (0.09, 0.95, 0.10), (228, 220, 206)))
    parts.append(box((-1.98, 1.52, 0.0), (0.10, 0.92, 1.55), (238, 232, 220)))
    parts.append(box((-1.90, 1.90, 0.0), (0.06, 0.10, 0.28), (228, 220, 206)))
    screen = Part(
        verts=[(-1.91, 1.10, -0.66), (-1.91, 1.10, 0.66), (-1.91, 1.86, 0.66), (-1.91, 1.86, -0.66)],
        faces=[(0, 1, 2, 3)],
        color=(70, 86, 104),
        emissive=True,
    )
    parts.append(screen)
    return parts, {'monitor': (-1.9, 1.95, 0.0), 'screen': (-1.9, 1.5, 0.0), 'chat': chat}


def overlay_layer(scene: str, size: int, meta: dict, t: float) -> Image.Image | None:
    if scene not in ('sleep', 'chat', 'study'):
        return None
    layer = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    if scene == 'chat':
        anchor = project(meta['monitor'], size)
        if anchor:
            for index in range(3):
                start = 0.08 + index * 0.24
                local = max(0.0, min(1.0, (t - start) / 0.18))
                if local <= 0.0:
                    continue
                scale = 0.7 + 0.3 * local
                bx = anchor[0] - 60 + index * 78
                by = anchor[1] - 120 - index * 54 - t * 10
                w, h = 66 * scale, 42 * scale
                fill = (255, 251, 244, 235)
                outline = (232, 106, 96, 120)
                draw.rounded_rectangle([bx - w / 2, by - h / 2, bx + w / 2, by + h / 2], radius=h / 2.4, fill=fill, outline=outline, width=3)
                draw.polygon([(bx - 12, by + h / 2 - 2), (bx - 2, by + h / 2 + 12), (bx + 6, by + h / 2 - 2)], fill=fill)
                for dot in range(3):
                    dx = bx - 14 + dot * 14
                    draw.ellipse([dx - 5, by - 5, dx + 5, by + 5], fill=(54, 48, 43, 210))
    elif scene == 'study':
        anchor = project(meta['screen'], size)
        if anchor:
            pulse = 0.82 + 0.18 * math.sin(t * 2.0 * math.pi)
            glow = Image.new('RGBA', (size, size), (0, 0, 0, 0))
            gdraw = ImageDraw.Draw(glow)
            gx, gy = anchor[0], anchor[1]
            for step in range(5, 0, -1):
                radius = int(size * 0.055 * step)
                alpha = int(7 * pulse)
                gdraw.ellipse([gx - radius, gy - radius * 0.8, gx + radius, gy + radius * 0.8], fill=(120, 170, 210, alpha))
            layer = Image.alpha_composite(layer, glow.filter(ImageFilter.GaussianBlur(int(size * 0.02))))
    elif scene == 'sleep':
        anchor = project(meta['head'], size)
        if anchor:
            for index in range(3):
                local = (t + index / 3.0) % 1.0
                alpha = int(210 * math.sin(math.pi * local))
                if alpha <= 0:
                    continue
                zx = anchor[0] + 30 + local * 80 + index * 12
                zy = anchor[1] - 70 - local * 130 + index * 10
                zsize = int(size * (0.040 + 0.020 * (1.0 - local)))
                font = _font(zsize)
                draw.text((zx, zy), 'Z', font=font, fill=(198, 184, 164, alpha))
    return layer


_FONT_CACHE: dict[int, ImageFont.ImageFont] = {}


def _font(size: int):
    if size not in _FONT_CACHE:
        try:
            _FONT_CACHE[size] = ImageFont.truetype(r'C:\Windows\Fonts\arialbd.ttf', size)
        except OSError:
            _FONT_CACHE[size] = ImageFont.load_default()
    return _FONT_CACHE[size]


def draw_face(img: Image.Image, scene: str, meta: dict, t: float, size: int) -> None:
    """Eyes are drawn in screen space so the face stays clean and cute."""
    if scene not in ('sleep', 'sit'):
        return
    if not meta or 'face' not in meta:
        return
    face = project(meta['face'], size)
    right = project(meta['right'], size)
    up = project(meta['up'], size)
    if not face or not right or not up:
        return
    draw = ImageDraw.Draw(img)
    radius = size * 0.032
    cx, cy = face[0], face[1]
    for sign in (-1.0, 1.0):
        ex = cx + radius * sign * 1.05
        ey = cy - radius * 0.18
        if scene == 'sleep':
            bbox = [ex - radius * 0.36, ey - radius * 0.16, ex + radius * 0.36, ey + radius * 0.26]
            draw.arc(bbox, start=20, end=160, fill=INK, width=max(2, int(size * 0.0065)))
        else:
            blink_phase = (t * 4.0) % 1.0
            if blink_phase < 0.05:
                bbox = [ex - radius * 0.34, ey - radius * 0.14, ex + radius * 0.34, ey + radius * 0.24]
                draw.arc(bbox, start=20, end=160, fill=INK, width=max(2, int(size * 0.0065)))
            else:
                draw.ellipse([ex - radius * 0.30, ey - radius * 0.34, ex + radius * 0.30, ey + radius * 0.34], fill=INK)
                draw.ellipse([ex - radius * 0.10, ey - radius * 0.24, ex + radius * 0.06, ey - radius * 0.12], fill=(252, 249, 242))
    nose = [
        (cx, cy + radius * 0.55),
        (cx - radius * 0.18, cy + radius * 0.42),
        (cx + radius * 0.18, cy + radius * 0.42),
    ]
    draw.polygon(nose, fill=(198, 164, 152))


def render_frame(scene: str, frame: int, frames: int, size: int) -> Image.Image:
    t = frame / float(frames)
    parts, data = scene_parts(scene, t)
    img = background(size)
    cat_groups = []
    for part in parts:
        if part.color == (70, 86, 104):
            continue
        cat_groups.append(part.verts)
    img = draw_shadow(img, cat_groups, size)
    img = draw_parts(img, parts, size)
    draw_face(img, scene, data['meta'], t, size)
    overlay = overlay_layer(scene, size, data['meta'], t)
    if overlay is not None:
        img = Image.alpha_composite(img.convert('RGBA'), overlay).convert('RGB')
    return img.resize((size, size), Image.Resampling.LANCZOS) if size != WORK_SIZE else img


def render(scenes: list[str], frames: int, size: int, outdir: Path | None, preview: bool) -> None:
    targets = []
    if outdir is None:
        targets = [(APP_MASCOT / 'cat'), (PLUGIN_MASCOT / 'cat')]
    else:
        targets = [outdir]
    for scene in scenes:
        for base in targets:
            shutil.rmtree(base / scene, ignore_errors=True)
            (base / scene).mkdir(parents=True, exist_ok=True)
        rendered: list[Image.Image] = []
        for frame in range(frames):
            image = render_frame(scene, frame, frames, WORK_SIZE)
            rendered.append(image.resize((size, size), Image.Resampling.LANCZOS))
            for base in targets:
                rendered[-1].save(base / scene / f'{frame + 1:02d}.png')
            print(f'{scene} frame {frame + 1}/{frames}')
        if preview:
            _save_preview(scene, rendered)
    if preview:
        _contact_sheet(scenes, targets[0] if outdir is None else outdir)


def _save_preview(scene: str, frames: list[Image.Image]) -> None:
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    gif_frames = [frame.convert('P', palette=Image.Palette.ADAPTIVE, colors=128) for frame in frames]
    gif_frames[0].save(PREVIEW_DIR / f'{scene}.gif', save_all=True, append_images=gif_frames[1:], duration=55, loop=0, optimize=True)


def _contact_sheet(scenes: list[str], base: Path) -> None:
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    tiles = []
    for scene in scenes:
        frames = sorted((base / scene).glob('*.png'))
        if not frames:
            continue
        pick = frames[min(2, len(frames) - 1)]
        tile = Image.open(pick).convert('RGB').resize((480, 480), Image.Resampling.LANCZOS)
        tiles.append((scene, tile))
    if not tiles:
        return
    cell = 520
    sheet = Image.new('RGB', (cell * 2 + 20, cell * 2 + 20), WHITE)
    draw = ImageDraw.Draw(sheet)
    font = _font(28)
    for index, (scene, tile) in enumerate(tiles[:4]):
        x = 10 + (index % 2) * cell + 20
        y = 10 + (index // 2) * cell + 20
        sheet.paste(tile, (x, y))
        draw.text((x + 8, y + 440), scene, font=font, fill=(90, 84, 74))
    sheet.save(PREVIEW_DIR / 'cat-contact.png')


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Render the low-poly cat frames')
    parser.add_argument('--scenes', default='sleep,sit,study,chat,enter')
    parser.add_argument('--frames', type=int, default=24)
    parser.add_argument('--size', type=int, default=512)
    parser.add_argument('--outdir', default=None)
    parser.add_argument('--no-preview', action='store_true')
    args = parser.parse_args(argv)
    scenes = [item.strip() for item in args.scenes.split(',') if item.strip()]
    outdir = Path(args.outdir) if args.outdir else None
    render(scenes, args.frames, args.size, outdir, not args.no_preview)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
