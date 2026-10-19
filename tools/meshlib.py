"""Read, edit and write the car-root-space OBJ files used by the vehicle pipeline.

Format (see export_car_mesh.py): x negated (right-handed), y up, z forward, metres.
Extensions beyond plain OBJ: optional vertex colours on v lines, "bw i0 i1 i2 i3 w0 w1 w2 w3"
skinning lines parallel to the v lines, and "bp" bind-pose lines (16 floats, row-major).
"""
import collections, math


class Obj:
    def __init__(self):
        self.header = []      # comment lines
        self.v = []           # [x, y, z]
        self.color = []       # [r, g, b] or None per vertex
        self.bw = []          # ([i0..i3], [w0..w3]) per vertex, empty if not skinned
        self.vt = []
        self.vn = []
        self.bp = []          # bind-pose lines, verbatim
        self.faces = []       # [[(v, vt, vn), ...], ...], 0-based, -1 for missing

    @classmethod
    def read(cls, path):
        o = cls()
        for line in open(path):
            p = line.split()
            if not p:
                continue
            if p[0] == "#":
                o.header.append(line.rstrip("\n"))
            elif p[0] == "v":
                o.v.append([float(c) for c in p[1:4]])
                o.color.append([float(c) for c in p[4:7]] if len(p) >= 7 else None)
            elif p[0] == "bw":
                o.bw.append(([int(c) for c in p[1:5]], [float(c) for c in p[5:9]]))
            elif p[0] == "vt":
                o.vt.append([float(c) for c in p[1:3]])
            elif p[0] == "vn":
                o.vn.append([float(c) for c in p[1:4]])
            elif p[0] == "bp":
                o.bp.append(line.rstrip("\n"))
            elif p[0] == "f":
                o.faces.append([tuple(int(i) - 1 if i else -1 for i in (t.split("/") + ["", ""])[:3]) for t in p[1:]])
        return o

    def write(self, path):
        with open(path, "w") as f:
            for line in self.header:
                f.write(line + "\n")
            for i, (x, y, z) in enumerate(self.v):
                colour = "" if not self.color[i] else " " + " ".join(f"{c:.3f}" for c in self.color[i])
                f.write(f"v {x:.6f} {y:.6f} {z:.6f}{colour}\n")
                if self.bw:
                    idx, w = self.bw[i]
                    f.write("bw " + " ".join(map(str, idx)) + " " + " ".join(f"{c:.6f}" for c in w) + "\n")
            for u, v in self.vt:
                f.write(f"vt {u:.6f} {v:.6f}\n")
            for x, y, z in self.vn:
                f.write(f"vn {x:.6f} {y:.6f} {z:.6f}\n")
            for line in self.bp:
                f.write(line + "\n")
            for face in self.faces:
                f.write("f " + " ".join("/".join("" if i < 0 else str(i + 1) for i in corner) for corner in face) + "\n")

    def components(self):
        """Connected pieces as lists of vertex indices; coincident positions count as connected."""
        parent = list(range(len(self.v)))

        def root(a):
            while parent[a] != a:
                parent[a] = parent[parent[a]]
                a = parent[a]
            return a

        for face in self.faces:
            for corner in face[1:]:
                parent[root(corner[0])] = root(face[0][0])
        seen = {}
        for i, p in enumerate(self.v):
            key = tuple(round(c, 4) for c in p)
            if key in seen:
                parent[root(i)] = root(seen[key])
            else:
                seen[key] = i
        groups = collections.defaultdict(list)
        for i in range(len(self.v)):
            groups[root(i)].append(i)
        return list(groups.values())

    def remove_vertices(self, doomed):
        """Drops faces touching any doomed vertex; orphaned vertices stay, unreferenced."""
        doomed = set(doomed)
        self.faces = [f for f in self.faces if not any(c[0] in doomed for c in f)]

    def dominant_bone(self, i):
        idx, w = self.bw[i]
        return idx[max(range(4), key=lambda k: w[k])]


def bounds(obj, idx):
    lo = [min(obj.v[i][k] for i in idx) for k in range(3)]
    hi = [max(obj.v[i][k] for i in idx) for k in range(3)]
    return lo, hi


