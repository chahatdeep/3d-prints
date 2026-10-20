"""Render each exterior design (pot + drip tray) for side-by-side selection.

usage: blender -b -P render_designs.py -- <designs dir> <original planter/ dir> <out dir>
Designs dir holds <name>_pot.stl / <name>_tray.stl from boho_designs.py (100%, design frame: y up).
"""
import math, os, sys
import bpy
from mathutils import Matrix, Vector

ARGS = sys.argv[sys.argv.index('--') + 1:]
DES, ORIG, OUT = ARGS[:3]
ONLY = set(ARGS[3].split(',')) if len(ARGS) > 3 else None
os.makedirs(OUT, exist_ok=True)

DESIGNS = [  # file prefix, label, colour (linear RGB)
    ('original', 'Current spiral', (0.40, 0.52, 0.40)),
    ('rattan', 'Rattan weave', (0.56, 0.38, 0.21)),
    ('rope', 'Seagrass rope coil', (0.74, 0.64, 0.47)),
    ('reeded', 'Terracotta reeds', (0.66, 0.30, 0.17)),
    ('dunes', 'Sand dunes', (0.82, 0.70, 0.53)),
    ('mudcloth', 'Mudcloth', (0.86, 0.81, 0.71)),
    ('berber', 'Berber diamonds', (0.84, 0.80, 0.73)),
    ('petals', 'Lotus petals', (0.46, 0.55, 0.42)),
    ('herringbone', 'Herringbone weave', (0.62, 0.42, 0.26)),
    ('mountains', 'Mountain chevrons', (0.55, 0.37, 0.20)),
    ('arches', 'Rainbow arches', (0.68, 0.36, 0.22)),
    ('slats', 'Wood slats', (0.60, 0.42, 0.25)),
    ('sunburst', 'Sunburst', (0.80, 0.62, 0.38)),
    ('ripples', 'Ripples', (0.78, 0.66, 0.50)),
    ('fern', 'Fern fronds', (0.38, 0.47, 0.37)),
    ('triptych', 'Triptych', (0.57, 0.39, 0.23)),
]
if ONLY:
    DESIGNS = [d for d in DESIGNS if d[0] in ONLY]
AXIS_Z, TRAY_DY = -3.23, -56.65
TO_BLENDER = Matrix(((-1, 0, 0, 0), (0, 0, 1, 0), (0, 1, 0, 0), (0, 0, 0, 1)))

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.render.engine = 'CYCLES'
try:
    prefs = bpy.context.preferences.addons['cycles'].preferences
    prefs.compute_device_type = 'OPTIX'; prefs.get_devices()
    for d in prefs.devices:
        d.use = d.type == 'OPTIX'
    sc.cycles.device = 'GPU'
except Exception as e:
    print('GPU setup failed, CPU:', e)
sc.cycles.samples = 128
sc.cycles.use_denoising = True
sc.view_settings.view_transform = 'AgX'
sc.view_settings.look = 'AgX - Medium High Contrast'
sc.render.resolution_x = sc.render.resolution_y = 1200
world = bpy.data.worlds.new('W'); sc.world = world; world.use_nodes = True
world.node_tree.nodes['Background'].inputs['Color'].default_value = (0.90, 0.86, 0.80, 1)
world.node_tree.nodes['Background'].inputs['Strength'].default_value = 0.5


def material(name, col):
    m = bpy.data.materials.new(name); m.use_nodes = True
    p = m.node_tree.nodes['Principled BSDF']
    p.inputs['Base Color'].default_value = (*col, 1)
    p.inputs['Roughness'].default_value = 0.7
    return m


def load(path, M, mat):
    before = set(bpy.data.objects)
    bpy.ops.wm.stl_import(filepath=path)
    ob = (set(bpy.data.objects) - before).pop()
    ob.matrix_world = M
    ob.data.materials.clear(); ob.data.materials.append(mat)
    return ob


# floor that catches a soft shadow
bpy.ops.mesh.primitive_plane_add(size=4000, location=(0, 0, -78))
floor = bpy.context.active_object
floor.data.materials.append(material('floor', (0.80, 0.74, 0.66)))

cam = bpy.data.objects.new('cam', bpy.data.cameras.new('cam')); sc.collection.objects.link(cam); sc.camera = cam
cam.data.lens = 85; cam.data.clip_end = 20000


def area(name, loc, size, energy, target):
    L = bpy.data.lights.new(name, 'AREA'); L.size = size; L.energy = energy; L.color = (1.0, 0.95, 0.88)
    o = bpy.data.objects.new(name, L); sc.collection.objects.link(o); o.location = loc
    o.rotation_euler = (Vector(target) - o.location).to_track_quat('-Z', 'Y').to_euler()


target = Vector((0, 3.23, -10))
area('key', target + Vector((-260, -320, 240)), 260, 2.2e6, target)
area('fill', target + Vector((330, -200, 60)), 320, 0.7e6, target)
area('rim', target + Vector((80, 360, 260)), 200, 1.0e6, target)

dirv = Vector((-0.45, -1.0, 0.32)).normalized()
cam.rotation_euler = (-dirv).to_track_quat('-Z', 'Y').to_euler()
cam.location = target + dirv * 520

objs = []
for key, label, col in DESIGNS:
    for o in objs:
        bpy.data.objects.remove(o, do_unlink=True)
    objs = []
    mat = material(key, col)
    if key == 'original':
        pot, tray = os.path.join(ORIG, '9_Top__Top.stl'), os.path.join(ORIG, '14_Bottom__Bottom.stl')
    else:
        pot, tray = os.path.join(DES, f'{key}_pot.stl'), os.path.join(DES, f'{key}_tray.stl')
    if not os.path.exists(pot):
        print('missing', pot); continue
    objs.append(load(pot, TO_BLENDER, mat))
    objs.append(load(tray, TO_BLENDER @ Matrix.Translation((0, TRAY_DY, AXIS_Z)), mat))
    sc.render.filepath = os.path.join(OUT, f'{key}.png')
    bpy.ops.render.render(write_still=True)
    print('rendered', key)
