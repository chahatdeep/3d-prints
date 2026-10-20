"""Generate boho exterior designs for the Brynhild pot + drip tray (100% size, no LODRET rail yet).

usage: python -I boho_designs.py <work dir with planter/> <out dir> [design ...]

Each design keeps the original pot's inside, rim, tray groove and wick holes:
    pot  = (original pot cut down to the smooth surface under its spiral ribs) + textured skin
    tray = (original tray cut the same way) + textured skin, continuing the pot's texture
The skin is a height field f(s, h) in [0, 1] wrapped around the pot axis:
    radius = base(h) + 0.05 + depth * fade(h) * f
s = arc length around the pot (mm, at radius 50), h = height in the pot's frame (mm).
"""
import os, sys
import numpy as np
import trimesh
import manifold3d as mf
from scipy.ndimage import gaussian_filter

W, OUT = sys.argv[1], sys.argv[2]
ONLY = set(sys.argv[3:])
os.makedirs(OUT, exist_ok=True)

AXIS_Z = -3.23            # pot axis (x=0, z=-3.23) in the pot's design frame
TRAY_DY = -56.65          # tray frame -> pot frame height offset
R_REF = 50.0              # arc-length reference radius
NT = 1800                 # samples around (0.17 mm at R_REF)
DH = 0.25                 # height step (mm)
TO_Z = [[1, 0, 0, 0], [0, 0, 1, 0], [0, -1, 0, 0], [0, 0, 0, 1]]


def to_mf(m):
    return mf.Manifold(mf.Mesh(vert_properties=np.asarray(m.vertices, np.float32),
                               tri_verts=np.asarray(m.faces, np.uint32)))


def to_tm(M):
    g = M.to_mesh()
    return trimesh.Trimesh(np.asarray(g.vert_properties)[:, :3], np.asarray(g.tri_verts), process=False)


# ---------------------------------------------------------------- base surfaces
def valley_profile(mesh_tm, cz, ys):
    """Smallest outer radius (rib valleys) of each horizontal slice, about the axis (0, cz)."""
    m = mesh_tm.copy(); m.apply_transform(TO_Z)
    M = to_mf(m)
    out = []
    for y in ys:
        polys = [np.asarray(p) for p in M.slice(-y).to_polygons()]
        rr = [np.hypot(p[:, 0], p[:, 1] - cz) for p in polys]
        o = rr[int(np.argmax([r.max() for r in rr]))]
        out.append(o.min())
    return np.array(out)


pot0 = trimesh.load(f'{W}/planter/9_Top__Top.stl', process=True)
tray0 = trimesh.load(f'{W}/planter/14_Bottom__Bottom.stl', process=True)

POT_Y = np.arange(-46.45, 46.46, DH)
TRAY_Y = np.arange(-13.5, 10.12, DH)
cache = f'{OUT}/_base_profiles.npz'
if os.path.exists(cache):
    d = np.load(cache); POT_R, TRAY_R = d['pot'], d['tray']
else:
    POT_R = valley_profile(pot0, AXIS_Z, POT_Y)
    TRAY_R = valley_profile(tray0, 0.0, TRAY_Y)
    np.savez(cache, pot=POT_R, tray=TRAY_R)


def revolve(ys, rs, cz):
    """Cutting solid (axis along y through x=0, z=cz): radius rs(ys) over the textured range and
    wide open (r=150) above and below it, so the rim, snap ring and foot stay untouched."""
    pts = ([(0.0, -300.0), (150.0, -300.0), (150.0, ys[0])] + list(zip(rs, ys))
           + [(150.0, ys[-1]), (150.0, 300.0), (0.0, 300.0)])
    cs = mf.CrossSection([np.array(pts, np.float64)])
    sol = mf.Manifold.revolve(cs, 720)          # axis = z
    return sol.rotate([-90, 0, 0]).translate([0, 0, cz])   # z -> y, centre on the axis


