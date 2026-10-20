"""Build a Brynhild pot (+ drip tray + wick feet) at any scale, keeping the LODRET dovetail rail at 100%.

usage: python -I build_pot.py <workdir> <outdir> <scale, e.g. 1.05>
<workdir> needs planter/ (from extract3mf.py) and in/Brynhild_hanging_planter.3mf.
The LODRET parts don't change with pot size; reuse the ones from build.py.

How the rail is swapped seamlessly:
  1. Scale the pot. Its rail is now oversized.
  2. Cut a block out of the back (the oversized rail + the wall behind it).
  3. Refill that block from the pot rotated 180 deg about its own axis. The surface pattern
     repeats every 20 deg (checked to 0.005 mm), so the ribs continue without a seam.
  4. Add the original 100% rail on a solid column, seated so the clearances under the
     LODRET hanger match the original design.
"""
import os, re, sys, zipfile
import numpy as np
import trimesh
import manifold3d as mf

W, OUT, S = sys.argv[1], sys.argv[2], float(sys.argv[3])
os.makedirs(OUT, exist_ok=True)
PCT = round(S * 100)

# original pot geometry (design axes: y up, rail toward +z)
AXIS_Z = -3.25        # pot axis is at x=0, z=-3.25 (100%)
RAIL = dict(x0=-11.2, x1=11.2, y0=-34, y1=21, z0=48.5, z1=58)  # rail + its base block, 100%
RAIL_TOP = 56.77
CLEAR = 7.85          # original: rail top to highest pot surface under the hanger wings
BLOCK_HALF = 14.5     # half-width of the oversized-rail block to replace (x 100% units)
INNER_TOP = 47.4      # inner wall at the back centre (100%)


def to_mf(m):
    return mf.Manifold(mf.Mesh(vert_properties=np.asarray(m.vertices, np.float32),
                               tri_verts=np.asarray(m.faces, np.uint32)))


def to_tm(M):
    g = M.to_mesh()
    return trimesh.Trimesh(np.asarray(g.vert_properties)[:, :3], np.asarray(g.tri_verts), process=False)


def box(x0, x1, y0, y1, z0, z1):
    return mf.Manifold.cube([x1 - x0, y1 - y0, z1 - z0]).translate([x0, y0, z0])


def plate_rotation(oid):
    top = zipfile.ZipFile(os.path.join(W, 'in', 'Brynhild_hanging_planter.3mf')).read('3D/3dmodel.model').decode()
    a = list(map(float, re.search(r'<item objectid="%s"[^>]*transform="([^"]+)"' % oid, top).group(1).split()))
    M = np.eye(4); M[:3, :3] = np.array(a[:9]).reshape(3, 3).T
    return M


def save(mesh, name, rot):
    m = mesh.copy(); m.apply_transform(rot)
    m.apply_translation(-m.bounds[0]); m.apply_translation([-m.extents[0] / 2, -m.extents[1] / 2, 0])
    m.export(os.path.join(OUT, name))
    print(f'{name:42s} size {np.round(m.extents, 1)} mm  watertight={m.is_watertight}  vol={m.volume / 1000:.1f} cm3')


pot = to_mf(trimesh.load(os.path.join(W, 'planter/9_Top__Top.stl'), process=True))
rail = pot ^ box(RAIL['x0'], RAIL['x1'], RAIL['y0'], RAIL['y1'], RAIL['z0'], RAIL['z1'])

big = pot.scale([S, S, S])
c = AXIS_Z * S
# block that holds the oversized rail and the wall behind it (its bottom is inside the cavity)
y0, y1 = -34 * S - 4, 21 * S + 4
B = box(-BLOCK_HALF * S, BLOCK_HALF * S, y0, y1, 40 * S, 200)
B_fill = box(-BLOCK_HALF * S - 0.3, BLOCK_HALF * S + 0.3, y0 - 0.3, y1 + 0.3, 40 * S, 200)
# the same pot turned 180 deg about its axis: its plain front now sits where the rail was
turned = big.translate([0, 0, -c]).rotate([0, 180, 0]).translate([0, 0, c])
big = (big - B) + (turned ^ B_fill)

# seat the 100% rail: rail top = (highest pot surface under the hanger wings) + original clearance
tm = to_tm(big)
v = tm.vertices
dy = (-33 + 20) / 2 * S - (-33 + 20) / 2                     # keep the rail where the scaled one was
band = (v[:, 1] > -33 + dy - 10) & (v[:, 1] < 20 + dy + 10) & (np.abs(v[:, 0]) > 11.5) & (np.abs(v[:, 0]) < 16)
wings = v[band][:, 2].max()
dz = wings + CLEAR - RAIL_TOP
rail = rail.translate([0, dy, dz])
# solid column under the rail's base block, down into the pot wall, with the base block's own
# rounded outline so nothing shows between the ribs
z_top = RAIL['z0'] + dz + 0.3
z_bot = INNER_TOP * S + 0.5
column = mf.Manifold.extrude(rail.slice(z_top), z_top - z_bot).translate([0, 0, z_bot])
pot_s = big + rail + column
print(f'scale {S}: wings at z={wings:.2f}, rail top at z={RAIL_TOP + dz:.2f} (clearance {CLEAR} mm as original)')

save(to_tm(pot_s), f'Brynhild_pot_{PCT}pct_LODRET-rail.stl', plate_rotation(9))
tray = trimesh.load(os.path.join(W, 'planter/14_Bottom__Bottom.stl'), process=True); tray.apply_scale(S)
save(tray, f'Brynhild_drip-tray_{PCT}pct.stl', plate_rotation(14))
foot = trimesh.load(os.path.join(W, 'planter/2_foot__foot.stl'), process=True); foot.apply_scale(S)
save(foot, f'Brynhild_wick-foot_{PCT}pct_print-3.stl', plate_rotation(2))
