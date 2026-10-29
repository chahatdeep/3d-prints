"""Build print-ready sets (pot with 100% LODRET rail + drip tray + 3 wick feet) for any design and size.

usage: python -I build_sizes.py <work dir> <designs dir> <out root> <sizes, e.g. 100,105,120,140,155> <design ...>
  <work dir>    planter/ (extract3mf.py output) and in/Brynhild_hanging_planter.3mf
  <designs dir> <name>_pot.stl / <name>_tray.stl from boho_designs.py; design 'original' = the stock spiral
Writes <out root>/<NN-name>/<name>_<pct>pct.3mf, one per size, laid out ready to arrange.

Rail: the scaled pot keeps no rail of its own. For textured designs the skin already covers the back;
for 'original' the oversized rail is cut out and refilled from the pot turned 180 deg (the spiral repeats
every 20 deg). Then the original 100% rail is added on a column shaped like its base, seated so that
rail top = highest pot surface under the hanger wings + 7.85 mm, exactly as on the original design.
"""
import io, os, re, sys, zipfile
from concurrent.futures import ProcessPoolExecutor, as_completed
import numpy as np
import trimesh
import manifold3d as mf

AXIS_Z = -3.25
RAIL = dict(x0=-11.2, x1=11.2, y0=-34, y1=21, z0=48.5, z1=58)
RAIL_TOP, CLEAR, BLOCK_HALF, INNER_TOP = 56.77, 7.85, 14.5, 47.4
SIMPLIFY_MM = 0.05
ORDER = ['original', 'rattan', 'rope', 'reeded', 'dunes', 'mudcloth', 'berber', 'petals', 'herringbone',
         'mountains', 'arches', 'slats', 'sunburst', 'ripples', 'fern', 'triptych']


def to_mf(m):
    return mf.Manifold(mf.Mesh(vert_properties=np.asarray(m.vertices, np.float32), tri_verts=np.asarray(m.faces, np.uint32)))


def to_tm(M):
    g = M.to_mesh()
    return trimesh.Trimesh(np.asarray(g.vert_properties)[:, :3], np.asarray(g.tri_verts), process=False)


def box(x0, x1, y0, y1, z0, z1):
    return mf.Manifold.cube([x1 - x0, y1 - y0, z1 - z0]).translate([x0, y0, z0])


def plate_rotation(src, oid):
    top = zipfile.ZipFile(src).read('3D/3dmodel.model').decode()
    a = list(map(float, re.search(r'<item objectid="%s"[^>]*transform="([^"]+)"' % oid, top).group(1).split()))
    M = np.eye(4); M[:3, :3] = np.array(a[:9]).reshape(3, 3).T
    return M


def write_3mf(path, parts):
    """parts: list of (name, trimesh). Plain core-spec 3MF, objects in a row, z=0 at the bed."""
    hdr = ('<?xml version="1.0" encoding="UTF-8"?>\n<model unit="millimeter" xml:lang="en-US" '
           'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">\n<resources>\n')
    items, x = [], 0.0
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        z.writestr('[Content_Types].xml', '<?xml version="1.0" encoding="UTF-8"?>\n<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/></Types>')
        z.writestr('_rels/.rels', '<?xml version="1.0" encoding="UTF-8"?>\n<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>')
        with z.open('3D/3dmodel.model', 'w', force_zip64=True) as f:
            f.write(hdr.encode())
            for oid, (name, m) in enumerate(parts, 1):
                v = m.vertices - m.bounds[0]
                f.write(f'<object id="{oid}" name="{name}" type="model"><mesh><vertices>\n'.encode())
                b = io.StringIO(); np.savetxt(b, v, fmt='<vertex x="%.3f" y="%.3f" z="%.3f"/>'); f.write(b.getvalue().encode())
                f.write(b'</vertices><triangles>\n')
                b = io.StringIO(); np.savetxt(b, m.faces, fmt='<triangle v1="%d" v2="%d" v3="%d"/>'); f.write(b.getvalue().encode())
                f.write(b'</triangles></mesh></object>\n')
                items.append(f'<item objectid="{oid}" transform="1 0 0 0 1 0 0 0 1 {x:.2f} 0 0"/>')
                x += m.extents[0] + 10
            f.write(('</resources>\n<build>\n' + '\n'.join(items) + '\n</build>\n</model>\n').encode())


