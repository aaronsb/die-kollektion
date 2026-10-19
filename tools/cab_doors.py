"""Give a Glyptodon-family cab master generated doors, headless in Blender.

Usage: blender -b meshes/glyptodon/<cab>_master.blend --python tools/cab_doors.py -- [--save]
then tools/build_cab_part.sh <master> --derive as usual (the parts bring their own far LODs).

The door is the family's door (a door reference photo): front-hinged, one window opening with a
narrow pane split off at its front, a rounded-rectangle inset below the window with the pull handle in a
dish at its rear end, and the swage line below that. Its front edge stands upright to KINK, then sweeps
back at the window's own angle along the A-pillar; its rear edge is upright. Front and rear doors are this
one outline; the rear door only fills the wheel-arch cutout in. The layout is the long crew-cab reference
drawing's, in proportion within our cab's length (see DOOR): 1.093 m door bays and, on the crew cab, a
B-pillar 9.8 cm wide at the sill that widens up the rear door's rake to the roof. The skin
follows the shell's own section at every height (pillar_gate checks it). Blender coordinates: +X the
truck's left, front toward -Y, Z up; the right side mirrors the left.

Every cab:
- The shell is cut along the front door's outline (its upright then raked front edge, the old door's
  rear edge, the door top; the wheel arch and the sill are the shell's own lower edge), leaving a strip
  of A-pillar skin ahead of the raked edge, and the old fused door goes: outer skin, window surround,
  inner panel, and on the crew cab its inner trim pieces in Shell_L/R.
- FrontDoor_L/R: the door with the wheel-arch cutout at its front bottom.
- BPillar_L/R: the skin behind the front door, on the section's rows: the crew cab's B-pillar, or on the
  two-door a strip to the shell's cut edge (its pillar behind the door gets wider).
- FrontDoorJamb_L/R, FrontDoorSeal_L/R: return faces on the shell side of the shut lines (the A-pillar
  line, the line behind the door), and a black seal behind each, so a look into a gap ends on metal and
  the line reads dark.

The crew cab, before that, once (marked on Shell.LOD0 as rear_layout): the old rear doors and their pillar
pieces go, the roof-band ledge they carried becomes SideHeader_L/R, and the rear quarter is trimmed back
to REAR_REAR; the rear doors' hinges, catch and rod and the rear step move back with the rear door. Then
RearDoor_L/R, RearDoorFrame_L/R, RearDoorGlass_L/R (the front door's frame and glass moved back), and
RearDoorJamb_L/R and RearDoorSeal_L/R (the B-pillar's raked edge, the C-pillar).

Run it again and it replaces its own parts. Profiles were measured on the crew cab's front door: the skin's
x against height, the window's outer opening and its pane openings, the inner panel's depth.
"""
import math, os, sys
import bpy, bmesh
from mathutils import Matrix, Vector, geometry

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from export_master import part_hash, SMOOTH_DEGREES  # noqa: E402

HINGE_Y = -1.277                 # the front door's hinge line
# The layout: our cab's side length (hinge line -1.277 to the cab's rear 1.151, 2.428 m) laid out in the
# proportions of the long crew-cab reference drawing (front door
# 1.010, B-pillar 0.090 at the sill, rear door 1.006, rear quarter 0.134 over its 2.240 m), scaled by 1.084.
# The two doors are one design, so they share the mean bay. The front door stays on its hinge line by the
# wheel arch; on the two-door the pillar behind the door takes up the rest of the old door's bay.
DOOR = 1.0926                    # a door bay, shut line to shut line
B_STRIP = 0.0976                 # the crew cab's B-pillar at the sill
FRONT_REAR = HINGE_Y + DOOR      # -0.1844: the front door's upright rear shut line
REAR_FRONT = FRONT_REAR + B_STRIP          # -0.0868: the rear door's shut line (raked above KINK)
REAR_REAR = REAR_FRONT + DOOR    # 1.0058: the rear door's rear shut line, the C-pillar's front
OLD_OPEN = (-0.150, 0.977)       # the original shells' cut: the old front door's rear edge, the old rear opening
TWO_DOOR_OVERLAP = 0.010         # the two-door's pillar strip tucks this far under the shell behind it
Z0, ZTOP = 0.988, 2.342          # door bottom (the cab's bottom edge); door top, under the roof band
GAP = 0.004                      # shut-line gap
JAMB = 0.035                     # depth of the shell-side return faces
SEAL = (0.040, 0.010)            # black seal behind a shut line: under the shell (deep enough for a 40-degree look), under the door
BELT = 1.555                     # beltline: above it the skin is one plane leaning in
TUMBLE = 0.15                    # the upper skin's lean, x per z
# The lower skin: a gentle bulge to the swage at 1.30, a step back, then the flat band.
PROFILE = [(0.988, 0.9910), (1.13, 1.0052), (1.22, 1.0107), (1.30, 1.0113), (1.315, 1.0054), (BELT, 1.0045)]
INNER_X, INNER_TUMBLE = 0.9045, 0.09                     # inner skin: upright below the belt, leaning above
Z_MID = 1.70                     # top of the pressing region (just under the window chamfer)
KINK = 1.65                      # where the doors' front edges (and the B-pillar's rear edge) start to sweep back
# Above KINK each door's front edge sweeps back along the A-pillar at the window's own front-edge angle
# (the long crew-cab reference drawing: front edge upright to
# about 1.70, then raked; rear edge upright). Both doors are this one outline; the crew cab's B-pillar is the
# wedge between the front door's upright rear edge and the rear door's raked front edge.
RAKE = 0.184                     # y per z, the window's front edge
# The wheel-arch cutout at the front door's front bottom: the shell's arch edge, (y, z).
ARCH = [(-1.277, 1.175), (-1.226, 1.180), (-1.091, 1.167), (-0.962, 1.129), (-0.841, 1.068), (-0.740, 0.988)]
# The inset: a rounded rectangle pressed in below the window at the old door's pressing height (z 1.44..1.61;
# the drawing has it at z 1.45..1.62), 4.5 cm in from the door's front and 5.5 cm from its rear, the handle at its rear end.
INSET = [((0.045, 1.440), 0.045), ((1.030, 1.440), 0.045), ((1.030, 1.610), 0.045), ((0.045, 1.610), 0.045)]
INSET_RING, INSET_DEPTH = 0.012, 0.008
# The dish pressed in behind the pull handle's grip (the old front door had one, 3 cm deep), centred on
# the grip (tools/cab_fixes.py: u 0.770..0.940, z 1.512..1.538) between its posts, kept under the beltline.
DISH = [((0.795, 1.488), 0.020), ((0.915, 1.488), 0.020), ((0.915, 1.552), 0.020), ((0.795, 1.552), 0.020)]
DISH_DEPTH = 0.020
CHAMFER = 0.034                  # the skin's chamfer into the window opening
# The window's outer opening, then its narrow (front) and large pane openings, as (y, z) on the front door.
WINDOW = [(-1.195, 1.846), (-1.193, 1.81), (-1.176, 1.779), (-1.148, 1.757), (-1.113, 1.749),
          (-0.396, 1.749), (-0.359, 1.757), (-0.329, 1.777), (-0.307, 1.807), (-0.298, 1.843),
          (-0.279, 2.197), (-0.284, 2.234), (-0.304, 2.266), (-0.336, 2.288), (-0.373, 2.296),
          (-1.062, 2.293), (-1.097, 2.274), (-1.122, 2.242)]
