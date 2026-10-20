"""Build the 155% Brynhild planter with a 100% LODRET rail, plus LODRET parts bored for a 7/8" dowel.

usage: python -I build.py <workdir> <outdir>
Inputs come from <workdir>/planter and <workdir>/lodret (made by extract3mf.py)
and the original 3MFs in <workdir>/in (for print orientations).
"""
import os, re, sys, zipfile
import numpy as np
import trimesh
import manifold3d as mf

W, OUT = sys.argv[1], sys.argv[2]
os.makedirs(OUT, exist_ok=True)
S = 1.55          # pot scale
BORE_R = 11.3     # 22.6 mm bore for a 22.2 mm (7/8") dowel


def to_mf(m):
    return mf.Manifold(mf.Mesh(vert_properties=np.asarray(m.vertices, np.float32),
                               tri_verts=np.asarray(m.faces, np.uint32)))


def to_tm(M):
    g = M.to_mesh()
    return trimesh.Trimesh(np.asarray(g.vert_properties)[:, :3], np.asarray(g.tri_verts), process=False)


def box(x0, x1, y0, y1, z0, z1):
    return mf.Manifold.cube([x1 - x0, y1 - y0, z1 - z0]).translate([x0, y0, z0])


def load(p):
    return trimesh.load(os.path.join(W, p), process=True)


def plate_rotation(src3mf, object_id):
    """Rotation part of the build-item transform (how the designer laid the part on the bed)."""
    top = zipfile.ZipFile(src3mf).read('3D/3dmodel.model').decode()
    t = re.search(r'<item objectid="%s"[^>]*transform="([^"]+)"' % object_id, top).group(1)
    a = list(map(float, t.split()))
    M = np.eye(4)
    M[:3, :3] = np.array(a[:9]).reshape(3, 3).T
    return M


def save(mesh, name, rot=None):
    m = mesh.copy()
    if rot is not None:
        m.apply_transform(rot)
    m.apply_translation(-m.bounds[0] + [0, 0, 0])            # sit on z=0, corner at origin
    m.apply_translation([-m.extents[0] / 2, -m.extents[1] / 2, 0])  # center on x/y
    m.export(os.path.join(OUT, name))
    print(f'{name:40s} size {np.round(m.extents, 1)} mm  watertight={m.is_watertight}  vol={m.volume / 1000:.1f} cm3')
    return m


PL = os.path.join(W, 'in', 'Brynhild_hanging_planter.3mf')
LD = os.path.join(W, 'in', 'LODRET_system.3mf')

# ---------------- pot: scale body, keep the LODRET dovetail rail at 100% ----------------
pot = to_mf(load('planter/9_Top__Top.stl'))
# original rail + its base block (back of the pot is +z, pot axis is y)
RAIL = dict(x0=-12, x1=12, y0=-34, y1=21, z0=47, z1=58)
rail = pot ^ box(RAIL['x0'], RAIL['x1'], RAIL['y0'], RAIL['y1'], RAIL['z0'], RAIL['z1'])

big = pot.scale([S, S, S])
ZCUT = 76.0                                   # just above the scaled rib tops (75.2)
big = big - box(-20, 20, -60, 40, ZCUT, 120)  # remove the oversized rail

# place the 100% rail on the scaled back, centred on the old (scaled) rail position
dy = (-33 + 20) / 2 * S - (-33 + 20) / 2
dz = ZCUT - RAIL['z0'] - 0.4                   # 0.4 mm overlap into the plateau
rail = rail.translate([0, dy, dz])
# solid backing pad that fuses rail, plateau and pot wall (inner wall top is z=73.5)
pad = box(-10.5, 10.5, -33 + dy, 20 + dy, 74.0, RAIL['z0'] + dz + 3)
pot155 = big + rail + pad
pot155_tm = to_tm(pot155)
rot_pot = plate_rotation(PL, 9)
save(pot155_tm, 'Brynhild_pot_155pct_LODRET-rail.stl', rot_pot)

# ---------------- drip tray + wick feet: plain 155% ----------------
tray = load('planter/14_Bottom__Bottom.stl'); tray.apply_scale(S)
save(tray, 'Brynhild_drip-tray_155pct.stl', plate_rotation(PL, 14))
foot = load('planter/2_foot__foot.stl'); foot.apply_scale(S)
save(foot, 'Brynhild_wick-foot_155pct_print-3.stl', plate_rotation(PL, 2))

# ---------------- LODRET at 100%, bores opened to 22.6 mm ----------------
hanger = to_mf(load('lodret/4_Rod_hanger__Rod_hanger.stl'))
cyl_y = lambda r, cx, cz, L: mf.Manifold.cylinder(L, r, r, 128, True).rotate([90, 0, 0]).translate([cx, 0, cz])
hanger = hanger - cyl_y(BORE_R, 0, 2.0, 80)
save(to_tm(hanger), 'LODRET_rod-hanger_22.6bore.stl', plate_rotation(LD, 4))

mount = load('lodret/6_Rod_mount__Rod_mount.stl')
v = mount.vertices
band = v[(np.abs(v[:, 0]) < 12) & (v[:, 2] < -3) & (v[:, 2] > -20)]
print('rod mount bore check: x range', band[:, 0].min().round(2), band[:, 0].max().round(2))
mountM = to_mf(mount)
# bore axis along y; find its centre z from the arc of the cavity
sec = v[(np.abs(v[:, 1]) < 0.5) & (np.abs(v[:, 0]) < 11.5) & (v[:, 2] < -3) & (v[:, 2] > -19)]
r_best, cz_best = None, None
for cz in np.arange(-16, -9, 0.05):
    r = np.hypot(sec[:, 0], sec[:, 2] - cz)
    inner = r[r < 13]
    if len(inner) and (r_best is None or inner.std() < r_best[1]):
        r_best, cz_best = (inner.min(), inner.std()), cz
print('rod mount bore centre z=%.2f r=%.3f' % (cz_best, r_best[0]))
mountM = mountM - cyl_y(BORE_R, 0, cz_best, 60)
save(to_tm(mountM), 'LODRET_wall-rod-mount_22.6bore_print-2.stl', plate_rotation(LD, 6))

fast = load('lodret/2_Fastener__Fastener.stl')
save(fast, 'LODRET_fastener-knob.stl', plate_rotation(LD, 2))
