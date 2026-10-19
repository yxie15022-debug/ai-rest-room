
"""Build and render the Marvis-style black-cat studio scene in Blender.

Run headless:
    blender --background --python scripts/render_studio_blender.py -- \
        --scenes sleep,sit,study,chat,enter --frames 20 --outdir data/_studio_render
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

# --- args -----------------------------------------------------------------

def parse_args() -> dict:
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    args: dict = {}
    i = 0
    while i < len(argv):
        key = argv[i]
        if key.startswith('--'):
            name = key[2:]
            if i + 1 < len(argv) and not argv[i + 1].startswith('--'):
                args[name] = argv[i + 1]
                i += 2
            else:
                args[name] = '1'
                i += 1
        else:
            i += 1
    return args


ARGS = parse_args()
ROOT = Path(ARGS.get('outdir', 'data/_studio_render')).resolve()
UI_DIR = Path(ARGS.get('ui', 'data/_blender_ui')).resolve()
FRAMES = int(ARGS.get('frames', '20'))
SCENES = [s for s in ARGS.get('scenes', 'sleep,sit,study,chat,enter').split(',') if s]

SCARF = {
    'enter': (0.94, 0.74, 0.28),
    'sit': (0.26, 0.73, 0.55),
    'study': (0.24, 0.56, 0.91),
    'chat': (0.89, 0.32, 0.31),
    'sleep': (0.34, 0.48, 0.88),
}
BLACK = (0.006, 0.006, 0.007)
WHITE = (0.78, 0.78, 0.78)
SOFT = (0.82, 0.82, 0.82)


def ease(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)


# --- fresh scene ----------------------------------------------------------

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene

sc.render.engine = 'CYCLES'
try:
    prefs = bpy.context.preferences.addons['cycles'].preferences
    prefs.compute_device_type = 'CUDA'
    prefs.get_devices()
    for device in prefs.devices:
        device.use = device.type == 'CUDA'
    sc.cycles.device = 'GPU'
except Exception:
    sc.cycles.device = 'CPU'
sc.cycles.samples = 48
sc.cycles.use_adaptive_sampling = True
sc.cycles.adaptive_threshold = 0.06
sc.cycles.use_denoising = True
sc.cycles.denoiser = 'OPENIMAGEDENOISE'
sc.render.resolution_x = 512
sc.render.resolution_y = 512
sc.render.resolution_percentage = 100
sc.render.image_settings.file_format = 'PNG'
sc.render.image_settings.color_mode = 'RGB'
sc.render.film_transparent = False
sc.view_settings.view_transform = 'Standard'
sc.view_settings.exposure = 0.0

world = bpy.data.worlds.new('World')
sc.world = world
world.use_nodes = True
world.node_tree.nodes['Background'].inputs['Color'].default_value = (1.0, 1.0, 1.0, 1.0)
world.node_tree.nodes['Background'].inputs['Strength'].default_value = 1.0

# --- helpers --------------------------------------------------------------

def material(name: str, color: tuple, rough: float = 0.6, specular: float = 0.35):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes['Principled BSDF']
    bsdf.inputs['Base Color'].default_value = (*color, 1.0)
    bsdf.inputs['Roughness'].default_value = rough
    if 'Specular IOR Level' in bsdf.inputs:
        bsdf.inputs['Specular IOR Level'].default_value = specular
    return m


def assign(obj, m):
    if obj.data.materials:
        obj.data.materials[0] = m
    else:
        obj.data.materials.append(m)


def box(name, loc, size, color, rough=0.55, specular=0.35, bevel=0.015):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    obj = bpy.context.object
    obj.name = name
    obj.scale = size
    if bevel:
        mod = obj.modifiers.new('Bevel', 'BEVEL')
        mod.width = bevel
        mod.segments = 4
    assign(obj, material(name, color, rough, specular))
    bpy.ops.object.shade_smooth()
    return obj


def sphere(name, loc, scale, color, rough=0.55, specular=0.25):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=48, ring_count=24, radius=1, location=loc)
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    assign(obj, material(name, color, rough, specular))
    return obj


def cylinder(name, loc, radius, depth, color, rough=0.5, specular=0.3, rot=(0.0, 0.0, 0.0)):
    bpy.ops.mesh.primitive_cylinder_add(vertices=48, radius=radius, depth=depth, location=loc)
    obj = bpy.context.object
    obj.name = name
    obj.rotation_euler = rot
    assign(obj, material(name, color, rough, specular))
    bpy.ops.object.shade_smooth()
    return obj


def cone(name, loc, radius, depth, color, rough=0.55, specular=0.25):
    bpy.ops.mesh.primitive_cone_add(vertices=48, radius1=radius, depth=depth, location=loc)
    obj = bpy.context.object
    obj.name = name
    assign(obj, material(name, color, rough, specular))
    bpy.ops.object.shade_smooth()
    return obj


def torus(name, loc, major, minor, color, rough=0.55, specular=0.3):
    bpy.ops.mesh.primitive_torus_add(major_radius=major, minor_radius=minor, location=loc)
    obj = bpy.context.object
    obj.name = name
    assign(obj, material(name, color, rough, specular))
    bpy.ops.object.shade_smooth()
    return obj


def parent_keep(child, parent):
    child.parent = parent
    child.matrix_parent_inverse = parent.matrix_world.inverted()


# --- lights + camera ------------------------------------------------------

bpy.ops.object.light_add(type='AREA', location=(0.8, 3.2, 4.8))
key = bpy.context.object
key.name = 'Key'
key.data.size = 6.0
key.data.energy = 220.0
key.rotation_euler = (math.radians(-40), 0.0, math.radians(8))

bpy.ops.object.camera_add(location=(0.0, 4.6, 2.4))
cam = bpy.context.object
sc.camera = cam
cam.data.lens = 50
look = Vector((0.0, 0.85, 1.2)) - cam.location
cam.rotation_euler = look.to_track_quat('-Z', 'Y').to_euler()

# --- environment ----------------------------------------------------------

floor = box('floor', (0, 0, -0.02), (40, 40, 0.04), (0.96, 0.96, 0.96), rough=0.65, specular=0.2, bevel=0.0)

# desk
box('desk_top', (0, -1.05, 1.0), (2.4, 0.95, 0.08), WHITE, rough=0.4, specular=0.25)
box('desk_leg_l', (-1.02, -0.7, 0.5), (0.07, 0.07, 1.0), SOFT, rough=0.5, specular=0.2, bevel=0.008)
box('desk_leg_r', (1.02, -0.7, 0.5), (0.07, 0.07, 1.0), SOFT, rough=0.5, specular=0.2, bevel=0.008)
box('cabinet', (1.13, -1.05, 0.55), (0.42, 0.42, 1.1), (0.95, 0.95, 0.95), rough=0.5, specular=0.25)

# monitor (tilted slightly toward the camera)
box('monitor_stand', (0, -1.3, 1.09), (0.48, 0.24, 0.07), (0.9, 0.9, 0.9), rough=0.5, specular=0.25)
box('monitor_neck', (0, -1.33, 1.36), (0.09, 0.12, 0.5), (0.88, 0.88, 0.88), rough=0.5, specular=0.25)

bpy.ops.object.empty_add(location=(0, -1.33, 1.6))
mon_rig = bpy.context.object
mon_rig.name = 'monitor_rig'

bezel = box('monitor_bezel', (0, -1.4, 2.05), (1.92, 0.09, 1.1), (0.82, 0.82, 0.82), rough=0.45, specular=0.3, bevel=0.025)
parent_keep(bezel, mon_rig)

# screen plane faces +Y (toward the camera)
bpy.ops.mesh.primitive_plane_add(size=1, location=(0, -1.345, 2.05))
screen = bpy.context.object
screen.name = 'screen'
screen.scale = (1.74, 0.98, 1.0)
screen.rotation_euler = (math.radians(-90), 0.0, 0.0)
parent_keep(screen, mon_rig)

screen_mat = material('screen', (1, 1, 1), rough=0.5, specular=0.0)
screen_mat.use_nodes = True
nodes = screen_mat.node_tree.nodes
nodes.remove(nodes['Principled BSDF'])
tex_node = nodes.new('ShaderNodeTexImage')
emit_node = nodes.new('ShaderNodeEmission')
emit_node.inputs['Strength'].default_value = 1.0
screen_mat.node_tree.links.new(tex_node.outputs['Color'], emit_node.inputs['Color'])
screen_mat.node_tree.links.new(emit_node.outputs['Emission'], nodes['Material Output'].inputs['Surface'])
assign(screen, screen_mat)
mon_rig.rotation_euler.x = math.radians(14)

# chair
box('chair_seat', (0, 0.35, 0.42), (0.72, 0.66, 0.1), (0.86, 0.86, 0.86), rough=0.55, specular=0.2, bevel=0.04)
cylinder('chair_post', (0, 0.35, 0.2), 0.12, 0.4, (0.84, 0.84, 0.84), rough=0.5)
for angle in (200, 245, 290, 335, 20):
    rad = math.radians(angle)
    cylinder(f'caster_{angle}', (0.45 * math.cos(rad), 0.35 + 0.38 * math.sin(rad), 0.05), 0.05, 0.32, (0.82, 0.82, 0.82), rough=0.5)

# --- cat rig --------------------------------------------------------------

bpy.ops.object.empty_add(location=(0.0, 0.3, 0.9))
rig = bpy.context.object
rig.name = 'cat_rig'

body = sphere('cat_body', (0, 0.3, 0.9), (0.46, 0.46, 0.56), BLACK, rough=0.7, specular=0.08)
head = sphere('cat_head', (0, 0.3, 1.52), (0.34, 0.34, 0.3), BLACK, rough=0.7, specular=0.08)
ear_l = cone('cat_ear_l', (-0.19, 0.3, 1.82), 0.11, 0.32, BLACK, rough=0.7, specular=0.08)
ear_r = cone('cat_ear_r', (0.19, 0.3, 1.82), 0.11, 0.32, BLACK, rough=0.7, specular=0.08)
ear_l.rotation_euler = (0, 0, math.radians(14))
ear_r.rotation_euler = (0, 0, math.radians(-14))
arm_l = sphere('cat_arm_l', (-0.56, -0.02, 1.0), (0.15, 0.36, 0.14), BLACK, rough=0.7, specular=0.08)
arm_r = sphere('cat_arm_r', (0.56, -0.02, 1.0), (0.15, 0.36, 0.14), BLACK, rough=0.7, specular=0.08)
scarf = torus('cat_scarf', (0, 0.3, 1.27), 0.34, 0.15, SCARF['sit'], rough=0.55, specular=0.2)
scarf.scale = (1.0, 0.95, 1.0)

for obj in (body, head, ear_l, ear_r, arm_l, arm_r, scarf):
    parent_keep(obj, rig)

scarf_bsdf = scarf.data.materials[0].node_tree.nodes['Principled BSDF']
RIG_BASE = rig.location.copy()
HEAD_BASE = head.location.copy()
EAR_REST = math.radians(-14)

# --- render loop ----------------------------------------------------------

for scene in SCENES:
    (ROOT / scene).mkdir(parents=True, exist_ok=True)
    scarf_bsdf.inputs['Base Color'].default_value = (*SCARF.get(scene, SCARF['sit']), 1.0)
    tex_node.image = bpy.data.images.load(str(UI_DIR / f'{scene}.png'))

    for f in range(FRAMES):
        t = f / float(FRAMES)
        phase = 2.0 * math.pi * t
        sc.frame_set(f + 1)

        breathe = 1.0 + 0.014 * math.sin(phase)
        rig.scale = (breathe, breathe, breathe)
        rig.location = RIG_BASE.copy()
        head.location = HEAD_BASE.copy()
        head.rotation_euler.x = 0.0
        ear_r.rotation_euler.z = EAR_REST

        if scene == 'sleep':
            head.rotation_euler.x = -0.5
            head.location = HEAD_BASE + Vector((0.0, 0.0, -0.05))
            rig.scale = (0.99, 0.99, 0.99)
        if scene == 'enter':
            e = ease(min(1.0, f / (FRAMES * 0.45)))
            rig.scale = (0.88 + 0.12 * e,) * 3
            rig.location = RIG_BASE + Vector((0.0, 0.0, -0.14 * (1.0 - e)))
        if 0.35 <= t <= 0.44:
            ear_r.rotation_euler.z = EAR_REST + math.radians(10)

        bpy.context.view_layer.update()
        sc.render.filepath = str(ROOT / scene / f'{f + 1:03d}.png')
        bpy.ops.render.render(write_still=True)

print('RENDER_DONE', ROOT)
