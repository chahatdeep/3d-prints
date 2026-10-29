"""Check every print file: all parts watertight; every pot's LODRET rail joint matches the original.

usage: python verify_all.py <project folder>
Needs 'Original downloads/Brynhild_hanging_planter.3mf' (for the pot's print orientation).
Joint numbers, from the rail top: rail head length 46.19, shoulder 4.00, wing clearance 7.85 mm.
"""
import glob, os, re, sys, zipfile
import numpy as np
import trimesh

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from meshio3mf import read_3mf

ROOT = sys.argv[1]
top = zipfile.ZipFile(os.path.join(ROOT, 'Original downloads', 'Brynhild_hanging_planter.3mf')).read('3D/3dmodel.model').decode()
a = list(map(float, re.search(r'<item objectid="9"[^>]*transform="([^"]+)"', top).group(1).split()))
R = np.eye(4); R[:3, :3] = np.array(a[:9]).reshape(3, 3).T
RINV = np.linalg.inv(R)


def joint(pot):
    m = pot.copy(); m.apply_transform(RINV)            # back to design axes: y up, rail toward +z
    v = m.vertices
    zt = v[:, 2].max()
    top = v[v[:, 2] > zt - 0.5][:, 0]
    cx = (top.min() + top.max()) / 2          # midpoint of the rail head (robust to uneven vertex spacing)
    x = v[:, 0] - cx
    head = v[(np.abs(x) < 6) & (v[:, 2] > zt - 1)]
    band = (v[:, 1] > head[:, 1].min() - 10) & (v[:, 1] < head[:, 1].max() + 10)
    wings = v[band & (np.abs(x) > 11.5) & (np.abs(x) < 16)][:, 2].max()
    shoulder = v[band & (np.abs(x) > 7.5) & (np.abs(x) < 9.5)][:, 2].max()
    return np.ptp(head[:, 1]), zt - shoulder, zt - wings


bad = 0
rows = []
files = sorted(glob.glob(os.path.join(ROOT, '**', '*.3mf'), recursive=True) + glob.glob(os.path.join(ROOT, '**', '*.stl'), recursive=True))
for f in files:
    if 'Original downloads' in f:
        continue
    if f.endswith('.3mf'):
        parts = [(n, m) for _, n, m in read_3mf(f)[0]]
    else:
        parts = [(os.path.basename(f), trimesh.load(f, process=True))]
    wt = all(m.is_watertight for _, m in parts)
    tris = sum(len(m.faces) for _, m in parts)
    j = ''
    for n, m in parts:
        if 'pot' in n.lower() and 'LODRET-rail' in n or n.endswith('_pot'):
            h, s, w = joint(m)
            okj = abs(h - 46.19) < 0.15 and abs(s - 4.00) < 0.12 and abs(w - 7.85) < 0.15
            j = f'rail head {h:.2f} shoulder {s:.2f} wings {w:.2f} {"OK" if okj else "OFF"}'
            bad += not okj
    bad += not wt
    rows.append(f'{os.path.relpath(f, ROOT):62s} {os.path.getsize(f) / 1e6:6.1f} MB {tris // 1000:5d}k tris  watertight={wt}  {j}')
print('\n'.join(rows))
print(f'\n{len(rows)} files checked, {bad} problems')
