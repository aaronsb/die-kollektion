"""Measure the Glyptodon cab's subtle shape on a car-root OBJ, to check decimation keeps it.

Usage: python3 tools/measure_cab.py <obj> [<obj> ...]

- tumblehome: cab width across the door region (z 0.3..0.9) at the beltline (y 1.75) and just
  under the roof edge (y 2.32), and how far each side leans in between them.
- windshield: the glass's lower edge height at the centre and at x = +-0.7; positive "rise"
  means the edge sits higher at the ends than the centre.
- hood crown: the hood top's height (z 1.75..1.95) at the centre minus at x = +-0.7.
Faces count as paint, hood or glass by their UV (the atlas points of the cab masters' Paint, Hood
and Glass materials); an OBJ without UVs falls back to the reference model import's group names.
"""
import sys, os

PAINT_UV, HOOD_UV, GLASS_UV = (0.635, 0.59), (0.636, 0.59), (0.537, 0.772)
PAINT_GROUPS, HOOD_GROUPS, GLASS_GROUPS = {"366", "303", "313", "488"}, {"323"}, {"701"}


def classify(path):
    """Paint, hood and glass faces, each a list of corner positions."""
    paint, hood, glass, group, verts, uvs = [], [], [], None, [], []
    for line in open(path):
        p = line.split()
        if not p:
            continue
        if p[0] == "v":
            verts.append(tuple(float(x) for x in p[1:4]))
        elif p[0] == "vt":
            uvs.append((float(p[1]), float(p[2])))
        elif p[0] == "g":
            group = p[1].split("|")[-1]
        elif p[0] == "f":
            corners = [c.split("/") for c in p[1:]]
            vi = [int(c[0]) - 1 for c in corners]
            if len(corners[0]) > 1 and corners[0][1]:
                u = uvs[int(corners[0][1]) - 1]
                target = (paint if _near(u, PAINT_UV) else hood if _near(u, HOOD_UV)
                          else glass if _near(u, GLASS_UV) else None)
            else:
                target = (paint if group in PAINT_GROUPS else hood if group in HOOD_GROUPS
                          else glass if group in GLASS_GROUPS else None)
            if target is not None:
                target.append([verts[i] for i in vi])
    return paint, hood, glass


def _near(a, b):
    return abs(a[0] - b[0]) < 2e-4 and abs(a[1] - b[1]) < 2e-4


def section(faces, x, keep=lambda p: True, axis=0):
    """Points where the faces' edges cross the plane axis = x (sampled on edges, not vertices, so
    a coarse LOD reads the same surface as a dense one)."""
    out = []
    for face in faces:
        for a, b in zip(face, face[1:] + face[:1]):
            if (a[axis] - x) * (b[axis] - x) <= 0 and a[axis] != b[axis]:
                t = (x - a[axis]) / (b[axis] - a[axis])
                p = tuple(a[k] + t * (b[k] - a[k]) for k in range(3))
                if keep(p):
                    out.append(p)
    return out


def edge(faces, x, pick=max, keep=lambda p: True):
    values = [p[1] for p in section(faces, x, keep)]
    return pick(values) if values else float("nan")


def measure(path):
    paint, hood, glass = classify(path)
    door = lambda p: 0.3 <= p[2] <= 0.9
    belt = section(paint, 1.75, door, axis=1)
    roof = section(paint, 2.32, door, axis=1)
    wb = max(p[0] for p in belt) - min(p[0] for p in belt)
    wr = max(p[0] for p in roof) - min(p[0] for p in roof)
    shield = [f for f in glass if all(p[2] > 1.1 for p in f)]
    c = edge(shield, 0.0, pick=min)
    ends = (edge(shield, -0.7, pick=min) + edge(shield, 0.7, pick=min)) / 2
    on_hood = lambda p: 1.75 <= p[2] <= 1.95 and p[1] > 1.4
    hc = edge(hood, 0.0, keep=on_hood)
    he = (edge(hood, -0.7, keep=on_hood) + edge(hood, 0.7, keep=on_hood)) / 2
    print(f"{os.path.basename(path)}: tumblehome belt {wb:.3f} m, roof edge {wr:.3f} m, "
          f"{(wb - wr) / 2 * 1000:.0f} mm per side | windshield lower edge centre y {c:.3f}, "
          f"ends {ends:.3f}, rise {(ends - c) * 1000:+.0f} mm | hood crown {(hc - he) * 1000:+.0f} mm "
          f"(centre {hc:.3f}, x+-0.7 {he:.3f})")


for path in sys.argv[1:]:
    measure(path)