def coil_springs(obj, outer_diameter=0.17, wire_diameter=0.024, turns=4.5, top=0.80, height=None,
                 leaf_x=(0.35, 0.49), sides=12, segments_per_turn=16, body_bone=0, x=None):
    """Replaces a leaf-sprung axle's springs with coils standing on the axle's spring seats.

    Leaf-spring geometry is every piece whose lateral centre lies within leaf_x (absolute), except
    the spring seat: the short piece directly over the axle. Each seat gets a coil from its top to
    `top`, or `height` above the seat when given, skinned to the seat's hub bone at the bottom and to body_bone at the top. The coil
    borrows its UV from the shock absorber so it shares the steel colour. x, if given, moves each
    seat sideways to that lateral centre (absolute) first, e.g. outboard of the frame rails.
    """
    pieces = [(idx, *bounds(obj, idx)) for idx in obj.components()]
    referenced = {c[0] for f in obj.faces for c in f}
    pieces = [p for p in pieces if p[0][0] in referenced]
    axle = max(pieces, key=lambda p: len(p[0]))  # the differential housing is the largest piece
    axle_z = (axle[1][2] + axle[2][2]) / 2

    def centre(p, k):
        return (p[1][k] + p[2][k]) / 2

    in_leaf_band = [p for p in pieces if leaf_x[0] <= abs(centre(p, 0)) <= leaf_x[1]]
    seats = [p for p in in_leaf_band if p[2][2] - p[1][2] < 0.12 and abs(centre(p, 2) - axle_z) < 0.05]
    doomed = [i for p in in_leaf_band if p not in seats for i in p[0]]
    obj.remove_vertices(doomed)

    shock = next(p for p in pieces if any(obj.dominant_bone(i) == body_bone for i in p[0]))
    uv = obj.vt[next(c[1] for f in obj.faces for c in f if c[0] in set(shock[0]) and c[1] >= 0)]
    uv_index = len(obj.vt)
    obj.vt.append(list(uv))

    if x is not None:
        moved = []
        for seat in seats:
            dx = math.copysign(x, centre(seat, 0)) - centre(seat, 0)
            for i in seat[0]:
                obj.v[i][0] += dx
            moved.append((seat[0], *bounds(obj, seat[0])))
        seats = moved
    for seat in seats:
        hub_bone = collections.Counter(obj.dominant_bone(i) for i in seat[0]).most_common(1)[0][0]
        coil_top = seat[2][1] + height if height is not None else top
        add_coil(obj, centre(seat, 0), seat[2][1], centre(seat, 2), coil_top, outer_diameter, wire_diameter,
                 turns, sides, segments_per_turn, hub_bone, body_bone, uv_index)
    return len(doomed), len(seats)


def add_coil(obj, cx, y0, cz, y1, outer_diameter, wire_diameter, turns, sides, segments_per_turn,
             bottom_bone, top_bone, uv_index):
    """Appends a helical tube (vertical axis) skinned bottom_bone -> top_bone by height."""
    radius = (outer_diameter - wire_diameter) / 2
    tube = wire_diameter / 2
    steps = int(turns * segments_per_turn)
    base = len(obj.v)
    for s in range(steps + 1):
        t = s / steps
        angle = 2 * math.pi * turns * t
        centre = (cx + radius * math.cos(angle), y0 + tube + (y1 - y0 - 2 * tube) * t, cz + radius * math.sin(angle))
        tangent = (-math.sin(angle), (y1 - y0) / (2 * math.pi * turns * radius), math.cos(angle))
        tl = math.sqrt(sum(c * c for c in tangent))
        tangent = [c / tl for c in tangent]
        outward = (math.cos(angle), 0.0, math.sin(angle))
        binormal = [tangent[1] * outward[2] - tangent[2] * outward[1],
                    tangent[2] * outward[0] - tangent[0] * outward[2],
                    tangent[0] * outward[1] - tangent[1] * outward[0]]
        for k in range(sides):
            a = 2 * math.pi * k / sides
            normal = [outward[i] * math.cos(a) + binormal[i] * math.sin(a) for i in range(3)]
            obj.v.append([centre[i] + tube * normal[i] for i in range(3)])
            obj.color.append([0.8, 0.8, 0.8])
            obj.vn.append(normal)
            obj.bw.append(([bottom_bone, top_bone, 0, 0], [1 - t, t, 0.0, 0.0]))
    normals_base = len(obj.vn) - (steps + 1) * sides

    def quad(s, k):
        return (s * sides + k, s * sides + (k + 1) % sides, (s + 1) * sides + (k + 1) % sides, (s + 1) * sides + k)

    # Front faces are counter-clockwise in this right-handed file; pick the order that makes the
    # first quad's geometric normal agree with its outward vertex normal.
    a, b, c, _ = quad(0, 0)
    pa, pb, pc = (obj.v[base + i] for i in (a, b, c))
    e1 = [pb[i] - pa[i] for i in range(3)]
    e2 = [pc[i] - pa[i] for i in range(3)]
    geometric = [e1[1] * e2[2] - e1[2] * e2[1], e1[2] * e2[0] - e1[0] * e2[2], e1[0] * e2[1] - e1[1] * e2[0]]
    forward = sum(geometric[i] * obj.vn[normals_base + a][i] for i in range(3)) > 0
    for s in range(steps):
        for k in range(sides):
            corners = quad(s, k) if forward else tuple(reversed(quad(s, k)))
            obj.faces.append([(base + i, uv_index, normals_base + i) for i in corners])


