"""Detail fixes on a Glyptodon-family cab master after tools/cab_doors.py, headless in Blender.

Usage: blender -b vehicles/<vehicle>/<cab>_master.blend --python tools/cab_fixes.py -- [--save]
Then tools/build_cab_part.sh <master> --derive as usual. Run it again and it changes nothing more.

- RearWallBacking goes from every LOD: a black sheet standing 8 cm inside the rear wall that the author
  found unnecessary. It was what hid the arched cutout along the bottom of the shell's rear wall (open
  from the cab's bottom edge up to z 1.17 across |x| < 0.9, about 1.8 x 0.18 m, a clear sight line
  through the empty cab to the grille), so RearWallSill closes that cutout in the wall's own plane.
- Intake_L/R, the louvred vents in the cowl sides: the top-front corner of each one's frame stood above
  the hood and cowl skin and showed as a black block on the hood. Every intake vertex with open sky above
  it is lowered to just under the surface over it, LOD by LOD, so only the louvres show in the opening.
- Door hinges: the old blobs (Hinge_L/R and DoorCatch_L/R, the front doors' upper and lower hinge;
  RearHinge_L/R and RearDoorCatch_L/R on the crew cab's rear doors) give way to DoorHinge_L/R and
  RearDoorHinge_L/R. Two per door on its front edge, each a knuckle on the shut line, a vertical cylinder
  (8 sides at LOD0, 6 at LOD1, a box at LOD2, none at LOD3) seated 2 mm into the skin and leaning with
  it where the upper one sits above the beltline.
- Door handles: the flat slab the window frames carried (DoorFrame, RearDoorFrame) goes, and
  DoorHandle_L/R and RearDoorHandle_L/R take its place over the door's dish (a door reference photo):
  a black pull grip standing off the inset on two short posts at its ends, the round lock at its rear
  end (away from the hinges, as on both doors in the photo). A box at LOD2, none at LOD3.
- The front shut line's cut left a 1.2 mm sliver of the old shell's raised upper-hinge boss (y -1.277,
  z 1.605..1.655, up to 2 cm proud) standing on the cowl side: shell faces hugging a shut line that stand
  well proud of the section go.
"""
import math, os, sys
import bpy, bmesh
from mathutils import Vector
from mathutils.bvhtree import BVHTree

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cab_doors as cd  # noqa: E402

HINGES = ((1.225, 1.290), (1.555, 1.620))   # lower (just under the swage step) and upper (from the belt up)
KNUCKLE_R = 0.010                # knuckle radius
SEAT = 0.002                     # the knuckle sinks this far into the skin, so nothing floats
# The pull handle, in door u (from the hinge line) and height: grip, posts at its ends, the lock at its rear end.
GRIP_U, GRIP_Z = (0.770, 0.940), (1.512, 1.538)
GRIP_OFF = (0.020, 0.036)        # the grip's back and front faces off the inset floor
POST = 0.018                     # post length along the grip
POST_Z = (1.516, 1.534)
LOCK = (0.931, 1.525, 0.009, 0.006)          # lock centre u, z, radius, how far it stands off the grip
SPIKE = (0.004, 0.004)           # a shell face within this of a shut line and this proud of the section goes
SEGMENTS = {0: 8, 1: 6, 2: 0}                # knuckle sides per LOD (0: a box)
OLD_HINGES = ("Hinge", "DoorCatch", "RearHinge", "RearDoorCatch")


def hinge_mesh(name, side, y_line, lod):
    """A door's two hinges on the shut line y_line."""
    b = cd.Builder(side, 0.0)
    segs = SEGMENTS[lod]
    for k, (z0, z1) in enumerate(HINGES):
        cx = lambda z: cd.x_out(z) + KNUCKLE_R - SEAT           # seated in the skin, leaning with it
        if segs:
            rings = [[b.p(y_line + KNUCKLE_R * math.sin(2 * math.pi * j / segs), z,
                          cx(z) + KNUCKLE_R * math.cos(2 * math.pi * j / segs)) for j in range(segs)] for z in (z0, z1)]
            for j in range(segs):
                i = (j + 1) % segs
                mid = 2 * math.pi * (j + 0.5) / segs
                b.face(f"knuckle{k}", [rings[0][j], rings[0][i], rings[1][i], rings[1][j]], (math.cos(mid), math.sin(mid), 0))
            b.face(f"cap{k}a", rings[0], (0, 0, -1))
            b.face(f"cap{k}b", rings[1], (0, 0, 1))
        else:
            box(b, f"knuckle{k}", (y_line - KNUCKLE_R, y_line + KNUCKLE_R), (z0, z1), lambda z: cx(z) - KNUCKLE_R, 2 * KNUCKLE_R)
    return b.mesh(name)


