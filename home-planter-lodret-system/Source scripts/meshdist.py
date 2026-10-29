"""Exact point-to-mesh distance (no rtree needed): KD-tree on triangle centres picks candidates,
then the true point-triangle distance is computed for each candidate."""
import numpy as np
from scipy.spatial import cKDTree


def _point_triangle_dist(p, a, b, c):
    """Vectorised distance from points p (n,3) to triangles (a,b,c) (n,3) each. Ericson, RTCD 5.1.5."""
    ab, ac, ap = b - a, c - a, p - a
    d1, d2 = (ab * ap).sum(1), (ac * ap).sum(1)
    bp = p - b; d3, d4 = (ab * bp).sum(1), (ac * bp).sum(1)
    cp = p - c; d5, d6 = (ab * cp).sum(1), (ac * cp).sum(1)
    va, vb, vc = d3 * d6 - d5 * d4, d5 * d2 - d1 * d6, d1 * d4 - d3 * d2
    denom = va + vb + vc
    denom[denom == 0] = 1e-30
    v, w = vb / denom, vc / denom
    q = a + ab * v[:, None] + ac * w[:, None]                         # interior
    m = (d1 <= 0) & (d2 <= 0); q[m] = a[m]                             # vertex A
    m = (d3 >= 0) & (d4 <= d3); q[m] = b[m]                            # vertex B
    m = (d6 >= 0) & (d5 <= d6); q[m] = c[m]                            # vertex C
    m = (vc <= 0) & (d1 >= 0) & (d3 <= 0)                              # edge AB
    t = d1 / np.where(d1 - d3 == 0, 1e-30, d1 - d3); q[m] = (a + ab * t[:, None])[m]
    m = (vb <= 0) & (d2 >= 0) & (d6 <= 0)                              # edge AC
    t = d2 / np.where(d2 - d6 == 0, 1e-30, d2 - d6); q[m] = (a + ac * t[:, None])[m]
    m = (va <= 0) & ((d4 - d3) >= 0) & ((d5 - d6) >= 0)                # edge BC
    t = (d4 - d3) / np.where((d4 - d3) + (d5 - d6) == 0, 1e-30, (d4 - d3) + (d5 - d6)); q[m] = (b + (c - b) * t[:, None])[m]
    return np.linalg.norm(p - q, axis=1)


def distance_to_mesh(mesh, pts, k=64, max_edge=0.3):
    """Large triangles are split first (same surface, smaller pieces) so the centre-based
    candidate search can't miss them."""
    import trimesh
    V, F = trimesh.remesh.subdivide_to_size(mesh.vertices, mesh.faces, max_edge=max_edge, max_iter=20)
    tri = V[F]
    tree = cKDTree(tri.mean(1))
    _, idx = tree.query(pts, k=k)
    best = np.full(len(pts), np.inf)
    for j in range(k):
        t = tri[idx[:, j]]
        best = np.minimum(best, _point_triangle_dist(pts, t[:, 0], t[:, 1], t[:, 2]))
    return best