def portal_axle(obj, lift=0.20, tube_scale=2.0, diff_scale=1.5, diff_offset=0.0, housing_width=0.10,
                housing_depth=0.24, housing_segments=20, body_bone=0):
    """Turns a beam axle into a portal axle: the beam rides above the wheel centres.

    The hub caps (the short pieces at the axle ends) stay at the wheel centre. Every other vertex
    skinned mainly to a hub bone rises by `lift`, so the tube, differential, spring seats and lower
    shock mounts move while body-skinned shock tops and leaf-spring hangers stay put. The tube's
    cross-section grows by tube_scale about its axis, the differential by diff_scale about its
    centre (a number, or [x, y, z] per axis), and the differential moves sideways by diff_offset (file x; positive is the vehicle's
    left). An oval housing at each end, upright in side profile, joins the hub cap to the raised
    tube.
    """
    pieces = [(idx, *bounds(obj, idx)) for idx in obj.components()]
    referenced = {c[0] for f in obj.faces for c in f}
    pieces = [p for p in pieces if p[0][0] in referenced]

    def centre(p, k):
        return (p[1][k] + p[2][k]) / 2

    diff = max(pieces, key=lambda p: len(p[0]))
    tube = max((p for p in pieces if p is not diff), key=lambda p: p[2][0] - p[1][0])
    hub_caps = [p for p in pieces if abs(centre(p, 0)) > 0.6 and p[2][0] - p[1][0] < 0.2]
    hub_bones = {obj.dominant_bone(p[0][0]) for p in hub_caps}
    cap_vertices = {i for p in hub_caps for i in p[0]}

    lifted = 0
    for i, p in enumerate(obj.v):
        if i not in cap_vertices and obj.dominant_bone(i) in hub_bones:
            p[1] += lift
            lifted += 1

    axis_y, axis_z = centre(tube, 1) + lift, centre(tube, 2)
    for i in tube[0]:
        p = obj.v[i]
        p[1] = axis_y + (p[1] - axis_y) * tube_scale
        p[2] = axis_z + (p[2] - axis_z) * tube_scale
    dc = [centre(diff, 0), centre(diff, 1) + lift, centre(diff, 2)]
    scale = diff_scale if isinstance(diff_scale, (list, tuple)) else [diff_scale] * 3
    for i in diff[0]:
        p = obj.v[i]
        for k in range(3):
            p[k] = dc[k] + (p[k] - dc[k]) * scale[k]
        p[0] += diff_offset

    tube_half = (tube[2][1] - tube[1][1]) / 2 * tube_scale
    for cap in hub_caps:
        bone = obj.dominant_bone(cap[0][0])
        uv = _uv_of(obj, cap[0])
        inner = cap[1][0] if centre(cap, 0) > 0 else cap[2][0]
        x0, x1 = sorted((inner, inner - housing_width if centre(cap, 0) > 0 else inner + housing_width))
        bottom, top = centre(cap, 1) - 0.10, axis_y + tube_half + 0.04
        add_oval_housing(obj, x0, x1, (bottom + top) / 2, axis_z, (top - bottom) / 2, housing_depth / 2,
                         bone, uv, housing_segments)
    return lifted, len(hub_caps)


def _uv_of(obj, vertices):
    vertices = set(vertices)
    uv = obj.vt[next(c[1] for f in obj.faces for c in f if c[0] in vertices and c[1] >= 0)]
    obj.vt.append(list(uv))
    return len(obj.vt) - 1


def add_oval_housing(obj, x0, x1, cy, cz, half_height, half_depth, bone, uv_index, segments=20):
    """Appends an elliptical prism (oval in side profile, extruded along x) skinned to one bone."""
    ring = []
    for k in range(segments):
        t = 2 * math.pi * k / segments
        y, z = cy + half_height * math.cos(t), cz + half_depth * math.sin(t)
        ny, nz = math.cos(t) / half_height, math.sin(t) / half_depth
        length = math.hypot(ny, nz)
        ring.append((y, z, (0.0, ny / length, nz / length)))
    for k in range(segments):
        a, b = ring[k], ring[(k + 1) % segments]
        corners = [((x0, a[0], a[1]), a[2]), ((x0, b[0], b[1]), b[2]), ((x1, b[0], b[1]), b[2]), ((x1, a[0], a[1]), a[2])]
        _add_face(obj, corners, outward=[(a[2][i] + b[2][i]) / 2 for i in range(3)], bone=bone, uv_index=uv_index)
    for x, nx in ((x0, -1.0), (x1, 1.0)):
        _add_face(obj, [((x, y, z), (nx, 0.0, 0.0)) for y, z, _ in ring], outward=(nx, 0.0, 0.0), bone=bone, uv_index=uv_index)


def _add_face(obj, corners, outward, bone, uv_index):
    """Appends one polygon from (position, normal) corners, ordered so it faces `outward`.
    In a skinned mesh the corners are bound wholly to bone; bone is ignored otherwise.
    """
    base, n_base = len(obj.v), len(obj.vn)
    for position, normal in corners:
        obj.v.append(list(position))
        obj.vn.append(list(normal))
        if obj.bw:
            obj.color.append([0.8, 0.8, 0.8])
            obj.bw.append(([bone, 0, 0, 0], [1.0, 0.0, 0.0, 0.0]))
        else:
            obj.color.append(None)
    a, b, c = (obj.v[base + i] for i in range(3))
    e1 = [b[i] - a[i] for i in range(3)]
    e2 = [c[i] - a[i] for i in range(3)]
    g = [e1[1] * e2[2] - e1[2] * e2[1], e1[2] * e2[0] - e1[0] * e2[2], e1[0] * e2[1] - e1[1] * e2[0]]
    order = range(len(corners)) if sum(g[i] * outward[i] for i in range(3)) > 0 else reversed(range(len(corners)))
    obj.faces.append([(base + i, uv_index, n_base + i) for i in order])


