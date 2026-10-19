"""Finds holes and see-through spots in a car-root-space OBJ the way the game draws it.

Usage: python3 tools/check_holes.py <obj> [<obj> ...] [--box x0,x1,y0,y1,z0,z1] [--pixel 0.005]
       [--close 0.02] [--min-area 2.0] [--fail-culled 25] [--fail-gap 20] [--min-loop 0.05]
       [--marks <out.obj>] [--quiet]

The game draws every face single-sided and culls back faces. OBJ files here are right-handed with
x negated, so a face's front is the side its counter-clockwise winding points to. Two checks:

1. Topology. Vertices within 0.1 mm are welded; edges used by one face are chained into open
   boundary loops (listed when longer than --min-loop metres, with bounding box and region), and
   edges used by three or more faces are counted as non-manifold. Open edges are not defects by
   themselves: separate surface patches meet along them. They locate where a gap can open.
2. Visibility. From 49 directions (the upper hemisphere in 25-degree steps of elevation, 30 of
   azimuth, plus straight down onto the roof) the mesh is rasterised orthographically into
   --pixel metre cells, once with every face and once with front faces only. A cell is flagged:
   - culled: some face covers it but the nearest face seen from there is a back face with no front
     face within 2 mm of it, so the game shows what lies behind it, or the background (a hole in
     game, geometry there in an editor; back-to-back double-sided pairs pass);
   - gap: no face covers it, but faces cover every side of it within --close metres (a small
     enclosed hole between surfaces that meet badly).
   Flagged cells are grouped per direction into clusters; a cluster is reported when its area is
   at least --min-area cm2. Culled cells are attributed to the nearest face, and faces within
   0.15 m form a patch whose area is the most of it one view sees; gaps go to the 3D point between
   the faces round them, so a gap seen from several directions merges by location.

--box limits the report to open loops, flagged faces and gaps inside it (OBJ convention: +x is the
truck's left, y up, z forward), e.g. the cab; the whole mesh still occludes, so a box never opens
new sight lines. --marks writes an OBJ with every face, flagged faces and gap
markers vertex-coloured, for tools/render_holes.py.

Exit status: 1 if any culled patch reaches --fail-culled cm2 or any gap --fail-gap cm2, else 0.
Calibration (2026-10-18, LOD0): the Megatherium body, stock-derived, peaks at 12 cm2 culled and
16 cm2 gap and passes; the Mastodon fails on real single-sided plates under its bed.
"""
import argparse, collections, math, sys

import numpy as np

import meshlib

WELD = 1e-4


def load(path):
    obj = meshlib.Obj.read(path)
    v = np.array(obj.v, float)
    tris, owner = [], []
    for n, f in enumerate(obj.faces):
        idx = [c[0] for c in f]
        for k in range(1, len(idx) - 1):
            tris.append((idx[0], idx[k], idx[k + 1]))
            owner.append(n)
    return obj, v, np.array(tris, int), np.array(owner, int)


def inside(points, box):
    return np.all((points >= box[:, 0]) & (points <= box[:, 1]), axis=-1)


def region(lo, hi, top):
    """A rough name for where a box sits on a truck (OBJ space)."""
    mid = (lo + hi) / 2
    if lo[1] > top - 0.12:
        return "roof"
    side = "left" if mid[0] > 0.3 else "right" if mid[0] < -0.3 else "centre"
    if mid[1] > 1.6:
        part = "greenhouse"
    elif mid[1] > 1.15:
        part = "body"
    else:
        part = "lower"
    return f"{part} {side}"


def topology(v, tris, min_loop):
    key = np.round(v / WELD).astype(np.int64)
    _, weld = np.unique(key, axis=0, return_inverse=True)
    weld = weld.ravel()
    t = weld[tris]
    edges = collections.Counter()
    for a, b, c in t:
        for e in ((a, b), (b, c), (c, a)):
            if e[0] != e[1]:
                edges[(min(e), max(e))] += 1
    open_edges = [e for e, n in edges.items() if n == 1]
    nonmanifold = sum(1 for n in edges.values() if n >= 3)
    rep = np.zeros(weld.max() + 1, int)
    rep[weld] = np.arange(len(weld))
    adj = collections.defaultdict(list)
    for a, b in open_edges:
        adj[a].append(b)
        adj[b].append(a)
    seen, loops = set(), []
    for start in adj:
        if start in seen:
            continue
        stack, comp = [start], []
        seen.add(start)
        while stack:
            p = stack.pop()
            comp.append(p)
            for q in adj[p]:
                if q not in seen:
                    seen.add(q)
                    stack.append(q)
        pts = v[rep[comp]]
        comp_set = set(comp)
        length = sum(np.linalg.norm(v[rep[a]] - v[rep[b]]) for a, b in open_edges if a in comp_set)
        loops.append((length, pts.min(axis=0), pts.max(axis=0)))
    loops.sort(key=lambda l: -l[0])
    return len(open_edges), nonmanifold, [l for l in loops if l[0] >= min_loop]


