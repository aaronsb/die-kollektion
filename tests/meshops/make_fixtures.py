#!/usr/bin/env python3
"""The fixtures tools/meshops-check compares the C# build with: synthetic meshes (never game geometry), a synthetic
vehicle that runs every operation on them, and what tools/build_vehicle.py and tools/meshlib.py make of it.

    python3 tests/meshops/make_fixtures.py      rewrite tests/meshops/{game,gen,vehicle,expected,numbers.json}

game/ stands in for extracted/ (which git ignores everywhere), gen/ for the vehicle's generated/. Run it again only
when meshlib.py or build_vehicle.py changes on purpose; the C# port must then match the new expectations.
"""
import contextlib, io, json, math, os, random, shutil, struct, sys, tempfile
from decimal import Decimal, ROUND_HALF_EVEN

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import build_vehicle  # noqa: E402
import meshlib  # noqa: E402


class Mesh:
    """A synthetic OBJ written by hand (9 decimals, comments, statements meshlib drops), so the reader is tested too."""

    def __init__(self, skinned=False):
        self.v, self.color, self.bw, self.vt, self.vn, self.faces = [], [], [], [], [], []
        self.skinned = skinned

    def vertex(self, p, bone=None, colour=None, weights=None):
        self.v.append(p)
        self.color.append(colour)
        if self.skinned:
            self.bw.append(weights or ([bone or 0, 0, 0, 0], [1.0, 0.0, 0.0, 0.0]))
        return len(self.v) - 1

    def prism(self, x, y, zs, uv, bone=None, colour=None, weights=None):
        """A box along z with a ring of four corners at each of zs, quads between rings and end caps."""
        rings = []
        for z in zs:
            ring = [self.vertex([px, py, z], bone, colour, weights) for px, py in
                    ((x[0], y[0]), (x[1], y[0]), (x[1], y[1]), (x[0], y[1]))]
            rings.append(ring)
        base_vt = len(self.vt)
        self.vt += [[uv[0], uv[1]], [uv[0] + 0.01, uv[1]], [uv[0] + 0.01, uv[1] + 0.01], [uv[0], uv[1] + 0.01]]
        n = len(self.vn)
        self.vn += [[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [-1.0, 0.0, 0.0], [0.0, 0.0, -1.0], [0.0, 0.0, 1.0]]
        for a, b in zip(rings, rings[1:]):
            for k in range(4):
                kk = (k + 1) % 4
                self.faces.append([(a[k], base_vt, n + k), (a[kk], base_vt + 1, n + k), (b[kk], base_vt + 2, n + k),
                                   (b[k], base_vt + 3, n + k)])
        self.faces.append([(rings[0][3 - k], base_vt + k, n + 4) for k in range(4)])
        self.faces.append([(rings[-1][k], base_vt + k, n + 5) for k in range(4)])

    def box(self, lo, hi, uv, **kw):
        self.prism((lo[0], hi[0]), (lo[1], hi[1]), (lo[2], hi[2]), uv, **kw)

    def write(self, path, crlf=False):
        nl = "\r\n" if crlf else "\n"
        lines = ["# synthetic test mesh (tests/meshops/make_fixtures.py)", "o synthetic", "g body", "s off"]
        for i, p in enumerate(self.v):
            c = self.color[i]
            lines.append("v " + " ".join(f"{x:.9f}" for x in p) + ("" if c is None else " " + " ".join(f"{x:.4f}" for x in c)))
            if self.skinned:
                idx, w = self.bw[i]
                lines.append("bw\t" + " ".join(map(str, idx)) + "  " + " ".join(f"{x:.7f}" for x in w))
        lines += ["vt " + " ".join(f"{x:.9f}" for x in t) for t in self.vt]
        lines += ["vn " + " ".join(f"{x:.9f}" for x in n) for n in self.vn]
        if self.skinned:
            lines += ["bp 1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1", "bp 1 0 0 0.75 0 1 0 -0.4 0 0 1 -1 0 0 0 1"]
        lines.append("#nospace is not a comment and is dropped")
        lines.append("usemtl paint")
        for f in self.faces:
            lines.append("f " + " ".join("/".join("" if i < 0 else str(i + 1) for i in c) for c in f))
        with open(path, "w", newline="") as fh:
            fh.write(nl.join(lines) + nl)


def body():
    """An unskinned body: a long floor (rings along z), side panels, small details, coincident-corner cubes, a
    wheel-arch block and a piece with a ragged face layout (faces without UVs or normals)."""
    m = Mesh()
    m.prism((-0.8, 0.8), (0.5, 0.6), [-2.0, -1.6, -1.2, -0.8, -0.4, 0.0, 0.4, 0.8], (0.10, 0.10))
    m.box([0.70, 0.6, -1.9], [0.80, 1.3, -0.3], (0.30, 0.10))
    m.box([-0.80, 0.6, -1.9], [-0.70, 1.3, -0.3], (0.30, 0.20))
    m.box([0.85, 0.70, -1.55], [0.95, 0.80, -1.45], (0.50, 0.50), colour=[0.0625, 0.5, 1.0])
    m.box([-0.95, 0.70, -1.55], [-0.85, 0.80, -1.45], (0.52, 0.50), colour=[0.1875, 0.25, 0.0])
    m.box([0.1, 1.40, -0.6], [0.3, 1.60, -0.4], (0.60, 0.60))     # two cubes touching at one corner:
    m.box([0.3, 1.60, -0.4], [0.5, 1.80, -0.2], (0.62, 0.60))     # coincident positions join them
    m.prism((-0.6, 0.6), (0.35, 0.55), [0.9, 1.0, 1.1, 1.2], (0.70, 0.30))   # round the front axle
    m.box([0.2, 0.9, 0.6], [0.4, 1.1, 0.75], (0.80, 0.80))
    m.box([-0.3, 0.9, -1.0], [-0.1, 1.2, -0.7], (0.85, 0.85))   # the relocated exhaust's stand-in
    a = m.vertex([0.0, 2.0, 0.0])
    b = m.vertex([0.1, 2.0, 0.0])
    c = m.vertex([0.1, 2.1, 0.0])
    d = m.vertex([0.0, 2.1, 0.05])
    m.faces += [[(a, -1, -1), (b, -1, -1), (c, -1, -1)], [(a, 0, -1), (c, 1, -1), (d, 2, -1)]]
    # Two slanted quads facing up at 45 and 15 degrees: paint's facing test keeps only the second.
    for k, (ny, nz) in enumerate(((0.7071067811865476, 0.7071067811865476), (0.9659258262890683, 0.25881904510252074))):
        n = len(m.vn)
        m.vn.append([0.0, ny, nz])
        z0 = 1.3 + 0.3 * k
        q = [m.vertex([x, 1.0 + (z - z0) * -nz / ny, z]) for x, z in ((-0.2, z0), (0.2, z0), (0.2, z0 + 0.2), (-0.2, z0 + 0.2))]
        m.faces.append([(i, 0, n) for i in q])
    return m


def edge_values():
    """Numbers whose formatting differs between careless implementations: ties at 6 and 3 decimals, negative zero,
    tiny negatives, values that need all 9 input decimals."""
    m = Mesh()
    m.box([-1e-9, 0.0078125, -0.0], [0.5078125, 0.123456789, 1.0000005], (0.0078125, 0.9921875),
          colour=[0.0625, 0.0005, 0.9995])
    m.box([-0.0000004, -2.5e-7, 2.0], [1.23456785, 3.000000500, 2.1], (0.25, 0.75), colour=[-0.0004, -0.0, 0.0015])
    return m


def axle(x_flip=1.0):
    """A skinned leaf-sprung beam axle at z = 1.0: differential (the largest piece), tube, hub caps, leaf springs,
    spring seats and a body-skinned shock; hub bones 1 (left, +x) and 2 (right)."""
    m = Mesh(skinned=True)
    m.prism((-0.15, 0.15), (0.30, 0.50), [0.90, 0.95, 1.00, 1.05, 1.10, 1.12], (0.20, 0.20), bone=1)
    m.box([-0.68, 0.37, 0.97], [0.68, 0.43, 1.03], (0.22, 0.20), bone=1,
          weights=([1, 2, 0, 0], [0.5, 0.5, 0.0, 0.0]))
    m.box([0.70, 0.30, 0.95], [0.80, 0.50, 1.05], (0.24, 0.20), bone=1)
    m.box([-0.80, 0.30, 0.95], [-0.70, 0.50, 1.05], (0.24, 0.22), bone=2)
    for sx, bone in ((1.0, 1), (-1.0, 2)):
        x0, x1 = sorted((sx * 0.40, sx * 0.44))
        m.prism((x0, x1), (0.48, 0.52), [0.5, 0.8, 1.2, 1.5], (0.26, 0.20), bone=bone)
        x0, x1 = sorted((sx * 0.38, sx * 0.46))
        m.box([x0, 0.43, 0.96], [x1, 0.47, 1.04], (0.28, 0.20), bone=bone)
    m.box([0.53 * x_flip, 0.45, 1.10], [0.57 * x_flip, 0.80, 1.15], (0.30, 0.20), bone=0,
          weights=([0, 1, 0, 0], [0.75, 0.25, 0.0, 0.0]))
    return m


def part(offset=0.0):
    """A cab-like part: a big shell, a small detail inside it and a strut, offset along x."""
    m = Mesh()
    m.box([-0.6 + offset, 1.0, -1.2], [0.6 + offset, 1.5, -0.2], (0.40, 0.40))
    m.box([0.0 + offset, 1.1, -0.9], [0.1 + offset, 1.2, -0.8], (0.42, 0.40), colour=[1.0, 0.0, 0.0])
    m.box([0.5 + offset, 0.6, -1.0], [0.55 + offset, 1.0, -0.95], (0.44, 0.40))
    return m


TUBES = [
    {"points": [[0.4, 0.83, 0.55], [0.4, 0.655, 0.15]], "radius": 0.07, "sides": 4, "square": True},
    {"points": [[0.28, 0.92, 1.4], [0.32, 0.8, 1.0], [0.42, 0.62, 0.6], [0.52, 0.49, 0.2], [0.55, 0.5, -0.66],
                [0.55, 0.55, -0.88], [0.55, 0.73, -0.98]], "radius": 0.04, "sides": 8},
    {"points": [[0.62, 0.725, -1.22], [1.06, 0.725, -1.27], [1.16, 0.69, -1.32]], "radius": 0.045, "sides": 6,
     "bendRadius": 0.3},
    {"points": [[0.0, 0.2, 0.0], [0.0, 0.9, 0.0], [0.3, 0.9, 0.0]], "radius": 0.03},
    {"points": [[-0.5, 1.0, 0.0], [-0.5, 1.0, -0.4], [-0.1, 1.0, -0.4]], "radius": 0.05, "sides": 4, "square": True,
     "bendRadius": 0.0},
]

DEFINITION = {
    "notes": "Synthetic: every build operation once or more on made-up meshes (tests/meshops/make_fixtures.py).",
    "codename": "Testwagen",
    "donor": "TestCar",
    "donorAxleZ": {"front": 1.0, "rear": -1.3099999999999998},
    "wheelbase": 2.75,
    "bodyCut": [[0.0, -0.62], [1.05, -0.865], [1.21, -1.45], [0.5, -0.7]],
    "meshes": {
        "Body/stretched": "stretched.obj",
        "Body/edge_values": {"file": "edge_values.obj", "stretch": False},
        "Body/regions": {"file": "regions.obj", "stretch": False, "ops": [
            {"op": "removeRegion", "box": [{"y": [1.35, None], "z": [-0.65, None]}, {"x": [None, -0.8]}]},
            {"op": "removeRegion", "box": {"y": [0.3, 0.6], "z": [0.85, 0.95]}, "unitSize": 0.05},
            {"op": "removeRegion", "box": []},
            {"op": "removePieces", "select": [{"x": [0.6, 0.9], "minSize": {"y": 0.3}}, {"minVertices": 30}]},
            {"op": "removePieces", "select": {"z": [-1.6, -1.4]}, "notes": "the small details"}]},
        "Body/pieces": {"file": "pieces.obj", "ops": [
            {"op": "stretchPieces", "select": {"x": [-0.81, 0.81], "y": [0.49, 0.61]}, "cutZ": -1.0, "shift": 0.3},
            {"op": "stretchPieces", "select": {"x": [0.69, 0.81]}, "cutZ": -1.5, "shift": -0.2, "move": "ahead"},
            {"op": "stretchPieces", "select": [{"x": [-0.81, -0.69]}], "cutZ": -1.0, "shift": 0.25, "move": "behind"},
            {"op": "movePieces", "select": {"z": [0.5, 0.8]}, "offset": [0.0, -0.1, 0.05]},
            {"op": "scalePieces", "select": {"x": [-0.81, 0.81], "minSize": {"y": 0.5}}, "origin": [0.0, 0.6, 0.0],
             "scale": [1.0, 1.2569, 1.0], "box": {"y": [0.65, None]}},
            {"op": "widenPieces", "select": [{"x": [0.6, 0.9]}, {"x": [-0.9, -0.6]}], "cutX": 0.7, "shift": 0.25},
            {"op": "widenPieces", "select": {"y": [0.49, 0.61]}, "cutX": 0.5, "shift": 0.1,
             "box": {"z": [None, -1.0]}}]},
        "Body/paint": {"file": "paint.obj", "stretch": False, "ops": [
            {"op": "paint", "uv": [0.635, 0.59], "select": {"x": [0.84, 0.96]}},
            {"op": "paint", "uv": [0.0264, 0.124], "box": {"y": [1.25, 1.31]}, "whole": True, "facing": [0, 1, 0]},
            {"op": "paint", "uv": [0.5, 0.5], "box": {"z": [-1.0, -0.5]}},
            {"op": "paint", "uv": [0.9, 0.1], "uvRect": [[0.09, 0.32], [0.09, 0.32]],
             "uvExclude": [[[0.29, 0.32], [0.09, 0.15]]], "facing": [-1.0, 0.0, 0.0]},
            {"op": "paint", "uv": [0.4, 0.4], "box": {"z": [1.2, 1.9]}, "facing": [0, 1, 0]},
            {"op": "paint", "uv": [0.1, 0.9], "uvRect": [[0.0, 1.0], [0.0, 1.0]]}]},
        "Body/shapes": {"file": "shapes.obj", "stretch": False, "ops": [
            {"op": "addBoxes", "boxes": [{"x": [0.1, 0.2], "y": [0.0, 0.05], "z": [-0.3, 0.3]},
                                         {"x": [-0.2, -0.1], "y": [1.0, 1.25], "z": [-2.0, -1.9]}], "uv": [0.25, 0.5]},
            {"op": "addPlates", "plates": [
                {"corners": [[0.6, 0.6, -0.5], [0.9, 0.5, -0.5], [0.9, 0.5, -0.2], [0.6, 0.6, -0.2]], "thickness": 0.004},
                {"corners": [[-0.6, 0.6, -0.2], [-0.6, 0.9, -0.2], [-0.9, 0.9, -0.3], [-0.9, 0.6, -0.3]], "thickness": 0.01}],
             "uv": [0.3, 0.3]},
            {"op": "addTubes", "tubes": TUBES, "uv": [0.0264, 0.124]},
            {"op": "addProfileBands", "bands": [
                {"inner": [[0.7, 1.4], [0.75, 1.42], [0.8, 1.38]], "outer": [[0.72, 1.45], [0.77, 1.47], [0.83, 1.41]],
                 "y": [0.9, 1.0]}], "uv": [0.6, 0.2]},
            {"op": "addDecals", "decals": [
                {"corners": [[0.7, 1.0, 1.5], [0.8, 1.0, 1.5], [0.8, 1.1, 1.5], [0.7, 1.1, 1.5]],
                 "uvs": [[0.1, 0.1], [0.2, 0.1], [0.2, 0.2], [0.1, 0.2]], "facing": [0, 0, 1]},
                {"corners": [[-0.7, 1.0, 1.5], [-0.8, 1.0, 1.5], [-0.75, 1.1, 1.5]],
                 "uvs": [[0.3, 0.1], [0.4, 0.1], [0.35, 0.2]], "facing": [0.1, 0.0, 2.0], "doubleSided": True}]}]},
        "Body/axle_clear": {"file": "axle_clear.obj", "stretch": False, "ops": [
            {"op": "removeNearAxle", "centre": [0.45, 1.05], "radius": 0.12, "box": {"x": [0.0, None]}},
            {"op": "removeNearAxle", "centre": [0.45, 1.05], "radius": 0.14}]},
        "Body/insert": {"file": "insert.obj", "ops": [
            {"op": "insertPart", "file": "meshes/part.obj", "box": {"y": [0.9, None]},
             "include": [{"minSize": {"x": 0.5}}, {"x": [-0.1, 0.2], "y": [1.05, 1.25]}],
             "exclude": [{"x": [0.05, 0.2]}]},
            {"op": "insertPart", "file": "extracted/shared/part_LOD0.obj", "unitSize": 0.2},
            {"op": "insertPart", "file": "generated/part_boxes.obj", "box": [{"x": [1.5, None]}]}]},
        "Body/relocate": {"file": "relocate.obj", "stretch": False, "ops": [
            {"op": "relocatePiece", "select": {"x": [-0.31, -0.09], "y": [0.89, 1.21], "minVertices": 8},
             "rotateY": -90, "anchorTo": [0.6, None, -0.7]},
            {"op": "relocatePiece", "select": {"x": [0.19, 0.41], "z": [0.59, 0.76]}, "rotateY": 33.5}]},
        "Axles/portal": {"file": "portal.obj", "stretch": False, "ops": [
            {"op": "portalAxle", "lift": 0.2, "tubeScale": 1.5, "diffScale": [1.1, 1.3, 1.2], "diffOffset": 0.07,
             "housingSegments": 12},
            {"op": "coilSprings", "outerDiameter": 0.16, "wireDiameter": 0.02, "turns": 5.0, "x": 0.5, "height": 0.3,
             "sides": 6, "segmentsPerTurn": 7}]},
        "Axles/coil": {"file": "coil.obj", "stretch": False, "ops": [
            {"op": "portalAxle", "diffScale": 1.25},
            {"op": "coilSprings", "turns": 1.5}]},
        "Axles/skinned_shapes": {"file": "skinned_shapes.obj", "stretch": False, "ops": [
            {"op": "addTubes", "tubes": TUBES[1:3], "uv": [0.1, 0.1]},
            {"op": "addBoxes", "boxes": [{"x": [0.0, 0.1], "y": [0.0, 0.1], "z": [0.0, 0.1]}], "uv": [0.2, 0.2]},
            {"op": "addDecals", "decals": [
                {"corners": [[0.0, 0.0, 2.0], [0.1, 0.0, 2.0], [0.1, 0.1, 2.0]], "uvs": [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0]],
                 "facing": [0.0, 0.0, -1.0], "doubleSided": True}]}]},
    },
}