def matches_select(lo, hi, n, select):
    """Whether a piece with bounds lo..hi and n vertices satisfies a selection:
    {"x": [lo, hi], "y": [...], "z": [...], "minVertices": n, "minSize": {"y": metres}};
    the piece must fall inside every given axis range and be at least minSize long on each given axis.
    """
    for k, axis in enumerate("xyz"):
        if axis in select and not (select[axis][0] <= lo[k] and hi[k] <= select[axis][1]):
            return False
        if hi[k] - lo[k] < select.get("minSize", {}).get(axis, 0.0):
            return False
    return n >= select.get("minVertices", 1)


def pieces(obj):
    """Connected pieces still referenced by a face, as (vertex indices, lo, hi)."""
    referenced = {c[0] for f in obj.faces for c in f}
    found = []
    for idx in obj.components():
        idx = [i for i in idx if i in referenced]
        if idx:
            found.append((idx, *bounds(obj, idx)))
    return found


def in_box(point, box):
    """box: {"x": [lo, hi], ...}, omitted axes and null bounds open; a list of boxes is their union."""
    if isinstance(box, list):
        return any(in_box(point, b) for b in box)
    for k, axis in enumerate("xyz"):
        lo, hi = box.get(axis, [None, None])
        if (lo is not None and point[k] < lo) or (hi is not None and point[k] > hi):
            return False
    return True


def faces_in_box(obj, box, unit_size=0.5):
    """Indices of faces whose centroid lies in box. A piece no longer than unit_size on any axis
    goes as a whole, by the centre of its bounds, so small details are never split.
    """
    unit_centre = {}
    for idx, lo, hi in pieces(obj):
        if max(hi[k] - lo[k] for k in range(3)) <= unit_size:
            centre = [(lo[k] + hi[k]) / 2 for k in range(3)]
            for i in idx:
                unit_centre[i] = centre
    chosen = []
    for n, face in enumerate(obj.faces):
        centre = unit_centre.get(face[0][0])
        if centre is None:
            centre = [sum(obj.v[c[0]][k] for c in face) / len(face) for k in range(3)]
        if in_box(centre, box):
            chosen.append(n)
    return chosen


def widen_pieces(obj, select, cut_x, shift, box=None):
    """Widens the pieces select_pieces chooses about the centreline: vertices with |x| > cut_x
    (and inside box, if given; see in_box) move outward by shift, so the sides move rigidly and
    faces spanning the cut (a floor, a tailgate) stretch. Returns the number of vertices moved.
    """
    moved = 0
    for idx in select_pieces(obj, select):
        for i in idx:
            p = obj.v[i]
            if abs(p[0]) > cut_x and (box is None or in_box(p, box)):
                p[0] += shift if p[0] > 0 else -shift
                moved += 1
    return moved


def remove_region(obj, box, unit_size=0.5):
    """Drops the faces faces_in_box selects; returns how many."""
    doomed = set(faces_in_box(obj, box, unit_size))
    obj.faces = [f for n, f in enumerate(obj.faces) if n not in doomed]
    return len(doomed)


def select_pieces(obj, select):
    """Vertex lists of the pieces matching select, or any of a list of selections (see matches_select)."""
    selects = select if isinstance(select, list) else [select]
    return [idx for idx, lo, hi in pieces(obj) if any(matches_select(lo, hi, len(idx), s) for s in selects)]


def remove_near_axle(obj, centre, radius, box=None):
    """Drops faces with any corner within radius of the lateral (x) line through centre [y, z]
    (an axle) and, if given, inside box: clears bodywork a larger tyre would run into. Returns how
    many."""
    def near(p):
        return math.hypot(p[1] - centre[0], p[2] - centre[1]) < radius and (box is None or in_box(p, box))
    doomed = {n for n, face in enumerate(obj.faces) if any(near(obj.v[c[0]]) for c in face)}
    obj.faces = [f for n, f in enumerate(obj.faces) if n not in doomed]
    return len(doomed)


def remove_pieces(obj, select):
    """Drops every piece select_pieces chooses; returns how many."""
    chosen = select_pieces(obj, select)
    obj.remove_vertices(i for idx in chosen for i in idx)
    return len(chosen)


