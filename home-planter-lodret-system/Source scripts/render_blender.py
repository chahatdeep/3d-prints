"""Render preview images of the planter system in Blender (Cycles).

usage: blender -b -P render_blender.py -- <scene.json> <lodret parts folder> <out folder>
scene.json comes from assemble.py. Units are millimetres (1 Blender unit = 1 mm).
"""
import json, math, os, sys
import bpy
from mathutils import Matrix, Vector

argv = sys.argv[sys.argv.index('--') + 1:]
SCENE_JSON, LODRET_DIR, OUT = argv
os.makedirs(OUT, exist_ok=True)
data = json.load(open(SCENE_JSON))

# ---------- clean scene ----------
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.render.engine = 'CYCLES'
try:
    prefs = bpy.context.preferences.addons['cycles'].preferences
    for dev in ('OPTIX', 'CUDA'):
        try:
            prefs.compute_device_type = dev
            prefs.get_devices()
            if any(d.type == dev for d in prefs.devices):
                for d in prefs.devices:
                    d.use = d.type == dev
                sc.cycles.device = 'GPU'
                print('Cycles device:', dev)
                break
        except TypeError:
            continue
except Exception as e:  # CPU fallback
    print('GPU setup failed, using CPU:', e)
sc.cycles.samples = 96
sc.cycles.use_denoising = True
sc.render.film_transparent = False
sc.view_settings.view_transform = 'AgX'
sc.view_settings.look = 'AgX - Medium High Contrast'

world = bpy.data.worlds.new('World'); sc.world = world
world.use_nodes = True
bg = world.node_tree.nodes['Background']
bg.inputs['Color'].default_value = (0.93, 0.93, 0.92, 1)
bg.inputs['Strength'].default_value = 0.55

# ---------- materials ----------
COLORS = {
    'sage': (0.40, 0.52, 0.40), 'terracotta': (0.70, 0.33, 0.20), 'white': (0.86, 0.86, 0.83),
    'lodret': (0.80, 0.80, 0.78), 'wick': (0.93, 0.92, 0.88), 'wood': (0.55, 0.36, 0.19),
    'wall': (0.90, 0.89, 0.86),
}
MATS = {}


def mat(name):
    if name in MATS:
        return MATS[name]
    base = name.replace('_dark', '')
    c = COLORS[base]
    if name.endswith('_dark'):
        c = tuple(x * 0.72 for x in c)
    m = bpy.data.materials.new(name); m.use_nodes = True
    p = m.node_tree.nodes['Principled BSDF']
    p.inputs['Base Color'].default_value = (*c, 1)
    p.inputs['Roughness'].default_value = 0.75 if base == 'wall' else 0.5
    if base == 'wood':
        p.inputs['Roughness'].default_value = 0.6
    MATS[name] = m
    return m


# ---------- load parts (meshes shared between copies of the same file) ----------
MESH_CACHE = {}
OBJS = {}


def import_stl(path):
    if path in MESH_CACHE:
        return MESH_CACHE[path]
    before = set(bpy.data.objects)
    bpy.ops.wm.stl_import(filepath=path)
    ob = (set(bpy.data.objects) - before).pop()
    me = ob.data
    bpy.data.objects.remove(ob)
    for f in me.polygons:
        f.use_smooth = False
    me.materials.clear()
    me.materials.append(None)      # one slot, set once; each object fills it with its own material
    MESH_CACHE[path] = me
    return me


def new_obj(name, me, material, group):
    ob = bpy.data.objects.new(name, me)
    sc.collection.objects.link(ob)
    ob.material_slots[0].link = 'OBJECT'
    ob.material_slots[0].material = mat(material)
    ob['group'] = group
    return ob


for p in data['parts']:
    ob = new_obj(p['name'], import_stl(p['file']), p['material'], p['group'])
    ob.matrix_world = Matrix(p['matrix'])
    OBJS[p['name']] = ob