PANE_NARROW = [(-1.17, 1.834), (-1.17, 1.815), (-1.158, 1.792), (-1.138, 1.776), (-1.112, 1.772),
               (-0.962, 1.772), (-0.934, 2.27), (-1.034, 2.27), (-1.06, 2.264), (-1.082, 2.249),
               (-1.098, 2.227), (-1.104, 2.211)]
PANE_LARGE = [(-0.937, 1.773), (-0.396, 1.773), (-0.37, 1.78), (-0.347, 1.795), (-0.331, 1.816),
              (-0.323, 1.842), (-0.303, 2.199), (-0.31, 2.225), (-0.325, 2.247), (-0.347, 2.264),
              (-0.372, 2.272), (-0.909, 2.273)]
NARROW_INSET = 0.012             # the narrow pane sits this much deeper than the large one
SHELL_SIDE_X = 0.80              # shell faces further out than this inside a door's outline are the door's
DETAIL = {0: ("full", 3), 1: ("full", 3), 2: ("lean", 1), 3: ("lean", 0)}   # rows, inset fillet segments (0: none)


def x_out(z):
    if z >= BELT:
        return PROFILE[-1][1] - TUMBLE * (z - BELT)
    for (za, xa), (zb, xb) in zip(PROFILE, PROFILE[1:]):
        if za <= z <= zb:
            return xa + (xb - xa) * (z - za) / (zb - za)
    return PROFILE[0][1]


def x_in(z):
    return INNER_X - INNER_TUMBLE * max(0.0, z - BELT)


def x_opening(z):                # the window's outer opening edge (the black frame's outer rim)
    return 0.938 - 0.1006 * (z - 1.749)


def x_pane(z, narrow):           # the pane openings (the frame's inner rim)
    return 0.923 - 0.1004 * (z - 1.773) - (NARROW_INSET if narrow else 0.0)


def to_u(loop):
    return [(y - HINGE_Y, z) for y, z in loop]



def raked(z):
    """How far a door's front edge (and a raked shut line) has swept back at height z."""
    return RAKE * max(0.0, z - KINK)


def lower_levels(rows):
    """Heights of the lower skin's rows: the bulge (in one row when lean), the swage step's top."""
    return [Z0, 1.13, 1.22, 1.30, 1.315] if rows == "full" else [Z0, 1.30, 1.315]


def offset_loop(loop, d):
    """Offsets a closed (u, z) loop outward by d (loop counter-clockwise)."""
    n = len(loop)
    out = []
    for i in range(n):
        p0, p1, p2 = Vector(loop[i - 1]), Vector(loop[i]), Vector(loop[(i + 1) % n])
        e0, e1 = (p1 - p0).normalized(), (p2 - p1).normalized()
        n0, n1 = Vector((e0.y, -e0.x)), Vector((e1.y, -e1.x))       # outward normals of a CCW loop
        m = (n0 + n1).normalized()
        out.append(tuple(p1 + m * (d / max(m.dot(n0), 0.3))))
    return out


def ccw(loop):
    a = sum(loop[i][0] * loop[(i + 1) % len(loop)][1] - loop[(i + 1) % len(loop)][0] * loop[i][1]
            for i in range(len(loop)))
    return loop if a > 0 else loop[::-1]


def fillet(control, segs):
    """A closed polygon with each control corner rounded by its radius (segs+1 points per corner)."""
    pts = []
    n = len(control)
    for i in range(n):
        a, (p, r), c = Vector(control[i - 1][0]), control[i], Vector(control[(i + 1) % n][0])
        p = Vector(p)
        d0, d1 = (a - p).normalized(), (c - p).normalized()
        half = math.acos(max(-1.0, min(1.0, d0.dot(d1)))) / 2
        t = r / math.tan(half)
        s0, s1 = p + d0 * t, p + d1 * t
        centre = p + (d0 + d1).normalized() * (r / math.sin(half))
        a0 = math.atan2(s0.y - centre.y, s0.x - centre.x)
        a1 = math.atan2(s1.y - centre.y, s1.x - centre.x)
        sweep = (a1 - a0 + math.pi) % (2 * math.pi) - math.pi
        for k in range(segs + 1):
            ang = a0 + sweep * k / segs
            pts.append((centre.x + r * math.cos(ang), centre.y + r * math.sin(ang)))
    return pts


