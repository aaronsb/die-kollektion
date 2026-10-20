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
    sx = max(-1.0, min(1.0, -r[1][2]))
    x = math.asin(sx)
    if abs(sx) < 0.9999999:
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
    try:
        values = [float(v) for v in value]
    except (TypeError, ValueError):
        raise WerkstattError(f"{name} must be three numbers, got {value!r}") from None
    if len(values) != 3 or any(isinstance(v, (str, bytes, bool)) for v in value):
        raise WerkstattError(f"{name} must be three numbers, got {value!r}")
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


def read_json(path, root=None):
    """A JSON file's content; a broken file is a WerkstattError naming it."""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
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

    __slots__ = ("path", "position", "rotation", "scale", "kind", "part", "file", "lod_group", "children")

    def __init__(self, path, position, rotation=(0, 0, 0, 1), scale=(1, 1, 1), kind="node", part=None, file=None, lod_group=False):
        self.path, self.position, self.rotation, self.scale = path, tuple(position), tuple(rotation), tuple(scale)
        self.kind, self.part, self.file, self.lod_group, self.children = kind, part, file, lod_group, []

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


class Vehicle:
    """A vehicle folder read as the scene shows it: parts, attach points and upgrade nodes, all in game space
    after the reshape's wheelbase sweep, plus its placements."""

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
        self.shift, self.cut = self._sweep_parameters()
        moved = self._swept(facts)
        self.sweep = moved          # path -> metres moved back with the rear (meshes move with their node)
        self.nodes = {}
        for n in upgrades["nodes"]:
            dz = moved.get(n["path"], 0.0)
            p = n["position"]
            kind = "option" if "part" in n else ("piece" if n.get("lodGroup") else "node")
            self.nodes[n["path"]] = Node(n["path"], (p[0], p[1], p[2] + dz), n["rotation"], n["scale"], kind,
                                         n.get("part"), n.get("file"), bool(n.get("lodGroup")))
        for path, node in self.nodes.items():
            parent = self.nodes.get(parent_path(path))
            if parent is not None:
                parent.children.append(node)
        for node in self.nodes.values():
            if node.kind == "node" and any(self._has_option_below(c) for c in node.children):
                node.kind = "group"
        self.attach_points = {}
        widen = self._track_widening(facts)
        for f in facts:
            if self.cosmetic_root and f["path"].startswith(self.cosmetic_root):
                continue
            types = {c["type"] for c in f["components"]}
            if self._is_attach_point(f["path"], types):
                p = f["position"]
                dx = widen.get(f["path"], 0.0)
                self.attach_points[f["path"]] = (p[0] + dx, p[1], p[2] + moved.get(f["path"], 0.0))
        self.placements, self.copies, self.notes = read_placements(os.path.join(self.folder, PLACEMENTS))

    @staticmethod
    def _is_attach_point(path, types):
        return (path.startswith(("Winch/WinchAttachPoints/", "Lights/", "Axles/WheelMeshes/", "WaterDetector/"))
                and path.count("/") <= 2) or path in ("CoM", "AckermanRef") or "MB:CarWinchPoint" in types

    def _has_option_below(self, node):
        return node.kind == "option" or any(self._has_option_below(c) for c in node.children)

    def _track_widening(self, facts):
        """dx per wheel node from the plugin's track change (Reshape): each corner's wheel mesh moves out (or in)
        to half the track, measured from the donor's front right wheel."""
        if "track" not in self.manifest:
            return {}
        fr = next((f for f in facts if f["path"] == "Axles/WheelMeshes/FR"), None)
        if fr is None:
            return {}
        widen = self.manifest["track"] / 2 - abs(fr["position"][0])
        return {f"Axles/WheelMeshes/{c}": (-widen if c[1] == "L" else widen) for c in ("FL", "FR", "RL", "RR")}

    def _sweep_parameters(self):
        m = self.manifest
        cut = max((s[1] for s in m.get("bodyCut", [])), default=float("-inf"))
        donor_wheelbase = m["donorAxleZ"]["front"] - m["donorAxleZ"]["rear"]
        return -(m["wheelbase"] - donor_wheelbase), cut

    def _swept(self, facts):
        """dz per path from the plugin's Sweep: a child of the root behind the cut moves with its subtree,
        otherwise its children are looked at in turn."""
        children = {}
        for f in facts:
            children.setdefault(parent_path(f["path"]), []).append(f)
        moved = {}

        def carry(path):
            moved[path] = self.shift
            for c in children.get(path, []):
                carry(c["path"])

        def visit(parent):
            for c in children.get(parent, []):
                if c["position"][2] < self.cut:
                    carry(c["path"])
                else:
                    visit(c["path"])

        if self.shift:
            visit("")
        return moved

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

    def wheels(self):
        """(corner, game position, radius, width) for the wheel references, from the definition."""
        m = self.manifest
        wheel = dict(m.get("wheel", {}), **m.get("tyre", {}))
        if "radius" not in wheel:
            return []
        front = m["donorAxleZ"]["front"]
        rear = front - m["wheelbase"]
        half = m["track"] / 2
        y = wheel.get("y", wheel["radius"])
        return [(c, (half if c[1] == "R" else -half, y, front if c[0] == "F" else rear), wheel["radius"], wheel.get("width", 0.3))
                for c in ("FL", "FR", "RL", "RR")]

    def donor_wheel(self):
        """The donor's wheel as modelled (the definition's "wheel": radius, width), which the wheel meshes are
        made for; the plugin scales each wheel node by the fitted tyre over it (ScaleTyres)."""
        wheel = self.manifest.get("wheel", {})
        return wheel.get("radius") or 1.0, wheel.get("width") or 1.0

    def part_shift(self, path):
        """Metres a part's node moves back with the rear in the sweep. Built meshes are in the donor's root space
        and the plugin maps them through the donor's layout before the sweep, so the rear axle and its springs
        move with their node, as in game."""
        return self.sweep.get(path, 0.0)

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
