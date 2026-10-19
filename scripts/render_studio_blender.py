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
WHITE = (0.92, 0.92, 0.92)


def ease(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)


# --- fresh scene ----------------------------------------------------------

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene

sc.render.engine = 'CYCLES'
sc.cycles.device = 'GPU'
sc.cycles.samples = 96
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

# world
world = bpy.data.worlds.new('World')
sc.world = world
world.use_nodes = True
world.node_tree.nodes['Background'].inputs['Color'].default_value = (1.0, 1.0, 1.0, 1.0)
world.node_tree.nodes['Background'].inputs['Strength'].default_value = 1.0

# --- helpers --------------------------------------------------------------

def material(name: str, color: tuple, rough: float = 0.5, metallic: float = 0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes['Principled BSDF']
    bsdf.inputs['Base Color'].default_value = (*color, 1.0)
    bsdf.inputs['Roughness'].default_value = rough
    bsdf.inputs['Metallic'].default_value = metallic
    return m


def assign(obj, m):
    if obj.data.materials:
        obj.data.materials[0] = m
    else:
        obj.data.materials.append(m)


def box(name, loc, size, color, rough=0.5, bevel=0.012):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    obj = bpy.context.object
    obj.name = name
    obj.scale = size
    if bevel:
        mod = obj.modifiers.new('Bevel', 'BEVEL')
        mod.width = bevel
        mod.segments = 4
    assign(obj, material(name, color, rough))
    bpy.ops.object.shade_smooth()
    return obj


def sphere(name, loc, scale, color, rough=0.35):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=48, ring_count=24, radius=1, location=loc)
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    assign(obj, material(name, color, rough))
    return obj


def cylinder(name, loc, radius, depth, color, rough=0.4, rot=(0.0, 0.0, 0.0)):
    bpy.ops.mesh.primitive_cylinder_add(vertices=48, radius=radius, depth=depth, location=loc)
    obj = bpy.context.object
    obj.name = name
    obj.rotation_euler = rot
    assign(obj, material(name, color, rough))
    bpy.ops.object.shade_smooth()
    return obj


def cone(name, loc, radius, depth, color, rough=0.4):
    bpy.ops.mesh.primitive_cone_add(vertices=48, radius1=radius, depth=depth, location=loc)
    obj = bpy.context.object
    obj.name = name
    assign(obj, material(name, color, rough))
    bpy.ops.object.shade_smooth()
    return obj


def torus(name, loc, major, minor, color, rough=0.5):
    bpy.ops.mesh.primitive_torus_add(major_radius=major, minor_radius=minor, location=loc)
    obj = bpy.context.object
    obj.name = name
    assign(obj, material(name, color, rough))
    bpy.ops.object.shade_smooth()
    return obj


# --- lights + camera ------------------------------------------------------

bpy.ops.object.light_add(type='AREA', location=(0.0, 3.4, 4.6))
key = bpy.context.object
key.name = 'Key'
key.data.size = 5.0
key.data.energy = 260.0
key.rotation_euler = (math.radians(-38), 0.0, 0.0)

bpy.ops.object.camera_add(location=(0.0, 4.6, 2.0))
cam = bpy.context.object
sc.camera = cam
cam.data.lens = 50
look = Vector((0.0, 0.8, 1.2)) - cam.location
cam.rotation_euler = look.to_track_quat('-Z', 'Y').to_euler()

# --- environment ----------------------------------------------------------

floor = box('floor', (0, 0, -0.02), (40, 40, 0.04), (0.95, 0.95, 0.95), rough=0.6, bevel=0.0)

# desk (far side, -Y)
box('desk_top', (0, -0.7, 1.02), (2.1, 0.9, 0.07), WHITE, rough=0.35)
box('desk_leg_l', (-0.85, -0.9, 0.5), (0.07, 0.07, 1.0), (0.88, 0.88, 0.88), rough=0.5, bevel=0.008)
box('desk_leg_r', (0.85, -0.9, 0.5), (0.07, 0.07, 1.0), (0.88, 0.88, 0.88), rough=0.5, bevel=0.008)
# side cabinet
box('cabinet', (0.95, -0.72, 0.62), (0.42, 0.42, 1.24), (0.97, 0.97, 0.97), rough=0.5)

# monitor
box('monitor_stand', (0, -0.78, 1.14), (0.5, 0.26, 0.08), (0.9, 0.9, 0.9), rough=0.5)
box('monitor_neck', (0, -0.85, 1.48), (0.1, 0.14, 0.68), (0.9, 0.9, 0.9), rough=0.5)

bpy.ops.object.empty_add(location=(0, -0.85, 1.46))
mon_rig = bpy.context.object
mon_rig.name = 'monitor_rig'

