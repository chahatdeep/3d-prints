"""Compare the rail joint of rebuilt pots with the original Brynhild pot.

usage: python -I check_joint.py <work dir with planter/ and in/> <plot.png> <pot.stl> [<pot.stl> ...]
Reports, relative to the rail top: rail head length, pot surface under the hanger wings,
the base-block shoulder (where the hanger face rests), and whether anything pokes into the pot cavity.
"""
import re, sys, zipfile
import numpy as np
import trimesh
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

W, PNG, pots = sys.argv[1], sys.argv[2], sys.argv[3:]
t = re.search(r'<item objectid="9"[^>]*transform="([^"]+)"',
              zipfile.ZipFile(f'{W}/in/Brynhild_hanging_planter.3mf').read('3D/3dmodel.model').decode()).group(1)
a = list(map(float, t.split())); R = np.eye(4); R[:3, :3] = np.array(a[:9]).reshape(3, 3).T
orig = trimesh.load(f'{W}/planter/9_Top__Top.stl', process=False)


def design(path):
    m = trimesh.load(path, process=False)
    m.apply_transform(np.linalg.inv(R))
    # x/y and front (min z) are unchanged by the rail work, so align on the scaled original's min corner
    S = (m.bounds[1][0] - m.bounds[0][0]) / (orig.bounds[1][0] - orig.bounds[0][0])
    m.apply_translation(orig.bounds[0] * S - m.bounds[0])
    return m, S


def stats(m):
    v = m.vertices
    zt = v[np.abs(v[:, 0]) < 6][:, 2].max()
    hy = v[(np.abs(v[:, 0]) < 6) & (v[:, 2] > zt - 1)][:, 1]
    band = (v[:, 1] > hy.min() - 10) & (v[:, 1] < hy.max() + 10)
    wings = v[band & (np.abs(v[:, 0]) > 11.5) & (np.abs(v[:, 0]) < 16)][:, 2].max()
    shoulder = v[band & (np.abs(v[:, 0]) > 7.5) & (np.abs(v[:, 0]) < 9.5)][:, 2].max()
    return zt, hy, wings, shoulder


rows = [('original', 1.0) + stats(orig)]
fig, ax = plt.subplots(1, len(pots), figsize=(7 * len(pots), 5))
ax = np.atleast_1d(ax)
for i, p in enumerate(pots):
    m, S = design(p)
    zt, hy, wings, shoulder = stats(m)
    rows.append((p.split('/')[-1], S, zt, hy, wings, shoulder))
    # inner cavity at the back centre must match the plain scaled pot (nothing grafted pokes inside)
    inner = m.section(plane_origin=(0, hy.mean(), 0), plane_normal=(0, 1, 0))
    for mm, c, ztt in ((orig, 'b', rows[0][2]), (m, 'r', zt)):
        s = mm.section(plane_origin=(0, (hy.mean() if mm is m else rows[0][3].mean()), 0), plane_normal=(0, 1, 0))
        for e in s.entities:
            q = s.vertices[e.points]; ax[i].plot(q[:, 0], q[:, 2] - ztt, c + '-', lw=0.8)
    ax[i].set_xlim(-28, 28); ax[i].set_ylim(-16, 2); ax[i].set_aspect('equal'); ax[i].grid(alpha=.3)
    ax[i].set_title(f'{p.split("/")[-1]}\nred = rebuilt, blue = original (aligned at rail top)', fontsize=8)
plt.tight_layout(); plt.savefig(PNG, dpi=80)

print(f'{"part":42s} scale  head-len  wings-below-top  shoulder-below-top')
for name, S, zt, hy, wings, shoulder in rows:
    print(f'{name:42s} {S:5.2f}  {np.ptp(hy):7.2f}  {zt - wings:14.2f}  {zt - shoulder:17.2f}')