def skin(ys, rs, cz, f, depth, fade):
    """Closed textured shell: inner radius rs-0.6, outer radius rs+0.05+depth*fade*f."""
    nh = len(ys)
    th = np.linspace(-np.pi, np.pi, NT, endpoint=False)
    ro = rs[:, None] + 0.05 + depth * fade[:, None] * f
    ri = np.repeat((rs - 0.6)[:, None], NT, 1)
    def ring(r):
        x = r * np.cos(th)[None, :]; z = cz + r * np.sin(th)[None, :]
        y = np.repeat(ys[:, None], NT, 1)
        return np.stack([x, y, z], -1).reshape(-1, 3)
    V = np.vstack([ring(ro), ring(ri)])
    off = nh * NT
    idx = lambda i, j: i * NT + (j % NT)
    F = []
    I, J = np.meshgrid(np.arange(nh - 1), np.arange(NT), indexing='ij')
    a, b, c, d = idx(I, J), idx(I, J + 1), idx(I + 1, J + 1), idx(I + 1, J)
    F.append(np.stack([a, c, b], -1).reshape(-1, 3)); F.append(np.stack([a, d, c], -1).reshape(-1, 3))       # outer
    F.append(np.stack([a, b, c], -1).reshape(-1, 3) + off); F.append(np.stack([a, c, d], -1).reshape(-1, 3) + off)  # inner
    J1 = np.arange(NT)
    for i, flip in ((0, False), (nh - 1, True)):                                                              # caps
        o0, o1, i0, i1 = idx(i, J1), idx(i, J1 + 1), idx(i, J1) + off, idx(i, J1 + 1) + off
        t1 = np.stack([o0, o1, i1], -1); t2 = np.stack([o0, i1, i0], -1)
        if flip:
            t1, t2 = t1[:, ::-1], t2[:, ::-1]
        F += [t1, t2]
    m = trimesh.Trimesh(V, np.vstack(F), process=False)
    if m.volume < 0:
        m.invert()
    return m


def fade_pot(h):          # plain band under the rim, texture down to the tray joint
    return np.clip((46.45 - h) / 4.0, 0, 1) ** 0.7


def fade_tray(y):         # plain chamfer at the tray's foot
    return np.clip((y + 13.5) / 2.5, 0, 1) ** 0.7


# ---------------------------------------------------------------- height fields (s, h in mm)
def sstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1); return t * t * (3 - 2 * t)


def rattan(s, h):          # over-under basket weave
    p = 6.0
    i, j = np.floor(h / p), np.floor(s / p)
    hp = np.sin(np.pi * np.mod(h, p) / p) ** 0.6
    vp = np.sin(np.pi * np.mod(s, p) / p) ** 0.6
    over_h = (i + j) % 2 == 0
    return np.where(over_h, 0.35 + 0.65 * hp, 0.35 + 0.65 * vp) * np.where(over_h, vp ** 0.15, hp ** 0.15)


def rope(s, h):            # stacked twisted rope rings (coiled seagrass)
    p = 7.0
    u = 2 * np.mod(h, p) / p - 1
    g = np.sqrt(np.clip(1 - u * u, 0, 1))
    twist = 0.78 + 0.22 * np.abs(np.cos(np.pi * (s / 3.2 + 2.2 * np.mod(h, p) / p)))
    return g * twist


def reeded(s, h):          # rounded vertical reeds (terracotta)
    n = 40
    pf = 2 * np.pi * R_REF / n
    return np.abs(np.cos(np.pi * s / pf)) ** 0.45


def dunes(s, h):           # wandering horizontal ripples
    th = s / R_REF
    ph = h / 5.0 + 0.55 * np.sin(3 * th) + 0.22 * np.sin(7 * th + h * 0.04)
    return (0.5 + 0.5 * np.sin(2 * np.pi * ph)) ** 1.6


def mudcloth(s, h):        # engraved bands: zig-zag, dots, dashes, crosses (bogolan)
    band = 13.0
    k = np.floor((h + 60) / band).astype(int) % 4
    lh = np.mod(h + 60, band)                 # 0..band inside a band
    g = np.zeros_like(s)
    # double separator lines
    for c in (0.9, 2.4):
        g = np.maximum(g, 1 - sstep(0.35, 0.6, np.abs(lh - c)))
    mid = lh - (band + 3.3) / 2               # centre of the band's motif area
    q = 6.0                                   # motif pitch along s
    sl = np.mod(s, q) - q / 2
    zig = (np.abs(2 * np.abs(np.mod(s / q, 1.0) - 0.5) * 7.0 - 3.5 - mid)) * 0.75
    zz = 1 - sstep(0.35, 0.65, zig)
    dots = 1 - sstep(1.0, 1.3, np.hypot(sl, mid))
    dash = (1 - sstep(0.35, 0.6, np.abs(sl))) * (1 - sstep(2.6, 3.0, np.abs(mid)))
    xx = (1 - sstep(0.3, 0.55, np.minimum(np.abs(sl - mid), np.abs(sl + mid)) / 1.414)) * (1 - sstep(2.8, 3.2, np.abs(mid)))
    motif = np.select([k == 0, k == 1, k == 2, k == 3], [zz, dots, dash, xx])
    g = np.maximum(g, motif * (lh > 3.3))
    return 1 - 0.75 * g                      # raised surface, engraved grooves