# size comparison: stand every pot set on the same baseline (z = 0)
bpy.context.view_layer.update()
for tag in {n.split('_')[1] for n, o in OBJS.items() if o['group'] == 'compare'}:
    grp = [o for n, o in OBJS.items() if o['group'] == 'compare' and n.split('_')[1] == tag]
    zmin = min((o.matrix_world @ Vector(c)).z for o in grp for c in o.bound_box)
    for o in grp:
        o.matrix_world = Matrix.Translation((0, 0, -zmin)) @ o.matrix_world

ex = data['extras']
# dowel (rod along blender z at x=0, y=0)
d = ex['dowel']
bpy.ops.mesh.primitive_cylinder_add(radius=d['radius'], depth=d['y1'] - d['y0'], vertices=96,
                                    location=(0, 0, (d['y0'] + d['y1']) / 2))
dowel = bpy.context.active_object; dowel.name = 'dowel'; dowel.data.materials.append(mat('wood'))
dowel['group'] = 'system'
bpy.ops.object.shade_smooth()
# wall
bpy.ops.mesh.primitive_plane_add(size=1, location=(0, ex['wall']['z'] + 0.01, (d['y0'] + d['y1']) / 2),
                                 rotation=(math.radians(90), 0, 0))
wall = bpy.context.active_object; wall.name = 'wall'; wall.scale = (900, d['y1'] - d['y0'] + 400, 1)
wall.data.materials.append(mat('wall')); wall['group'] = 'system'

# LODRET parts lineup (separate group)
x = 0.0
for fn, n in (('LODRET_wall-rod-mount_22.6bore_print-2.stl', 1), ('LODRET_rod-hanger_22.6bore.stl', 1),
              ('LODRET_fastener-knob.stl', 1)):
    ob = new_obj('lineup_' + fn[:-4], import_stl(os.path.join(LODRET_DIR, fn)), 'lodret', 'lineup')
    bb = [Vector(c) for c in ob.bound_box]
    mn = Vector((min(c.x for c in bb), min(c.y for c in bb), min(c.z for c in bb)))
    mx = Vector((max(c.x for c in bb), max(c.y for c in bb), max(c.z for c in bb)))
    ob.location = (x - mn.x, -(mn.y + mx.y) / 2, -mn.z + 2000)   # parked far away from the system
    x += (mx.x - mn.x) + 25
    ob['group'] = 'lineup'

# ---------- lights ----------
def area(name, loc, size, energy, rot_to=(0, 0, 0)):
    L = bpy.data.lights.new(name, 'AREA'); L.size = size; L.energy = energy
    o = bpy.data.objects.new(name, L); sc.collection.objects.link(o); o.location = loc
    tgt = Vector(rot_to); o.rotation_euler = (tgt - o.location).to_track_quat('-Z', 'Y').to_euler()
    return o


cam_data = bpy.data.cameras.new('cam'); cam = bpy.data.objects.new('cam', cam_data)
sc.collection.objects.link(cam); sc.camera = cam
cam_data.clip_start = 1; cam_data.clip_end = 20000


def visible(groups, hide_names=()):
    for o in sc.objects:
        if o.type in ('LIGHT', 'CAMERA'):
            continue
        show = o.get('group') in groups and o.name not in hide_names
        o.hide_render = not show
        o.hide_viewport = not show


def frame(objs, direction, lens=60, margin=1.08, up=(0, 0, 1), res=(1600, 1200)):
    bpy.context.view_layer.update()
    pts = []
    for o in objs:
        pts += [o.matrix_world @ Vector(c) for c in o.bound_box]
    c = sum(pts, Vector()) / len(pts)
    dirv = Vector(direction).normalized()
    cam_data.lens = lens
    sc.render.resolution_x, sc.render.resolution_y = res
    cam.rotation_euler = (-dirv).to_track_quat('-Z', 'Y').to_euler()
    # pull back until every bbox corner is inside the frame
    cam_data.sensor_fit = 'AUTO'
    aspect = res[0] / res[1]
    fov_x = 2 * math.atan(cam_data.sensor_width / 2 / lens)
    fov_h, fov_v = (fov_x, 2 * math.atan(math.tan(fov_x / 2) / aspect)) if aspect >= 1 else \
        (2 * math.atan(math.tan(fov_x / 2) * aspect), fov_x)
    rot = cam.rotation_euler.to_matrix()
    right, upv, fwd = rot @ Vector((1, 0, 0)), rot @ Vector((0, 1, 0)), rot @ Vector((0, 0, -1))
    dist = 0
    for p in pts:
        v = p - c
        depth_off = v.dot(fwd)
        dist = max(dist, abs(v.dot(right)) / math.tan(fov_h / 2) * margin - depth_off,
                   abs(v.dot(upv)) / math.tan(fov_v / 2) * margin - depth_off)
    cam.location = c - fwd * dist
    return c, dist