def bits(x):
    return struct.unpack("<q", struct.pack("<d", x))[0]


def numbers():
    """Doubles (as their bits) with Python's renderings of them, its round(x, 4) as an integer count of 1e-4, and
    sums and hypots."""
    rng = random.Random(7)
    values = [0.0, -0.0, 1e-9, -1e-9, 0.0078125, -0.0078125, 0.5078125, 0.0625, -0.0625, 0.1875, 2.5e-7, -2.5e-7,
              0.00005, -0.00005, 0.00015, 1.00005, 123456.78125, 1e16, 1e-5, 1e-4, 0.1, 0.2, 0.3, 1.3099999999999998,
              -2.7929999999999997, 5e-324, 2.2250738585072014e-308, 1.7976931348623157e308, 12345678.9, 0.5, 2.5]
    values += [rng.uniform(-3, 3) for _ in range(150)]
    values += [rng.randint(-200000, 200000) / 2 ** rng.randint(4, 24) for _ in range(150)]
    values += [round(rng.uniform(-2, 2), 4) + rng.choice([0.00005, -0.00005, 0.0]) for _ in range(150)]
    rows = []
    for x in values:
        row = {"bits": bits(x), "f6": f"{x:.6f}", "f3": f"{x:.3f}", "s3": f"{x:+.3f}", "f2": f"{x:.2f}",
               "s2": f"{x:+.2f}", "repr": repr(x)}
        if abs(x) < 1e9:
            n = int(Decimal(x).quantize(Decimal("0.0001"), ROUND_HALF_EVEN) * 10000)
            assert round(x, 4) == float(Decimal(n) / 10000), x
            row["round4"] = n
        rows.append(row)
    sums = []
    for _ in range(100):
        xs = [rng.uniform(-1, 1) * 10 ** rng.randint(-8, 3) for _ in range(rng.randint(1, 6))]
        sums.append({"bits": [bits(x) for x in xs], "sum": bits(sum(xs))})
    sums.append({"bits": [bits(-0.0)], "sum": bits(sum([-0.0]))})
    sums.append({"bits": [bits(1e100), bits(1.0), bits(-1e100)], "sum": bits(sum([1e100, 1.0, -1e100]))})
    hypots = []
    for _ in range(100):
        a, b = rng.uniform(-5, 5) * 10 ** rng.randint(-3, 3), rng.uniform(-5, 5) * 10 ** rng.randint(-3, 3)
        hypots.append({"bits": [bits(a), bits(b)], "hypot": bits(math.hypot(a, b))})
    hypots.append({"bits": [bits(3.0), bits(4.0)], "hypot": bits(5.0)})
    hypots.append({"bits": [bits(5e-324), bits(1e-320)], "hypot": bits(math.hypot(5e-324, 1e-320))})
    # The C library's cos, sin, tan and acos (glibc here) on the angles the operations use: coil and housing steps,
    # tube sides, fillet turns. A C library that rounds differently shows here first (informational).
    trig = []
    angles = [2 * math.pi * 4.5 * s / 72 for s in range(73)] + [2 * math.pi * k / 20 for k in range(20)]
    angles += [math.pi / 8 + 2 * math.pi * j / 8 for j in range(8)] + [rng.uniform(0, math.pi) for _ in range(60)]
    for a in angles:
        c = max(-1.0, min(1.0, math.cos(a)))
        trig.append({"bits": bits(a), "cos": bits(math.cos(a)), "sin": bits(math.sin(a)), "tan": bits(math.tan(a / 2)),
                     "acos": bits(math.acos(c))})
    return {"notes": "Written by tests/meshops/make_fixtures.py from CPython " + sys.version.split()[0] + ".",
            "numbers": rows, "sums": sums, "hypots": hypots, "trig": trig}


