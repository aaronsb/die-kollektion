"""Replace a Glyptodon-family cab master's roof with generated geometry, headless in Blender.

Usage: blender -b meshes/glyptodon/<cab>_master.blend --python tools/cab_roof.py -- [--save]
Then tools/build_cab_part.sh <master> --derive as usual (the new parts bring their own far LODs, so
--derive leaves them alone).

Writes, in every LOD collection (Blender coordinates: +X the truck's left, front toward -Y, Z up):
- RoofFront: the roof from the front rail (RoofBridge, kept) to a seam in the flat gap behind the
  hatch, with a flat rib-free bay on the -X side for the hatch, a skirt down behind the rail and a
  down-facing ceiling quad under it.
- RoofRear: the roof from the seam to the rear edge of the shell (the 2.4 cm overhang).
- Hatch: the round domed hatch, its boss and lever, standing on the bay (the reference model's old dome footprint).
- Variants/RoofFront_Plain.LOD0-3: the front section ribbed right across, for the plain-roof upgrade;
  the Variants collection is not a LOD collection, so the exporter ignores it.
The old roof parts it supersedes (Roof, Hatch, Roof_L/R, Header_L/R) go from every LOD, and so do
the crew cab's painted patch faces in RoofFitting (its black interior fitting stays).

The roof is one skin at the front rail's height (2.4188), meeting the shell's roll-over at the sides
by a 28-degree chamfer that dips under it, and its rear lip by a short slope that dips under the
shell's flat plate, so no ledge shows and no crack opens. The ribs keep the original cab's profile:
across the truck, 7.4 mm tall, 40 mm on top, 8 mm flanks, ends ramped over 16 mm, at 0.162 m pitch from
y -1.058 to 0.2 m short of the rear edge. Every cell is a planar quad on a grid shared by both sections
and the variant (no T-junctions at the seam); the hip corners at rib ends are split into two planar
triangles. The script is idempotent: re-running replaces its own parts. It also sets every mesh's
viewport shading to the exporter's (smooth within 35 degrees, flat for "flat" materials).
"""
import math, os, sys
import bpy, bmesh

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from export_master import part_hash, SMOOTH_DEGREES  # noqa: E402

SKIN = 2.4188                    # roof skin height, the front rail's top
FRONT_Y = -1.152                 # skin front edge, over the front rail
SEAM_Y = -0.167                  # front/rear section seam, mid-gap between the ribs at -0.248 and -0.086
RIB_H, RIB_TOP, RIB_FLANK, RIB_RAMP = 0.0074, 0.040, 0.008, 0.016
RIB_PITCH, RIB_FIRST, RIB_X = 0.162, -1.058, 0.754      # RIB_X: |x| where a full rib's ramp meets the skin
RIB_CLEAR_REAR = 0.20            # no rib centred closer than this to the rear edge
FLAT_X, EDGE_X, EDGE_DROP = 0.792, 0.812, 0.0108          # side chamfer: flat to FLAT_X, down EDGE_DROP by EDGE_X
REAR_FLAT, REAR_DROP = 0.012, 0.0058                      # rear slope: from rear-REAR_FLAT down REAR_DROP at the edge
CEILING = (0.785, -1.150, -0.140)                         # |x|, y range of the front ceiling quad (the shell's plate covers the rest)
SKIRT_Z = 2.406                  # foot of the skirt under the skin's front edge, just above the front rail's underside
HATCH_C, HATCH_R = (-0.328, -0.6365), 0.420               # the old dome's footprint
BAY_MARGIN = 0.030               # flat skin between the hatch and the ramp feet of the ribs cut by the bay
LEVER_DIR = (0.21, 0.41)         # the lever runs from the boss toward the rear-left, as on the old hatch
OLD_PARTS = ("Roof", "Hatch", "Roof_L", "Roof_R", "Header_L", "Header_R", "RoofFront", "RoofRear")
# Dome profile (radius, height over the skin): flange, lip, dome, then the boss wall and dished top.
DOME = [(0.420, 0.0), (0.405, 0.005), (0.390, 0.007), (0.300, 0.022), (0.180, 0.033), (0.100, 0.037)]
BOSS = [(0.100, 0.043), (0.088, 0.044)]
BOSS_CENTRE = 0.042