lights = []


def light_rig(center, dist):
    for o in lights:
        bpy.data.objects.remove(o)
    lights.clear()
    c = Vector(center)
    s = dist
    lights.append(area('key', c + Vector((-0.6 * s, -0.8 * s, 0.7 * s)), 0.6 * s, 2.2 * s * s, c))
    lights.append(area('fill', c + Vector((0.8 * s, -0.6 * s, 0.2 * s)), 0.8 * s, 0.8 * s * s, c))
    lights.append(area('rim', c + Vector((0.2 * s, 0.9 * s, 0.9 * s)), 0.5 * s, 1.2 * s * s, c))


def shot(name, groups, objs_for_frame, direction, lens=60, res=(1600, 1200), hide=(), margin=1.08):
    visible(groups, hide)
    c, dist = frame(objs_for_frame, direction, lens, margin, res=res)
    light_rig(c, dist)
    sc.render.filepath = os.path.join(OUT, name)
    bpy.ops.render.render(write_still=True)
    print('rendered', name)


g = lambda prefix: [o for n, o in OBJS.items() if n.startswith(prefix)]
system_objs = [o for o in OBJS.values() if o['group'] == 'system'] + [dowel]
lineup = [o for o in sc.objects if o.get('group') == 'lineup']

shot('01_system_front.png', {'system'}, system_objs, (-0.55, -1, 0.25), lens=50, res=(1200, 1600))
shot('02_system_side.png', {'system'}, system_objs, (-1, -0.12, 0.1), lens=50, res=(1200, 1600))
shot('03_pot155.png', {'system'}, g('pot_155') + g('tray_155'), (-0.6, -1, 0.55), lens=70,
     hide=('pot_105', 'tray_105', 'hanger_105', 'hanger_knob_105', 'mount_top', 'mount_top_knob', 'wall'))
shot('04_pot105.png', {'system'}, g('pot_105') + g('tray_105'), (-0.6, -1, 0.55), lens=70,
     hide=('pot_155', 'tray_155', 'hanger_155', 'hanger_knob_155', 'mount_bottom', 'mount_bottom_knob', 'wall'))
shot('05_size_comparison.png', {'compare'}, [o for o in OBJS.values() if o['group'] == 'compare'],
     (0.0, -1, 0.3), lens=60, res=(1800, 1000))
shot('06_rail_and_hanger_closeup.png', {'system'}, g('hanger_155') + g('hanger_knob_155'), (-1, 0.9, 0.35), lens=60,
     hide=('wall',), margin=1.9)
shot('07_lodret_parts.png', {'lineup'}, lineup, (-0.3, -1, 0.6), lens=60, res=(1600, 900))
# pot / drip-tray joint close up: ribs should run straight across the seam
shot('09_pot_tray_joint.png', {'system'}, g('tray_155'), (-0.35, -1, 0.12), lens=85, res=(1600, 1000), margin=1.02,
     hide=('pot_105', 'tray_105', 'hanger_105', 'hanger_knob_105', 'hanger_155', 'hanger_knob_155',
           'mount_top', 'mount_top_knob', 'mount_bottom', 'mount_bottom_knob', 'wall', 'dowel'))
# back of the bare 155% pot: the 100% rail with the rib pattern running up to it
shot('08_pot155_back_rail.png', {'system'}, g('pot_155'), (-0.55, 1, 0.25), lens=70, res=(1400, 1400),
     hide=('pot_105', 'tray_105', 'hanger_105', 'hanger_knob_105', 'hanger_155', 'hanger_knob_155',
           'mount_top', 'mount_top_knob', 'mount_bottom', 'mount_bottom_knob', 'wall', 'dowel'))