def paint(obj, uv, select=None, box=None, uv_rect=None, whole=False, facing=None, uv_exclude=()):
    """Maps every corner of the chosen faces to one atlas point uv (e.g. a painted panel or glass),
    so they take that spot's flat colour. Faces are chosen by any combination of: belonging to a
    piece select_pieces picks, centroid in box (see in_box; every vertex in it when whole), UV
    centroid inside uv_rect [[u0, u1], [v0, v1]] and outside every rect in uv_exclude (e.g. a lamp's
    lenses, to repaint only its housing), and a mean vertex normal within about 25 degrees of facing. A whole-face box with facing follows a recessed panel's own outline: the bevels
    around it reach back to the surface or face sideways. Returns the number of faces repainted.
    """
    vertices = None if select is None else {i for idx in select_pieces(obj, select) for i in idx}
    obj.vt.append(list(uv))
    uv_index = len(obj.vt) - 1
    painted = 0
    for n, face in enumerate(obj.faces):
        if vertices is not None and face[0][0] not in vertices:
            continue
        if box is not None:
            points = [obj.v[c[0]] for c in face] if whole else \
                [[sum(obj.v[c[0]][k] for c in face) / len(face) for k in range(3)]]
            if not all(in_box(p, box) for p in points):
                continue
        if facing is not None:
            if any(c[2] < 0 for c in face):
                continue
            normal = [sum(obj.vn[c[2]][k] for c in face) for k in range(3)]
            length = math.sqrt(sum(n * n for n in normal)) or 1.0
            if sum(normal[k] * facing[k] for k in range(3)) / length < 0.9:
                continue
        if uv_rect is not None:
            if any(c[1] < 0 for c in face):
                continue
            centre = [sum(obj.vt[c[1]][k] for c in face) / len(face) for k in range(2)]
            if not all(uv_rect[k][0] <= centre[k] <= uv_rect[k][1] for k in range(2)):
                continue
            if any(all(r[k][0] <= centre[k] <= r[k][1] for k in range(2)) for r in uv_exclude):
                continue
        obj.faces[n] = [(v, uv_index, vn) for v, vt, vn in face]
        painted += 1
    return painted


def insert_part(obj, part, box=None, include=None, exclude=(), unit_size=0.5):
    """Appends the faces of another mesh (same file conventions and space) that lie in box.
    Whole pieces are kept only if they match a selection in include (when given) and none in
    exclude (see matches_select). Returns the number of faces added.
    """
    if obj.bw:
        raise ValueError("insert_part does not skin inserted geometry; the base mesh is skinned")
    excluded = set()
    for idx, lo, hi in pieces(part):
        wanted = include is None or any(matches_select(lo, hi, len(idx), s) for s in include)
        if not wanted or any(matches_select(lo, hi, len(idx), s) for s in exclude):
            excluded.update(idx)
    chosen = faces_in_box(part, box or {}, unit_size)
    v_map, vt_map, vn_map = {}, {}, {}

    def remap(table, index, source, target):
        if index < 0:
            return -1
        if index not in table:
            table[index] = len(target)
            target.append(list(source[index]))
        return table[index]

    added = 0
    for n in chosen:
        face = part.faces[n]
        if any(c[0] in excluded for c in face):
            continue
        new_face = []
        for v, vt, vn in face:
            if v not in v_map:
                obj.color.append(part.color[v])
            new_face.append((remap(v_map, v, part.v, obj.v), remap(vt_map, vt, part.vt, obj.vt),
                             remap(vn_map, vn, part.vn, obj.vn)))
        obj.faces.append(new_face)
        added += 1
    return added


def scale_pieces(obj, select, origin, scale, box=None):
    """Scales the vertices of the pieces select_pieces chooses about origin, by scale [x, y, z],
    only those inside box if given (see in_box): e.g. [1, k, 1] above a bed's floor makes its sides
    taller and keeps their ribs evenly spread. Returns the number of vertices moved."""
    moved = 0
    for i in {i for idx in select_pieces(obj, select) for i in idx}:
        p = obj.v[i]
        if box is None or in_box(p, box):
            for k in range(3):
                p[k] = origin[k] + (p[k] - origin[k]) * scale[k]
            moved += 1
    return moved


def move_pieces(obj, select, offset):
    """Moves the pieces select_pieces chooses rigidly by offset [dx, dy, dz]; returns the number of
    pieces and vertices moved."""
    chosen = select_pieces(obj, select)
    moved = {i for idx in chosen for i in idx}
    for i in moved:
        for k in range(3):
            obj.v[i][k] += offset[k]
    return len(chosen), len(moved)


def stretch_pieces(obj, select, cut_z, shift, move=None):
    """Lengthens or shortens the pieces select_pieces chooses across cut_z: their vertices on one
    side of the cut move by shift along z, so faces spanning the cut stretch and pieces wholly past
    it move rigidly. move is "ahead" (z > cut_z) or "behind"; by default the side shift points to,
    which lengthens. Returns the number of pieces and vertices moved.
    """
    ahead = shift > 0 if move is None else move == "ahead"
    chosen = select_pieces(obj, select)
    moved = 0
    for idx in chosen:
        for i in idx:
            if (obj.v[i][2] > cut_z) == ahead:
                obj.v[i][2] += shift
                moved += 1
    return len(chosen), moved