VIEW_NAMES = ["top"] + [f"e{e}a{a}" for e in (0, 25, 50, 75) for a in range(0, 360, 30)]


def directions():
    """View directions; VIEW_NAMES labels them (elevation, azimuth from the front, +a toward the left)."""
    dirs = [np.array([0.0, -1.0, 0.0])]
    for elev in (0, 25, 50, 75):
        for az in range(0, 360, 30):
            e, a = math.radians(elev), math.radians(az)
            # Looking from a camera at (cos e sin a, sin e, cos e cos a) toward the origin.
            dirs.append(-np.array([math.cos(e) * math.sin(a), math.sin(e), math.cos(e) * math.cos(a)]))
    return dirs


def basis(d):
    up = np.array([0.0, 1.0, 0.0]) if abs(d[1]) < 0.9 else np.array([0.0, 0.0, 1.0])
    u = np.cross(up, d)
    u /= np.linalg.norm(u)
    return u, np.cross(d, u)


def rasterise(p2, depth, tris, front, pixel):
    """Nearest-face index per cell, all faces and front faces only (-1: none)."""
    lo = p2.min(axis=0) - 2 * pixel
    size = np.ceil((p2.max(axis=0) + 2 * pixel - lo) / pixel).astype(int) + 1
    zall = np.full((size[1], size[0]), np.inf)
    zfront = np.full((size[1], size[0]), np.inf)
    iall = np.full((size[1], size[0]), -1)
    ifront = np.full((size[1], size[0]), -1)
    q = (p2 - lo) / pixel
    for n, (a, b, c) in enumerate(tris):
        pa, pb, pc = q[a], q[b], q[c]
        x0, y0 = np.floor(np.minimum(np.minimum(pa, pb), pc)).astype(int)
        x1, y1 = np.ceil(np.maximum(np.maximum(pa, pb), pc)).astype(int)
        area = (pb[0] - pa[0]) * (pc[1] - pa[1]) - (pc[0] - pa[0]) * (pb[1] - pa[1])
        if abs(area) < 1e-12:
            continue
        xs, ys = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
        w0 = ((pb[0] - xs) * (pc[1] - ys) - (pc[0] - xs) * (pb[1] - ys)) / area
        w1 = ((pc[0] - xs) * (pa[1] - ys) - (pa[0] - xs) * (pc[1] - ys)) / area
        w2 = 1 - w0 - w1
        eps = -1e-6
        inside = (w0 >= eps) & (w1 >= eps) & (w2 >= eps)
        if not inside.any():
            continue
        z = w0 * depth[a] + w1 * depth[b] + w2 * depth[c]
        ys_i, xs_i = np.nonzero(inside)
        ys_i, xs_i = ys_i + y0, xs_i + x0
        zz = z[inside]
        closer = zz < zall[ys_i, xs_i]
        zall[ys_i[closer], xs_i[closer]] = zz[closer]
        iall[ys_i[closer], xs_i[closer]] = n
        if front[n]:
            closer = zz < zfront[ys_i, xs_i]
            zfront[ys_i[closer], xs_i[closer]] = zz[closer]
            ifront[ys_i[closer], xs_i[closer]] = n
    return lo, iall, ifront, zall, zfront


def shift_max(m, r, axis):
    out = m.copy()
    for s in range(1, r + 1):
        out[tuple(slice(s, None) if k == axis else slice(None) for k in range(2))] |= \
            m[tuple(slice(None, -s) if k == axis else slice(None) for k in range(2))]
        out[tuple(slice(None, -s) if k == axis else slice(None) for k in range(2))] |= \
            m[tuple(slice(s, None) if k == axis else slice(None) for k in range(2))]
    return out


def enclosed(hit, r):
    """Empty cells with geometry on all four sides within r cells (left, right, up and down)."""
    def reach(m, axis, forward):
        out = np.zeros_like(m)
        for s in range(1, r + 1):
            if axis == 0:
                src = m[s:, :] if forward else m[:-s, :]
                dst = out[:-s, :] if forward else out[s:, :]
            else:
                src = m[:, s:] if forward else m[:, :-s]
                dst = out[:, :-s] if forward else out[:, s:]
            dst |= src
        return out
    return ~hit & reach(hit, 0, True) & reach(hit, 0, False) & reach(hit, 1, True) & reach(hit, 1, False)


