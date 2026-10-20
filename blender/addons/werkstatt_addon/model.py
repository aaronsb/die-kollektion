"""The vehicle model behind the Werkstatt add-on: files in, files out, and the maths between the game and Blender.

Pure Python (no bpy), so tests run it without Blender. It is the middle of three layers, kept apart so the add-on
can later write meshes or ops as well as placements without a rewrite:

  files  (vehicle.json, extracted/<donor>/nodes.json and upgrades.json, vehicles/<name>/placements.json)
    <-> model  (Vehicle: its parts, attach points, upgrade nodes at their pose after the reshape, placements)
    <-> scene  (the add-on's Blender side: collections, empties and meshes)

Game space is Unity car-root space: x right, y up, z forward, metres, left-handed. Blender space is what the
OBJ files import as: Blender (x, y, z) = (-x, -z, y) of the game. Placement semantics are the plugin's
(plugins/VehicleMods/PlacementPlan.cs): an entry's offset (metres) and rotation (Euler degrees in Unity's
z-x-y order) are in car-root axes as turned and scaled by the placements of the node's ancestors, the rotation
is about the node's own pivot, and scale multiplies the node's local scale.
"""
import hashlib, json, math, os

PLACEMENTS = "placements.json"
OFFSET_DIGITS, ROTATION_DIGITS, SCALE_DIGITS = 4, 3, 4


class WerkstattError(Exception):
    """A problem worth a plain message (a missing file, an unknown node), never a traceback."""


# ---- maths -------------------------------------------------------------------------------------------------

def quat_mul(a, b):
    """Hamilton product of quaternions (x, y, z, w)."""
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw,
            aw * bw - ax * bx - ay * by - az * bz)


def quat_inv(q):
    x, y, z, w = q
    n = x * x + y * y + z * z + w * w
    return (-x / n, -y / n, -z / n, w / n)


def quat_axis(axis, degrees):
    half = math.radians(degrees) / 2
    s = math.sin(half)
    return (axis[0] * s, axis[1] * s, axis[2] * s, math.cos(half))


def quat_rotate(q, v):
    p = quat_mul(quat_mul(q, (v[0], v[1], v[2], 0.0)), quat_inv(q))
    return (p[0], p[1], p[2])


def euler_to_quat(degrees):
    """Unity's Quaternion.Euler: z degrees about z, then x about x, then y about y."""
    x, y, z = degrees
    return quat_mul(quat_mul(quat_axis((0, 1, 0), y), quat_axis((1, 0, 0), x)), quat_axis((0, 0, 1), z))


def quat_to_matrix(q):
    x, y, z, w = q
    return [[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]]


def quat_to_euler(q):
    """The inverse of euler_to_quat (R = Ry Rx Rz), in degrees; x within [-90, 90]."""
    r = quat_to_matrix(q)
    # atan2 rather than asin(-r12): asin loses about 0.01° within a degree of a quarter turn of pitch
    cx = math.hypot(r[0][2], r[2][2])
    x = math.atan2(-r[1][2], cx)
    if cx > 1e-9:
        y = math.atan2(r[0][2], r[2][2])
        z = math.atan2(r[1][0], r[1][1])
    else:                                  # gimbal lock: put the whole turn about y
        y = math.atan2(-r[2][0], r[0][0])
        z = 0.0
    return tuple(math.degrees(v) for v in (x, y, z))


def game_to_blender(v):
    return (-v[0], -v[2], v[1])


def blender_to_game(v):
    return (-v[0], v[2], -v[1])


def quat_game_to_blender(q):
    """A rotation in game axes as the same rotation in Blender axes. The axis change is a reflection, so the
    axis maps with a sign flip and the angle keeps its value."""
    x, y, z, w = q
    bx, by, bz = game_to_blender((x, y, z))
    return (-bx, -by, -bz, w)


def quat_blender_to_game(q):
    x, y, z, w = q
    gx, gy, gz = blender_to_game((x, y, z))
    return (-gx, -gy, -gz, w)


def scale_game_to_blender(s):
    return (s[0], s[2], s[1])


def scale_blender_to_game(s):
    return (s[0], s[2], s[1])


def clean(values, digits):
    return [round(v, digits) + 0.0 for v in values]


