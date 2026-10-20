"""Work out where every printed part sits in the assembled planter system; write scene.json for render_blender.py.

usage: python -I assemble.py <system folder> <extracted work dir> <out scene.json>
<extracted work dir> holds planter/ and lodret/ from extract3mf.py (design-frame originals).

Frames: every part is brought back to its *design* frame (pot: y up, rail toward +z).
The assembly is built in that frame (rod along y at x=0, z=0; wall at +z), then
converted to Blender's z-up frame: (x, y, z) -> (-x, z, y).
"""
import json, os, re, sys, zipfile
import numpy as np
import trimesh

SYS, WORK, OUT = sys.argv[1:4]
ORIG = os.path.join(SYS, 'Original downloads')


def plate_rot(src, oid):
    top = zipfile.ZipFile(src).read('3D/3dmodel.model').decode()
    a = list(map(float, re.search(r'<item objectid="%s"[^>]*transform="([^"]+)"' % oid, top).group(1).split()))
    M = np.eye(4); M[:3, :3] = np.array(a[:9]).reshape(3, 3).T
    return M


def T(t):
    M = np.eye(4); M[:3, 3] = t; return M


def to_design(path, rot, ref_min):
    """Matrix taking an output STL (plate-oriented, recentred) back to its design frame."""
    m = trimesh.load(path, process=False)
    Rinv = np.linalg.inv(rot)
    m.apply_transform(Rinv)
    return T(np.asarray(ref_min) - m.bounds[0]) @ Rinv, m.copy().apply_transform(T(np.asarray(ref_min) - m.bounds[0]))


PL = os.path.join(ORIG, 'Brynhild_hanging_planter.3mf')
LD = os.path.join(ORIG, 'LODRET_system.3mf')
orig = {k: trimesh.load(os.path.join(WORK, p), process=False) for k, p in {
    'pot': 'planter/9_Top__Top.stl', 'tray': 'planter/14_Bottom__Bottom.stl', 'foot': 'planter/2_foot__foot.stl',
    'hanger': 'lodret/4_Rod_hanger__Rod_hanger.stl', 'mount': 'lodret/6_Rod_mount__Rod_mount.stl',
    'knob': 'lodret/2_Fastener__Fastener.stl'}.items()}

# --- wick-foot holes in the original pot floor (design frame, x/z), found from floor-slice vertices
v = orig['pot'].vertices
fl = v[(v[:, 1] > -45.5) & (v[:, 1] < -44.0)]
fl = fl[(np.hypot(fl[:, 0], fl[:, 2]) > 8) & (np.hypot(fl[:, 0], fl[:, 2]) < 34)]
pts = fl[:, [0, 2]]
cent = np.array([[-22.0, -4.0], [10.0, 18.0], [10.0, -22.0]])   # rough positions from the top-view render
for _ in range(20):                                               # k-means, k=3
    lab = np.argmin(((pts[:, None, :] - cent[None]) ** 2).sum(-1), 1)
    cent = np.array([pts[lab == k].mean(0) for k in range(3)])
HOLES = list(cent)
print('wick holes (x,z):', np.round(HOLES, 1).tolist())

FLOOR_TOP = -43.5          # pot floor top surface (design frame, 100%)
# Tray under the pot (measured with tray_alignment.py, 100% design frames):
#  - the pot's bottom, groove and outer skin are centred on the pot axis at z = -3.23
#  - the tray's outer wall top (y = 10.15) meets the pot's bottom (y = -46.5)
#  - turning the tray -0.29 deg continues the pot's 54 spiral ribs across the joint
POT_AXIS_Z = -3.23
TRAY_DY = -56.65
TRAY_ROT_DEG = 6.377 - 360 / 54
FOOT_TOP = orig['foot'].bounds[1][1]

scene = []                 # entries: name, file, matrix (blender frame), material


def add(name, path, M, mat):
    scene.append(dict(name=name, file=path, matrix=M.tolist(), material=mat))


TO_BLENDER = np.array([[-1, 0, 0, 0], [0, 0, 1, 0], [0, 1, 0, 0], [0, 0, 0, 1]], float)