def split_at(pts, z, closed=True):
    """Inserts a point wherever the polygon's (or open polyline's) edges cross height z."""
    out = []
    n = len(pts)
    for i in range(n):
        p = pts[i]
        out.append(p)
        if i + 1 == n and not closed:
            break
        q = pts[(i + 1) % n]
        if (p[1] - z) * (q[1] - z) < 0:
            t = (z - p[1]) / (q[1] - p[1])
            out.append((p[0] + t * (q[0] - p[0]), z))
    return out


def crossings(loop, z):
    return sorted(p[0] for p in loop if abs(p[1] - z) < 1e-9)


def inside(p, loop):
    x, y = p
    c = False
    for i in range(len(loop)):
        (x0, y0), (x1, y1) = loop[i - 1], loop[i]
        if (y0 > y) != (y1 > y) and x < x0 + (y - y0) * (x1 - x0) / (y1 - y0):
            c = not c
    return c


def cdt(outer, holes, lines=()):
    """Triangles of the (u, z) region inside outer and outside the holes, from the loops' own points;
    lines are extra constraint segments (a crease the triangles must not straddle)."""
    pts, edges = [], []
    for loop in [outer] + holes:
        b = len(pts)
        pts += loop
        edges += [(b + i, b + (i + 1) % len(loop)) for i in range(len(loop))]
    for p, q in lines:
        pts += [p, q]
        edges.append((len(pts) - 2, len(pts) - 1))
    verts, _, faces, orig, *_ = geometry.delaunay_2d_cdt([Vector(p) for p in pts], edges, [], 0, 1e-9)
    # Back to the input points themselves (the solver works in single precision), so a loop shared
    # with another region keeps exactly the same coordinates there.
    exact = [pts[o[0]] if o else tuple(v) for v, o in zip(verts, orig)]
    tris = []
    for f in faces:
        t = [exact[i] for i in f]
        area = (t[1][0] - t[0][0]) * (t[2][1] - t[0][1]) - (t[2][0] - t[0][0]) * (t[1][1] - t[0][1])
        if abs(area) < 1e-9:      # three points of one constraint edge (a split point and its ends)
            continue
        c = (sum(p[0] for p in t) / 3, sum(p[1] for p in t) / 3)
        if inside(c, outer) and not any(inside(c, h) for h in holes):
            tris.append(t)
    return tris


class Builder:
    """Faces in groups: a group shares its vertices (smooth within it), groups share none (hard edges
    between them, so the exporter's smoothing can't tilt a flat panel's normals at a crease)."""

    def __init__(self, side, y0):
        self.bm = bmesh.new()
        self.groups = {}
        self.sx = 1.0 if side == "L" else -1.0
        self.y0 = y0
        self.flags = []

    def p(self, u, z, x):
        return (self.sx * x, self.y0 + u, z)

    def face(self, group, pts, want, two_sided=0):
        verts = self.groups.setdefault(group, {})
        n = Vector((0.0, 0.0, 0.0))
        for i in range(len(pts)):
            a, b = Vector(pts[i]), Vector(pts[(i + 1) % len(pts)])
            n += Vector(((a.y - b.y) * (a.z + b.z), (a.z - b.z) * (a.x + b.x), (a.x - b.x) * (a.y + b.y)))
        want = Vector((self.sx * want[0], want[1], want[2]))
        if n.dot(want) < 0:
            pts = pts[::-1]
        vs = []
        for q in pts:
            k = tuple(round(c, 6) for c in q)
            if k not in verts:
                verts[k] = self.bm.verts.new(k)
            vs.append(verts[k])
        self.bm.faces.new(vs)
        self.flags.append(two_sided)

    def mesh(self, name):
        mesh = bpy.data.meshes.new(name)
        self.bm.to_mesh(mesh)
        self.bm.free()
        if any(self.flags):
            attr = mesh.attributes.new("two_sided", "INT", "FACE")
            for i, f in enumerate(self.flags):
                attr.data[i].value = f
        return mesh


def door_bottom(arch):
    """The door's bottom edge from its front to its rear corner, (u, z): straight, or the wheel arch."""
    u0, u1 = GAP, DOOR - GAP
    if not arch:
        return [(u0, Z0), (u1, Z0)]
    return [(max(u0, u), z) for u, z in to_u(ARCH)] + [(u1, Z0)]


