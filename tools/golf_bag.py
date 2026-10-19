"""Generate the canary golf bag: a low-poly golf bag with clubs, strapped to a car's roof.

Usage: python3 tools/golf_bag.py vehicles/<car>/vehicle.json            write meshes/golf_bag_LOD0-3.obj
       python3 tools/golf_bag.py vehicles/<car>/vehicle.json --measure  print the roof heights the
                                                                        "golfBag" block needs, from the
                                                                        car's extracted body (game data)

The bag is our own geometry (CC BY-SA), built from primitives, deterministic, and placed from the
manifest's "golfBag" block, so generating it needs no game data:
  "golfBag": {"x": 0.2, "z": -0.75, "roofY": 2.09, "legY": 2.07, "headsForward": true,
              "uv": {"bag": [u, v], "trim": [u, v], "metal": [u, v]}}
x and z are the bag's centre on the roof in Unity car-root space (x right, z forward); roofY is the
roof height under the bag and legY the lowest roof height where the straps meet it (--measure finds
both). The uv points are flat colours on the car's own atlas (one point per colour, as the cab
masters use). The output is in the repository's OBJ convention: car-root space, metres, x negated,
counter-clockwise outward faces; build_vehicle.py's insertPart adds it to each body LOD.
"""
import json, math, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

RADIUS = 0.125        # bag body
LENGTH = 0.92         # base to collar rim
BAND_GAP = 0.003      # strap band clear of the bag
BAND_THICK = 0.010
BAND_WIDTH = 0.035
# Per LOD: polygon sides of the round parts, and which details are kept.
LODS = [
    {"sides": 8, "base": True, "collar": True, "pocket": True, "legs": True, "clubs": "full", "straps": True},
    {"sides": 8, "base": True, "collar": True, "pocket": True, "legs": False, "clubs": "full", "straps": True},
    {"sides": 6, "base": False, "collar": True, "pocket": False, "legs": False, "clubs": "blocks", "straps": True},
    {"sides": 6, "base": False, "collar": False, "pocket": False, "legs": False, "clubs": "block", "straps": False},
]


def sub(a, b): return [a[i] - b[i] for i in range(3)]
def add(a, b): return [a[i] + b[i] for i in range(3)]
def mul(a, s): return [a[i] * s for i in range(3)]
def dot(a, b): return sum(a[i] * b[i] for i in range(3))
def cross(a, b): return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]
def unit(a):
    n = math.sqrt(dot(a, a))
    return [c / n for c in a]


class Mesh:
    """Closed pieces with per-corner normals and one atlas point per piece."""

    def __init__(self):
        self.v, self.vn, self.vt, self.faces = [], [], [], []

    def uv(self, point):
        if list(point) not in self.vt:
            self.vt.append(list(point))
        return self.vt.index(list(point))

    def piece(self, verts, faces, normals, uv):
        """faces: lists of vertex indices into verts (CCW outward); normals: per face, a list of
        per-corner normals. Checks the piece is closed and outward (positive signed volume)."""
        vol = 0.0
        for f in faces:
            for k in range(1, len(f) - 1):
                vol += dot(verts[f[0]], cross(verts[f[k]], verts[f[k + 1]])) / 6
        if vol <= 0:
            raise SystemExit(f"piece with {len(faces)} faces is inside out (volume {vol:.6f})")
        base, t = len(self.v), self.uv(uv)
        self.v += verts
        for f, ns in zip(faces, normals):
            corners = []
            for vi, n in zip(f, ns):
                self.vn.append(n)
                corners.append((base + vi, t, len(self.vn) - 1))
            self.faces.append(corners)

    def prism(self, centre, axis, u, profile, z0, z1, uv, smooth=False):
        """A closed prism along unit axis from centre+z0*axis to centre+z1*axis, with the 2-D profile
        (counter-clockwise in the (u, axis x u) plane). smooth: radial normals on the sides."""
        v_dir = cross(axis, u)
        u_dir = cross(v_dir, axis)          # (u, v, axis) right-handed
        n = len(profile)
        verts = []
        for z in (z0, z1):
            for pu, pv in profile:
                verts.append(add(centre, add(add(mul(u_dir, pu), mul(v_dir, pv)), mul(axis, z))))
        faces, normals = [], []
        for i in range(n):
            j = (i + 1) % n
            faces.append([i, j, n + j, n + i])
            if smooth:
                ri = unit(add(mul(u_dir, profile[i][0]), mul(v_dir, profile[i][1])))
                rj = unit(add(mul(u_dir, profile[j][0]), mul(v_dir, profile[j][1])))
                normals.append([ri, rj, rj, ri])
            else:
                fn = unit(cross(sub(verts[j], verts[i]), sub(verts[n + i], verts[i])))
                normals.append([fn] * 4)
        faces.append(list(range(n, 2 * n)))
        normals.append([axis] * n)
        faces.append(list(range(n - 1, -1, -1)))
        normals.append([mul(axis, -1)] * n)
        self.piece(verts, faces, normals, uv)

    def band(self, centre, radius, sides, phase, uv):
        """A strap: a closed band around the z axis through centre, its section a flat triangle with
        the point on the bag and the broad face outward (three faces per segment)."""
        r0, r1 = radius, radius + BAND_THICK
        verts = []
        for i in range(sides):
            a = phase + 2 * math.pi * i / sides
            c, s = math.cos(a), math.sin(a)
            for r, dz in ((r0, 0.0), (r1, -BAND_WIDTH / 2), (r1, BAND_WIDTH / 2)):
                verts.append([centre[0] + r * c, centre[1] + r * s, centre[2] + dz])
        faces, normals = [], []
        for i in range(sides):
            j = (i + 1) % sides
            a, b = 3 * i, 3 * j
            for k in range(3):
                k1 = (k + 1) % 3
                faces.append([a + k, b + k, b + k1, a + k1])
                fn = unit(cross(sub(verts[b + k], verts[a + k]), sub(verts[a + k1], verts[a + k])))
                normals.append([fn] * 4)
        self.piece(verts, faces, normals, uv)

    def write(self, path, header):
        with open(path, "w") as f:
            for line in header:
                f.write(f"# {line}\n")
            for x, y, z in self.v:
                f.write(f"v {x:.6f} {y:.6f} {z:.6f}\n")
            for u, v in self.vt:
                f.write(f"vt {u:.6f} {v:.6f}\n")
            for x, y, z in self.vn:
                f.write(f"vn {x:.6f} {y:.6f} {z:.6f}\n")
            for face in self.faces:
                f.write("f " + " ".join(f"{v + 1}/{t + 1}/{n + 1}" for v, t, n in face) + "\n")

    def triangles(self):
        return sum(len(f) - 2 for f in self.faces)


