"""Find how the drip tray sits under the pot: centre, height, and the rotation that makes the
tray's spiral ribs continue the pot's ribs across the joint.

usage: python -I tray_alignment.py <work dir with planter/>
Prints values used by assemble.py. All in the 100% design frames (y up).
"""
import sys
import numpy as np
import trimesh
import manifold3d as mf

W = sys.argv[1]
TO_Z = [[1, 0, 0, 0], [0, 0, 1, 0], [0, -1, 0, 0], [0, 0, 0, 1]]   # design y -> -z, so slice(-y) cuts at height y


def load(p):
    m = trimesh.load(f'{W}/{p}', process=True); m.apply_transform(TO_Z)
    return mf.Manifold(mf.Mesh(vert_properties=np.asarray(m.vertices, np.float32), tri_verts=np.asarray(m.faces, np.uint32)))


def outer_profile(Mm, y, cz, nb=7200):
    """Outer radius vs angle (about x=0, z=cz) of the slice at height y; NaN where empty."""
    out = np.full(nb, np.nan)
    polys = [np.asarray(p) for p in Mm.slice(-y).to_polygons()]
    rmax = max(np.hypot(p[:, 0], p[:, 1] - cz).max() for p in polys)
    for p in polys:
        if np.hypot(p[:, 0], p[:, 1] - cz).max() < rmax - 3:   # keep only the outer skin
            continue
        q = np.vstack([np.linspace(p[i], p[(i + 1) % len(p)], 8, endpoint=False) for i in range(len(p))])
        a = np.arctan2(q[:, 1] - cz, q[:, 0]); r = np.hypot(q[:, 0], q[:, 1] - cz)
        k = ((a + np.pi) / (2 * np.pi) * nb).astype(int) % nb
        np.fmax.at(out, k, r)
    return out


def rib_count(prof):
    p = np.nan_to_num(prof - np.nanmean(prof))
    f = np.abs(np.fft.rfft(p)); f[:10] = 0
    return int(np.argmax(f[:400]))


def phase(prof, n):
    """Angle (deg) of the rib crests' n-fold pattern."""
    th = np.linspace(-np.pi, np.pi, len(prof), endpoint=False)
    ok = ~np.isnan(prof)
    p = prof[ok] - prof[ok].mean()
    z = np.sum(p * np.exp(-1j * n * th[ok]))
    return np.degrees(np.angle(z)) / n   # crest at this angle (mod 360/n)


pot, tray = load('planter/9_Top__Top.stl'), load('planter/14_Bottom__Bottom.stl')
POT_CZ, TRAY_CZ = -3.23, 0.0

n_pot = rib_count(outer_profile(pot, -30, POT_CZ))
n_tray = rib_count(outer_profile(tray, 3, TRAY_CZ))
print('rib count  pot', n_pot, ' tray', n_tray)
n = n_pot
per = 360 / n


def fit_phase(Mm, ys, cz, name):
    ys = np.asarray(ys, float)
    amp, ph = [], []
    for y in ys:
        pr = outer_profile(Mm, y, cz)
        amp.append(np.nanmax(pr) - np.nanmin(pr)); ph.append(phase(pr, n))
    ph = np.degrees(np.unwrap(np.radians(np.array(ph)) * n)) / n   # unwrap in units of the rib period
    c = np.polyfit(ys, ph, 2)
    print(f'{name}: y {ys[0]:.1f}..{ys[-1]:.1f}  rib depth {min(amp):.2f}..{max(amp):.2f} mm  '
          f'twist {np.polyval(np.polyder(c), ys[-1] if name == "tray" else ys[0]):.4f} deg/mm  '
          f'fit residual {np.ptp(ph - np.polyval(c, ys)):.3f} deg')
    return c


POT_BOTTOM, TRAY_SHOULDER = -46.5, 10.15     # joint plane in each part's frame
cp = fit_phase(pot, np.arange(-45.0, -37.9, 0.5), POT_CZ, 'pot')
ct = fit_phase(tray, np.arange(3.0, 9.85, 0.5), TRAY_CZ, 'tray')
phi_pot = np.polyval(cp, POT_BOTTOM)
phi_tray = np.polyval(ct, TRAY_SHOULDER)
rot = (phi_pot - phi_tray) % per
print(f'TRAY_ROT_DEG = {rot:.3f}   (rib period {per:.3f} deg; any multiple of it works too)')
print(f'TRAY_DY = {POT_BOTTOM - TRAY_SHOULDER:.2f}   TRAY_CENTRE_Z = {POT_CZ}')