def handle_mesh(name, side, y0, lod):
    """A door's pull handle over its dish, for the door hinged at y0."""
    b = cd.Builder(side, y0)
    floor = lambda z: cd.x_out(z) - cd.INSET_DEPTH
    (ua, ub), (za, zb) = GRIP_U, GRIP_Z
    if lod >= 2:
        box(b, "grip", (ua, ub), (za, zb), lambda z: floor(z) + GRIP_OFF[0], GRIP_OFF[1] - GRIP_OFF[0])
        return b.mesh(name)
    box(b, "grip", (ua, ub), (za, zb), lambda z: floor(z) + GRIP_OFF[0], GRIP_OFF[1] - GRIP_OFF[0])
    for pu in ((ua, ua + POST), (ub - POST, ub)):
        box(b, f"post{pu[0]}", pu, POST_Z, lambda z: floor(z) - 0.002, GRIP_OFF[0] + 0.002)
    lu, lz, lr, lout = LOCK
    segs = 6
    x0 = lambda: floor(lz) + GRIP_OFF[1] - 0.001
    ring = lambda x: [b.p(lu + lr * math.cos(2 * math.pi * j / segs), lz + lr * math.sin(2 * math.pi * j / segs), x) for j in range(segs)]
    back, front = ring(x0()), ring(x0() + lout)
    for j in range(segs):
        i = (j + 1) % segs
        mid = 2 * math.pi * (j + 0.5) / segs
        b.face("lock", [back[j], back[i], front[i], front[j]], (0, math.cos(mid), math.sin(mid)))
    b.face("lock_face", front, (1, 0, 0))
    return b.mesh(name)


def strip_handle_slabs():
    """Deletes the flat handle slab from the window frames (faces standing on the skin below the window)."""
    removed = {}
    for part in ("DoorFrame", "RearDoorFrame"):
        for side in ("L", "R"):
            for n in range(4):
                ob = cd.lod_object(f"{part}_{side}", n)
                if ob:
                    k = cd.strip_faces(ob, lambda c, nrm, ya, yb: abs(c.x) > 0.99 and c.z < 1.6)
                    if k:
                        removed[ob.name] = k
            cd.far_hashes(f"{part}_{side}")
    return removed


def shut_lines():
    """(y at height z) of every shut line the shell was cut along."""
    lines = [lambda z: cd.HINGE_Y + cd.raked(z), lambda z: cd.FRONT_REAR]
    if cd.lod_object("RearDoor_L", 0):
        lines += [lambda z: cd.REAR_FRONT + cd.raked(z), lambda z: cd.REAR_REAR]
    return lines


def remove_spikes():
    """Deletes shell faces that hug a shut line and stand proud of the section (cut remnants of old bosses)."""
    near, proud = SPIKE
    lines = shut_lines()

    def doomed(ob):
        mw = ob.matrix_world
        out = []
        for p in ob.data.polygons:
            vs = [mw @ ob.data.vertices[i].co for i in p.vertices]
            hug = any(all(abs(v.y - line(v.z)) < near for v in vs) for line in lines)
            if hug and max(abs(v.x) - cd.x_out(v.z) for v in vs) > proud:
                out.append(p.index)
        return out

    removed = {}
    for n in range(4):
        ob = cd.lod_object("Shell", n)
        bad = doomed(ob)
        if bad:
            bm = bmesh.new()
            bm.from_mesh(ob.data)
            bm.faces.ensure_lookup_table()
            bmesh.ops.delete(bm, geom=[bm.faces[i] for i in bad], context="FACES")
            bm.to_mesh(ob.data)
            bm.free()
            removed[ob.name] = len(bad)
    cd.far_hashes("Shell")
    return removed


