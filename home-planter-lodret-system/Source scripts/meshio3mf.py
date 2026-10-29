"""Fast reader/writer for the plain core-spec 3MFs these scripts produce (one mesh per object)."""
import io, os, re, zipfile
import numpy as np
import trimesh

_NUM = re.compile(r'"(-?[\d.]+(?:[eE][-+]?\d+)?)"')


def read_3mf(path):
    """Return ([(id, name, trimesh)], {id: transform string})."""
    xml = zipfile.ZipFile(path).read('3D/3dmodel.model').decode()
    objs = []
    for m in re.finditer(r'<object id="(\d+)" name="([^"]*)"[^>]*><mesh><vertices>(.*?)</vertices><triangles>(.*?)</triangles>', xml, re.S):
        V = np.array(_NUM.findall(m.group(3)), float).reshape(-1, 3)
        F = np.array(_NUM.findall(m.group(4)), np.int64).reshape(-1, 3)
        objs.append((m.group(1), m.group(2), trimesh.Trimesh(V, F, process=False)))
    items = dict(re.findall(r'<item objectid="(\d+)" transform="([^"]+)"', xml))
    return objs, items


def write_3mf(path, objs, items=None):
    """objs: [(id, name, trimesh)]. Writes atomically."""
    items = items or {}
    tmp = path + '.tmp'
    with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        z.writestr('[Content_Types].xml', '<?xml version="1.0" encoding="UTF-8"?>\n<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/></Types>')
        z.writestr('_rels/.rels', '<?xml version="1.0" encoding="UTF-8"?>\n<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>')
        with z.open('3D/3dmodel.model', 'w', force_zip64=True) as f:
            f.write(b'<?xml version="1.0" encoding="UTF-8"?>\n<model unit="millimeter" xml:lang="en-US" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">\n<resources>\n')
            for oid, name, m in objs:
                f.write(f'<object id="{oid}" name="{name}" type="model"><mesh><vertices>\n'.encode())
                b = io.StringIO(); np.savetxt(b, m.vertices, fmt='<vertex x="%.3f" y="%.3f" z="%.3f"/>'); f.write(b.getvalue().encode())
                f.write(b'</vertices><triangles>\n')
                b = io.StringIO(); np.savetxt(b, m.faces, fmt='<triangle v1="%d" v2="%d" v3="%d"/>'); f.write(b.getvalue().encode())
                f.write(b'</triangles></mesh></object>\n')
            f.write(b'</resources>\n<build>\n')
            for oid, _, _ in objs:
                f.write(f'<item objectid="{oid}" transform="{items.get(oid, "1 0 0 0 1 0 0 0 1 0 0 0")}"/>\n'.encode())
            f.write(b'</build>\n</model>\n')
    os.replace(tmp, path)
