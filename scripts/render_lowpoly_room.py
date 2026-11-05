"""Low-poly 3D rest-room, animated, rendered headless in Blender (Eevee).

One cozy room and the black cat. Five scenes, 20 frames each:
  enter: door swings out, the cat walks in, the door closes behind it.
  sit / sleep / study / chat: the cat on the rug, the bed, the chair, the sofa.

Run headless:
    blender --background --python scripts/render_lowpoly_room.py -- \
        --scenes enter,sit,sleep,study,chat --frames 20
"""

from __future__ import annotations

import math
import random
import sys
from pathlib import Path

import bpy
from mathutils import Vector


def parse_args() -> dict:
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    out: dict = {}
    i = 0
    while i < len(argv):
        if argv[i].startswith('--'):
            key = argv[i][2:]
            if i + 1 < len(argv) and not argv[i + 1].startswith('--'):
                out[key] = argv[i + 1]
                i += 2
            else:
                out[key] = '1'
                i += 1
        else:
            i += 1
    return out


ARGS = parse_args()
OUTDIR = Path(ARGS.get('outdir', 'data/_lowpoly_render')).resolve()
ROOT = Path(__file__).resolve().parents[1]
FRAMES = int(ARGS.get('frames', '20'))
SCENES = [s for s in ARGS.get('scenes', 'enter,sit,sleep,study,chat').split(',') if s]
MODELS = [m for m in ARGS.get('models', 'default,deepseek,claude,gpt').split(',') if m]

SCARF_COLORS = {
    'enter': (0.85, 0.28, 0.28),
    'sit': (0.29, 0.62, 0.42),
    'sleep': (0.45, 0.48, 0.72),
    'study': (0.90, 0.55, 0.22),
    'chat': (0.72, 0.38, 0.62),
}

# ---------------------------------------------------------------- palette

WOOD = (0.72, 0.55, 0.36)
WOOD_DARK = (0.60, 0.44, 0.28)
SAGE = (0.66, 0.76, 0.58)
CREAM = (0.93, 0.90, 0.84)
WHITE = (0.96, 0.95, 0.93)
QUILT = (0.45, 0.66, 0.45)
QUILT_DARK = (0.36, 0.55, 0.37)
SOFA_BLUE = (0.45, 0.58, 0.75)
SOFA_DARK = (0.37, 0.48, 0.64)
RUG_RED = (0.75, 0.42, 0.36)
RUG_INNER = (0.88, 0.77, 0.62)
SCREEN_BLUE = (0.29, 0.57, 0.89)
LEAF = (0.36, 0.62, 0.35)
POT = (0.72, 0.42, 0.30)
DOOR_WOOD = (0.55, 0.38, 0.24)
SKIN = (0.95, 0.82, 0.70)
HAIR = (0.22, 0.18, 0.16)
BUBBLE = (0.98, 0.98, 0.97)

M = {}  # materials
R = {}  # objects

PATH_STONES = ((0.40, -3.85), (0.50, -4.55), (0.38, -5.25), (0.48, -5.95),
               (0.30, -6.60), (0.42, -7.25), (0.28, -7.90), (0.40, -8.55),
               (0.26, -9.20))
PATH_LIGHTS = tuple(
    (sx + (0.62 if i % 2 == 0 else -0.62), sy + 0.12)
    for i, (sx, sy) in enumerate(PATH_STONES)
) + ((3.60, -4.60), (4.60, -0.40), (-4.30, -6.90))