def circle(radius, sides, phase):
    return [(radius * math.cos(phase + 2 * math.pi * i / sides), radius * math.sin(phase + 2 * math.pi * i / sides))
            for i in range(sides)]


def rect(hu, hv):
    return [(-hu, -hv), (hu, -hv), (hu, hv), (-hu, hv)]


def bag(spec, lod):
    """One LOD of the bag in OBJ space (x negated)."""
    uv = spec["uv"]
    sides = lod["sides"]
    phase = math.pi / 2 - math.pi / sides     # a flat face on the roof, under the bag
    # The bag and its straps are polygons with a flat face down, so the band's lowest face sits
    # (R + gap + thickness) * cos(pi / sides) below the axis; it rests 2 mm into the roof.
    cx, cy = -spec["x"], spec["roofY"] + (RADIUS + BAND_GAP + BAND_THICK) * math.cos(math.pi / sides) - 0.002
    zc = spec["z"]
    fwd = 1.0 if spec.get("headsForward", True) else -1.0
    z_base, z_top = zc - fwd * LENGTH / 2, zc + fwd * LENGTH / 2
    axis = [0.0, 0.0, fwd]
    xu = [fwd, 0.0, 0.0]                      # keeps axis x u pointing up for either direction
    m = Mesh()
    centre = [cx, cy, z_base]
    # Distances along the axis from the base end.
    m.prism(centre, axis, xu, circle(RADIUS, sides, phase), 0.05 if lod["base"] else 0.0, LENGTH - 0.05, uv["bag"], smooth=True)
    if lod["base"]:
        m.prism(centre, axis, xu, circle(RADIUS * 1.05, sides, phase), 0.0, 0.07, uv["trim"], smooth=True)
    if lod["collar"]:
        m.prism(centre, axis, xu, circle(RADIUS * 1.08, sides, phase), LENGTH - 0.07, LENGTH, uv["trim"], smooth=True)
    if lod["pocket"]:
        # On the upper outside of the bag, a ball pocket in trim colour.
        a = math.radians(55)
        side = 1 if spec["x"] >= 0 else -1          # outboard, in Unity x
        pc = [cx - side * (RADIUS - 0.012) * math.cos(a), cy + (RADIUS - 0.012) * math.sin(a), 0.0]
        out = unit([-side * math.cos(a), math.sin(a), 0.0])
        tangent = unit(cross(out, axis))      # so the profile's second axis points outward
        m.prism([pc[0], pc[1], z_base], axis, tangent, [(-0.05, -0.012), (0.05, -0.012), (0.05, 0.035), (-0.05, 0.035)],
                0.30, 0.62, uv["trim"])
    clubs(m, [cx, cy, z_top], axis, lod, uv)
    if lod["straps"]:
        for at in (0.24, 0.70):
            zs = z_base + fwd * at * LENGTH
            m.band([cx, cy, zs], RADIUS + BAND_GAP, sides, phase, uv["trim"])
            if lod["legs"]:
                for side in (-1, 1):
                    top = [cx + side * (RADIUS + BAND_GAP + BAND_THICK * 0.5), cy - 0.02, zs]
                    foot = [cx + side * (RADIUS + 0.10), spec["legY"] - 0.006, zs]
                    leg_axis = unit(sub(foot, top))
                    m.prism(top, leg_axis, [0.0, 0.0, 1.0], rect(BAND_WIDTH / 2, 0.004), 0.0,
                            math.dist(top, foot) + 0.004, uv["trim"])
    return m


