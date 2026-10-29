"""Shrink oversized meshes (STL / 3MF) in place, keeping them watertight and accurate.

usage: python shrink.py [--tol 0.05] [--workers 6] <file.3mf|file.stl> ...
Uses manifold3d's simplify(tol): it only removes vertices whose removal keeps the surface
within `tol` mm and never breaks the mesh's closed, manifold topology. Every result is checked:
  - watertight
  - exact surface deviation from the original (sampled, 99.9th percentile) <= 1.5 * tol
If a check fails, the original mesh is kept. 3MFs keep object names, order and layout.
"""
import os, sys
from concurrent.futures import ProcessPoolExecutor, as_completed
import numpy as np
import trimesh
import manifold3d as mf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from meshio3mf import read_3mf, write_3mf
from meshdist import distance_to_mesh


MIN_DENSITY = 10.0   # triangles per mm^2; below this a mesh is already simplified and is left alone
ACCEPT = float(os.environ.get('SHRINK_ACCEPT', '0.075'))   # max 99.9th-percentile deviation (mm); set by --accept


def simplify(m, tol):
    if len(m.faces) / max(m.area, 1e-9) < MIN_DENSITY:
        return m, 0.0, True
    M = mf.Manifold(mf.Mesh(vert_properties=np.asarray(m.vertices, np.float32), tri_verts=np.asarray(m.faces, np.uint32)))
    g = M.simplify(tol).to_mesh()
    s = trimesh.Trimesh(np.asarray(g.vert_properties)[:, :3], np.asarray(g.tri_verts), process=False)
    pts = trimesh.sample.sample_surface(s, 30000, seed=1)[0]
    p999 = float(np.percentile(distance_to_mesh(m, pts), 99.9))
    ok = s.is_watertight and p999 <= ACCEPT and len(s.faces) < len(m.faces)
    return (s if ok else m), p999, ok


def process(path, tol):
    before = os.path.getsize(path)
    notes = []
    if path.lower().endswith('.3mf'):
        objs, items = read_3mf(path)
        cache, out = {}, []
        for oid, name, m in objs:
            key = (len(m.faces), round(float(m.area), 2))       # identical copies (wick feet, knobs) once
            if key not in cache:
                cache[key] = simplify(m, tol)
            s, dev, ok = cache[key]
            out.append((oid, name, s))
            notes.append(f'{name.rsplit("_", 1)[-1] if not name[-1].isdigit() else name.rsplit("_", 2)[-2]} '
                         f'{len(m.faces) // 1000}k->{len(s.faces) // 1000}k dev {dev:.3f} {"ok" if ok else "KEPT"}')
        write_3mf(path, out, items)
    else:
        m = trimesh.load(path, process=True)
        s, dev, ok = simplify(m, tol)
        notes.append(f'{len(m.faces) // 1000}k->{len(s.faces) // 1000}k dev {dev:.3f} {"ok" if ok else "KEPT"}')
        if ok:
            s.export(path)
    after = os.path.getsize(path)
    return f'{os.path.relpath(path)}: {before / 1e6:.1f} -> {after / 1e6:.1f} MB | ' + '; '.join(dict.fromkeys(notes)), before, after


if __name__ == '__main__':
    args = sys.argv[1:]
    tol = float(args[args.index('--tol') + 1]) if '--tol' in args else 0.05
    workers = int(args[args.index('--workers') + 1]) if '--workers' in args else 6
    ACCEPT = float(args[args.index('--accept') + 1]) if '--accept' in args else 1.5 * tol
    os.environ['SHRINK_ACCEPT'] = str(ACCEPT)
    files = [a for i, a in enumerate(args) if not a.startswith('--') and (i == 0 or args[i - 1] not in ('--tol', '--workers', '--accept'))]
    tb = ta = 0
    with ProcessPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(process, f, tol): f for f in files}
        for fu in as_completed(futs):
            try:
                line, b, a = fu.result(); tb += b; ta += a
                print(line, flush=True)
            except Exception as e:
                print('FAILED', futs[fu], repr(e), flush=True)
    print(f'TOTAL {tb / 1e9:.2f} GB -> {ta / 1e9:.2f} GB')