def rib_profile(t, top_lo, top_hi, foot_lo, foot_hi):
    """0 at and beyond the feet, 1 between the tops, linear between."""
    if t <= foot_lo or t >= foot_hi:
        return 0.0
    if t < top_lo:
        return (t - foot_lo) / (top_lo - foot_lo)
    if t > top_hi:
        return (foot_hi - t) / (foot_hi - top_hi)
    return 1.0


class Rib:
    """One rib segment: centred at y, feet at x0..x1 (ramps inside that)."""

    def __init__(self, y, x0, x1):
        self.y, self.x0, self.x1 = y, x0, x1

    def ys(self):
        h = RIB_TOP / 2
        return (self.y - h - RIB_FLANK, self.y - h, self.y + h, self.y + h + RIB_FLANK)

    def xs(self):
        return (self.x0, self.x0 + RIB_RAMP, self.x1 - RIB_RAMP, self.x1)

    def height(self, x, y):
        a, b, c, d = self.ys()
        p, q, r, s = self.xs()
        return RIB_H * min(rib_profile(y, b, c, a, d), rib_profile(x, q, r, p, s))


def base_height(x, y, rear_y):
    """The skin with its side chamfers and rear slope."""
    z = SKIN
    ax = abs(x)
    if ax > FLAT_X:
        z = min(z, SKIN - EDGE_DROP * (ax - FLAT_X) / (EDGE_X - FLAT_X))
    if y > rear_y - REAR_FLAT:
        z = min(z, SKIN - REAR_DROP * (y - (rear_y - REAR_FLAT)) / REAR_FLAT)
    return z


def rib_centres(rear_y):
    ys, k = [], 0
    while RIB_FIRST + k * RIB_PITCH <= rear_y - RIB_CLEAR_REAR:
        ys.append(round(RIB_FIRST + k * RIB_PITCH, 4))
        k += 1
    return ys


def hatch_bay_x():
    """The +X edge of the bay: where the ribs it cuts have their feet."""
    return round(HATCH_C[0] + HATCH_R + BAY_MARGIN, 4)


def section_ribs(kind, rear_y):
    """Rib segments of one section: 'front' (hatch bay), 'plain' (front, ribbed across), 'rear'."""
    ribs = []
    for y in rib_centres(rear_y):
        if kind == "rear":
            if y > SEAM_Y:
                ribs.append(Rib(y, -RIB_X, RIB_X))
            continue
        if y > SEAM_Y:
            continue
        foot = y - RIB_TOP / 2 - RIB_FLANK, y + RIB_TOP / 2 + RIB_FLANK
        in_bay = foot[1] > HATCH_C[1] - HATCH_R - BAY_MARGIN and foot[0] < HATCH_C[1] + HATCH_R + BAY_MARGIN
        if kind == "front" and in_bay:
            ribs.append(Rib(y, hatch_bay_x(), RIB_X))
        else:
            ribs.append(Rib(y, -RIB_X, RIB_X))
    return ribs


def grid_x(rear_y):
    """X breakpoints shared by every section and variant, so the seam has no T-junctions."""
    xs = {-EDGE_X, -FLAT_X, FLAT_X, EDGE_X}
    for kind in ("front", "plain", "rear"):
        for rib in section_ribs(kind, rear_y):
            xs.update(rib.xs())
    return sorted(xs)