def spike_gate():
    """Paint faces at LOD0 within 6 cm of a shut line with a vertex more than 2 mm outboard of the section,
    up to the door top (the roof-edge ledge above it overhangs by design), outside the swage step's band
    (where the old shell's step sits up to 2.4 mm off the door's)."""
    lines = shut_lines()
    found = []
    for ob in bpy.data.collections["LOD0"].objects:
        m = ob.data
        if ob.type != "MESH" or not m.materials or m.materials[0].name != "Paint":
            continue
        mw = ob.matrix_world
        for p in m.polygons:
            for v in (mw @ m.vertices[i].co for i in p.vertices):
                if cd.Z0 < v.z < cd.ZTOP - cd.GAP and not 1.295 < v.z < 1.32 and any(abs(v.y - line(v.z)) < 0.06 for line in lines) \
                        and abs(v.x) - cd.x_out(v.z) > 0.002:
                    found.append((ob.name, p.index, round(v.y, 3), round(v.z, 3), round((abs(v.x) - cd.x_out(v.z)) * 1000, 1)))
                    break
    return found


def box(b, group, ys, zs, x_at, depth):
    """A closed box between ys and zs, from x_at(z) outward by depth (it leans with x_at)."""
    (ya, yb), (za, zb) = ys, zs
    c = {(i, j, k): b.p((ya, yb)[i], (za, zb)[j], x_at((za, zb)[j]) + depth * k) for i in (0, 1) for j in (0, 1) for k in (0, 1)}
    b.face(group + "o", [c[0, 0, 1], c[1, 0, 1], c[1, 1, 1], c[0, 1, 1]], (1, 0, 0))
    b.face(group + "i", [c[0, 0, 0], c[1, 0, 0], c[1, 1, 0], c[0, 1, 0]], (-1, 0, 0))
    b.face(group + "f", [c[0, 0, 0], c[0, 1, 0], c[0, 1, 1], c[0, 0, 1]], (0, -1, 0))
    b.face(group + "r", [c[1, 0, 0], c[1, 1, 0], c[1, 1, 1], c[1, 0, 1]], (0, 1, 0))
    b.face(group + "b", [c[0, 0, 0], c[1, 0, 0], c[1, 0, 1], c[0, 0, 1]], (0, 0, -1))
    b.face(group + "t", [c[0, 1, 0], c[1, 1, 0], c[1, 1, 1], c[0, 1, 1]], (0, 0, 1))


def trees(objects):
    """World-space BVH trees of the objects' meshes (built from the data, so hidden LODs work too)."""
    out = []
    for o in objects:
        mw = o.matrix_world
        out.append(BVHTree.FromPolygons([mw @ v.co for v in o.data.vertices], [p.vertices[:] for p in o.data.polygons]))
    return out


def covered(bvhs, w):
    return any(t.ray_cast(w + Vector((0, 0, 0.0005)), Vector((0, 0, 1)))[0] is not None for t in bvhs)


def surface_below(bvhs, w):
    """The highest surface under (w.x, w.y) seen from above, or None."""
    hits = [t.ray_cast(Vector((w.x, w.y, 4.0)), Vector((0, 0, -1)))[0] for t in bvhs]
    zs = [h.z for h in hits if h is not None]
    return max(zs) if zs else None


def lod_others(n):
    coll = bpy.data.collections.get(f"LOD{n}")
    return [o for o in coll.objects if o.type == "MESH" and not o.name.startswith("Intake")] if coll else []


def clip_intakes():
    """Lowers each intake vertex that has open sky above it to just under the surface over it, LOD by
    LOD against that LOD's own parts. Returns the vertices moved per object."""
    moved = {}
    for n in range(4):
        bvhs = trees(lod_others(n))
        for side in ("L", "R"):
            ob = cd.lod_object(f"Intake_{side}", n)
            if not ob:
                continue
            mw, inv = ob.matrix_world, ob.matrix_world.inverted()
            count = 0
            for v in ob.data.vertices:
                w = mw @ v.co
                if covered(bvhs, w):
                    continue
                top = surface_below(bvhs, w)
                if top is not None and top < w.z:
                    w.z = top - 0.003
                    v.co = inv @ w
                    count += 1
            moved[ob.name] = count
    return moved


def intake_gate():
    """Intake vertices with open sky above them, per LOD (should be none)."""
    out = []
    for n in range(4):
        bvhs = trees(lod_others(n))
        out.append(sum(not covered(bvhs, ob.matrix_world @ v.co)
                       for ob in (cd.lod_object(f"Intake_{s}", n) for s in ("L", "R")) if ob for v in ob.data.vertices))
    return out