def add_boxes(obj, boxes, uv):
    """Appends closed axis-aligned boxes, {"x": [lo, hi], "y": [...], "z": [...]} each, with every
    corner mapped to one atlas point uv so the faces take that spot's flat colour.
    """
    obj.vt.append(list(uv))
    uv_index = len(obj.vt) - 1
    for box in boxes:
        lo = [box[axis][0] for axis in "xyz"]
        hi = [box[axis][1] for axis in "xyz"]
        for k in range(3):
            a, b = (k + 1) % 3, (k + 2) % 3
            for side, value in ((-1.0, lo[k]), (1.0, hi[k])):
                corners = []
                for ca, cb in ((lo[a], lo[b]), (hi[a], lo[b]), (hi[a], hi[b]), (lo[a], hi[b])):
                    p = [0.0, 0.0, 0.0]
                    p[k], p[a], p[b] = value, ca, cb
                    normal = [0.0, 0.0, 0.0]
                    normal[k] = side
                    corners.append((p, normal))
                _add_face(obj, corners, outward=corners[0][1], bone=0, uv_index=uv_index)
    return len(boxes)


def _fillet(points, radius, min_turn_deg=30.0):
    """The polyline with every corner turning more than min_turn_deg rounded into an arc of the
    given radius (shrunk where the neighbouring segments are short), one point per 15 degrees."""
    out = [list(points[0])]
    for i in range(1, len(points) - 1):
        p, prev, nxt = points[i], out[-1], points[i + 1]
        a = [p[k] - prev[k] for k in range(3)]
        b = [nxt[k] - p[k] for k in range(3)]
        la, lb = math.sqrt(sum(c * c for c in a)), math.sqrt(sum(c * c for c in b))
        a, b = [c / la for c in a], [c / lb for c in b]
        turn = math.acos(max(-1.0, min(1.0, sum(a[k] * b[k] for k in range(3)))))
        if radius <= 0 or math.degrees(turn) <= min_turn_deg:
            out.append(list(p))
            continue
        r = min(radius, 0.45 * min(la, lb) / math.tan(turn / 2))
        t = r * math.tan(turn / 2)
        s_pt = [p[k] - a[k] * t for k in range(3)]
        e_pt = [p[k] + b[k] * t for k in range(3)]
        inward = _normalised([b[k] - a[k] for k in range(3)])
        centre = [p[k] + inward[k] * r / math.cos(turn / 2) for k in range(3)]
        v0 = [s_pt[k] - centre[k] for k in range(3)]
        v1 = [e_pt[k] - centre[k] for k in range(3)]
        steps = max(2, math.ceil(math.degrees(turn) / 15.0))
        for j in range(steps + 1):
            f = j / steps     # slerp between the arc's ends about its centre
            w0, w1 = math.sin((1 - f) * turn) / math.sin(turn), math.sin(f * turn) / math.sin(turn)
            out.append([centre[k] + w0 * v0[k] + w1 * v1[k] for k in range(3)])
    out.append(list(points[-1]))
    return out


def _turned(v, a, b):
    """v rotated by the smallest rotation taking unit vector a to unit vector b."""
    axis, c = _cross(a, b), sum(a[k] * b[k] for k in range(3))
    s = math.sqrt(sum(x * x for x in axis))
    if s < 1e-9:
        return list(v)
    axis = [x / s for x in axis]
    dot = sum(axis[k] * v[k] for k in range(3))
    cross = _cross(axis, v)
    return [v[k] * c + cross[k] * s + axis[k] * dot * (1 - c) for k in range(3)]