def berber(s, h):          # raised diamond lattice with centre dots
    p = 12.0
    u, v = (s + h) / p, (s - h) / p
    du, dv = np.abs(u - np.round(u)) * p / 1.414, np.abs(v - np.round(v)) * p / 1.414
    lines = 1 - sstep(0.55, 0.95, np.minimum(du, dv))
    cu, cv = np.abs(np.mod(u, 1) - 0.5) * p / 1.414, np.abs(np.mod(v, 1) - 0.5) * p / 1.414
    dot = 1 - sstep(1.0, 1.5, np.hypot(cu, cv))
    return np.maximum(lines, 0.8 * dot)


def petals(s, h):          # overlapping lotus petals, pointing up
    pw, ph = 15.0, 18.0
    best = np.zeros_like(s)
    for row_shift in (0, 1, 2):
        row = np.floor(h / (ph * 0.55)) - row_shift
        base = row * ph * 0.55
        off = np.where(row % 2 == 0, 0.0, pw / 2)
        v = (h - base) / ph                    # 0 at petal base, 1 at tip
        u = (np.mod(s + off, pw) - pw / 2) / (pw / 2)
        width = np.sin(np.pi * np.clip(v, 0, 1)) ** 0.6 * (1 - 0.35 * v)
        inside = (v > 0) & (v < 1) & (np.abs(u) < width)
        dome = np.sqrt(np.clip(1 - (u / np.maximum(width, 1e-3)) ** 2, 0, 1)) * (0.45 + 0.55 * v)
        vein = 1 - 0.25 * (1 - sstep(0.04, 0.1, np.abs(u)))
        best = np.maximum(best, np.where(inside, dome * vein, 0))
    return best


def herringbone(s, h):     # woven herringbone columns
    col = 9.0
    j = np.floor(s / col)
    d = np.where(j % 2 == 0, s + h, s - h)
    stripe = np.sin(np.pi * np.mod(d / 3.4, 1.0)) ** 0.6
    edge = np.sin(np.pi * np.mod(s, col) / col) ** 0.12
    return (0.25 + 0.75 * stripe) * edge


# ---- wall-art inspired (slatted wood panels: mountains, arches, suns, ripples, ferns) ----
CIRC = 2 * np.pi * R_REF


def band(dist, width, soft=0.25):
    """Raised line of the given width (mm) from a distance field."""
    return 1 - sstep(width / 2 - soft, width / 2 + soft, dist)


def cell(s, n):
    """Local coordinate inside one of n repeats around the pot: (offset from cell centre, cell width)."""
    w = CIRC / n
    return np.mod(s + w / 2, w) - w / 2, w


def slats_bg(s, pitch=3.6, width=1.3, level=0.35):
    return level * band(np.abs(np.mod(s, pitch) - pitch / 2), width)


def mountains(s, h):       # nested chevron peaks over vertical slats, with a sun disc
    ls, w = cell(s, 4)
    f = slats_bg(s)
    out = np.zeros_like(s)
    for cx, peak, k in ((-0.18 * w, 30.0, 1.0), (0.2 * w, 12.0, 1.0)):    # back and front mountains
        d = ls - cx
        top = peak - np.abs(d) * k                                       # 45 deg sides
        inside = h < top
        lines = band(np.abs(np.mod(top - h, 4.2) - 2.1), 1.6)            # chevrons parallel to the sides
        out = np.where(inside, np.maximum(lines, 0.15), out)
    sun = band(np.hypot(ls - 0.3 * w, h - 33.0), 13.0, 0.4)
    return np.where(out > 0, out, np.maximum(f, sun))


def arches(s, h):          # nested rainbow U-arches
    ls, w = cell(s, 6)
    hc = 8.0
    rho = np.where(h > hc, np.hypot(ls, h - hc), np.abs(ls))            # arcs on top, straight legs below
    rings = band(np.abs(np.mod(rho, 3.6) - 1.8), 1.7) * (rho < 22) * (rho > 4)
    return np.maximum(rings, slats_bg(s, 3.0, 0.9, 0.2) * (rho >= 23.5))


def wood_slats(s, h):      # flat-faced vertical slats with small chamfers
    p = 5.2
    d = np.abs(np.mod(s, p) - p / 2)
    return 1 - sstep(1.55, 2.05, d)


def sunburst(s, h):        # half suns rising from the base, with rays
    ls, w = cell(s, 5)
    hc = -40.0
    dx, dy = ls, h - hc
    rho = np.hypot(dx, dy)
    ang = np.degrees(np.arctan2(dy, dx))
    disc = band(rho, 22.0, 0.4) * (dy > -2)
    ray_d = np.abs(np.mod(ang + 7.5, 15.0) - 7.5) * np.pi / 180 * rho  # distance to nearest ray (mm)
    rays = band(ray_d, 1.6) * (rho > 14) * (rho < 0.5 * w + 22) * (dy > 0)
    rings = band(np.abs(rho - 17.0), 1.4) * (dy > 0)
    return np.maximum.reduce([disc, rays, rings])