def clubs(m, top, axis, lod, uv):
    """Club heads poking out of the collar: two woods in headcovers, three irons."""
    woods = [(-0.045, 0.04), (0.045, 0.045)]
    irons = [(-0.055, -0.035), (0.0, -0.055), (0.055, -0.03)]
    if lod["clubs"] == "block":
        m.prism(top, axis, [1.0, 0.0, 0.0], rect(0.07, 0.06), -0.02, 0.16, uv["trim"])
        return
    if lod["clubs"] == "blocks":
        m.prism(add(top, [0.0, 0.04, 0.0]), axis, [1.0, 0.0, 0.0], rect(0.09, 0.04), -0.02, 0.17, uv["trim"])
        m.prism(add(top, [0.0, -0.045, 0.0]), axis, [1.0, 0.0, 0.0], rect(0.09, 0.025), -0.02, 0.16, uv["metal"])
        return
    for dx, dy in woods:
        m.prism(add(top, [dx, dy, 0.0]), axis, [1.0, 0.0, 0.0], circle(0.045, 6, 0.0), -0.03, 0.15, uv["trim"], smooth=True)
    for k, (dx, dy) in enumerate(irons):
        base = add(top, [dx, dy, 0.0])
        m.prism(base, axis, [1.0, 0.0, 0.0], circle(0.008, 3, 0.0), -0.03, 0.12, uv["metal"])
        turn = math.radians((-25, 5, 30)[k])
        blade = [math.cos(turn), math.sin(turn), 0.0]
        m.prism(add(base, mul(axis, 0.12)), axis, blade, rect(0.04, 0.012), 0.0, 0.045, uv["metal"])


def measure(manifest_path, spec):
    """Roof heights from the car's extracted LOD0 body: under the bag, and where the strap legs land."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import meshlib
    manifest = json.load(open(manifest_path))
    donor = manifest["donor"]
    body = next(p for p in manifest["meshes"] if p.endswith("_body_LOD0"))
    obj = meshlib.Obj.read(os.path.join(ROOT, "extracted", donor.lower(), body.replace("/", "__") + ".obj"))
    tris = [[obj.v[c[0]] for c in f] for f in obj.faces]

    def height(x, z):
        best = None
        for t in tris:
            for k in range(1, len(t) - 1):
                a, b, c = t[0], t[k], t[k + 1]
                d = (b[2] - c[2]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[2] - c[2])
                if abs(d) < 1e-12:
                    continue
                w0 = ((b[2] - c[2]) * (x - c[0]) + (c[0] - b[0]) * (z - c[2])) / d
                w1 = ((c[2] - a[2]) * (x - c[0]) + (a[0] - c[0]) * (z - c[2])) / d
                w2 = 1 - w0 - w1
                if min(w0, w1, w2) < -1e-9:
                    continue
                y = w0 * a[1] + w1 * b[1] + w2 * c[1]
                best = y if best is None else max(best, y)
        return best

    cx, zc = -spec["x"], spec["z"]
    under = [height(cx + dx, zc + dz) for dx in (-RADIUS, 0.0, RADIUS) for dz in (-LENGTH / 2, -0.2, 0.0, 0.2, LENGTH / 2)]
    legs = [height(cx + side * (RADIUS + 0.10), zc + dz) for side in (-1, 1) for dz in (-0.25, 0.20)]
    print(json.dumps({"roofY": round(max(h for h in under if h is not None), 4),
                      "legY": round(min(h for h in legs if h is not None), 4),
                      "underBag": [None if h is None else round(h, 4) for h in under],
                      "atLegs": [None if h is None else round(h, 4) for h in legs]}))


def main():
    manifest_path = sys.argv[1]
    spec = json.load(open(manifest_path))["golfBag"]
    if "--measure" in sys.argv:
        measure(manifest_path, spec)
        return
    out_dir = os.path.join(os.path.dirname(os.path.abspath(manifest_path)), "meshes")
    os.makedirs(out_dir, exist_ok=True)
    for n, lod in enumerate(LODS):
        m = bag(spec, lod)
        path = os.path.join(out_dir, f"golf_bag_LOD{n}.obj")
        m.write(path, [f"golf_bag_LOD{n}: tools/golf_bag.py from {os.path.relpath(manifest_path, ROOT)}",
                       "car-root space, metres, x negated (right-handed); our own geometry, CC BY-SA 4.0"])
        print(f"{os.path.relpath(path, ROOT)}: {m.triangles()} triangles")


if __name__ == "__main__":
    main()