# ---- placements files ----------------------------------------------------------------------------------------

class Placement:
    """A delta for one node (see the module docstring). source is set for a copy."""

    __slots__ = ("offset", "rotation", "scale", "source")

    def __init__(self, offset=(0.0, 0.0, 0.0), rotation=(0.0, 0.0, 0.0), scale=(1.0, 1.0, 1.0), source=None):
        self.offset, self.rotation, self.scale, self.source = tuple(offset), tuple(rotation), tuple(scale), source

    def is_identity(self):
        return (all(abs(v) < 0.5 * 10 ** -OFFSET_DIGITS for v in self.offset)
                and all(abs(v) < 0.5 * 10 ** -ROTATION_DIGITS for v in self.rotation)
                and all(abs(v - 1) < 0.5 * 10 ** -SCALE_DIGITS for v in self.scale))

    def as_dict(self):
        out = {}
        if self.source is not None:
            out["source"] = self.source
        if any(abs(v) >= 0.5 * 10 ** -OFFSET_DIGITS for v in self.offset):
            out["offset"] = clean(self.offset, OFFSET_DIGITS)
        if any(abs(v) >= 0.5 * 10 ** -ROTATION_DIGITS for v in self.rotation):
            out["rotation"] = clean(self.rotation, ROTATION_DIGITS)
        if any(abs(v - 1) >= 0.5 * 10 ** -SCALE_DIGITS for v in self.scale):
            out["scale"] = clean(self.scale, SCALE_DIGITS)
        return out

    def __repr__(self):
        return f"Placement({self.as_dict()})"


def parent_path(path):
    return path.rsplit("/", 1)[0] if "/" in path else ""


# The plugin's limits (PlacementPlan.cs): an item moved 10 m, turned past a full turn or scaled 100x is a typo.
MAX_OFFSET, MAX_ROTATION, MIN_SCALE, MAX_SCALE = 10.0, 360.0, 0.01, 100.0
FILE_KEYS = {"notes", "nodes", "copies"}
ENTRY_KEYS = {"notes", "offset", "rotation", "scale"}
COPY_KEYS = ENTRY_KEYS | {"source"}


def _vector(value, where, name, lo, hi):
    if not (isinstance(value, list) and len(value) == 3 and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in value)):
        raise WerkstattError(f"{where}: \"{name}\" must be three numbers")
    if any(not math.isfinite(v) or v < lo or v > hi for v in value):
        raise WerkstattError(f"{where}: \"{name}\" out of range ({lo:g} to {hi:g})")
    return tuple(float(v) for v in value)


def vector3(value, name, lo=-math.inf, hi=math.inf):
    """Three finite numbers within [lo, hi] from a caller's value (a tuple, list or Blender vector)."""
    if isinstance(value, (str, bytes, bytearray, dict, set)) or not hasattr(value, "__len__") or len(value) != 3:
        raise WerkstattError(f"{name} must be three numbers, got {value!r}")
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in value):
        raise WerkstattError(f"{name} must be three numbers, got {value!r}")
    values = [float(v) for v in value]
    if not all(math.isfinite(v) for v in values):
        raise WerkstattError(f"{name} must be finite numbers, got {value!r}")
    if any(v < lo or v > hi for v in values):
        raise WerkstattError(f"{name} out of range ({lo:g} to {hi:g}): {value!r}")
    return tuple(values)


def number(value, name, lo=-math.inf, hi=math.inf):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not lo <= value <= hi:
        raise WerkstattError(f"{name} must be a number from {lo:g} to {hi:g}, got {value!r}")
    return value


def _is_path(path):
    return isinstance(path, str) and bool(path) and "" not in path.split("/")


def _no_duplicates(pairs):
    seen = {}
    for key, value in pairs:
        if key in seen:
            raise WerkstattError(f"duplicate key \"{key}\"")
        seen[key] = value
    return seen


def _no_constants(name):
    raise WerkstattError(f"{name} is not a number")


def _keys(obj, where, allowed):
    unknown = sorted(set(obj) - allowed)
    if unknown:
        raise WerkstattError(f"{where}: unknown key \"{unknown[0]}\"")