def main():
    for d in ("game", "gen", "vehicle", "expected"):
        shutil.rmtree(os.path.join(HERE, d), ignore_errors=True)
    game = os.path.join(HERE, "game")
    os.makedirs(os.path.join(game, "testcar"))
    os.makedirs(os.path.join(game, "shared"))
    os.makedirs(os.path.join(HERE, "gen"))
    os.makedirs(os.path.join(HERE, "vehicle", "meshes"))
    for name in ("Body__stretched", "Body__regions", "Body__pieces", "Body__paint", "Body__shapes", "Body__axle_clear",
                 "Body__insert", "Body__relocate", "Body__our_shapes"):
        body().write(os.path.join(game, "testcar", name + ".obj"), crlf=name == "Body__regions")
    edge_values().write(os.path.join(game, "testcar", "Body__edge_values.obj"))
    axle().write(os.path.join(game, "testcar", "Axles__portal.obj"))
    axle(x_flip=-1.0).write(os.path.join(game, "testcar", "Axles__coil.obj"))
    axle().write(os.path.join(game, "testcar", "Axles__skinned_shapes.obj"))
    part().write(os.path.join(HERE, "vehicle", "meshes", "part.obj"))
    part(0.4).write(os.path.join(game, "shared", "part_LOD0.obj"))
    part(1.6).write(os.path.join(HERE, "gen", "part_boxes.obj"))
    # Our own trucks' added parts (their manifest data, no game geometry): the many near-axis plate and tube normals
    # whose zero components get their sign from Python's compensated sum.
    ours = json.load(open(os.path.join(ROOT, "vehicles", "glyptodon", "vehicle.json")))
    DEFINITION["meshes"]["Body/our_shapes"] = {"file": "our_shapes.obj", "stretch": False, "ops": [
        op for op in ours["meshes"]["Parts/Mammoth/Mammoth_body_LOD3"]["ops"] if op["op"] in ("addBoxes", "addPlates", "addTubes")]}
    with open(os.path.join(HERE, "vehicle", "vehicle.json"), "w") as f:
        json.dump(DEFINITION, f, indent=1)
        f.write("\n")

    # build_vehicle.py reads ROOT/extracted and the vehicle's own generated/: lay them out in a scratch copy.
    with tempfile.TemporaryDirectory() as tmp:
        shutil.copytree(game, os.path.join(tmp, "extracted"))
        shutil.copytree(os.path.join(HERE, "vehicle"), os.path.join(tmp, "vehicle"))
        shutil.copytree(os.path.join(HERE, "gen"), os.path.join(tmp, "vehicle", "generated"))
        build_vehicle.ROOT = tmp
        sys.argv = ["build_vehicle.py", os.path.join(tmp, "vehicle", "vehicle.json")]
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            build_vehicle.main()
        shutil.copytree(os.path.join(tmp, "vehicle", "build"), os.path.join(HERE, "expected"))
    with open(os.path.join(HERE, "expected.log"), "w") as f:
        f.write(out.getvalue())
    with open(os.path.join(HERE, "numbers.json"), "w") as f:
        data = numbers()
        f.write("{\"notes\": " + json.dumps(data["notes"]))
        for key in ("numbers", "sums", "hypots", "trig"):
            f.write(f",\n\"{key}\": [\n" + ",\n".join(json.dumps(row) for row in data[key]) + "\n]")
        f.write("}\n")
    print(out.getvalue(), end="")


if __name__ == "__main__":
    main()
