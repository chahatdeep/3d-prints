"""Separate 'pinch' vertices so meshes stay watertight after STL/3MF export and slicer vertex merging.

A simplified manifold can keep two distinct vertices at the same spot where two parts of the surface
touch. Formats and slicers that merge by position fuse them, leaving an edge shared by 4 triangles.
Each such vertex is nudged 0.003 mm along its own normal (far below print resolution).

usage: python fix_pinches.py <file.3mf|file.stl> ...
"""
import os, sys
import numpy as np
import trimesh
from scipy.spatial import cKDTree

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from meshio3mf import read_3mf, write_3mf

NUDGE = 0.003


def fix(m):
    """m: indexed mesh (process=False). Returns (mesh, number of vertices moved)."""
    V = np.asarray(m.vertices, float).copy()
    pairs = cKDTree(V).query_pairs(0.0015, output_type='ndarray')
    if len(pairs) == 0:
        return m, 0
    vn = trimesh.Trimesh(V, m.faces, process=False).vertex_normals
    idx = np.unique(pairs.ravel())
    V[idx] -= vn[idx] * NUDGE          # move inward along each copy's own normal: the copies part ways
    return trimesh.Trimesh(V, m.faces, process=False), len(idx)


def split_pinches(m):
    """m: position-merged mesh with edges used by 4 faces. Give each extra sheet at a pinch
    vertex its own copy of the vertex, then nudge copies apart. Returns (mesh, vertices split)."""
    V, F = np.asarray(m.vertices, float).copy(), np.asarray(m.faces).copy()
    es = np.sort(np.stack([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]], 1).reshape(-1, 2), 1)
    groups = trimesh.grouping.group_rows(es)
    bad_edges = {tuple(es[g[0]]) for g in groups if len(g) > 2}
    pinch_verts = sorted({v for e in bad_edges for v in e})
    vf = trimesh.Trimesh(V, F, process=False).vertex_faces
    new_rows, split = [], 0
    for v in pinch_verts:
        faces = [f for f in vf[v] if f >= 0]
        # faces around v are connected if they share an edge through v that is not a pinch edge
        parent = {f: f for f in faces}
        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]; x = parent[x]
            return x
        edge_owner = {}
        for f in faces:
            for u in F[f]:
                if u == v:
                    continue
                e = (min(u, v), max(u, v))
                if e in bad_edges:
                    continue
                if e in edge_owner:
                    parent[find(f)] = find(edge_owner[e])
                else:
                    edge_owner[e] = f
        comps = {}
        for f in faces:
            comps.setdefault(find(f), []).append(f)
        for comp in list(comps.values())[1:]:            # first fan keeps v, each other fan gets a copy
            nv = len(V) + len(new_rows)
            new_rows.append(V[v].copy())
            for f in comp:
                F[f][F[f] == v] = nv
            split += 1
    if new_rows:
        V = np.vstack([V, new_rows])
    out = trimesh.Trimesh(V, F, process=False)
    out, _ = fix(out)
    return out, split


def roundtrip_watertight(m):
    """Watertight after merging vertices by position (what STL and slicers do)?"""
    r = trimesh.Trimesh(np.round(m.vertices, 3), m.faces, process=True)
    return r.is_watertight


for path in sys.argv[1:]:
    if path.lower().endswith('.3mf'):
        objs, items = read_3mf(path)
        out, moved, ok = [], 0, True
        for oid, name, m in objs:
            s, k = fix(m); moved += k; ok &= roundtrip_watertight(s)
            out.append((oid, name, s))
        if moved:
            write_3mf(path, out, items)
    else:
        raw = trimesh.load(path, process=False)
        m = trimesh.Trimesh(raw.vertices, raw.faces, process=True)   # STL: rebuild shared vertices
        if m.is_watertight:
            moved, ok = 0, True
        else:
            m2, moved = split_pinches(m)
            tmp = path + '.tmp.stl'
            m2.export(tmp)                                   # real STL round trip (float32), then reload
            ok = trimesh.load(tmp, process=True).is_watertight
            if ok:
                os.replace(tmp, path)
            else:
                os.remove(tmp)
    print(f'{os.path.basename(path)}: moved {moved} vertices, watertight after merge: {ok}', flush=True)