def pot_set(folder, pct, hanger_y, mat, origin_x=0.0, tag=None, with_lodret=True):
    """Place pot (+tray, feet, hanger, knob) so its hanger bore is on the rod at height hanger_y."""
    S = pct / 100
    tag = tag or f'{pct}'
    potp = os.path.join(SYS, folder, f'Brynhild_pot_{pct}pct_LODRET-rail.stl') if pct != 100 else None
    if potp:
        Mpot, pm = to_design(potp, plate_rot(PL, 9), orig['pot'].bounds[0] * S)
    else:  # original pot straight from the extracted design-frame file
        potp = os.path.join(WORK, 'planter/9_Top__Top.stl'); Mpot = np.eye(4); pm = orig['pot']
    pv = pm.vertices
    head = pv[(np.abs(pv[:, 0]) < 6)]
    zt = head[:, 2].max()
    hy = pv[(np.abs(pv[:, 0]) < 6) & (pv[:, 2] > zt - 1)][:, 1]
    rail_bottom = hy.min()
    # hanger (design frame): bore centre (0, *, 2), channel bottom z=-13, channel starts at y=-20 (stop lip below)
    hz = -2.0                                  # puts the bore on the rod at z=0
    pot_shift = np.array([origin_x, (hanger_y - 20) - rail_bottom, (-13 + hz - 0.2) - zt])
    Pw = T(pot_shift)
    add(f'pot_{tag}', potp, TO_BLENDER @ Pw @ Mpot, mat)
    # tray: rim top snaps into the groove under the pot
    if pct != 100:
        trayp = os.path.join(SYS, folder, f'Brynhild_drip-tray_{pct}pct.stl')
        Mtray, _ = to_design(trayp, plate_rot(PL, 14), orig['tray'].bounds[0] * S)
        footp = os.path.join(SYS, folder, f'Brynhild_wick-foot_{pct}pct_print-3.stl')
        Mfoot, _ = to_design(footp, plate_rot(PL, 2), orig['foot'].bounds[0] * S)
    else:
        trayp = os.path.join(WORK, 'planter/14_Bottom__Bottom.stl'); Mtray = np.eye(4)
        footp = os.path.join(WORK, 'planter/2_foot__foot.stl'); Mfoot = np.eye(4)
    t = np.radians(TRAY_ROT_DEG)   # positive turns +x toward +z (same sense as the angle used to measure it)
    Rt = np.array([[np.cos(t), 0, -np.sin(t), 0], [0, 1, 0, 0], [np.sin(t), 0, np.cos(t), 0], [0, 0, 0, 1]])
    add(f'tray_{tag}', trayp, TO_BLENDER @ Pw @ T([0, TRAY_DY * S, POT_AXIS_Z * S]) @ Rt @ Mtray, mat)
    for i, (hx, hzz) in enumerate(HOLES):
        add(f'foot_{tag}_{i + 1}', footp,
            TO_BLENDER @ Pw @ T([hx * S, (FLOOR_TOP + 1.0 - FOOT_TOP) * S, hzz * S]) @ Mfoot, 'wick')
    if with_lodret:
        Mh, _ = to_design(os.path.join(SYS, 'LODRET parts (7-8 in dowel)', 'LODRET_rod-hanger_22.6bore.stl'),
                          plate_rot(LD, 4), orig['hanger'].bounds[0])
        add(f'hanger_{tag}', HANGER, TO_BLENDER @ T([origin_x, hanger_y, hz]) @ Mh, 'lodret')
        Mk, _ = to_design(KNOB, plate_rot(LD, 2), orig['knob'].bounds[0])
        # knob threads into the hanger's back (+z) face
        add(f'hanger_knob_{tag}', KNOB, TO_BLENDER @ T([origin_x, hanger_y, hz + orig['hanger'].bounds[1][2] - 1.0]) @ Mk, 'lodret')
    return pot_shift, pm.bounds + pot_shift


HANGER = os.path.join(SYS, 'LODRET parts (7-8 in dowel)', 'LODRET_rod-hanger_22.6bore.stl')
KNOB = os.path.join(SYS, 'LODRET parts (7-8 in dowel)', 'LODRET_fastener-knob.stl')
MOUNT = os.path.join(SYS, 'LODRET parts (7-8 in dowel)', 'LODRET_wall-rod-mount_22.6bore_print-2.stl')

# ---------- assembled system: 155% low, 105% above, mounts top and bottom ----------
_, b155 = pot_set('Pot 155% (fits 32 oz Fage tub)', 155, 0.0, 'sage')
gap = 150.0                                     # room for the plant in the lower pot
y105 = 0.0 + 82 + 42 + gap                      # 155% "above" + 105% "below" + plant room
_, b105 = pot_set('Pot 105%', 105, y105, 'terracotta')
y_bot = b155[0][1] - 30                         # bottom mount below the big pot's tray
y_top = b105[1][1] + 60
Mm, _ = to_design(MOUNT, plate_rot(LD, 6), orig['mount'].bounds[0])
Mk, _ = to_design(KNOB, plate_rot(LD, 2), orig['knob'].bounds[0])
FLIP_X = np.diag([1, -1, -1, 1.0])              # knob turned to face the pot (-z)
mz = 12.45                                      # mount bore centre is at z=-12.45 in its design frame
for nm, y in (('mount_bottom', y_bot), ('mount_top', y_top)):
    add(nm, MOUNT, TO_BLENDER @ T([0, y, mz]) @ Mm, 'lodret')
    front = orig['mount'].bounds[0][2] + mz
    add(nm + '_knob', KNOB, TO_BLENDER @ T([0, y, front + 1.0]) @ FLIP_X @ Mk, 'lodret')
wall_z = orig['mount'].bounds[1][2] + mz
extras = dict(
    dowel=dict(radius=11.1, y0=y_bot - 45, y1=y_top + 45),
    wall=dict(z=wall_z),
    floor_y=None,
    bounds=dict(ymin=float(b155[0][1]), ymax=float(y_top + 45)))

# ---------- size comparison row (no LODRET): 100%, 105%, 155% side by side ----------
comp = []
xpos = {100: 0.0, 105: 150.0, 155: 345.0}
for pct, folder, mat in ((100, None, 'white'), (105, 'Pot 105%', 'terracotta'), (155, 'Pot 155% (fits 32 oz Fage tub)', 'sage')):
    n0 = len(scene)
    pot_set(folder, pct, 0.0, mat, origin_x=-xpos[pct], tag=f'cmp{pct}', with_lodret=False)
    for e in scene[n0:]:
        e['group'] = 'compare'
for e in scene:
    e.setdefault('group', 'system')

json.dump(dict(parts=scene, extras=extras, holes=[list(map(float, h)) for h in HOLES]), open(OUT, 'w'), indent=1)
print('parts:', len(scene), ' rod', extras['dowel'], ' wall z', round(wall_z, 2))