def door_mesh(name, side, y0, rows, inset_segs, arch):
    """One door at hinge line y0. rows 'full' keeps the bulge's three rows, 'lean' one; inset_segs is the
    inset's fillet segments per corner (0 leaves the pressing out); arch cuts the wheel arch out."""
    b = Builder(side, y0)
    u0, u1, zt = GAP, DOOR - GAP, ZTOP - GAP
    um, ut = u0 + raked(Z_MID), u0 + raked(zt)               # the raked front edge at Z_MID and at the top
    low = lower_levels(rows)
    out = lambda u, z: b.p(u, z, x_out(z))
    inn = lambda u, z: b.p(u, z, x_in(z))
    deep = lambda u, z: b.p(u, z, x_out(z) - INSET_DEPTH)
    side_of_belt = lambda t: "lo" if sum(p[1] for p in t) / 3 < BELT else "hi"

    # The bottom edge, with a point wherever it crosses a row line, so every surface meeting it agrees.
    bottom = door_bottom(arch)
    rows_z = [z for z in low if bottom[-1][1] < z < 1.30]
    for z in rows_z:
        bottom = split_at(bottom, z, closed=False)
    front = [bottom[0][1]] + [z for z in low[1:] if z > bottom[0][1]]   # front edge points below the swage top
    rear = [bottom[-1][1]] + low[1:]

    # The bulge (smooth, rows as constraints so each triangle lies in one row's plane), the swage step.
    bulge = bottom + [(u1, z) for z in rear[1:] if z <= 1.30] + [(u0, z) for z in reversed(front[1:]) if z <= 1.30]
    lines = []
    for z in rows_z:
        us = crossings(bulge, z)
        if len(us) >= 2:
            lines.append(((us[0], z), (us[-1], z)))
    for t in cdt(bulge, [], lines):
        b.face("bulge", [out(u, z) for u, z in t], (1, 0, 0))
    b.face("swage", [out(u0, 1.30), out(u1, 1.30), out(u1, 1.315), out(u0, 1.315)], (1, 0, 0))

    # The pressing region, from the swage to just under the window: the beltline is a constraint so no
    # triangle straddles its crease, and the faces either side of it keep their own vertices.
    region = [(u0, 1.315), (u1, 1.315), (u1, BELT), (u1, Z_MID), (um, Z_MID), (u0, KINK), (u0, BELT)]
    if inset_segs:
        outline = fillet(INSET, inset_segs)
        rim = split_at(outline, BELT)
        floor = split_at(offset_loop(outline, -INSET_RING), BELT)
        belt, inner_belt = crossings(rim, BELT), crossings(floor, BELT)
        for t in cdt(region, [rim], [((u0, BELT), (belt[0], BELT)), ((belt[-1], BELT), (u1, BELT))]):
            b.face("skin_" + side_of_belt(t), [out(u, z) for u, z in t], (1, 0, 0))
        rim_set = set(rim)
        for t in cdt(rim, [floor], [((belt[0], BELT), (inner_belt[0], BELT)), ((inner_belt[-1], BELT), (belt[-1], BELT))]):
            b.face("inset_wall", [out(u, z) if (u, z) in rim_set else deep(u, z) for u, z in t], (1, 0, 0))
        holes = []
        if inset_segs >= 2:
            dish = fillet(DISH, 2)
            holes.append(dish)
            dish_floor = offset_loop(dish, -0.010)
            sunk = lambda u, z: b.p(u, z, x_out(z) - INSET_DEPTH - DISH_DEPTH)
            for i in range(len(dish)):
                j = (i + 1) % len(dish)
                b.face("dish_wall", [deep(*dish[i]), deep(*dish[j]), sunk(*dish_floor[j]), sunk(*dish_floor[i])], (1, 0, 0))
            for t in cdt(dish_floor, []):
                b.face("dish", [sunk(u, z) for u, z in t], (1, 0, 0))
        for t in cdt(floor, holes, [((inner_belt[0], BELT), (inner_belt[-1], BELT))]):
            b.face("inset_" + side_of_belt(t), [deep(u, z) for u, z in t], (1, 0, 0))
    else:
        b.face("skin_lo", [out(u0, 1.315), out(u1, 1.315), out(u1, BELT), out(u0, BELT)], (1, 0, 0))
        b.face("skin_hi", [out(u0, BELT), out(u1, BELT), out(u1, Z_MID), out(um, Z_MID), out(u0, KINK)], (1, 0, 0))

    # Round the window: the skin plane, chamfered into the opening the black frame fills.
    window = ccw(to_u(WINDOW))
    rim = offset_loop(window, CHAMFER)
    for t in cdt([(um, Z_MID), (u1, Z_MID), (u1, zt), (ut, zt)], [rim]):
        b.face("skin_hi", [out(u, z) for u, z in t], (1, 0, 0))
    cu = sum(p[0] for p in window) / len(window)
    cz = sum(p[1] for p in window) / len(window)
    for i in range(len(window)):
        j = (i + 1) % len(window)
        mu, mz = (window[i][0] + window[j][0]) / 2, (window[i][1] + window[j][1]) / 2
        b.face("chamfer", [out(*rim[i]), out(*rim[j]), b.p(*window[j], x_opening(window[j][1])),
                           b.p(*window[i], x_opening(window[i][1]))], (1.0, cu - mu, cz - mz))

    # Pane openings: the reveal from the frame's inner rim back to the inner skin.
    panes = []
    for loop, narrow in ((PANE_NARROW, True), (PANE_LARGE, False)):
        pane = ccw(to_u(loop))
        panes.append(pane)
        pu = sum(p[0] for p in pane) / len(pane)
        pz = sum(p[1] for p in pane) / len(pane)
        for i in range(len(pane)):
            j = (i + 1) % len(pane)
            mu, mz = (pane[i][0] + pane[j][0]) / 2, (pane[i][1] + pane[j][1]) / 2
            b.face("reveal", [b.p(*pane[i], x_pane(pane[i][1], narrow)), b.p(*pane[j], x_pane(pane[j][1], narrow)),
                              inn(*pane[j]), inn(*pane[i])], (0.0, pu - mu, pz - mz))

    # Inner skin: upright below the belt (on the edges' points), one leaning plane above.
    inner_lo = bottom + [(u1, z) for z in rear[1:]] + [(u1, BELT), (u0, BELT)] + [(u0, z) for z in reversed(front[1:])]
    for t in cdt(inner_lo, []):
        b.face("inner_lo", [inn(u, z) for u, z in t], (-1, 0, 0))
    for t in cdt([(u0, BELT), (u1, BELT), (u1, Z_MID), (u1, zt), (ut, zt), (um, Z_MID), (u0, KINK)], panes):
        b.face("inner_hi", [inn(u, z) for u, z in t], (-1, 0, 0))

    # Edges: front (hinge, raked at the top), rear, top, and the bottom (along the arch on a front door).
    for g, pts, toward in (("edge_front", [(u0, z) for z in front + [BELT, KINK]] + [(um, Z_MID), (ut, zt)], -1),
                           ("edge_rear", [(u1, z) for z in rear + [BELT, Z_MID, zt]], 1)):
        for (ua, za), (ub, zb) in zip(pts, pts[1:]):
            b.face(g, [out(ua, za), out(ub, zb), inn(ub, zb), inn(ua, za)], (0, toward * (zb - za), -toward * (ub - ua)))
    b.face("edge_top", [out(ut, zt), out(u1, zt), inn(u1, zt), inn(ut, zt)], (0, 0, 1))
    for (ua, za), (ub, zb) in zip(bottom, bottom[1:]):
        b.face("edge_bottom", [out(ua, za), out(ub, zb), inn(ub, zb), inn(ua, za)], (0, zb - za, -(ub - ua)))
    return b.mesh(name)


