"""Pack STL parts into one plain 3MF (one object per copy, laid out in a row).

usage: python -I pack3mf.py <folder> <out.3mf> <part.stl:qty> [<part.stl:qty> ...]
"""
import os, sys, zipfile
import trimesh

D, OUT = sys.argv[1], sys.argv[2]
PARTS = [(p.rsplit(':', 1)[0], int(p.rsplit(':', 1)[1])) for p in sys.argv[3:]]

CT = ('<?xml version="1.0" encoding="UTF-8"?>\n<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
      '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
      '<Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/></Types>')
RELS = ('<?xml version="1.0" encoding="UTF-8"?>\n<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>')

out = os.path.join(D, OUT)
with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
    z.writestr('[Content_Types].xml', CT)
    z.writestr('_rels/.rels', RELS)
    with z.open('3D/3dmodel.model', 'w', force_zip64=True) as f:
        w = lambda s: f.write(s.encode())
        w('<?xml version="1.0" encoding="UTF-8"?>\n<model unit="millimeter" xml:lang="en-US" '
          'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">\n<resources>\n')
        items, oid, x = [], 1, 0.0
        for name, n in PARTS:
            m = trimesh.load(os.path.join(D, name), process=True)
            vtxt = ''.join('<vertex x="%.4f" y="%.4f" z="%.4f"/>' % tuple(v) for v in (m.vertices - m.bounds[0]))
            ttxt = ''.join('<triangle v1="%d" v2="%d" v3="%d"/>' % tuple(t) for t in m.faces)
            for i in range(n):
                label = os.path.basename(name)[:-4] + ('' if n == 1 else '_%d' % (i + 1))
                w('<object id="%d" name="%s" type="model"><mesh><vertices>' % (oid, label))
                w(vtxt); w('</vertices><triangles>'); w(ttxt); w('</triangles></mesh></object>\n')
                items.append('<item objectid="%d" transform="1 0 0 0 1 0 0 0 1 %.2f 0 0"/>' % (oid, x))
                x += m.extents[0] + 10; oid += 1
        w('</resources>\n<build>\n' + '\n'.join(items) + '\n</build>\n</model>\n')
print(out, os.path.getsize(out) // 1_000_000, 'MB')