def mat(name, color, rough=0.9, emission=None, strength=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = next(n for n in m.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
    bsdf.inputs['Base Color'].default_value = (*color, 1.0)
    bsdf.inputs['Roughness'].default_value = rough
    if emission is not None:
        bsdf.inputs['Emission Color'].default_value = (*emission, 1.0)
        bsdf.inputs['Emission Strength'].default_value = strength
    M[name] = m
    return m


def floor_mat():
    m = bpy.data.materials.new('woodfloor')
    m.use_nodes = True
    nodes = m.node_tree.nodes
    links = m.node_tree.links
    bsdf = next(n for n in nodes if n.type == 'BSDF_PRINCIPLED')
    bsdf.inputs['Roughness'].default_value = 0.85
    tex = nodes.new('ShaderNodeTexImage')
    tex.image = bpy.data.images.load(str(ROOT / 'data' / 'herringbone.png'))
    tex.interpolation = 'Closest'
    mapping = nodes.new('ShaderNodeMapping')
    coord = nodes.new('ShaderNodeTexCoord')
    mapping.inputs['Scale'].default_value = (8.0, 9.5, 1.0)
    links.new(coord.outputs['Generated'], mapping.inputs['Vector'])
    links.new(mapping.outputs['Vector'], tex.inputs['Vector'])
    links.new(tex.outputs['Color'], bsdf.inputs['Base Color'])
    M['woodfloor'] = m
    return m


def assign(obj, material):
    obj.data.materials.append(material)


def cube(name, loc, scale, material, bevel=0.0):
    bpy.ops.mesh.primitive_cube_add(location=loc)
    obj = bpy.context.object
    obj.name = name
    obj.scale = (scale[0] / 2, scale[1] / 2, scale[2] / 2)
    bpy.ops.object.transform_apply(scale=True)
    if bevel > 0:
        mod = obj.modifiers.new('soft', 'BEVEL')
        mod.width = bevel
        mod.segments = 1
    assign(obj, material)
    R[name] = obj
    return obj


def sphere(name, loc, scale, material, segments=12, subdiv=2):
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=subdiv, location=loc)
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    bpy.ops.object.transform_apply(scale=True)
    assign(obj, material)
    R[name] = obj
    return obj


def cone(name, loc, radius, depth, material, vertices=8, rotation=(0, 0, 0)):
    bpy.ops.mesh.primitive_cone_add(vertices=vertices, radius1=radius, radius2=0,
                                    depth=depth, location=loc, rotation=rotation)
    obj = bpy.context.object
    obj.name = name
    assign(obj, material)
    R[name] = obj
    return obj


def cyl(name, loc, radius, depth, material, vertices=10):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth, location=loc)
    obj = bpy.context.object
    obj.name = name
    assign(obj, material)
    R[name] = obj
    return obj


def torus(name, loc, major, minor, material, rotation=(0, 0, 0)):
    bpy.ops.mesh.primitive_torus_add(major_radius=major, minor_radius=minor,
                                     major_segments=12, minor_segments=6,
                                     location=loc, rotation=rotation)
    obj = bpy.context.object
    obj.name = name
    assign(obj, material)
    R[name] = obj
    return obj


# ---------------------------------------------------------------- build once