def shut_line(y, z_bottom, rows, rake):
    """A vertical shut line's points (y, z) from z_bottom to the door top; rake sweeps it back above
    KINK like the doors' front edges."""
    zs = [z_bottom] + [z for z in lower_levels(rows)[1:] if z > z_bottom] + [BELT, KINK, Z_MID, ZTOP]
    return [(y + (raked(z) if rake else 0.0), z) for z in zs]


def line_normals(pts):
    """Per point, the (y, z) normal of a polyline pointing toward +y, mitred at the kinks."""
    segs = []
    for (ya, za), (yb, zb) in zip(pts, pts[1:]):
        n = math.hypot(yb - ya, zb - za)
        segs.append(((zb - za) / n, -(yb - ya) / n))
    out = []
    for i in range(len(pts)):
        a, c = segs[max(0, i - 1)], segs[min(len(segs) - 1, i)]
        m = (a[0] + c[0], a[1] + c[1])
        k = math.hypot(*m)
        m = (m[0] / k, m[1] / k)
        out.append((m[0] / max(0.3, m[0] * c[0] + m[1] * c[1]), m[1] / max(0.3, m[0] * c[0] + m[1] * c[1])))
    return out


def jamb_mesh(name, side, shut_lines, top):
    """Return faces on the shell side of shut lines, double-sided. shut_lines: (points, toward) with
    toward the door's side in y (+1 the door is behind the line); top: the door top's (y0, y1) span."""
    b = Builder(side, 0.0)
    for k, (pts, toward) in enumerate(shut_lines):
        for (ya, za), (yb, zb) in zip(pts, pts[1:]):
            b.face(f"jamb{k}", [b.p(ya, za, x_out(za)), b.p(yb, zb, x_out(zb)), b.p(yb, zb, x_out(zb) - JAMB),
                                b.p(ya, za, x_out(za) - JAMB)], (0, toward * (zb - za), -toward * (yb - ya)), 1)
    if top:
        xt = x_out(ZTOP)
        b.face("top", [b.p(top[0], ZTOP, xt), b.p(top[1], ZTOP, xt), b.p(top[1], ZTOP, xt - JAMB),
                       b.p(top[0], ZTOP, xt - JAMB)], (0, 0, -1), 1)
    return b.mesh(name)


def seal_mesh(name, side, shut_lines):
    """The rubber seal behind each shut line, at the jamb's depth, mitred round a kink: a straight-on
    look into the gap ends on it, and the line reads dark."""
    b = Builder(side, 0.0)
    under, over = SEAL
    for k, (pts, toward) in enumerate(shut_lines):
        ns = line_normals(pts)
        a = [(y - toward * under * n[0], z - toward * under * n[1]) for (y, z), n in zip(pts, ns)]
        c = [(y + toward * over * n[0], z + toward * over * n[1]) for (y, z), n in zip(pts, ns)]
        at = lambda q: b.p(q[0], q[1], x_out(q[1]) - JAMB)
        for i in range(len(pts) - 1):
            b.face(f"seal{k}", [at(a[i]), at(a[i + 1]), at(c[i + 1]), at(c[i])], (1, 0, 0), 1)
    return b.mesh(name)


def b_pillar_mesh(name, side, y_front, y_rear, rear_raked, inset=0.0):
    """The pillar strip behind a front door: skin from its upright front line y_front to y_rear (raked
    above KINK on the crew cab, where the rear door's front edge sweeps back), following the section's rows,
    double-sided. inset sinks it below the section (the two-door's strip tucks under the shell)."""
    b = Builder(side, 0.0)
    levels = lower_levels("full") + [BELT, KINK, Z_MID, ZTOP]
    yr = lambda z: y_rear + (raked(z) if rear_raked else 0.0)
    at = lambda y, z: b.p(y, z, x_out(z) - inset)
    for za, zb in zip(levels, levels[1:]):
        group = "bulge" if zb <= 1.30 else "swage" if zb <= 1.315 else "lo" if zb <= BELT else "hi"
        b.face(group, [at(y_front, za), at(yr(za), za), at(yr(zb), zb), at(y_front, zb)], (1, 0, 0), 1)
    return b.mesh(name)


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


def lod_object(part, n):
    return bpy.data.objects.get(f"{part}.LOD{n}")