def ripples(s, h):         # concentric arcs from alternate corners plus a big disc
    ls, w = cell(s, 5)
    a = np.hypot(ls + w / 2, h + 46.0)                                   # from bottom-left corner
    b = np.hypot(ls - w / 2, h - 46.0)                                   # from top-right corner
    ra = band(np.abs(np.mod(a, 4.0) - 2.0), 1.6) * (a < 46)
    rb = band(np.abs(np.mod(b, 4.0) - 2.0), 1.6) * (b < 46)
    disc = band(np.hypot(ls, h - 0.0), 26.0, 0.4)
    return np.where(disc > 0.5, 0.9, np.maximum(ra, rb) * 0.95)


def fern(s, h):            # fern fronds: stem with paired leaflets
    ls, w = cell(s, 6)
    stem_x = 1.8 * np.sin(h / 40.0)
    d = ls - stem_x
    v = (h + 60) / 100                                                   # 0 bottom .. 1 top
    reach = np.clip(13 * np.sin(np.pi * np.clip(v, 0, 1)) ** 0.8, 0, None)
    stem = band(np.abs(d), 1.3) * (v > 0.05) * (v < 0.97)
    lt = h - np.abs(d) * 0.75                                            # leaflets slope upward
    leaf = band(np.abs(np.mod(lt, 4.5) - 2.25), 1.8) * (np.abs(d) < reach) * (np.abs(d) > 0.6)
    return np.maximum(stem, leaf)


def triptych(s, h):        # three panels around the pot: mountains | arches | sunburst, framed
    th = np.mod(s / CIRC, 1.0)
    k = np.floor(th * 3).astype(int)
    f = np.select([k == 0, k == 1, k == 2], [mountains(s, h), arches(s, h), sunburst(s, h)])
    edge = np.abs(np.mod(th * 3 + 0.5, 1.0) - 0.5) * CIRC / 3            # distance to a panel border (mm)
    frame = band(edge, 3.0)
    return np.maximum(f * (edge > 2.5), frame)


DESIGNS = {  # name: (height field, depth mm, blur sigma mm)
    'mountains': (mountains, 1.5, 0.2), 'arches': (arches, 1.5, 0.2), 'slats': (wood_slats, 1.6, 0.15),
    'sunburst': (sunburst, 1.5, 0.2), 'ripples': (ripples, 1.4, 0.2), 'fern': (fern, 1.4, 0.2),
    'triptych': (triptych, 1.5, 0.2),
    'rattan': (rattan, 1.5, 0.35), 'rope': (rope, 1.6, 0.25), 'reeded': (reeded, 1.5, 0.2),
    'dunes': (dunes, 1.4, 0.25), 'mudcloth': (mudcloth, 1.2, 0.18), 'berber': (berber, 1.3, 0.2),
    'petals': (petals, 1.6, 0.35), 'herringbone': (herringbone, 1.4, 0.3),
}

# ---------------------------------------------------------------- cores (computed once)
core_cache = {}


def cores():
    if not core_cache:
        pot_core = to_mf(pot0) ^ revolve(POT_Y, POT_R, AXIS_Z)
        tray_core = to_mf(tray0) ^ revolve(TRAY_Y, TRAY_R, 0.0)
        core_cache.update(pot=pot_core, tray=tray_core)
    return core_cache['pot'], core_cache['tray']


s_grid = (np.linspace(-np.pi, np.pi, NT, endpoint=False) * R_REF)[None, :]
for name, (fn, depth, blur) in DESIGNS.items():
    if ONLY and name not in ONLY:
        continue
    pot_core, tray_core = cores()
    for part, ys, rs, cz, hoff, fade in (('pot', POT_Y, POT_R, AXIS_Z, 0.0, fade_pot(POT_Y)),
                                         ('tray', TRAY_Y, TRAY_R, 0.0, TRAY_DY, fade_tray(TRAY_Y))):
        f = fn(np.repeat(s_grid, len(ys), 0), np.repeat((ys + hoff)[:, None], NT, 1)).astype(float)
        f = gaussian_filter(f, sigma=(blur / DH, blur / (2 * np.pi * R_REF / NT)), mode=('nearest', 'wrap'))
        shell = to_mf(skin(ys, rs, cz, f, depth, fade))
        solid = (pot_core if part == 'pot' else tray_core) + shell
        tm = to_tm(solid)
        tm.export(f'{OUT}/{name}_{part}.stl')
        print(f'{name:12s} {part:4s} tris={len(tm.faces):8d} watertight={tm.is_watertight} size={np.round(tm.extents, 1)}')