def parse_placements(text, where="placements.json"):
    """(nodes, copies, notes) from a placements file's text, with the plugin's validation rules."""
    try:
        data = json.loads(text, object_pairs_hook=_no_duplicates, parse_constant=_no_constants)
    except json.JSONDecodeError as e:
        raise WerkstattError(f"{where} isn't valid JSON: {e}") from None
    except WerkstattError as e:
        raise WerkstattError(f"{where}: {e}") from None
    if not isinstance(data, dict):
        raise WerkstattError(f"{where} must hold an object")
    _keys(data, where, FILE_KEYS)
    nodes, copies = {}, {}
    for key, target, is_copy in (("nodes", nodes, False), ("copies", copies, True)):
        section = data.get(key, {})
        if not isinstance(section, dict):
            raise WerkstattError(f"{where}: \"{key}\" must be an object")
        for path, entry in section.items():
            here = f"{where}: {path}"
            if not _is_path(path):
                raise WerkstattError(f"{where}: \"{path}\" is not a node path")
            if not isinstance(entry, dict):
                raise WerkstattError(f"{here}: must be an object")
            _keys(entry, here, COPY_KEYS if is_copy else ENTRY_KEYS)
            source = None
            if is_copy:
                source = entry.get("source")
                if not isinstance(source, str):
                    raise WerkstattError(f"{here}: a copy needs a \"source\" node path")
                if not _is_path(source):
                    raise WerkstattError(f"{here}: \"{source}\" is not a node path")
                if parent_path(path) not in (parent_path(source), source) or path == source:
                    raise WerkstattError(f"{here}: a copy sits beside its source or inside it (source {source})")
                if path in nodes:
                    raise WerkstattError(f"{here}: in both nodes and copies")
            target[path] = Placement(
                _vector(entry["offset"], here, "offset", -MAX_OFFSET, MAX_OFFSET) if "offset" in entry else (0.0, 0.0, 0.0),
                _vector(entry["rotation"], here, "rotation", -MAX_ROTATION, MAX_ROTATION) if "rotation" in entry else (0.0, 0.0, 0.0),
                _vector(entry["scale"], here, "scale", MIN_SCALE, MAX_SCALE) if "scale" in entry else (1.0, 1.0, 1.0),
                source)
    return nodes, copies, data.get("notes")


def read_placements(path):
    if not os.path.isfile(path):
        return {}, {}, None
    with open(path, encoding="utf-8") as f:
        return parse_placements(f.read(), os.path.basename(os.path.dirname(path)) + "/" + PLACEMENTS)


def file_hash(path):
    """The sha256 of a file's bytes, or "" when it doesn't exist (save compares it with the one at open)."""
    if not os.path.isfile(path):
        return ""
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


class _RepeatedKeys(dict):
    """A JSON object that repeated a key (holding the last value, as json.load would)."""


def _mark_repeats(pairs):
    out = dict(pairs)
    return _RepeatedKeys(out) if len(out) < len(pairs) else out


def read_json(path, root=None):
    """A JSON file's content, an object that repeats a key read as a _RepeatedKeys; a broken file is a WerkstattError
    naming it."""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f, object_pairs_hook=_mark_repeats)
    except (OSError, ValueError) as e:
        raise WerkstattError(f"can't read {os.path.relpath(path, root) if root else path}: {e}") from None


DEFAULT_NOTES = ("Placements of this vehicle's upgrade nodes, written by the Werkstatt Blender add-on (format: "
                 "docs/engine.md, \"Upgrade nodes\"). Each entry is a delta from the node's pose after the reshape: "
                 "offset in metres and rotation in Euler degrees (Unity order z, x, y) in car-root axes (x right, y up, "
                 "z forward) as turned by the node's placed ancestors, about the node's pivot; scale multiplies "
                 "its local scale. Copies add a copy of an upgrade option or of a piece inside one, shown with it.")