def remove_part(part):
    """Removes every LOD of a part; returns its triangles per LOD."""
    tris = {}
    for n in range(4):
        ob = lod_object(part, n)
        if ob:
            tris[n] = sum(len(p.vertices) - 2 for p in ob.data.polygons)
            remove_object(ob)
    return tris


def strip_faces(ob, doomed_test):
    """Deletes the faces doomed_test(centre, normal, ymin, ymax) picks; returns how many."""
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    mw = ob.matrix_world
    doomed = []
    for f in bm.faces:
        ys = [(mw @ v.co).y for v in f.verts]
        if doomed_test(mw @ f.calc_center_median(), mw.to_3x3() @ f.normal, min(ys), max(ys)):
            doomed.append(f)
    bmesh.ops.delete(bm, geom=doomed, context="FACES")
    bm.to_mesh(ob.data)
    bm.free()
    return len(doomed)


def cut_shell(ob, y0, y1):
    """Cuts the shell along a door's outline (its upright then raked front edge from y0, an upright rear
    edge at y1, the door top) and deletes the old door inside it; returns the faces deleted."""
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bm.transform(ob.matrix_world)

    def near(z_lo=0.9, z_hi=ZTOP + 0.1):
        """The side faces reaching into the door's span and the height band (a face partly inside is cut)."""
        faces = [f for f in bm.faces
                 if all(abs(v.co.x) > SHELL_SIDE_X - 0.05 and 0.9 < v.co.z < ZTOP + 0.1 for v in f.verts)
                 and min(v.co.y for v in f.verts) < y1 + 0.01 and max(v.co.y for v in f.verts) > y0 - 0.01
                 and min(v.co.z for v in f.verts) < z_hi and max(v.co.z for v in f.verts) > z_lo]
        edges = {e for f in faces for e in f.edges}
        verts = {v for f in faces for v in f.verts}
        return faces + list(edges) + list(verts)

    rake_no = Vector((0, 1, -RAKE)).normalized()
    below_top = ZTOP - 0.002            # leaves the roof band's long strips (from ZTOP up) uncut
    for geom, co, no in ((near(z_hi=KINK + 0.01), (0, y0, 0), (0, 1, 0)),
                         (near(z_lo=KINK - 0.01, z_hi=below_top), (0, y0, KINK), rake_no),
                         (near(z_hi=below_top), (0, y1, 0), (0, 1, 0)),
                         (near(z_hi=below_top), (0, 0, ZTOP), (0, 0, 1))):
        bmesh.ops.bisect_plane(bm, geom=geom, dist=1e-6, plane_co=co, plane_no=no)
    doomed = []
    for f in bm.faces:
        c = f.calc_center_median()
        if y0 + raked(c.z) < c.y < y1 and c.z < ZTOP and abs(c.x) > SHELL_SIDE_X:
            doomed.append(f)
    bmesh.ops.delete(bm, geom=doomed, context="FACES")
    bm.transform(ob.matrix_world.inverted())
    bm.to_mesh(ob.data)
    bm.free()
    return len(doomed)


def header_strip(src):
    """A copy of the faces of src that run the cab's length under the roof band (over 2 m long)."""
    mesh = src.data.copy()
    ob = bpy.data.objects.new("tmp_header", mesh)
    bpy.context.scene.collection.objects.link(ob)
    strip_faces(ob, lambda c, n, y0, y1: y1 - y0 < 2.0)
    bpy.context.scene.collection.objects.unlink(ob)
    bpy.data.objects.remove(ob)
    return mesh


def place(coll, name, mesh, material):
    if not mesh.materials:
        mesh.materials.append(material)
    set_shading(mesh)
    ob = bpy.data.objects.new(name, mesh)
    coll.objects.link(ob)
    return ob


def far_hashes(part):
    """Marks a part's far LODs as made from its current LOD0, so --derive leaves them alone."""
    src = lod_object(part, 0)
    if not src:
        return
    h = part_hash(src.data)
    src["far_hash"] = h
    for n in (1, 2, 3):
        ob = lod_object(part, n)
        if ob:
            ob["src_hash"] = h
            ob["ratio"] = round(len(ob.data.polygons) / max(1, len(src.data.polygons)), 3)


def tris(part, n):
    ob = lod_object(part, n)
    return sum(len(p.vertices) - 2 for p in ob.data.polygons) if ob else 0


def build_doors(prefix, y0, arch, shut_lines, top, paint, black, frame_from=None):
    """Places a pair of doors and their jambs and seals in every LOD; shut_lines(rows) gives the lines.
    Returns their triangles per LOD."""
    counts = {}
    for n in range(4):
        coll = bpy.data.collections[f"LOD{n}"]
        rows, inset_segs = DETAIL[n]
        for side in ("L", "R"):
            place(coll, f"{prefix}_{side}.LOD{n}", door_mesh(f"{prefix}_{side}.LOD{n}", side, y0, rows, inset_segs, arch), paint)
            place(coll, f"{prefix}Jamb_{side}.LOD{n}", jamb_mesh(f"{prefix}Jamb_{side}.LOD{n}", side, shut_lines(rows), top), paint)
            place(coll, f"{prefix}Seal_{side}.LOD{n}", seal_mesh(f"{prefix}Seal_{side}.LOD{n}", side, shut_lines(rows)), black)
            for src_part, part in ((frame_from, f"{prefix}Frame_{side}"), ("DoorGlass" if frame_from else None, f"{prefix}Glass_{side}")):
                src = lod_object(f"{src_part}_{side}", n) if src_part else None
                if src:
                    mesh = src.data.copy()
                    mesh.transform(src.matrix_world)
                    for v in mesh.vertices:
                        v.co.y += y0 - HINGE_Y
                    set_shading(mesh)
                    coll.objects.link(bpy.data.objects.new(f"{part}.LOD{n}", mesh))
    for side in ("L", "R"):
        for part in (f"{prefix}_{side}", f"{prefix}Jamb_{side}", f"{prefix}Seal_{side}", f"{prefix}Frame_{side}", f"{prefix}Glass_{side}"):
            far_hashes(part)
            if lod_object(part, 0):
                counts[part] = [tris(part, n) for n in range(4)]
    return counts