def build():
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj)
    for m in list(bpy.data.materials):
        bpy.data.materials.remove(m)

    mat('wood', WOOD)
    mat('wood_d', WOOD_DARK)
    floor_mat()
    mat('sage', SAGE)
    mat('cream', CREAM)
    mat('white', WHITE)
    mat('quilt', QUILT)
    mat('quilt_d', QUILT_DARK)
    mat('sofa', SOFA_BLUE)
    mat('sofa_d', SOFA_DARK)
    mat('rug', RUG_RED)
    mat('rug_in', RUG_INNER)
    mat('screen', (0.10, 0.12, 0.16), emission=SCREEN_BLUE, strength=1.5)
    mat('monitor', (0.10, 0.10, 0.12))
    mat('leaf', LEAF)
    mat('pot', POT)
    mat('door', DOOR_WOOD)
    mat('glass', (0.62, 0.80, 0.92), rough=0.4)
    mat('book1', (0.80, 0.42, 0.36))
    mat('book2', (0.90, 0.74, 0.30))
    mat('book3', (0.35, 0.55, 0.80))
    mat('bubble', BUBBLE, rough=0.6)
    mat('heart', (0.89, 0.32, 0.31), emission=(0.89, 0.32, 0.31), strength=0.6)
    mat('cat', (0.055, 0.052, 0.062), rough=0.85)
    mat('eye', (0.45, 0.78, 0.38), emission=(0.30, 0.62, 0.28), strength=0.35)
    mat('eye_shine', (0.96, 0.98, 0.96))
    mat('scarf', (0.85, 0.28, 0.28), rough=0.7)
    mat('moon', (0.95, 0.93, 0.80), emission=(0.95, 0.93, 0.80), strength=2.5)
    mat('lampglow', (1.0, 0.88, 0.55), emission=(1.0, 0.88, 0.55), strength=3.0)
    mat('skin', SKIN, rough=0.7)
    mat('hair', HAIR, rough=0.8)

    # grassy ground with a mottled two-tone noise texture
    mat('grass', (0.38, 0.64, 0.36), rough=1.0)
    g = M['grass']
    gbsdf = next(n for n in g.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
    gnoise = g.node_tree.nodes.new('ShaderNodeTexNoise')
    gnoise.inputs['Scale'].default_value = 5.0
    gnoise.inputs['Detail'].default_value = 3.0
    gramp = g.node_tree.nodes.new('ShaderNodeValToRGB')
    gramp.color_ramp.elements[0].color = (0.31, 0.55, 0.26, 1.0)
    gramp.color_ramp.elements[0].position = 0.25
    gramp.color_ramp.elements[1].color = (0.45, 0.68, 0.36, 1.0)
    gramp.color_ramp.elements[1].position = 0.75
    g.node_tree.links.new(gnoise.outputs['Fac'], gramp.inputs['Fac'])
    g.node_tree.links.new(gramp.outputs['Color'], gbsdf.inputs['Base Color'])
    cube('grass', (0, 0.0, -0.09), (30, 30, 0.08), M['grass'])

    # ---- garden path: stepping stones from the doorway northward
    mat('stone', (0.74, 0.68, 0.56), rough=1.0)
    for i, (sx, sy) in enumerate(PATH_STONES):
        st = cyl(f'stone{i}', (sx, sy, 0.02), 0.34 + (0.06 if i % 2 == 0 else 0.0),
                 0.10, M['stone'], vertices=7)
        st.rotation_euler = (0, 0, i * 0.7)

    # garden lights lining the path + a few on the lawn
    mat('plight', (0.98, 0.88, 0.62), rough=0.5, emission=(1.0, 0.85, 0.50), strength=0.6)
    mat('plmetal', (0.16, 0.17, 0.19), rough=0.6)
    for i, (lx, ly) in enumerate(PATH_LIGHTS):
        cyl(f'pl_base{i}', (lx, ly, 0.04), 0.10, 0.09, M['plmetal'], vertices=8)
        cyl(f'pl_pole{i}', (lx, ly, 0.28), 0.035, 0.46, M['plmetal'], vertices=8)
        sphere(f'pl_globe{i}', (lx, ly, 0.56), (0.12, 0.12, 0.12), M['plight'], segments=8)

    # ------------------------------------------------- vegetation helpers
    for i, col in enumerate(((0.27, 0.52, 0.23), (0.36, 0.62, 0.28), (0.46, 0.66, 0.33))):
        mat(f'tuft{i}', col, rough=1.0)
    for i, col in enumerate(((0.95, 0.80, 0.30), (0.95, 0.55, 0.65), (0.96, 0.95, 0.92), (0.90, 0.35, 0.30))):
        mat(f'petal{i}', col, rough=0.8)

    def grass_clump(cx, cy, seed, s=1.0):
        crng = random.Random(seed)
        for b in range(3):
            h = crng.uniform(0.45, 0.75) * s
            ang = crng.uniform(0, math.tau)
            tilt = crng.uniform(0.10, 0.30)
            blade = cube(f'blade{seed}_{b}',
                         (cx + crng.uniform(-0.10, 0.10) * s,
                          cy + crng.uniform(-0.10, 0.10) * s, h / 2 - 0.04),
                         (0.13, 0.04, h), M[f'tuft{crng.randrange(3)}'])
            blade.rotation_euler = (tilt * math.cos(ang), tilt * math.sin(ang), 0)

    def bush(bx, by, seed, s=1.0):
        brng = random.Random(seed)
        for i in range(brng.randrange(3, 5)):
            r = brng.uniform(0.22, 0.38) * s
            sphere(f'bush{seed}_{i}',
                   (bx + brng.uniform(-0.22, 0.22) * s,
                    by + brng.uniform(-0.22, 0.22) * s,
                    r * 0.75 + brng.uniform(0.0, 0.12) * s),
                   (r, r, r * 0.85), M[f'tuft{brng.randrange(3)}'], subdiv=1)

    def flower(fx, fy, seed):
        frng = random.Random(seed)
        h = frng.uniform(0.28, 0.45)
        cyl(f'fstem{seed}', (fx, fy, h / 2), 0.016, h, M['leaf'], vertices=6)
        sphere(f'fhead{seed}', (fx, fy, h + 0.045), (0.06, 0.06, 0.055),
               M[f'petal{frng.randrange(4)}'], subdiv=1)

    prng = random.Random(7)
    veg = 0
    for i, (sx, sy) in enumerate(PATH_STONES):
        for side in (-1.05, 1.05):
            if prng.random() < 0.82:
                vx = sx + side + prng.uniform(-0.20, 0.20)
                vy = sy + prng.uniform(-0.35, 0.35)
                r = prng.random()
                if r < 0.45:
                    grass_clump(vx, vy, 20000 + veg, s=prng.uniform(0.8, 1.1))
                elif r < 0.78:
                    bush(vx, vy, 20000 + veg, s=prng.uniform(0.55, 0.85))
                else:
                    flower(vx, vy, 20000 + veg)
                veg += 1

    cyl('tree_trunk', (-1.2, -7.9, 0.6), 0.14, 1.2, M['wood_d'], vertices=8)
    sphere('tree_c1', (-1.2, -7.9, 1.55), (0.72, 0.72, 0.62), M['tuft1'], subdiv=1)
    sphere('tree_c2', (-1.55, -7.7, 1.2), (0.46, 0.46, 0.40), M['tuft0'], subdiv=1)
    sphere('tree_c3', (-0.85, -7.75, 1.28), (0.50, 0.50, 0.42), M['tuft2'], subdiv=1)

    bush(-0.55, -4.30, 9001)
    bush(1.35, -4.55, 9002)
    for i, (fx, fy) in enumerate(((0.0, -4.05), (0.92, -4.15), (-0.25, -5.05), (1.15, -5.25))):
        flower(fx, fy, 9100 + i)

    def lawn_spot_ok(gx, gy):
        if abs(gx) < 4.5 and -4.5 < gy < 4.7:
            return False
        if abs(gx) < 3.4 and -6.7 < gy < -3.5:
            return False
        if (gx - 0.4) ** 2 + (gy + 4.5) ** 2 < 1.6 ** 2:
            return False
        if any((gx - sx) ** 2 + (gy - sy) ** 2 < 0.60 ** 2 for sx, sy in PATH_STONES):
            return False
        if any((gx - lx) ** 2 + (gy - ly) ** 2 < 0.40 ** 2 for lx, ly in PATH_LIGHTS):
            return False
        if (gx + 1.2) ** 2 + (gy + 7.9) ** 2 < 1.1 ** 2:
            return False
        return True

    rng = random.Random(42)
    placed = 0
    tries = 0
    while placed < 60 and tries < 1600:
        tries += 1
        gx = rng.uniform(-7.5, 7.5)
        gy = rng.uniform(-9.5, 6.0)
        if not lawn_spot_ok(gx, gy):
            continue
        grass_clump(gx, gy, 1000 + placed)
        placed += 1

    brng2 = random.Random(77)
    b_placed = f_placed = 0
    b_tries = 0
    while (b_placed < 12 or f_placed < 18) and b_tries < 1600:
        b_tries += 1
        gx = brng2.uniform(-7.5, 7.5)
        gy = brng2.uniform(-9.5, 6.0)
        if not lawn_spot_ok(gx, gy):
            continue
        if b_placed < 12 and brng2.random() < 0.5:
            bush(gx, gy, 5000 + b_placed, s=brng2.uniform(0.85, 1.25))
            b_placed += 1
        elif f_placed < 18:
            flower(gx, gy, 6000 + f_placed)
            f_placed += 1

    # bigger room: herringbone floor, walls pushed out
    cube('floor', (-0.03, 0.1, -0.05), (6.46, 7.6, 0.1), M['woodfloor'])

    # back wall in three parts, leaving a REAL doorway (0.025..0.775, z 0..2)
    cube('wall_w', (-1.6025, -3.4, 0.75), (3.255, 0.12, 1.5), M['sage'])
    cube('wall_e', (1.9875, -3.4, 0.75), (2.425, 0.12, 1.5), M['sage'])
    cube('wall_top', (0.4, -3.4, 2.4), (0.75, 0.12, 0.8), M['sage'])
    cube('baseboard_w', (-1.6025, -3.32, 0.09), (3.255, 0.05, 0.18), M['cream'])
    cube('baseboard_e', (1.9875, -3.32, 0.09), (2.425, 0.05, 0.18), M['cream'])
    cube('frame_l', (0.025, -3.36, 1.0), (0.10, 0.18, 2.06), M['white'], bevel=0.01)
    cube('frame_r', (0.775, -3.36, 1.0), (0.10, 0.18, 2.06), M['white'], bevel=0.01)
    cube('frame_t', (0.4, -3.36, 2.03), (0.85, 0.18, 0.10), M['white'], bevel=0.01)

    # left wall (west): full-height side wall, L-shaped room
    cube('left_wall', (-3.26, 0.2, 1.4), (0.12, 7.6, 2.8), M['sage'])
    cube('left_baseboard', (-3.19, 0.2, 0.09), (0.05, 7.6, 0.18), M['cream'])
    cube('corner_post', (-3.215, -3.345, 1.4), (0.17, 0.15, 2.8), M['cream'], bevel=0.01)

    # three windows on the LEFT wall
    for idx, (wy, wz) in enumerate(((-2.2, 1.7), (-0.45, 1.95), (1.5, 1.7))):
        cube(f'win_frame{idx}', (-3.27, wy, wz), (0.06, 0.95, 1.0), M['white'], bevel=0.02)
        cube(f'win_glass{idx}', (-3.30, wy, wz), (0.05, 0.78, 0.83), M['glass'])
        cube(f'win_h{idx}', (-3.28, wy, wz), (0.04, 0.78, 0.05), M['white'])
        cube(f'win_v{idx}', (-3.28, wy, wz), (0.04, 0.05, 0.83), M['white'])
    sphere('moon', (-3.55, -0.6, 2.05), (0.11, 0.11, 0.11), M['moon'], segments=10)

    # door centred on the back wall
    mat('door_red', (0.66, 0.28, 0.24), rough=0.85)
    cube('door', (0.4, -3.4, 1.0), (0.75, 0.18, 2.0), M['door_red'], bevel=0.02)
    cube('door_panel', (0.4, -3.34, 1.42), (0.55, 0.03, 0.62), M['wood_d'])
    cube('door_panel2', (0.4, -3.34, 0.6), (0.55, 0.03, 0.62), M['wood_d'])
    sphere('knob', (0.70, -3.32, 1.0), (0.05, 0.05, 0.05), M['cream'], segments=8)
    hinge = bpy.data.objects.new('door_hinge', None)
    bpy.context.scene.collection.objects.link(hinge)
    hinge.location = (0.025, -3.33, 0.0)
    R['door_hinge'] = hinge
    bpy.context.view_layer.update()
    _hinv = hinge.matrix_world.inverted()
    for _n in ('door', 'door_panel', 'door_panel2', 'knob'):
        R[_n].parent = hinge
        R[_n].matrix_parent_inverse = _hinv
    bpy.context.view_layer.update()


    # bed (top-left, against the back wall)
    cube('bedframe', (-2.0, -2.4, 0.25), (1.5, 1.6, 0.25), M['wood_d'], bevel=0.03)
    cube('headboard', (-2.0, -3.15, 0.7), (1.5, 0.12, 0.9), M['wood_d'], bevel=0.03)
    cube('mattress', (-2.0, -2.4, 0.42), (1.4, 1.5, 0.16), M['white'], bevel=0.04)
    cube('quilt', (-2.0, -2.2, 0.5), (1.4, 1.1, 0.08), M['quilt'], bevel=0.03)
    cube('quilt_fold', (-2.0, -2.7, 0.52), (1.4, 0.16, 0.06), M['quilt_d'])
    cube('pillow', (-2.0, -2.95, 0.58), (0.7, 0.35, 0.12), M['white'], bevel=0.05)

    # desk against the left wall, monitor screen facing east (the camera)
    cube('desk_top', (-2.75, -0.4, 0.78), (0.7, 1.4, 0.07), M['wood'], bevel=0.02)
    for dx in (-0.28, 0.28):
        for dy in (-0.62, 0.62):
            cube('desk_leg', (-2.75 + dx, -0.4 + dy, 0.38), (0.07, 0.07, 0.76), M['wood_d'])
    cube('monitor', (-2.95, -0.4, 1.25), (0.06, 0.75, 0.5), M['monitor'], bevel=0.02)
    cube('screen', (-2.91, -0.4, 1.25), (0.02, 0.66, 0.41), M['screen'])
    cube('mstand', (-2.9, -0.4, 0.93), (0.08, 0.08, 0.16), M['monitor'])
    cube('keyboard', (-2.6, -0.4, 0.83), (0.18, 0.5, 0.02), M['white'], bevel=0.01)
    # chair on the room side of the desk
    cube('chair_seat', (-2.3, -0.4, 0.5), (0.5, 0.55, 0.07), M['sofa_d'], bevel=0.03)
    cube('chair_back', (-2.12, -0.4, 0.95), (0.07, 0.55, 0.6), M['sofa_d'], bevel=0.03)
    cyl('chair_post', (-2.3, -0.4, 0.25), 0.04, 0.45, M['monitor'])

    # sofa moved next to the door, against the back wall, facing south
    cube('sofa_base', (1.7, -2.55, 0.3), (1.4, 0.8, 0.35), M['sofa'], bevel=0.06)
    cube('sofa_back', (1.7, -2.9, 0.75), (1.4, 0.25, 0.75), M['sofa_d'], bevel=0.06)
    cube('sofa_arm1', (1.02, -2.55, 0.62), (0.18, 0.8, 0.5), M['sofa_d'], bevel=0.05)
    cube('sofa_arm2', (2.38, -2.55, 0.62), (0.18, 0.8, 0.5), M['sofa_d'], bevel=0.05)
    cube('sofa_cushion', (1.7, -2.5, 0.5), (1.2, 0.6, 0.12), M['sofa'], bevel=0.04)

    # rug with a petal border
    cyl('rug', (0, 0.5, 0.02), 1.0, 0.03, M['rug'], vertices=24)
    cyl('rug_inner', (0, 0.5, 0.035), 0.72, 0.03, M['rug_in'], vertices=24)
    for i in range(8):
        ang = i * math.pi / 4
        cyl(f'petal{i}', (0.86 * math.cos(ang), 0.5 + 0.86 * math.sin(ang), 0.03),
            0.12, 0.032, M['rug_in'], vertices=10)

    # standing bookshelf on the left wall, north of the desk
    cube('shelf', (-3.05, -1.55, 0.9), (0.35, 0.9, 1.8), M['wood'], bevel=0.02)
    for i, key in enumerate(('book1', 'book2', 'book3', 'book1', 'book2')):
        cube(f'book{i}', (-2.86, -1.85 + i * 0.16, 1.55), (0.14, 0.09, 0.26 - (i % 2) * 0.04), M[key])
    for i, key in enumerate(('book3', 'book1', 'book2', 'book3')):
        cube(f'bookb{i}', (-2.86, -1.8 + i * 0.16, 1.15), (0.14, 0.09, 0.24 + (i % 2) * 0.04), M[key])
    cube('shelf_b1', (-3.02, -1.55, 1.35), (0.32, 0.84, 0.04), M['wood_d'])
    cube('shelf_b2', (-3.02, -1.55, 0.75), (0.32, 0.84, 0.04), M['wood_d'])

    # floor lamp on the OTHER side of the headboard (east of the bed)
    cyl('lamp_post', (-1.0, -3.05, 0.75), 0.025, 1.5, M['monitor'])
    cone('lamp_shade', (-1.0, -3.05, 1.55), 0.22, 0.3, M['cream'], vertices=10)
    cyl('lamp_base', (-1.0, -3.05, 0.03), 0.14, 0.05, M['monitor'])
    bpy.ops.object.light_add(type='POINT', location=(-1.0, -3.05, 1.45))
    lamp = bpy.context.object
    lamp.name = 'lamp_light'
    lamp.data.energy = 0
    lamp.data.color = (1.0, 0.82, 0.55)
    lamp.data.shadow_soft_size = 0.5
    R['lamp_light'] = lamp

    # plant (moved east so it doesn't block the new third window)
    cyl('pot', (2.75, 1.3, 0.18), 0.2, 0.36, M['pot'], vertices=10)
    for i, (dx, dy, dz, s) in enumerate(((-0.12, 0, 0.5, 0.22), (0.1, 0.05, 0.62, 0.25), (0, -0.08, 0.45, 0.18), (0.02, 0.12, 0.52, 0.19))):
        sphere(f'leaf{i}', (2.75 + dx, 1.3 + dy, dz), (s, s * 0.8, s * 1.3), M['leaf'], segments=8)

    # chat bubble (hidden until chat) - white bubble geometry only; text is HTML
    sphere('bub1', (0, 0, -8), (0.18, 0.18, 0.14), M['bubble'], segments=10)
    sphere('bub2', (0, 0, -8), (0.13, 0.13, 0.11), M['bubble'], segments=10)
    cone('bub_tail', (0, 0, -8), 0.06, 0.14, M['bubble'], vertices=6, rotation=(math.radians(180), 0, 0))
    sphere('bub_heart', (0, 0, -8), (0.06, 0.04, 0.06), M['heart'], segments=8)
    for n in ('bub1', 'bub2', 'bub_tail', 'bub_heart'):
        R[n].hide_render = True

    # three Z markers for sleep
    for i in range(3):
        bpy.ops.object.text_add(location=(0, 0, -8))
        z = bpy.context.object
        z.name = f'zzz{i}'
        z.data.body = 'Z'
        z.data.size = 0.22 - i * 0.04
        z.data.extrude = 0.02
        assign(z, M['bubble'])
        R[f'zzz{i}'] = z
        z.hide_render = True

    # ------------------------------------------------- lights
    bpy.ops.object.light_add(type='AREA', location=(3.5, 4.5, 6.5))
    key = bpy.context.object
    key.name = 'key'
    key.data.energy = 1400
    key.data.shape = 'DISK'
    key.data.size = 5.0
    key.rotation_euler = (math.radians(25), math.radians(-15), math.radians(30))
    R['key'] = key

    bpy.ops.object.light_add(type='AREA', location=(-4, 1, 3))
    fill = bpy.context.object
    fill.name = 'fill'
    fill.data.energy = 500
    fill.data.size = 4.0
    R['fill'] = fill

    bpy.ops.object.light_add(type='AREA', location=(0, -1.5, 5.5))
    top = bpy.context.object
    top.name = 'top'
    top.data.energy = 800
    top.data.size = 3.5
    R['top'] = top

    # camera: lower than the last version, wide enough to include grass + path
    bpy.ops.object.camera_add(location=(6.2, 8.2, 7.2))
    cam = bpy.context.object
    cam.name = 'cam'
    target = Vector((0.0, 0.0, 0.4))
    cam.rotation_euler = (target - cam.location).to_track_quat('-Z', 'Y').to_euler()
    cam.data.type = 'ORTHO'
    cam.data.ortho_scale = 10.3
    bpy.context.scene.camera = cam

    scene = bpy.context.scene
    try:
        scene.render.engine = 'BLENDER_EEVEE_NEXT'
    except TypeError:
        scene.render.engine = 'BLENDER_EEVEE'
    scene.render.resolution_x = 512
    scene.render.resolution_y = 512
    scene.render.image_settings.file_format = 'PNG'
    world = bpy.data.worlds.new('world') if not bpy.data.worlds else bpy.data.worlds[0]
    scene.world = world
    world.use_nodes = True
    R['world'] = world
    return scene


# ---------------------------------------------------------------- day / night

def set_day():
    R['key'].data.energy = 1400
    R['key'].data.color = (1.0, 1.0, 1.0)
    R['fill'].data.energy = 500
    R['top'].data.energy = 800
    R['lamp_light'].data.energy = 0
    bg = R['world'].node_tree.nodes['Background']
    bg.inputs[0].default_value = (1.0, 0.98, 0.95, 1.0)
    bg.inputs[1].default_value = 1.0
    for idx in (0, 1, 2):
        R[f'win_glass{idx}'].data.materials[0] = M['glass']
    R['moon'].hide_render = True
    R['lamp_shade'].data.materials[0] = M['cream']
    pbsdf = next(n for n in M['plight'].node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
    pbsdf.inputs['Emission Strength'].default_value = 0.6


def set_night():
    R['key'].data.energy = 250
    R['key'].data.color = (0.55, 0.65, 1.0)
    R['fill'].data.energy = 80
    R['top'].data.energy = 120
    R['lamp_light'].data.energy = 260
    bg = R['world'].node_tree.nodes['Background']
    bg.inputs[0].default_value = (0.05, 0.07, 0.14, 1.0)
    bg.inputs[1].default_value = 1.0
    night_glass = mat('night_glass', (0.10, 0.16, 0.34), rough=0.3, emission=(0.10, 0.16, 0.34), strength=0.4) \
        if 'night_glass' not in M else M['night_glass']
    for idx in (0, 1, 2):
        R[f'win_glass{idx}'].data.materials[0] = night_glass
    R['moon'].hide_render = False
    R['lamp_shade'].data.materials[0] = M['lampglow']
    pbsdf = next(n for n in M['plight'].node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
    pbsdf.inputs['Emission Strength'].default_value = 4.0


# ---------------------------------------------------------------- visitor (downloaded, rigged)

CHAR_SCALE = 0.92
# The glTF faces -Y. pi turns them toward the camera (+Y). -pi/2 faces the desk.
FACE_CAM = math.pi
FACE_DOOR = 0.0
FACE_DESK = -math.pi / 2


def clear_character():
    for obj in list(bpy.data.objects):
        if obj.get('is_char'):
            bpy.data.objects.remove(obj, do_unlink=True)
    for act in list(bpy.data.actions):
        if act.name.startswith('CharacterArmature'):
            bpy.data.actions.remove(act)


def load_character(model: str):
    """Import one Quaternius character and keep a single action playing."""
    clear_character()
    path = ROOT / 'data' / 'characters' / model / 'character.glb'
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    imported = [obj for obj in bpy.data.objects if obj not in before]
    root = bpy.data.objects.new('chr_root', None)
    bpy.context.scene.collection.objects.link(root)
    root['is_char'] = True
    root.scale = (CHAR_SCALE, CHAR_SCALE, CHAR_SCALE)
    arm = next(obj for obj in imported if obj.type == 'ARMATURE')
    for obj in imported:
        obj['is_char'] = True
        if obj.type == 'MESH' and 'Icosphere' in obj.name:
            obj.hide_render = True
    arm.parent = root
    if arm.animation_data:
        for track in list(arm.animation_data.nla_tracks):
            arm.animation_data.nla_tracks.remove(track)
    clips = {}
    for act in bpy.data.actions:
        if '|' not in act.name:
            continue
        short = act.name.split('|', 1)[1].split('_Character', 1)[0]
        clips[short] = act
    R['chr'] = root
    R['arm'] = arm
    R['clips'] = clips


def play(clip: str, frame: int):
    arm = R['arm']
    act = R['clips'][clip]
    if arm.animation_data is None:
        arm.animation_data_create()
    arm.animation_data.action = act
    last = max(int(act.frame_range[1]), 1)
    bpy.context.scene.frame_set(1 + (int(frame) % last))


def place(x, y, z, yaw):
    root = R['chr']
    root.location = (x, y, z)
    root.rotation_euler = (0, 0, yaw)


def hide_z_and_bubbles():
    for i in range(3):
        R[f'zzz{i}'].hide_render = True
    for name in ('bub1', 'bub2', 'bub_tail', 'bub_heart'):
        R[name].hide_render = True


# ---------------------------------------------------------------- scenes

RUG = (0.0, 0.35)
DOOR_OUT = (0.40, -4.6)
DOOR_IN = (0.40, -2.7)


def _lerp(a, b, t):
    return a + (b - a) * t


def frame(scene_name, f):
    """One frame. f is 0..FRAMES-1. Clips are the character's own actions."""
    hide_z_and_bubbles()
    n = max(FRAMES, 1)
    if scene_name == 'sleep':
        set_night()
    else:
        set_day()

    if scene_name == 'enter':
        # shut, open while they step through, shut again before they sit
        if f < 6:
            ang = 0.0
        elif f < 9:
            ang = -90.0 * (f - 5) / 3.0
        elif f < 13:
            ang = -90.0
        elif f < 18:
            ang = -90.0 * (1.0 - (f - 12) / 5.0)
        else:
            ang = 0.0
        R['door_hinge'].rotation_euler = (0, 0, math.radians(ang))
        if f < 7:
            t = f / 6.0
            play('Walk', f * 4)
            place(_lerp(DOOR_OUT[0], DOOR_IN[0], t), _lerp(DOOR_OUT[1], -3.55, t), 0.0, FACE_CAM)
        elif f < 10:
            play('Interact', (f - 7) * 8)
            place(DOOR_OUT[0], -3.55, 0.0, FACE_DOOR)
        elif f < 16:
            t = (f - 10) / 5.0
            play('Walk', f * 4)
            place(_lerp(0.40, RUG[0], t), _lerp(-3.15, RUG[1], t), 0.0, FACE_CAM)
        else:
            play('Idle', f * 2)
            place(RUG[0], RUG[1], 0.0, FACE_CAM)
        return

    R['door_hinge'].rotation_euler = (0, 0, 0)
    if scene_name == 'sit':
        play('Idle', f * 2)
        place(RUG[0], RUG[1], 0.0, FACE_CAM)
    elif scene_name == 'study':
        play('Idle', f * 2)
        place(-2.15, -0.40, 0.0, FACE_DESK)
    elif scene_name == 'chat':
        play('Wave', f * 3)
        place(1.70, -1.85, 0.0, FACE_CAM)
        show = f >= 3
        R['bub1'].hide_render = not show
        R['bub_tail'].hide_render = not show
        R['bub_heart'].hide_render = f < 12
        R['bub1'].location = (1.05, -1.55, 1.70)
        R['bub_tail'].location = (1.25, -1.75, 1.48)
        R['bub_tail'].rotation_euler = (math.radians(180), 0, 0.3)
        R['bub_heart'].location = (1.05, -1.55, 1.70)
    elif scene_name == 'sleep':
        play('Death', 22 + (f % 3))
        # Death lies along +Y; yaw pi puts the head toward the headboard.
        place(-2.00, -1.55, 0.50, FACE_CAM)
        for i in range(3):
            t = (f + i * 4) % 12
            z = R[f'zzz{i}']
            z.hide_render = False
            z.location = (-2.15 + i * 0.16, -2.85, 1.15 + t * 0.08)
            z.rotation_euler = (math.radians(90), 0, -0.3)


def export_room(path: Path):
    """Write the empty room (no visitor, no lights) as one GLB for the web player."""
    for name in ('bub1', 'bub2', 'bub_tail', 'bub_heart', 'moon', 'floor'):
        if name in R:
            bpy.data.objects.remove(R.pop(name), do_unlink=True)
    for obj in list(bpy.data.objects):
        if obj.type in ('FONT', 'LIGHT', 'CAMERA'):
            bpy.data.objects.remove(obj, do_unlink=True)
    # procedural colour nodes do not survive glTF; keep the flat base colour
    for m in bpy.data.materials:
        if not m.use_nodes:
            continue
        bsdf = next((n for n in m.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None)
        if bsdf is None:
            continue
        for link in list(bsdf.inputs['Base Color'].links):
            m.node_tree.links.remove(link)
    path.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.export_scene.gltf(
        filepath=str(path), export_format='GLB', export_apply=True,
        export_lights=False, export_cameras=False, export_animations=False,
    )
    print('EXPORTED', path)


def main():
    scene = build()
    if ARGS.get('export'):
        export_room(Path(ARGS['export']).resolve())
        return
    OUTDIR.mkdir(parents=True, exist_ok=True)
    for model in MODELS:
        load_character(model)
        for scene_name in SCENES:
            out = OUTDIR / model / scene_name
            out.mkdir(parents=True, exist_ok=True)
            for f_idx in range(FRAMES):
                frame(scene_name, f_idx)
                scene.render.filepath = str(out / f'{f_idx + 1:03d}.png')
                bpy.ops.render.render(write_still=True)
            print('DONE', model, scene_name, FRAMES)


main()