# The cutout's edge, measured on both cabs (|x|, z), and the closer's overlap behind the wall above it.
CUTOUT = [(0.905, 0.988), (0.90, 0.99), (0.80, 1.03), (0.70, 1.14), (0.60, 1.17)]
SILL_OVERLAP = 0.010


def rear_wall_y():
    """The rear wall's plane: the rearmost shell vertex low down near the centreline."""
    sh = cd.lod_object("Shell", 0)
    return max(w.y for w in (sh.matrix_world @ v.co for v in sh.data.vertices) if w.z < 1.5 and abs(w.x) < 0.5)


def sill_mesh(name, y):
    """A panel 1 mm inside the rear wall covering the cutout along its bottom, following the cutout's arched
    edge with a centimetre to spare, double-sided."""
    edge = [(x, z + SILL_OVERLAP) for x, z in CUTOUT[1:]]
    outline = ([(-CUTOUT[0][0], cd.Z0), (CUTOUT[0][0], cd.Z0)] + edge + [(-x, z) for x, z in reversed(edge)])
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([(x, y, z) for x, z in outline], [], [list(range(len(outline)))])
    if mesh.polygons[0].normal.y < 0:
        mesh.flip_normals()
    attr = mesh.attributes.new("two_sided", "INT", "FACE")
    attr.data[0].value = 1
    return mesh


def main():
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    black = bpy.data.materials["Black"]
    crew_cab = bool(cd.lod_object("RearDoor_L", 0))
    paint = bpy.data.materials["Paint"]
    report = {"RearWallBacking removed": cd.remove_part("RearWallBacking")}
    cd.remove_part("RearWallSill")
    y = rear_wall_y() - 0.001
    for n in range(4):
        cd.place(bpy.data.collections[f"LOD{n}"], f"RearWallSill.LOD{n}", sill_mesh(f"RearWallSill.LOD{n}", y), paint)
    cd.far_hashes("RearWallSill")
    report["RearWallSill at y"] = round(y, 4)
    report["intake vertices lowered"] = clip_intakes()
    for side in ("L", "R"):
        for part in OLD_HINGES:
            removed = cd.remove_part(f"{part}_{side}")
            if removed:
                report[f"{part}_{side} removed"] = removed
    for prefix, y_line in (("DoorHinge", cd.HINGE_Y),) + ((("RearDoorHinge", cd.REAR_FRONT),) if crew_cab else ()):
        for side in ("L", "R"):
            cd.remove_part(f"{prefix}_{side}")
            for n in SEGMENTS:
                cd.place(bpy.data.collections[f"LOD{n}"], f"{prefix}_{side}.LOD{n}", hinge_mesh(f"{prefix}_{side}.LOD{n}", side, y_line, n), black)
            cd.far_hashes(f"{prefix}_{side}")
            report[f"{prefix}_{side} tris"] = [cd.tris(f"{prefix}_{side}", n) for n in range(4)]
    report["handle slabs removed"] = strip_handle_slabs()
    for prefix, y0 in (("DoorHandle", cd.HINGE_Y),) + ((("RearDoorHandle", cd.REAR_FRONT),) if crew_cab else ()):
        for side in ("L", "R"):
            cd.remove_part(f"{prefix}_{side}")
            for n in (0, 1, 2):
                cd.place(bpy.data.collections[f"LOD{n}"], f"{prefix}_{side}.LOD{n}", handle_mesh(f"{prefix}_{side}.LOD{n}", side, y0, n), black)
            cd.far_hashes(f"{prefix}_{side}")
            report[f"{prefix}_{side} tris"] = [cd.tris(f"{prefix}_{side}", n) for n in range(4)]
    report["shut-line spikes removed"] = remove_spikes()
    report["spike gate (paint proud > 2 mm near shut lines)"] = spike_gate()
    for part in ("Intake_L", "Intake_R"):
        cd.far_hashes(part)
    report["intake vertices with open sky (gate)"] = intake_gate()
    print(f"cab_fixes: {report}")
    if "--save" in args:
        bpy.ops.wm.save_mainfile()
        print(f"cab_fixes: saved {bpy.data.filepath}")


main()