def build(task):
    W, DES, OUT, design, pct = task
    S = pct / 100
    PL = f'{W}/in/Brynhild_hanging_planter.3mf'
    orig = to_mf(trimesh.load(f'{W}/planter/9_Top__Top.stl', process=True))
    rail = orig ^ box(RAIL['x0'], RAIL['x1'], RAIL['y0'], RAIL['y1'], RAIL['z0'], RAIL['z1'])
    if design == 'original':
        big = orig.scale([S, S, S]); c = AXIS_Z * S
        y0, y1 = -34 * S - 4, 21 * S + 4
        B = box(-BLOCK_HALF * S, BLOCK_HALF * S, y0, y1, 40 * S, 200)
        Bf = box(-BLOCK_HALF * S - 0.3, BLOCK_HALF * S + 0.3, y0 - 0.3, y1 + 0.3, 40 * S, 200)
        turned = big.translate([0, 0, -c]).rotate([0, 180, 0]).translate([0, 0, c])
        big = (big - B) + (turned ^ Bf)
        tray = trimesh.load(f'{W}/planter/14_Bottom__Bottom.stl', process=True)
    else:
        big = to_mf(trimesh.load(f'{DES}/{design}_pot.stl', process=True)).scale([S, S, S])
        tray = trimesh.load(f'{DES}/{design}_tray.stl', process=True)
    v = to_tm(big).vertices
    dy = (-33 + 20) / 2 * S - (-33 + 20) / 2
    band = (v[:, 1] > -33 + dy - 10) & (v[:, 1] < 20 + dy + 10) & (np.abs(v[:, 0]) > 11.5) & (np.abs(v[:, 0]) < 16)
    wings = v[band][:, 2].max()
    dz = wings + CLEAR - RAIL_TOP
    r = rail.translate([0, dy, dz])
    z_top, z_bot = RAIL['z0'] + dz + 0.3, INNER_TOP * S + 0.5
    column = mf.Manifold.extrude(r.slice(z_top), z_top - z_bot).translate([0, 0, z_bot])
    # simplify(0.05): drop vertices only where the surface stays within 0.05 mm (a quarter of a
    # 0.2 mm layer); keeps the mesh watertight and cuts it ~5-30x
    pot = to_tm((big + r + column).simplify(SIMPLIFY_MM))

    tray.apply_scale(S)
    tray = to_tm(to_mf(tray).simplify(SIMPLIFY_MM))
    foot = trimesh.load(f'{W}/planter/2_foot__foot.stl', process=True); foot.apply_scale(S)
    foot = to_tm(to_mf(foot).simplify(SIMPLIFY_MM))

    def lay(m, oid):
        m = m.copy(); m.apply_transform(plate_rotation(PL, oid)); m.apply_translation(-m.bounds[0]); return m

    folder = f'{OUT}/{ORDER.index(design)}-{design}'
    os.makedirs(folder, exist_ok=True)
    out = f'{folder}/{design}_{pct}pct.3mf'
    P, T, F = lay(pot, 9), lay(tray, 14), lay(foot, 2)
    write_3mf(out, [(f'{design}_{pct}pct_pot', P), (f'{design}_{pct}pct_drip-tray', T)] +
              [(f'{design}_{pct}pct_wick-foot_{i}', F) for i in (1, 2, 3)])
    # joint check in the design frame: wings and shoulder relative to the rail top
    pv = pot.vertices
    zt = pv[np.abs(pv[:, 0]) < 6][:, 2].max()
    hy = pv[(np.abs(pv[:, 0]) < 6) & (pv[:, 2] > zt - 1)][:, 1]
    bnd = (pv[:, 1] > hy.min() - 10) & (pv[:, 1] < hy.max() + 10)
    w2 = pv[bnd & (np.abs(pv[:, 0]) > 11.5) & (np.abs(pv[:, 0]) < 16)][:, 2].max()
    sh = pv[bnd & (np.abs(pv[:, 0]) > 7.5) & (np.abs(pv[:, 0]) < 9.5)][:, 2].max()
    return (f'{design:12s} {pct:3d}%  pot {np.round(P.extents, 1)}  watertight pot/tray {pot.is_watertight}/{tray.is_watertight}  '
            f'head {np.ptp(hy):.2f}  wings {zt - w2:.2f}  shoulder {zt - sh:.2f}  {os.path.getsize(out) / 1e6:.0f} MB')


if __name__ == '__main__':
    W, DES, OUT, sizes = sys.argv[1:5]
    designs = sys.argv[5:] or ORDER
    tasks = [(W, DES, OUT, d, int(p)) for d in designs for p in sizes.split(',')]
    with ProcessPoolExecutor(max_workers=int(os.environ.get('WORKERS', '6'))) as ex:
        futs = {ex.submit(build, t): t for t in tasks}
        for f in as_completed(futs):
            try:
                print(f.result(), flush=True)
            except Exception as e:
                print('FAILED', futs[f][3:], repr(e), flush=True)
