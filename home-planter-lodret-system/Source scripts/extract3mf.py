"""Extract every named object of a Bambu 3MF to STL (object-local coords) and print a summary.

usage: python -I extract3mf.py <file.3mf> <outdir>
Parts are written as <object name>__<part name>.stl; the transform of each
part inside its object is applied, the build-plate placement is not.
"""
import os, re, sys, zipfile
import numpy as np
import trimesh

src, out = sys.argv[1], sys.argv[2]
os.makedirs(out, exist_ok=True)
z = zipfile.ZipFile(src)
top = z.read('3D/3dmodel.model').decode('utf8')
ms = z.read('Metadata/model_settings.config').decode('utf8')

VERT = re.compile(rb'<vertex x="([^"]+)" y="([^"]+)" z="([^"]+)"')
TRI = re.compile(rb'<triangle v1="(\d+)" v2="(\d+)" v3="(\d+)"')
OBJ = re.compile(rb'<object id="(\d+)"')


def read_meshes(path):
    """Return {object id: (V, F)} for one object .model file, streaming."""
    meshes, cur, vs, fs, tail = {}, None, [], [], b''
    with z.open(path.lstrip('/')) as f:
        while True:
            chunk = f.read(1 << 24)
            if not chunk and not tail:
                break
            buf = tail + chunk
            cut = buf.rfind(b'>') + 1 if chunk else len(buf)
            tail, buf = buf[cut:], buf[:cut]
            pos = 0
            for m in re.finditer(rb'<object id="(\d+)"|</mesh>', buf):
                seg = buf[pos:m.start()]
                if cur is not None:
                    vs.extend(VERT.findall(seg)); fs.extend(TRI.findall(seg))
                if m.group(1):
                    cur, vs, fs = m.group(1).decode(), [], []
                else:
                    meshes[cur] = (np.array(vs, dtype=np.float64), np.array(fs, dtype=np.int64)); cur = None
                pos = m.end()
            if cur is not None:
                seg = buf[pos:]
                vs.extend(VERT.findall(seg)); fs.extend(TRI.findall(seg))
            if not chunk:
                break
    return meshes


def tf(s):
    a = list(map(float, s.split()))
    M = np.eye(4)
    M[:3, :3] = np.array(a[:9]).reshape(3, 3).T  # 3MF: row-vector convention
    M[:3, 3] = a[9:]
    return M


names = {}
for m in re.finditer(r'<object id="(\d+)">([\s\S]*?)</object>', ms):
    oname = re.search(r'key="name" value="([^"]*)"', m.group(2)).group(1)
    parts = {p.group(1): p.group(2) for p in re.finditer(r'<part id="(\d+)"[^>]*>[\s\S]*?key="name" value="([^"]*)"', m.group(2))}
    names[m.group(1)] = (oname, parts)

cache = {}
for m in re.finditer(r'<object id="(\d+)"[^>]*>([\s\S]*?)</object>', top):
    oid = m.group(1)
    if oid not in names:
        continue
    oname, parts = names[oid]
    for c in re.finditer(r'p:path="([^"]+)" objectid="(\d+)"[^>]*transform="([^"]+)"', m.group(2)):
        path, pid, t = c.groups()
        if path not in cache:
            cache[path] = read_meshes(path)
        V, F = cache[path][pid]
        mesh = trimesh.Trimesh(V, F, process=False)
        mesh.apply_transform(tf(t))
        pname = parts.get(pid, pid)
        fn = f'{oid}_{oname}__{pname}'.replace('.stl', '') + '.stl'
        fn = re.sub(r'[^\w.\-]+', '_', fn)
        mesh.export(os.path.join(out, fn))
        print(f'{fn:60s} tris={len(F):8d} size={np.round(mesh.extents, 2)} min={np.round(mesh.bounds[0], 2)}')