def dump_placements(nodes, copies, notes=None):
    """The file's text, or None when there is nothing to write. Keys sorted, defaults left out, numbers
    rounded, so a save that changes nothing changes no byte."""
    out_nodes = {p: pl.as_dict() for p, pl in sorted(nodes.items()) if not pl.is_identity()}
    out_copies = {p: pl.as_dict() for p, pl in sorted(copies.items())}
    if not out_nodes and not out_copies:
        return None
    sections = [f'  "notes": {json.dumps(notes or DEFAULT_NOTES, ensure_ascii=False)}']
    for key, entries in (("nodes", out_nodes), ("copies", out_copies)):
        if entries:
            # One line per entry, vectors inline: a nudge changes one line of the diff.
            lines = [f"    {json.dumps(path, ensure_ascii=False)}: {json.dumps(entry, ensure_ascii=False, allow_nan=False)}"
                     for path, entry in entries.items()]
            sections.append(f'  "{key}": {{\n' + ",\n".join(lines) + "\n  }")
    return "{\n" + ",\n".join(sections) + "\n}\n"


def quat_angle(a, b):
    """The angle in degrees between two rotations (x, y, z, w)."""
    dot = abs(sum(x * y for x, y in zip(a, b)))
    return math.degrees(2 * math.acos(min(1.0, dot)))


def same_entries(a, b):
    """Whether two {path: Placement} hold the same placements, as the game would show them: offsets and scales
    within half the file's last digit, rotations within 0.01° however they are written ((0, 200, 0) and
    (0, -160, 0) are one turn)."""
    if set(a) != set(b):
        return False
    for path, pa in a.items():
        pb = b[path]
        if pa.source != pb.source:
            return False
        if any(abs(x - y) > 0.5 * 10 ** -OFFSET_DIGITS for x, y in zip(pa.offset, pb.offset)):
            return False
        if any(abs(x - y) > 0.5 * 10 ** -SCALE_DIGITS for x, y in zip(pa.scale, pb.scale)):
            return False
        if quat_angle(euler_to_quat(pa.rotation), euler_to_quat(pb.rotation)) > 0.01:
            return False
    return True


def write_placements(path, nodes, copies, notes=None):
    """Writes (or, with nothing to say, removes) the placements file. Returns 'written', 'unchanged' or 'removed'
    or 'absent'."""
    text = dump_placements(nodes, copies, notes)
    old = None
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            old = f.read()
    if text is None:
        if old is None:
            return "absent"
        os.remove(path)
        return "removed"
    if text == old:
        return "unchanged"
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    os.replace(tmp, path)
    return "written"


def _mat_mul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def _mat_apply(m, v):
    return tuple(sum(m[i][k] * v[k] for k in range(3)) for i in range(3))


IDENTITY3 = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]


def steps(nodes, copies):
    """The plugin's PlacementPlan.Steps(): (path, offset, turn) in car-root space, in apply order. An offset goes
    through its placed ancestors' turns and scales exactly (as a child's location under its parent in Blender);
    a turn through their turns only (under a non-uniformly scaled ancestor Blender would shear it)."""
    entries = dict(copies)
    entries.update(nodes)
    frames, out = {}, []
    for path in sorted(entries, key=lambda p: (p.count("/"), p)):
        pl = entries[path]
        anc_turn, anc_map = (0.0, 0.0, 0.0, 1.0), IDENTITY3
        parent = parent_path(path)
        while parent:
            if parent in frames:
                anc_turn, anc_map = frames[parent]
                break
            parent = parent_path(parent)
        offset = _mat_apply(anc_map, pl.offset)
        own = euler_to_quat(pl.rotation)
        turn = quat_mul(quat_mul(anc_turn, own), quat_inv(anc_turn))
        scale = [[pl.scale[0], 0.0, 0.0], [0.0, pl.scale[1], 0.0], [0.0, 0.0, pl.scale[2]]]
        frames[path] = (quat_mul(anc_turn, own), _mat_mul(_mat_mul(anc_map, quat_to_matrix(own)), scale))
        out.append((path, offset, turn))
    return out


# ---- the vehicle -------------------------------------------------------------------------------------------

class Node:
    """A prefab node at its pose after the reshape (game space)."""

    __slots__ = ("path", "position", "rotation", "scale", "kind", "part", "file", "lod_group", "active", "children")

    def __init__(self, path, position, rotation=(0, 0, 0, 1), scale=(1, 1, 1), kind="node", part=None, file=None, lod_group=False,
                 active=True):
        self.path, self.position, self.rotation, self.scale = path, tuple(position), tuple(rotation), tuple(scale)
        self.kind, self.part, self.file, self.lod_group, self.active, self.children = kind, part, file, lod_group, active, []

    @property
    def name(self):
        return self.path.rsplit("/", 1)[-1]


