"""Reports sliver faces in built meshes: longest edge over a length with an area under a limit.

Usage: python3 tools/check_slivers.py <obj> [<obj> ...] [--length 1.5] [--area 0.01] [--allow x0,x1,y0,y1,z0,z1 ...]

Prints each sliver's piece bounds and atlas UV so its source can be found; exits 1 if any are found
outside the --allow boxes. An --allow box (repeatable) names a region where long thin faces are
intended, such as roof ribs; slivers lying wholly inside one are listed as allowed and don't fail.
Stretched or misplaced bits (a lamp lens dragged across the bed, a collapsed bracket) show up here
before they show up as stray lines in a render.
"""
import argparse, math, sys

import meshlib


def slivers(obj, length, area):
    found = []
    for n, face in enumerate(obj.faces):
        pts = [obj.v[c[0]] for c in face]
        longest = max(math.dist(pts[i], pts[(i + 1) % len(pts)]) for i in range(len(pts)))
        if longest <= length:
            continue
        total = 0.0
        for k in range(1, len(pts) - 1):
            a, b, c = pts[0], pts[k], pts[k + 1]
            e1 = [b[i] - a[i] for i in range(3)]
            e2 = [c[i] - a[i] for i in range(3)]
            cross = [e1[1] * e2[2] - e1[2] * e2[1], e1[2] * e2[0] - e1[0] * e2[2], e1[0] * e2[1] - e1[1] * e2[0]]
            total += math.sqrt(sum(x * x for x in cross)) / 2
        if total < area:
            uv = obj.vt[face[0][1]] if face[0][1] >= 0 else None
            found.append((n, longest, total, pts, uv))
    return found


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("objs", nargs="+")
    ap.add_argument("--length", type=float, default=1.5)
    ap.add_argument("--area", type=float, default=0.01)
    ap.add_argument("--allow", action="append", default=[])
    args = ap.parse_args()
    boxes = [[float(x) for x in a.split(",")] for a in args.allow]
    bad = 0
    for path in args.objs:
        obj = meshlib.Obj.read(path)
        found = slivers(obj, args.length, args.area)
        rows, allowed = [], 0
        for n, longest, total, pts, uv in found:
            lo = [round(min(p[k] for p in pts), 3) for k in range(3)]
            hi = [round(max(p[k] for p in pts), 3) for k in range(3)]
            ok = any(all(b[2 * k] <= lo[k] and hi[k] <= b[2 * k + 1] for k in range(3)) for b in boxes)
            allowed += ok
            rows.append(f"  face {n}: edge {longest:.2f} m, area {total:.4f} m2, {lo}..{hi}, uv {uv}" + ("  (allowed)" if ok else ""))
        print(f"{path}: {len(found) - allowed} sliver faces (> {args.length} m, < {args.area} m2)"
              + (f", {allowed} allowed" if allowed else ""))
        for row in rows:
            print(row)
        bad += len(found) - allowed
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