def add_cell(bm, vert, quad, heights, h):
    """Adds one grid cell, a quad when planar, else the two triangles closer to the true surface h."""
    (x0, y0), (x1, y1) = quad
    z00, z10, z11, z01 = heights
    if abs((z00 + z11) - (z10 + z01)) < 1e-7:
        bm.faces.new((vert(x0, y0, z00), vert(x1, y0, z10), vert(x1, y1, z11), vert(x0, y1, z01)))
        return
    centre = h((x0 + x1) / 2, (y0 + y1) / 2)
    if abs((z00 + z11) / 2 - centre) <= abs((z10 + z01) / 2 - centre):
        tris = ((0, 1, 2), (0, 2, 3))           # split along 00-11
    else:
        tris = ((0, 1, 3), (1, 2, 3))           # split along 10-01
    corners = [(x0, y0, z00), (x1, y0, z10), (x1, y1, z11), (x0, y1, z01)]
    for t in tris:
        bm.faces.new([vert(*corners[i]) for i in t])


def roof_mesh(name, kind, rear_y, y0, y1, ribs_mode="full", ceiling=False):
    """One roof section as a mesh. ribs_mode: 'full' (shaped ribs), 'tops' (rib tops as raised quads
    over a plain skin, for LOD2) or 'none' (LOD3)."""
    ribs = section_ribs(kind, rear_y)
    shaped = ribs if ribs_mode == "full" else []

    def h(x, y):
        z = base_height(x, y, rear_y)
        return z + max((r.height(x, y) for r in shaped), default=0.0)

    xs = grid_x(rear_y) if ribs_mode == "full" else [-EDGE_X, -FLAT_X, FLAT_X, EDGE_X]
    ys = {y0, y1}
    for r in shaped:
        ys.update(t for t in r.ys() if y0 < t < y1)
    if y1 >= rear_y - 1e-6:
        ys.add(rear_y - REAR_FLAT)
    ys = sorted(ys)
    bm = bmesh.new()
    verts = {}

    def vert(x, y, z):
        key = (round(x, 6), round(y, 6), round(z, 6))
        if key not in verts:
            verts[key] = bm.verts.new(key)
        return verts[key]

    def facet(x, y, z):
        return bm.verts.new((x, y, z))

    def on_rib(x, y):
        return any(r.xs()[0] < x < r.xs()[3] and r.ys()[0] < y < r.ys()[3] for r in shaped)

    def on_edge(x, y):
        return abs(x) > FLAT_X or y > rear_y - REAR_FLAT

    # Rib, chamfer and rear-slope faces share no vertices with the skin or each other. The exporter
    # smooths across anything under 35 degrees, which these slopes are, and a shared vertex would
    # tilt the normals of the long flat skin cells beside it and streak them.
    for j in range(len(ys) - 1):
        for i in range(len(xs) - 1):
            xa, xb, ya, yb = xs[i], xs[i + 1], ys[j], ys[j + 1]
            cx, cy = (xa + xb) / 2, (ya + yb) / 2
            add_cell(bm, facet if on_rib(cx, cy) or on_edge(cx, cy) else vert, ((xa, ya), (xb, yb)),
                     (h(xa, ya), h(xb, ya), h(xb, yb), h(xa, yb)), h)
    if ribs_mode == "tops":
        for r in ribs:
            _, b, c, _ = r.ys()
            _, q, rr, _ = r.xs()
            z = SKIN + RIB_H
            bm.faces.new((vert(q, b, z), vert(rr, b, z), vert(rr, c, z), vert(q, c, z)))
    if y0 == FRONT_Y:
        # A skirt under the skin's front edge, behind the front rail, so no sight line runs in under
        # the skin between the rail's top and the skin.
        for xa, xb in zip(xs, xs[1:]):
            bm.faces.new((vert(xa, y0, SKIRT_Z), vert(xb, y0, SKIRT_Z), vert(xb, y0, h(xb, y0)), vert(xa, y0, h(xa, y0))))
    if ceiling:
        cx, ca, cb = CEILING
        z = SKIN - 0.002
        bm.faces.new((vert(-cx, ca, z), vert(-cx, cb, z), vert(cx, cb, z), vert(cx, ca, z)))   # faces down
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    return mesh


def dome_height(r):
    """The hatch dome's height over the skin at radius r (the boss top inside the boss)."""
    if r >= DOME[0][0]:
        return 0.0
    for (ra, za), (rb, zb) in zip(DOME, DOME[1:]):
        if rb <= r <= ra:
            return za + (zb - za) * (ra - r) / (ra - rb)
    return BOSS[-1][1]