def clusters(mask):
    """Connected cell groups (4-neighbour) as lists of (row, col)."""
    seen = np.zeros_like(mask)
    out = []
    for r0, c0 in zip(*np.nonzero(mask)):
        if seen[r0, c0]:
            continue
        stack, comp = [(r0, c0)], []
        seen[r0, c0] = True
        while stack:
            r, c = stack.pop()
            comp.append((r, c))
            for rr, cc in ((r + 1, c), (r - 1, c), (r, c + 1), (r, c - 1)):
                if 0 <= rr < mask.shape[0] and 0 <= cc < mask.shape[1] and mask[rr, cc] and not seen[rr, cc]:
                    seen[rr, cc] = True
                    stack.append((rr, cc))
        out.append(comp)
    return out


def visibility(v, tris, pixel, close, min_area):
    a, b, c = v[tris[:, 0]], v[tris[:, 1]], v[tris[:, 2]]
    normal = np.cross(b - a, c - a)
    normal /= np.linalg.norm(normal, axis=1, keepdims=True) + 1e-30
    cell_cm2 = (pixel * 100) ** 2
    min_cells = max(1, int(round(min_area / cell_cm2)))
    r = max(1, int(round(close / pixel)))
    culled_faces = collections.defaultdict(collections.Counter)   # face -> view -> cm2
    gaps = []   # (area cm2, point, view)
    for vi, d in enumerate(directions()):
        u, w = basis(d)
        p2 = np.stack([v @ u, v @ w], axis=1)
        depth = v @ d
        front = (normal @ d) < 0
        lo, iall, ifront, zall, zfront = rasterise(p2, depth, tris, front, pixel)
        # A back face nearest, with no front face within 2 mm of it (back-to-back pairs pass).
        culled = (iall >= 0) & ~front[np.maximum(iall, 0)] & (zfront > zall + 0.002)
        for comp in clusters(culled):
            if len(comp) < min_cells:
                continue
            rows, cols = zip(*comp)
            for f, n in collections.Counter(iall[rows, cols]).items():
                culled_faces[f][vi] += n * cell_cm2
        gap = enclosed(iall >= 0, r)
        # Depth of a gap: that of the covered cells nearest its middle.
        ring = shift_max(shift_max(gap, 2, 0), 2, 1) & (iall >= 0)
        rr, cc = np.nonzero(ring)
        for comp in clusters(gap):
            if len(comp) < min_cells:
                continue
            rows, cols = map(np.array, zip(*comp))
            near = np.argsort((rr - rows.mean()) ** 2 + (cc - cols.mean()) ** 2)[:10]
            zc = float(np.median(zall[rr[near], cc[near]]))
            x2 = lo[0] + (cols.mean() + 0.5) * pixel
            y2 = lo[1] + (rows.mean() + 0.5) * pixel
            point = x2 * u + y2 * w + zc * d
            gaps.append((len(comp) * cell_cm2, point, vi))
    return culled_faces, merge_gaps(gaps)


def merge_gaps(gaps, radius=0.04):
    merged = []   # [area max, point, views]
    for area, p, vi in sorted(gaps, key=lambda g: -g[0]):
        for m in merged:
            if np.linalg.norm(m[1] - p) < radius:
                m[0] = max(m[0], area)
                m[2].add(vi)
                break
        else:
            merged.append([area, p, {vi}])
    return merged


def face_clusters(v, tris, owner, culled_faces, radius=0.15):
    """Groups flagged triangles whose centroids lie within radius into patches. A patch's area is
    the most of it any one view sees (cm2), so it does not grow with the number of views."""
    flagged = list(culled_faces)
    centroid = {f: v[tris[f]].mean(axis=0) for f in flagged}
    groups = []
    for f in sorted(flagged, key=lambda f: -max(culled_faces[f].values())):
        for g in groups:
            if min(np.linalg.norm(centroid[f] - centroid[h]) for h in g["faces"]) < radius:
                g["faces"].append(f)
                g["by_view"].update(culled_faces[f])
                break
        else:
            groups.append({"faces": [f], "by_view": collections.Counter(culled_faces[f])})
    for g in groups:
        g["area"] = max(g["by_view"].values())
        g["views"] = set(g["by_view"])
        pts = v[tris[g["faces"]].ravel()]
        g["lo"], g["hi"] = pts.min(axis=0), pts.max(axis=0)
        g["obj_faces"] = sorted({int(owner[f]) for f in g["faces"]})
    return groups