def cut_band(ob, y0, y1):
    """Deletes the side faces of ob between y0 and y1 (upright cuts, below the door top); returns how many."""
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bm.transform(ob.matrix_world)
    for y in (y0, y1):
        geom = [f for f in bm.faces if all(abs(v.co.x) > SHELL_SIDE_X - 0.05 for v in f.verts)
                and min(v.co.z for v in f.verts) < ZTOP - 0.002       # reaches below the door top
                and max(v.co.y for v in f.verts) - min(v.co.y for v in f.verts) < 1.0]   # not the roof band's long strips
        geom += list({e for f in geom for e in f.edges}) + list({v for f in geom for v in f.verts})
        bmesh.ops.bisect_plane(bm, geom=geom, dist=1e-6, plane_co=(0, y, 0), plane_no=(0, 1, 0))
    doomed = [f for f in bm.faces if y0 < f.calc_center_median().y < y1 and f.calc_center_median().z < ZTOP
              and abs(f.calc_center_median().x) > SHELL_SIDE_X]
    bmesh.ops.delete(bm, geom=doomed, context="FACES")
    bm.transform(ob.matrix_world.inverted())
    bm.to_mesh(ob.data)
    bm.free()
    return len(doomed)


def prepare_crew_cab(paint):
    """Once per master (marked on Shell.LOD0 as rear_layout): clears the old rear doors and their pillar
    pieces, lifts out the roof-band ledge they carried, and trims the rear quarter back to REAR_REAR.
    The rear doors' hinges, catch and rod, and the rear step, follow the rear door back."""
    shell = lod_object("Shell", 0)
    if shell.get("rear_layout"):
        return {"already prepared": True}
    report = {}
    for side, holder in (("L", "RearDoor"), ("R", "Shell")):     # the ledge the old left door carried
        mesh = header_strip(lod_object(f"{holder}_{side}", 0))
        for n in range(4):
            place(bpy.data.collections[f"LOD{n}"], f"SideHeader_{side}.LOD{n}", mesh if n == 0 else mesh.copy(), paint)
    report["old_parts_removed"] = {part: remove_part(part) for side in ("L", "R")
                                   for part in (f"RearDoor_{side}", f"RearDoorFrame_{side}", f"RearDoorGlass_{side}", f"Door_{side}")}
    trimmed = {}
    for part in ("Shell", "Shell_L", "Shell_R"):
        for n in range(4):
            ob = lod_object(part, n)
            if ob:
                if part != "Shell":
                    strip_faces(ob, lambda c, nrm, ya, yb: OLD_OPEN[0] - 0.0005 < c.y < OLD_OPEN[1] - 0.0005 or yb - ya > 2.0)
                trimmed[f"{part}.LOD{n}"] = cut_band(ob, OLD_OPEN[1] - 0.001, REAR_REAR)
    report["rear_quarter_faces_trimmed"] = trimmed
    move = REAR_FRONT - OLD_OPEN[0]
    for part in ("RearHinge_L", "RearHinge_R", "RearDoorCatch_L", "RearDoorCatch_R", "RearDoorRod_L"):
        for n in range(4):
            ob = lod_object(part, n)
            if ob:
                ob.data.transform(ob.matrix_world.inverted() @ Matrix.Translation((0, move, 0)) @ ob.matrix_world)
    for n in range(4):                                         # the rear step, behind y 0.45
        for side in ("L", "R"):
            ob = lod_object(f"StepHanger_{side}", n)
            if ob:
                mw, inv = ob.matrix_world, ob.matrix_world.inverted()
                for v in ob.data.vertices:
                    w = mw @ v.co
                    if w.y > 0.45:
                        w.y += move
                        v.co = inv @ w
    shell["rear_layout"] = 1
    for part in {o.name.rsplit(".LOD", 1)[0] for o in bpy.data.objects if ".LOD" in o.name}:
        far_hashes(part)
    report["rear_parts_moved_by"] = round(move, 4)
    return report


def rear_doors(paint, black):
    """The crew cab's rear doors, between the B-pillar and the C-pillar."""
    report = {"replaced": {part: remove_part(part) for side in ("L", "R")
                           for part in (f"RearDoor_{side}", f"RearDoorFrame_{side}", f"RearDoorGlass_{side}",
                                        f"RearDoorJamb_{side}", f"RearDoorSeal_{side}")}}
    shut = lambda rows: [(shut_line(REAR_FRONT, Z0, rows, True), 1),        # the B-pillar's rear (raked) edge
                         (shut_line(REAR_REAR, Z0, rows, False), -1)]       # the C-pillar
    report["built"] = build_doors("RearDoor", REAR_FRONT, False, shut, (REAR_FRONT + raked(ZTOP), REAR_REAR),
                                  paint, black, frame_from="DoorFrame")
    return report