def add_tubes(obj, tubes, uv):
    """Appends capped tubes swept along polylines, {"points": [[x, y, z], ...], "radius": r, "sides":
    n} each, every corner mapped to one atlas point uv. Each polyline is one continuous tube: one
    ring of vertices per point, shared by the segments either side, each ring lying in the plane that
    bisects its corner (the section stretched by 1/cos of the half-turn there, so the wall keeps its
    radius), with frames carried along the path so it never twists. Corners turning more than 30
    degrees are first rounded into arcs of "bendRadius" (default twice the tube's radius). Normals
    are smooth round the tube and flat on the end caps. Four sides with "square": true give a
    square-section beam with flat top and bottom and flat sides, e.g. a sloped stretch of frame rail.
    Returns the number of tubes and of rings.
    """
    obj.vt.append(list(uv))
    uv_index = len(obj.vt) - 1
    rings_added = 0

    def vertex(position, colour=None):
        obj.v.append(list(position))
        if obj.bw:
            obj.color.append([0.8, 0.8, 0.8])
            obj.bw.append(([0, 0, 0, 0], [1.0, 0.0, 0.0, 0.0]))
        else:
            obj.color.append(colour)
        return len(obj.v) - 1

    def normal(n):
        obj.vn.append(list(n))
        return len(obj.vn) - 1

    for tube in tubes:
        r, n, square = tube["radius"], tube.get("sides", 8), tube.get("square", False)
        start = math.pi / n if square else 0.0
        path = _fillet(tube["points"], tube.get("bendRadius", 2.0 * r))
        dirs = []
        for p0, p1 in zip(path, path[1:]):
            d = [p1[k] - p0[k] for k in range(3)]
            length = math.sqrt(sum(c * c for c in d))
            dirs.append([c / length for c in d])
        # The first segment's frame, then carried along: (u, w) span the plane square to the path.
        d0 = dirs[0]
        ref = [0.0, 1.0, 0.0] if abs(d0[1]) < 0.9 else [1.0, 0.0, 0.0]
        u = _normalised(_cross(ref, d0))
        frames = [u]
        for a, b in zip(dirs, dirs[1:]):
            frames.append(_normalised(_turned(frames[-1], a, b)))
        rings, radial = [], []
        for i, p in enumerate(path):
            seg = min(i, len(dirs) - 1)              # the segment arriving here (the first one at the start)
            d, u = dirs[seg], frames[seg]
            w = _cross(d, u)
            if 0 < i < len(path) - 1:
                t = _normalised([dirs[i - 1][k] + dirs[i][k] for k in range(3)])
            else:
                t = d
            ring, out = [], []
            for j in range(n):
                ang = start + 2 * math.pi * j / n
                c = [math.cos(ang) * u[k] + math.sin(ang) * w[k] for k in range(3)]
                # The section square to the arriving segment, slid along it onto the bisecting plane.
                slide = -r * sum(c[k] * t[k] for k in range(3)) / sum(d[k] * t[k] for k in range(3))
                ring.append(vertex([p[k] + r * c[k] + slide * d[k] for k in range(3)]))
                out.append(c)
            rings.append(ring)
            radial.append(out)
            rings_added += 1
        for i in range(len(path) - 1):
            for j in range(n):
                jj = (j + 1) % n
                if square:     # flat sides: one normal per face, square to the segment
                    side = _normalised([radial[i][j][k] + radial[i][jj][k] for k in range(3)])
                    nn = [normal(side)] * 4
                else:
                    nn = [normal(radial[i][j]), normal(radial[i][jj]), normal(radial[i + 1][jj]), normal(radial[i + 1][j])]
                quad = [rings[i][j], rings[i][jj], rings[i + 1][jj], rings[i + 1][j]]
                outward = _normalised([radial[i][j][k] + radial[i][jj][k] for k in range(3)])
                e1 = [obj.v[quad[1]][k] - obj.v[quad[0]][k] for k in range(3)]
                e2 = [obj.v[quad[2]][k] - obj.v[quad[0]][k] for k in range(3)]
                order = range(4) if sum(_cross(e1, e2)[k] * outward[k] for k in range(3)) > 0 else reversed(range(4))
                obj.faces.append([(quad[m], uv_index, nn[m]) for m in order])
        for ring, d, sign in ((rings[0], dirs[0], -1.0), (rings[-1], dirs[-1], 1.0)):
            cap = normal([sign * c for c in d])
            e1 = [obj.v[ring[1]][k] - obj.v[ring[0]][k] for k in range(3)]
            e2 = [obj.v[ring[2]][k] - obj.v[ring[0]][k] for k in range(3)]
            order = range(n) if sum(_cross(e1, e2)[k] * sign * d[k] for k in range(3)) > 0 else reversed(range(n))
            obj.faces.append([(ring[m], uv_index, cap) for m in order])
    return len(tubes), rings_added


def add_plates(obj, plates, uv):
    """Appends flat plates of any orientation, {"corners": [p0, p1, p2, p3], "thickness": t} each:
    the quad p0..p3 (in order round its edge) thickened by t about its own plane into a closed
    slab, every corner mapped to one atlas point uv. For slanted sheet-steel guards and the like.
    """
    obj.vt.append(list(uv))
    uv_index = len(obj.vt) - 1
    for plate in plates:
        quad, half = plate["corners"], plate["thickness"] / 2
        e1 = [quad[1][k] - quad[0][k] for k in range(3)]
        e2 = [quad[3][k] - quad[0][k] for k in range(3)]
        n = _normalised(_cross(e1, e2))
        faces = [[[p[k] + sign * half * n[k] for k in range(3)] for p in quad] for sign in (1.0, -1.0)]
        for sign, face in zip((1.0, -1.0), faces):
            normal = [sign * c for c in n]
            _add_face(obj, [(p, normal) for p in face], outward=normal, bone=0, uv_index=uv_index)
        centre = [sum(p[k] for p in quad) / 4 for k in range(3)]
        for i in range(4):
            j = (i + 1) % 4
            mid = [(quad[i][k] + quad[j][k]) / 2 for k in range(3)]
            normal = _normalised([mid[k] - centre[k] for k in range(3)])
            corners = [faces[0][i], faces[0][j], faces[1][j], faces[1][i]]
            _add_face(obj, [(p, normal) for p in corners], outward=normal, bone=0, uv_index=uv_index)
    return len(plates)