def box(bm, p0, p1, width, z0a, z0b, thick):
    """A box along p0->p1 (plan), bottom from z0a at p0 to z0b at p1, open underneath."""
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    n = math.hypot(dx, dy)
    nx, ny = -dy / n * width / 2, dx / n * width / 2
    b = [(p0[0] - nx, p0[1] - ny, z0a), (p1[0] - nx, p1[1] - ny, z0b),
         (p1[0] + nx, p1[1] + ny, z0b), (p0[0] + nx, p0[1] + ny, z0a)]
    t = [(x, y, z + thick) for x, y, z in b]
    bv = [bm.verts.new(c) for c in b]
    tv = [bm.verts.new(c) for c in t]
    bm.faces.new(tv)
    for i in range(4):
        k = (i + 1) % 4
        bm.faces.new((bv[i], bv[k], tv[k], tv[i]))


def hatch_mesh(name, segments, boss=True, lever=True):
    cx, cy = HATCH_C
    profile = DOME + (BOSS if boss else [])
    bm = bmesh.new()
    rings = []
    for r, dz in profile:
        rings.append([bm.verts.new((cx + r * math.cos(2 * math.pi * j / segments),
                                    cy + r * math.sin(2 * math.pi * j / segments), SKIN + dz))
                      for j in range(segments)])
    for a, b in zip(rings, rings[1:]):
        for j in range(segments):
            k = (j + 1) % segments
            bm.faces.new((a[j], a[k], b[k], b[j]))
    centre = bm.verts.new((cx, cy, SKIN + (BOSS_CENTRE if boss else profile[-1][1] + 0.003)))
    last = rings[-1]
    for j in range(segments):
        bm.faces.new((last[j], last[(j + 1) % segments], centre))
    if lever:
        n = math.hypot(*LEVER_DIR)
        d = (LEVER_DIR[0] / n, LEVER_DIR[1] / n)
        s1 = 0.36      # from the boss centre to near the flange, its underside a chord sunk into the dome
        p0, p1 = (cx, cy), (cx + d[0] * s1, cy + d[1] * s1)
        box(bm, p0, p1, 0.040, SKIN + BOSS_CENTRE, SKIN + dome_height(s1) - 0.002, 0.010)
        h0, h1 = (cx + d[0] * 0.385, cy + d[1] * 0.385), (cx + d[0] * 0.44, cy + d[1] * 0.44)
        box(bm, h0, h1, 0.060, SKIN - 0.001, SKIN - 0.001, 0.013)    # hinge block over the flange
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    return mesh


def set_shading(mesh):
    mat = mesh.materials[0] if mesh.materials else None
    if mat and mat.get("flat"):
        mesh.shade_flat()
    else:
        mesh.shade_smooth()
        mesh.set_sharp_from_angle(angle=math.radians(SMOOTH_DEGREES))


def remove_object(ob):
    mesh = ob.data
    bpy.data.objects.remove(ob)
    if mesh and mesh.users == 0:
        bpy.data.meshes.remove(mesh)


def strip_roof_patches():
    """Drops the painted patch faces the crew cab added to RoofFitting (a rib underside and the step
    behind the old front roof plate); keeps its black fitting, and keeps its far LODs in step."""
    lod0 = bpy.data.objects.get("RoofFitting.LOD0")
    if not lod0 or "Paint" not in [m.name for m in lod0.data.materials if m]:
        return 0
    removed = 0
    for n in range(4):
        ob = bpy.data.objects.get(f"RoofFitting.LOD{n}")
        if not ob:
            continue
        bm = bmesh.new()
        bm.from_mesh(ob.data)
        slots = [m.name if m else "" for m in ob.data.materials]
        doomed = [f for f in bm.faces if slots[f.material_index] == "Paint"]
        removed += len(doomed)
        bmesh.ops.delete(bm, geom=doomed, context="FACES")
        bm.to_mesh(ob.data)
        bm.free()
        idx = slots.index("Paint")
        ob.data.materials.pop(index=idx)
    h = part_hash(lod0.data)
    for n in (1, 2, 3):
        ob = bpy.data.objects.get(f"RoofFitting.LOD{n}")
        if ob:
            ob["src_hash"] = h
    lod0["far_hash"] = h
    return removed