def front_doors(paint, black, crew_cab):
    """Cuts the fused front doors (and on the crew cab the old B-pillar) out of the shell, then puts the
    generated doors and a clean pillar strip behind each in their place."""
    report = {}
    cut = {}
    if not lod_object("Shell", 0).get("front_doors_cut"):   # the cut is made once; a rerun only rebuilds parts
        for n in range(4):
            ob = lod_object("Shell", n)
            before = sum(len(p.vertices) - 2 for p in ob.data.polygons)
            deleted = cut_shell(ob, HINGE_Y, OLD_OPEN[0])
            cut[f"Shell.LOD{n}"] = (deleted, before, sum(len(p.vertices) - 2 for p in ob.data.polygons))
        lod_object("Shell", 0)["front_doors_cut"] = 1
        far_hashes("Shell")
        if crew_cab:
            for side in ("L", "R"):
                for n in range(4):
                    ob = lod_object(f"Shell_{side}", n)
                    if ob:
                        strip_faces(ob, lambda c, nrm, ya, yb: HINGE_Y < c.y < OLD_OPEN[0] + 0.0005 and yb - ya < 1.0 and c.z < ZTOP)
                far_hashes(f"Shell_{side}")
    report["shell_cut"] = cut
    report["replaced"] = {part: remove_part(part) for side in ("L", "R")
                          for part in (f"FrontDoor_{side}", f"FrontDoorJamb_{side}", f"FrontDoorSeal_{side}", f"BPillar_{side}")}
    zf = ARCH[0][1]
    shut = lambda rows: [(shut_line(HINGE_Y, zf, rows, True), 1), (shut_line(FRONT_REAR, Z0, rows, False), -1)]
    report["built"] = build_doors("FrontDoor", HINGE_Y, True, shut, (HINGE_Y + raked(ZTOP), FRONT_REAR), paint, black)
    # The pillar behind the front door: on the crew cab the B-pillar to the rear door's raked edge; on the
    # two-door a strip to the shell's cut edge, tucked a hair under it.
    for side in ("L", "R"):
        for n in range(4):
            mesh = (b_pillar_mesh(f"BPillar_{side}.LOD{n}", side, FRONT_REAR, REAR_FRONT, True) if crew_cab else
                    b_pillar_mesh(f"BPillar_{side}.LOD{n}", side, FRONT_REAR, OLD_OPEN[0] + TWO_DOOR_OVERLAP, False, 0.001))
            place(bpy.data.collections[f"LOD{n}"], f"BPillar_{side}.LOD{n}", mesh, paint)
        far_hashes(f"BPillar_{side}")
    return report


def pillar_gate():
    """No door skin vertex may stand more than 2 mm outboard of the shell's section, nor of the shell
    or B-pillar just across a shut line from it. Returns (worst protrusion m, vertices over, misses)."""
    dg = bpy.context.evaluated_depsgraph_get()
    surfaces = ("Shell", "BPillar_L", "BPillar_R", "SideHeader_L", "SideHeader_R", "FrontDoor_L", "FrontDoor_R",
                "RearDoor_L", "RearDoor_R")
    lod0 = [o for o in bpy.data.collections["LOD0"].objects if o.name.split(".")[0] in surfaces]
    worst, over, misses = 0.0, 0, 0
    for prefix, y0 in (("FrontDoor", HINGE_Y), ("RearDoor", REAR_FRONT)):
        for side, sx in (("L", 1.0), ("R", -1.0)):
            door = lod_object(f"{prefix}_{side}", 0)
            if not door:
                continue
            targets = [o for o in lod0 if o is not door]
            for v in door.data.vertices:
                p = door.matrix_world @ v.co
                x = sx * p.x
                if x < x_out(p.z) - 0.012:               # inner skin and reveals
                    continue
                worst = max(worst, x - x_out(p.z))
                over += x - x_out(p.z) > 0.002
                y_front, y_rear = y0 + GAP + raked(p.z), y0 + DOOR - GAP
                probes = []
                if p.y - y_front < 0.03:
                    probes.append((y_front - 2 * GAP - 0.004, p.z))
                if y_rear - p.y < 0.03:
                    probes.append((y_rear + 2 * GAP + 0.004, p.z))
                if p.z > ZTOP - GAP - 0.002:
                    probes.append((p.y, ZTOP + 0.004))
                for py, pz in probes:
                    lean = TUMBLE * (pz - p.z) if pz > BELT else 0.0   # the section's own lean between the heights
                    hit = None
                    for o in targets:
                        inv = o.matrix_world.inverted()
                        ok, loc, *_ = o.ray_cast(inv @ Vector((sx * 2.0, py, pz)), (inv.to_3x3() @ Vector((-sx, 0, 0))).normalized())
                        if ok:
                            hx = sx * (o.matrix_world @ loc).x
                            hit = hx if hit is None else max(hit, hx)
                    if hit is None or hit < 0.8:
                        misses += 1
                        continue
                    worst = max(worst, x - hit - lean)
                    over += x - hit - lean > 0.002
    return round(worst, 4), over, misses


def main():
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    paint, black = bpy.data.materials["Paint"], bpy.data.materials["Black"]
    shell = bpy.data.objects["Shell.LOD0"]
    crew_cab = shell.get("rear_layout") or max((shell.matrix_world @ v.co).y for v in shell.data.vertices) > 0.9
    if crew_cab:
        print(f"cab_doors: prepare {prepare_crew_cab(paint)}")
    print(f"cab_doors: front doors {front_doors(paint, black, crew_cab)}")
    if crew_cab:
        print(f"cab_doors: rear doors {rear_doors(paint, black)}")
    for coll in [bpy.data.collections.get(f"LOD{n}") for n in range(4)]:
        for ob in coll.objects if coll else []:
            if ob.type == "MESH":
                set_shading(ob.data)
    print(f"cab_doors: pillar gate (worst protrusion m, vertices over 2 mm, probes with no shell) {pillar_gate()}")
    if "--save" in args:
        bpy.ops.wm.save_mainfile()
        print(f"cab_doors: saved {bpy.data.filepath}")

if __name__ == "__main__":
    main()