def repo_root(start=None):
    """The Werkstatt checkout: WERKSTATT_DIR, else the folder holding this add-on if it is inside one."""
    for candidate in (os.environ.get("WERKSTATT_DIR"), start,
                      os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))):
        if candidate and os.path.isfile(os.path.join(candidate, "Makefile")) and os.path.isdir(os.path.join(candidate, "vehicles")):
            return os.path.abspath(candidate)
    return None


def list_vehicles(root):
    out = []
    for name in sorted(os.listdir(os.path.join(root, "vehicles"))):
        manifest = os.path.join(root, "vehicles", name, "vehicle.json")
        if not os.path.isfile(manifest):
            continue
        try:
            m = read_json(manifest, root)
            if not isinstance(m, dict):
                raise WerkstattError(f"vehicles/{name}/vehicle.json must hold an object")
            donor = m.get("donor", "")
            nodes, copies, _ = read_placements(os.path.join(root, "vehicles", name, PLACEMENTS))
        except WerkstattError as e:
            out.append({"name": name, "codename": name, "donor": "", "patch": False, "built": False, "extracted": False,
                        "placements": 0, "error": str(e)})
            continue
        out.append({"name": name, "codename": m.get("codename", name), "donor": donor, "patch": bool(m.get("patch")),
                    "built": os.path.isfile(os.path.join(root, "vehicles", name, "build", "body_LOD0.obj"))
                             or bool(m.get("patch")),
                    "extracted": os.path.isfile(os.path.join(root, "extracted", donor.lower(), "upgrades.json")),
                    "placements": len(nodes) + len(copies)})
    return out


IDENTITY_POSE = ((0.0, 0.0, 0.0, 1.0), (0.0, 0.0, 0.0))


def _add(a, b):
    return tuple(x + y for x, y in zip(a, b))


def _sub(a, b):
    return tuple(x - y for x, y in zip(a, b))