def write_marks(path, v, tris, flagged, gaps):
    with open(path, "w") as out:
        out.write("# check_holes.py marks: grey faces, red culled faces, magenta gap markers\n")
        n = 0
        for t, (a, b, c) in enumerate(tris):
            col = "0.85 0.10 0.10" if t in flagged else "0.62 0.62 0.62"
            for p in (v[a], v[b], v[c]):
                out.write(f"v {p[0]:.6f} {p[1]:.6f} {p[2]:.6f} {col}\n")
            out.write(f"f {n + 1} {n + 2} {n + 3}\n")
            n += 3
        for _, p, _ in gaps:
            s = 0.012
            corners = [p + np.array([dx, dy, dz]) * s for dx in (-1, 1) for dy in (-1, 1) for dz in (-1, 1)]
            for q in corners:
                out.write(f"v {q[0]:.6f} {q[1]:.6f} {q[2]:.6f} 0.95 0.10 0.95\n")
            for f in ((0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)):
                out.write("f " + " ".join(str(n + 1 + k) for k in f) + "\n")
            n += 8


def fmt(p):
    return "(" + ", ".join(f"{c:+.3f}" for c in p) + ")"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("objs", nargs="+")
    ap.add_argument("--box")
    ap.add_argument("--pixel", type=float, default=0.005)
    ap.add_argument("--close", type=float, default=0.02)
    ap.add_argument("--min-area", type=float, default=2.0)
    ap.add_argument("--fail-culled", type=float, default=25.0)
    ap.add_argument("--fail-gap", type=float, default=20.0)
    ap.add_argument("--min-loop", type=float, default=0.05)
    ap.add_argument("--marks")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    box = None if not args.box else np.array([float(c) for c in args.box.split(",")]).reshape(3, 2)
    bad = 0
    for index, path in enumerate(args.objs):
        obj, v, tris, owner = load(path)
        top = v[tris].reshape(-1, 3)[:, 1].max()
        n_open, nonmanifold, loops = topology(v, tris, args.min_loop)
        culled_faces, gaps = visibility(v, tris, args.pixel, args.close, args.min_area)
        if box is not None:
            in_box = inside(v[tris].mean(axis=1), box)
            if not in_box.any():
                print(f"{path}: no faces in the box; nothing checked")
                bad += 1
                continue
            loops = [l for l in loops if inside((l[1] + l[2]) / 2, box)]
            culled_faces = {f: a for f, a in culled_faces.items() if in_box[f]}
            gaps = [g for g in gaps if inside(g[1], box)]
        groups = face_clusters(v, tris, owner, culled_faces)
        print(f"== {path}: {len(tris)} triangles checked from 49 directions at {args.pixel * 1000:.0f} mm cells")
        print(f"   topology: {n_open} open edges, {len(loops)} open loops >= {args.min_loop} m, {nonmanifold} non-manifold edges")
        if not args.quiet:
            for length, lo, hi in loops[:12]:
                print(f"     open loop {length:5.2f} m  {fmt(lo)}..{fmt(hi)}  {region(lo, hi, top)}")
        print(f"   culled: {len(groups)} patches where the nearest surface is a back face")
        for g in sorted(groups, key=lambda g: -g["area"])[:20]:
            print(f"     {g['area']:7.1f} cm2  {len(g['faces'])} tris  {len(g['views'])} views  "
                  f"{fmt(g['lo'])}..{fmt(g['hi'])}  {region(g['lo'], g['hi'], top)}  obj faces {g['obj_faces'][:6]}"
                  f"  from {','.join(VIEW_NAMES[k] for k in sorted(g['views'])[:6])}")
        print(f"   gaps: {len(gaps)} enclosed holes with no surface")
        for area, p, views in sorted(gaps, key=lambda g: -g[0])[:20]:
            print(f"     {area:7.1f} cm2  at {fmt(p)}  {len(views)} views  {region(p, p, top)}"
                  f"  from {','.join(VIEW_NAMES[k] for k in sorted(views)[:6])}")
        if args.marks:
            marks = args.marks if len(args.objs) == 1 else args.marks.replace(".obj", f"_{index}.obj")
            write_marks(marks, v, tris, set(culled_faces), gaps)
            print(f"   marks: {marks}")
        failing = sum(g["area"] >= args.fail_culled for g in groups) + sum(g[0] >= args.fail_gap for g in gaps)
        print(f"   {'FAIL' if failing else 'pass'}: {failing} findings at or over {args.fail_culled:g} cm2 culled / {args.fail_gap:g} cm2 gap")
        if failing:
            bad += 1
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