def place(coll, name, mesh, paint):
    mesh.materials.append(paint)
    set_shading(mesh)
    ob = bpy.data.objects.new(name, mesh)
    coll.objects.link(ob)
    return ob


def main():
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    shell = bpy.data.objects["Shell.LOD0"]
    rear_y = round(max((shell.matrix_world @ v.co).y for v in shell.data.vertices
                       if (shell.matrix_world @ v.co).z > 2.40), 4)
    paint = bpy.data.materials["Paint"]

    removed = []
    for ob in list(bpy.data.objects):
        if ob.name.rsplit(".LOD", 1)[0] in OLD_PARTS and ".LOD" in ob.name:
            removed.append(ob.name)
            remove_object(ob)
    variants = bpy.data.collections.get("Variants")
    if variants:
        for ob in list(variants.objects):
            remove_object(ob)
    else:
        variants = bpy.data.collections.new("Variants")
        bpy.context.scene.collection.children.link(variants)
    patches = strip_roof_patches()

    built = {}
    detail = {0: ("full", 18, True, True), 1: ("full", 16, True, True), 2: ("tops", 12, False, False),
              3: ("none", 8, False, False)}
    for n, (ribs_mode, seg, boss, lever) in detail.items():
        coll = bpy.data.collections[f"LOD{n}"]
        built[("RoofFront", n)] = place(coll, f"RoofFront.LOD{n}",
                                        roof_mesh(f"RoofFront.LOD{n}", "front", rear_y, FRONT_Y, SEAM_Y, ribs_mode, True), paint)
        built[("RoofRear", n)] = place(coll, f"RoofRear.LOD{n}",
                                       roof_mesh(f"RoofRear.LOD{n}", "rear", rear_y, SEAM_Y, rear_y, ribs_mode), paint)
        built[("Hatch", n)] = place(coll, f"Hatch.LOD{n}", hatch_mesh(f"Hatch.LOD{n}", seg, boss, lever), paint)
        built[("RoofFront_Plain", n)] = place(variants, f"RoofFront_Plain.LOD{n}",
                                              roof_mesh(f"RoofFront_Plain.LOD{n}", "plain", rear_y, FRONT_Y, SEAM_Y, ribs_mode, True), paint)
    for part in ("RoofFront", "RoofRear", "Hatch", "RoofFront_Plain"):
        src = built[(part, 0)]
        h = part_hash(src.data)
        src["far_hash"] = h
        for n in (1, 2, 3):
            ob = built[(part, n)]
            ob["src_hash"] = h
            ob["ratio"] = round(len(ob.data.polygons) / len(src.data.polygons), 3)

    for coll in [bpy.data.collections.get(f"LOD{n}") for n in range(4)]:
        for ob in coll.objects if coll else []:
            if ob.type == "MESH":
                set_shading(ob.data)
    for lc in bpy.context.view_layer.layer_collection.children:
        if lc.name == "Variants":
            lc.exclude = True

    counts = {p: [len(built[(p, n)].data.polygons) for n in range(4)] for p in ("RoofFront", "RoofRear", "Hatch", "RoofFront_Plain")}
    print(f"cab_roof: rear edge y {rear_y}; ribs at {rib_centres(rear_y)}; removed {len(removed)} old objects "
          f"({sorted(set(n.rsplit('.LOD', 1)[0] for n in removed))}); {patches} RoofFitting patch faces dropped")
    print(f"cab_roof: faces per LOD {counts}")
    if "--save" in args:
        bpy.ops.wm.save_mainfile()
        print(f"cab_roof: saved {bpy.data.filepath}")


main()