def add_profile_bands(obj, bands, uv):
    """Appends closed solids swept straight up: each band {"inner": [[x, z], ...], "outer": [[x, z], ...],
    "y": [y0, y1]} pairs an inner and an outer polyline of equal length in plan (e.g. a recess floor and
    the lens face standing proud of the panel round a cab corner), and fills between them from y0 to
    y1 with outer, inner, top, bottom and end faces. Every corner maps to one atlas point uv. Returns
    the number of bands."""
    obj.vt.append(list(uv))
    uv_index = len(obj.vt) - 1
    for band in bands:
        inner, outer, (y0, y1) = band["inner"], band["outer"], band["y"]
        p3 = lambda q, y: [q[0], y, q[1]]
        for i in range(len(inner) - 1):
            a, b, c, d = inner[i], inner[i + 1], outer[i + 1], outer[i]
            out = [(c[0] + d[0] - a[0] - b[0]) / 2, 0.0, (c[1] + d[1] - a[1] - b[1]) / 2]
            back = [-x for x in out]
            for (q0, q1), facing in (((d, c), out), ((a, b), back)):
                corners = [p3(q0, y0), p3(q1, y0), p3(q1, y1), p3(q0, y1)]
                _add_face(obj, [(p, _normalised(facing)) for p in corners], outward=facing, bone=0, uv_index=uv_index)
            for y, facing in ((y0, [0.0, -1.0, 0.0]), (y1, [0.0, 1.0, 0.0])):
                _add_face(obj, [(p3(q, y), facing) for q in (a, b, c, d)], outward=facing, bone=0, uv_index=uv_index)
        for i, j in ((0, 1), (len(inner) - 1, len(inner) - 2)):
            facing = [inner[i][0] - inner[j][0], 0.0, inner[i][1] - inner[j][1]]
            corners = [p3(inner[i], y0), p3(outer[i], y0), p3(outer[i], y1), p3(inner[i], y1)]
            _add_face(obj, [(p, _normalised(facing)) for p in corners], outward=facing, bone=0, uv_index=uv_index)
    return len(bands)


def add_decals(obj, decals):
    """Appends single-sided convex polygons with their own UVs, {"corners": [p0, p1, ...], "uvs":
    [[u, v], ...], "facing": [x, y, z]} each: e.g. a lamp lens showing an atlas graphic across its face.
    Corners go round the polygon; the face is wound to face "facing", and with "doubleSided": true gets
    a back face too, so it never shows as a hole from behind. Returns the number added."""
    for decal in decals:
        base_vt = len(obj.vt)
        obj.vt.extend([list(uv) for uv in decal["uvs"]])
        facing = _normalised(decal["facing"])
        base, n_base = len(obj.v), len(obj.vn)
        for p in decal["corners"]:
            obj.v.append(list(p))
            obj.vn.append(list(facing))
            obj.color.append(None)
            if obj.bw:
                obj.bw.append(([0, 0, 0, 0], [1.0, 0.0, 0.0, 0.0]))
        a, b, c = decal["corners"][:3]
        g = _cross([b[k] - a[k] for k in range(3)], [c[k] - a[k] for k in range(3)])
        n = len(decal["corners"])
        order = range(n) if sum(g[k] * facing[k] for k in range(3)) > 0 else reversed(range(n))
        face = [(base + i, base_vt + i, n_base + i) for i in order]
        obj.faces.append(face)
        if decal.get("doubleSided"):
            back_n = len(obj.vn)
            obj.vn.extend([[-c for c in facing]] * n)
            obj.faces.append([(v, t, back_n + (vn - n_base)) for v, t, vn in reversed(face)])
    return len(decals)


def _cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def _normalised(v):
    n = math.sqrt(sum(c * c for c in v))
    return [c / n for c in v]


def relocate_piece(obj, select, rotate_y=0.0, anchor_to=None):
    """Moves one connected piece: rotate it about the vertical through its anchor, then move the anchor.

    select: the piece to move (see matches_select); exactly one piece must match.
    The anchor is the centre of the piece's +z end (its front).
    rotate_y: degrees, right-handed about +y in file coordinates (-90 turns a rearward pipe to
    point at +x, the vehicle's left). anchor_to: [x, y, z] in file coordinates; null keeps an axis.
    Returns the piece's bounds after the move.
    """
    matches = [idx for idx, lo, hi in pieces(obj) if matches_select(lo, hi, len(idx), select)]
    if len(matches) != 1:
        raise ValueError(f"relocatePiece selection {select} matched {len(matches)} pieces")
    idx = matches[0]
    lo, hi = bounds(obj, idx)
    front = [obj.v[i] for i in idx if obj.v[i][2] > hi[2] - 0.03]
    anchor = [sum(p[k] for p in front) / len(front) for k in range(3)]
    a = math.radians(rotate_y)
    c, s_ = math.cos(a), math.sin(a)
    target = [anchor[k] if anchor_to is None or anchor_to[k] is None else anchor_to[k] for k in range(3)]
    normals = {cn[2] for f in obj.faces for cn in f if cn[0] in set(idx) and cn[2] >= 0}
    for i in idx:
        x, y, z = (obj.v[i][k] - anchor[k] for k in range(3))
        obj.v[i] = [x * c + z * s_ + target[0], y + target[1], -x * s_ + z * c + target[2]]
    for n in normals:
        x, y, z = obj.vn[n]
        obj.vn[n] = [x * c + z * s_, y, -x * s_ + z * c]
    return bounds(obj, idx)