class Vehicle:
    """A vehicle folder read as the scene shows it: parts, attach points and upgrade nodes, all in game space
    where the plugin's reshape puts them at spawn (wheelbase sweep, centre of mass, track, the definition's
    transforms), plus its placements."""

    def __init__(self, root, name):
        self.root, self.name = root, name
        self.folder = os.path.join(root, "vehicles", name)
        manifest = os.path.join(self.folder, "vehicle.json")
        if not os.path.isfile(manifest):
            raise WerkstattError(f"no vehicle called {name} in {root}/vehicles")
        self.manifest = read_json(manifest, root)
        if not isinstance(self.manifest, dict) or not isinstance(self.manifest.get("donor"), str):
            raise WerkstattError(f"vehicles/{name}/vehicle.json names no donor")
        self.codename = self.manifest.get("codename", name)
        self.donor = self.manifest["donor"]
        self.extracted = os.path.join(root, "extracted", self.donor.lower())
        for need, what in ((os.path.join(self.extracted, "nodes.json"), "node facts"),
                           (os.path.join(self.extracted, "upgrades.json"), "upgrade nodes")):
            if not os.path.isfile(need):
                raise WerkstattError(f"the {self.donor}'s {what} aren't extracted yet ({os.path.relpath(need, root)}): run `make extract`")
        facts = read_json(os.path.join(self.extracted, "nodes.json"), root)["nodes"]
        upgrades = read_json(os.path.join(self.extracted, "upgrades.json"), root)
        self.cosmetic_root = upgrades.get("cosmeticRoot") or ""      # empty: the donor has no upgrade nodes
        self.poses = self._reshape(facts)
        self.nodes = {}
        for n in upgrades["nodes"]:
            q, _ = self.pose(n["path"])
            kind = "option" if "part" in n else ("piece" if n.get("lodGroup") else "node")
            self.nodes[n["path"]] = Node(n["path"], self.place(n["path"], n["position"]), quat_mul(q, tuple(n["rotation"])),
                                         n["scale"], kind, n.get("part"), n.get("file"), bool(n.get("lodGroup")),
                                         n.get("active", True))
        for path, node in self.nodes.items():
            parent = self.nodes.get(parent_path(path))
            if parent is not None:
                parent.children.append(node)
        for node in self.nodes.values():
            if node.kind == "node" and any(self._has_option_below(c) for c in node.children):
                node.kind = "group"
        self.wheel_nodes = {f["path"]: self.place(f["path"], f["position"]) for f in facts
                            if parent_path(f["path"]) == "Axles/WheelMeshes"}
        self.attach_points = {}
        for f in facts:
            if self.cosmetic_root and f["path"].startswith(self.cosmetic_root):
                continue
            types = {c["type"] for c in f["components"]}
            if self._is_attach_point(f["path"], types):
                self.attach_points[f["path"]] = self.place(f["path"], f["position"])
        self.tool_nodes = self._tool_nodes()
        self.placements, self.copies, self.notes = read_placements(os.path.join(self.folder, PLACEMENTS))

    def _tool_nodes(self):
        """The definition's toolNodes ({node path: toolset ItemId}) as the plugin reads them (ToolNodes.cs): none on
        a patch, which is the stock car, and none when the block is malformed (a repeated key included)."""
        block = self.manifest.get("toolNodes")
        if self.manifest.get("patch") or not isinstance(block, dict) or isinstance(block, _RepeatedKeys):
            return {}
        tools = {p: t for p, t in block.items() if p != "notes"}
        if not all(_is_path(p) and isinstance(t, int) and not isinstance(t, bool) and 0 < t < 2 ** 32 for p, t in tools.items()):
            return {}
        return tools

    @staticmethod
    def _is_attach_point(path, types):
        return (path.startswith(("Winch/WinchAttachPoints/", "Lights/", "Axles/WheelMeshes/", "WaterDetector/"))
                and path.count("/") <= 2) or path in ("CoM", "AckermanRef") or "MB:CarWinchPoint" in types

    def _has_option_below(self, node):
        return node.kind == "option" or any(self._has_option_below(c) for c in node.children)

    def _reshape(self, facts):
        """The plugin's Reshape (DerivedVehicles.cs) on the donor's nodes, step by step in its order: the wheelbase
        sweep (a node behind the body cut moves back with its subtree, otherwise its children are looked at), the
        centre of mass to its share of the new wheelbase, each corner's wheel nodes out to half the track, then the
        definition's transforms (a node to its position, then turned by its yaw about the car's up, its subtree
        with it). Returns {path: (q, t)}: a donor-space point x in that node's subtree lands at q x + t."""
        m = self.manifest
        donor = {f["path"]: tuple(f["position"]) for f in facts}
        children = {}
        for path in donor:
            children.setdefault(parent_path(path), []).append(path)
        poses = {}

        def subtree(path):
            yield path
            for c in children.get(path, []):
                yield from subtree(c)

        def where(path):
            q, t = poses.get(path, IDENTITY_POSE)
            return _add(quat_rotate(q, donor[path]), t)

        def move(path, q_op, t_op):
            for p in subtree(path):
                q, t = poses.get(p, IDENTITY_POSE)
                poses[p] = (quat_mul(q_op, q), _add(quat_rotate(q_op, t), t_op))

        still = IDENTITY_POSE[0]
        front = donor.get("Axles/WheelMeshes/FL", (0.0, 0.0, m["donorAxleZ"]["front"]))[2]
        rear = donor.get("Axles/WheelMeshes/RL", (0.0, 0.0, m["donorAxleZ"]["rear"]))[2]
        self.shift = -(m["wheelbase"] - (front - rear))
        self.cut = max((step[1] for step in m.get("bodyCut", [])), default=float("-inf"))
        com = donor.get("CoM")
        com_target = rear + self.shift + (com[2] - rear) * (m["wheelbase"] / (front - rear)) if com else None
        self.com_target = com_target

        def sweep(parent):
            for c in children.get(parent, []):
                if where(c)[2] < self.cut:
                    move(c, still, (0.0, 0.0, self.shift))
                else:
                    sweep(c)

        sweep("")
        if com is not None:
            move("CoM", still, (0.0, 0.0, com_target - where("CoM")[2]))
        if "track" in m and "Axles/WheelMeshes/FR" in donor:
            widen = m["track"] / 2 - abs(where("Axles/WheelMeshes/FR")[0])
            for corner in ("FL", "FR", "RL", "RR"):
                dx = -widen if corner[1] == "L" else widen
                for path in (f"Axles/WheelColliders/Wheel{corner}", f"Axles/WheelMeshes/{corner}",
                             f"Effects/TerrainParticles/{corner}Wheel", f"Audio/{corner}Wheel"):
                    if path in donor:
                        move(path, still, (dx, 0.0, 0.0))
        for path, transform in m.get("transforms", {}).items():
            if path not in donor:
                continue                                # the plugin skips a node the prefab lacks too
            if "position" in transform:
                move(path, still, _sub(tuple(transform["position"]), where(path)))
            if transform.get("yaw"):
                turn, pivot = quat_axis((0.0, 1.0, 0.0), transform["yaw"]), where(path)
                move(path, turn, _sub(pivot, quat_rotate(turn, pivot)))
        return poses

    def pose(self, path):
        """(q, t) of the reshape for a node: its own, or its nearest ancestor's among the donor's nodes."""
        while path:
            if path in self.poses:
                return self.poses[path]
            path = parent_path(path)
        return IDENTITY_POSE

    def place(self, path, point):
        """A donor-space point of the node at path (its pivot, or a vertex of its mesh) where the reshape puts it."""
        q, t = self.pose(path)
        return _add(quat_rotate(q, tuple(point)), t)

    # -- files the scene shows
    def part_files(self):
        """(part name, node path, OBJ path, kind) for the body and colliders this vehicle builds or the donor's."""
        build = os.path.join(self.folder, "build")
        out = []
        for path, entry in sorted(self.manifest.get("meshes", {}).items()):
            name = entry if isinstance(entry, str) else entry["file"]
            file = os.path.join(build, name)
            if not os.path.isfile(file) and name.startswith("extracted/"):
                file = os.path.join(self.root, name)
            if not name.endswith((".obj",)) or not os.path.isfile(file):
                continue
            if "_LOD" in name and not name.endswith("LOD0.obj"):
                continue
            kind = "collider" if path.startswith("Collider/") else ("axle" if path.startswith("Axles/") else "body")
            out.append((os.path.splitext(os.path.basename(name))[0], path, file, kind))
        if not any(k == "body" for *_, k in out):
            donor_body = os.path.join(self.extracted, f"Parts__{self.donor}__{self.donor}_body_LOD0.obj")
            if os.path.isfile(donor_body):
                out.append((f"{self.donor}_body_LOD0", f"Parts/{self.donor}/{self.donor}_body_LOD0", donor_body, "body"))
        return out

    def donor_body(self):
        f = os.path.join(self.extracted, f"Parts__{self.donor}__{self.donor}_body_LOD0.obj")
        return f if os.path.isfile(f) else None

    def atlas(self):
        """(image path or None, note or None): the donor's atlas for the parts that carry its UVs. The composite
        (tools/composite_atlas.py, which `make extract` runs) is the livery with the glass shaded dark, as the game
        draws it; the bare livery (<Donor>_skin00) shows the windows in the livery's colour, so the note says so.
        With neither, the scene keeps flat colours and the note says what to run."""
        textures = os.path.join(self.root, "extracted", "textures")
        composite = os.path.join(textures, f"{self.donor}_composite.png")
        if os.path.isfile(composite):
            return composite, None
        skin = os.path.join(textures, f"{self.donor}_skin00.png")
        want = os.path.relpath(composite, self.root)
        if os.path.isfile(skin):
            return skin, f"Windows in the livery's colour: no {want} (run `make extract`)"
        return None, f"Flat colours: no {want} (run `make extract`)"

    def wheels(self):
        """(corner, game position, radius, width) for the wheel references: each corner's wheel node where the
        reshape puts it (the definition's numbers when the donor's node facts lack it), with the fitted tyre."""
        m = self.manifest
        wheel = dict(m.get("wheel", {}), **m.get("tyre", {}))
        if "radius" not in wheel:
            return []
        front = m["donorAxleZ"]["front"]
        rear = front - m["wheelbase"]
        half = m["track"] / 2
        y = wheel.get("y", wheel["radius"])
        return [(c, self.wheel_nodes.get(f"Axles/WheelMeshes/{c}",
                                         (half if c[1] == "R" else -half, y, front if c[0] == "F" else rear)),
                 wheel["radius"], wheel.get("width", 0.3))
                for c in ("FL", "FR", "RL", "RR")]

    def donor_wheel(self):
        """The donor's wheel as modelled (the definition's "wheel": radius, width), which the wheel meshes are
        made for; the plugin scales each wheel node by the fitted tyre over it (ScaleTyres)."""
        wheel = self.manifest.get("wheel", {})
        return wheel.get("radius") or 1.0, wheel.get("width") or 1.0

    def is_turned(self, path):
        """Whether the game turns this node relative to the car at its base pose. Scale applies along a node's own
        axes in game, and the add-on's empties carry no base rotation, so a non-uniform scale shows right only
        on nodes that aren't turned."""
        node = self.nodes.get(path)
        if node is None:
            return False
        # A half turn about an axis only flips signs, so a scale along the car's axes still lands on the node's.
        m = quat_to_matrix(node.rotation)
        return any(abs(abs(m[i][i]) - 1.0) > 1e-4 for i in range(3))

    BUILT_KINDS = ("group", "option", "piece")

    def is_built(self, path, source=None):
        """Whether the scene builds this node (a slot group, an option or a piece inside one), or, for a copy, its
        source. The scene owns these entries whether or not they are in it now (a copy deleted or undone); a
        file's entries for anything else are kept as they are."""
        node = self.nodes.get(source or path)
        return node is not None and node.kind in self.BUILT_KINDS

    def option_file(self, node):
        return os.path.join(self.extracted, node.file) if node.file else None

    def slot_of(self, path):
        node = self.nodes.get(path)
        while node is not None:
            if node.part and (node.part.get("cosmeticType") or node.part.get("upgradeType")):
                return node.part.get("cosmeticType") or node.part.get("upgradeType")
            node = self.nodes.get(parent_path(node.path))
        rest = path[len(self.cosmetic_root) + 1:].split("/")
        return rest[1] if len(rest) > 1 else rest[0]

    def options(self):
        return [n for n in self.nodes.values() if n.kind == "option"]

    def options_below(self, path):
        return [n for p, n in self.nodes.items() if n.kind == "option" and p.startswith(path + "/")]

    def in_game(self, path):
        """How the game shows a node, as (how, toolset ItemIds). It shows while every node on its path is active: one
        the definition's toolNodes names while the loadout carries that tool (the plugin's ToolNodes.cs), an option
        with a part while its item is fitted (the game's), any other node as the prefab has it. So "never" when a node
        on the path is inactive and nothing turns it on (Performance/Winch/Winch_01 and Performance/Rollcage/rollcage
        on the Mammoth: no part, inactive, unless a toolNodes entry names them, as our trucks' does the winch); else
        "item" when an item is needed, with the tools also needed; "tool" when only tools are; "always" when nothing
        is (an option without a part that the prefab shows). A slot group reads as its options when they all agree,
        else ("item", ())."""
        node = self.nodes.get(path)
        if node is not None and node.kind == "group":
            found = {self.in_game(o.path) for o in self.options_below(path)}
            return found.pop() if len(found) == 1 else ("item", ())
        item, tools = False, set()
        while node is not None:
            if node.path in self.tool_nodes:
                tools.add(self.tool_nodes[node.path])
            elif node.kind == "option" and (node.part or {}).get("name"):
                item = True
            elif not node.active:
                return ("never", ())
            node = self.nodes.get(parent_path(node.path))
        return ("item" if item else "tool" if tools else "always", tuple(sorted(tools)))

    def placement(self, path):
        return self.copies.get(path) or self.placements.get(path) or Placement()

    def next_copy_path(self, source, taken=()):
        """The next free copy path: inside an option copied, beside a piece. `taken` adds the scene's paths."""
        node_path = source if self.nodes.get(source) and self.nodes[source].kind == "option" else parent_path(source)
        base = source.rsplit("/", 1)[-1]
        n = 2
        while True:
            candidate = f"{node_path}/{base}~{n}"
            if candidate not in self.copies and candidate not in self.nodes and candidate not in taken:
                return candidate
            n += 1

    def save(self):
        return write_placements(os.path.join(self.folder, PLACEMENTS), self.placements, self.copies, self.notes)