bezel = box('monitor_bezel', (0, -0.92, 2.1), (1.9, 0.14, 1.15), (0.94, 0.94, 0.94), rough=0.4, bevel=0.02)
# screen (emissive box whose front face shows the UI texture)
screen = box('screen', (0, -0.85, 2.1), (1.75, 0.04, 1.0), (1, 1, 1), rough=0.5, bevel=0.0)
bezel.parent = mon_rig
screen.parent = mon_rig
mon_rig.rotation_euler.x = math.radians(18)
screen_mat = material('screen', (1, 1, 1))
screen_mat.use_nodes = True
nodes = screen_mat.node_tree.nodes
nodes.remove(nodes['Principled BSDF'])
out = nodes['Material Output']
tex_node = nodes.new('ShaderNodeTexImage')
emit_node = nodes.new('ShaderNodeEmission')
emit_node.inputs['Strength'].default_value = 1.2
screen_mat.node_tree.links.new(tex_node.outputs['Color'], emit_node.inputs['Color'])
screen_mat.node_tree.links.new(emit_node.outputs['Emission'], out.inputs['Surface'])
assign(screen, screen_mat)

# chair (near camera, +Y)
box('chair_back', (0, 0.78, 1.12), (0.98, 0.14, 1.16), WHITE, rough=0.5, bevel=0.05)
box('chair_seat', (0, 0.42, 0.66), (0.98, 0.88, 0.12), (0.96, 0.96, 0.96), rough=0.5, bevel=0.03)
cylinder('chair_post', (0, 0.42, 0.28), 0.16, 0.56, (0.9, 0.9, 0.9), rough=0.5)
for angle in (210, 250, 290, 330, 20):
    rad = math.radians(angle)
    cylinder(f'caster_{angle}', (0.55 * math.cos(rad), 0.42 + 0.5 * math.sin(rad), 0.09), 0.06, 0.5, (0.86, 0.86, 0.86), rough=0.5)

# --- cat rig --------------------------------------------------------------

bpy.ops.object.empty_add(location=(0.0, 0.42, 1.0))
rig = bpy.context.object
rig.name = 'cat_rig'

body = sphere('cat_body', (0, 0.42, 1.02), (0.46, 0.46, 0.56), BLACK, rough=0.6)
head = sphere('cat_head', (0, 0.42, 1.4), (0.34, 0.34, 0.32), BLACK, rough=0.6)
ear_l = cone('cat_ear_l', (-0.19, 0.42, 1.74), 0.12, 0.28, BLACK, rough=0.6)
ear_r = cone('cat_ear_r', (0.19, 0.42, 1.74), 0.12, 0.28, BLACK, rough=0.6)
ear_l.rotation_euler = (0, 0, math.radians(16))
ear_r.rotation_euler = (0, 0, math.radians(-16))
arm_l = cylinder('cat_arm_l', (-0.52, -0.02, 1.05), 0.1, 0.55, BLACK, rough=0.6, rot=(math.radians(90), 0, 0))
arm_r = cylinder('cat_arm_r', (0.52, -0.02, 1.05), 0.1, 0.55, BLACK, rough=0.6, rot=(math.radians(90), 0, 0))
scarf = torus('cat_scarf', (0, 0.42, 1.18), 0.45, 0.1, SCARF['sit'], rough=0.45)
scarf.scale = (1.0, 0.92, 1.0)

for obj in (body, head, ear_l, ear_r, arm_l, arm_r, scarf):
    obj.parent = rig

objs = {'rig': rig, 'body': body, 'head': head, 'ear_l': ear_l, 'ear_r': ear_r, 'scarf': scarf}
scarf_bsdf = scarf.data.materials[0].node_tree.nodes['Principled BSDF']

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
        rig.location.z = 0.0
        head.location.z = 0.006 * math.sin(phase)
        head.rotation_euler.x = 0.0
        ear_r.rotation_euler.z = 0.0

        if scene == 'sleep':
            head.rotation_euler.x = -0.4
            head.location.z = -0.16
            rig.scale = (0.99, 0.99, 0.99)
        if scene == 'enter':
            e = ease(min(1.0, f / (FRAMES * 0.45)))
            rig.scale = (0.9 + 0.1 * e,) * 3
            rig.location.z = -0.14 * (1.0 - e)
            head.location.z = 0.0
        if 0.35 <= t <= 0.44:
            ear_r.rotation_euler.z = 0.16

        bpy.context.view_layer.update()
        sc.render.filepath = str(ROOT / scene / f'{f + 1:03d}.png')
        bpy.ops.render.render(write_still=True)

print('RENDER_DONE', ROOT)
