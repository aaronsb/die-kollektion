"""The add-on as Python calls, for scripts and agents (e.g. over the Blender MCP server's execute_blender_code).

Every function returns a plain dict (or a list of them) that reads back as JSON. Success carries "ok": True;
a problem returns {"ok": False, "error": "<plain message>"} instead of raising, so a caller sees what to fix.
Node arguments take a full node path or any unique suffix of one ("Winch_01", "Roof/RoofSpare"). Axes are the
game's: x right, y up, z forward.

    from werkstatt_addon import api
    api.open_vehicle("megaloceros")
    api.items(slot="Roof")
    api.frame("Roof/RoofSpare")
    api.nudge("Roof/RoofSpare", "y", 2, "cm")
    api.save()
"""
import functools, os, subprocess, time

import bpy
import mathutils

from . import model, scene

UNITS = {"mm": 0.001, "cm": 0.01, "dm": 0.1, "m": 1.0}
AXES = {"x": (1.0, 0.0, 0.0), "y": (0.0, 1.0, 0.0), "z": (0.0, 0.0, 1.0)}

_state = {"vehicle": None}


def _api(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            result = fn(*args, **kwargs)
        except model.WerkstattError as e:
            return {"ok": False, "error": str(e)}
        if isinstance(result, dict):
            return {"ok": True, **result}
        return result
    return wrapper


# ---- where we are --------------------------------------------------------------------------------------------

def werkstatt_root():
    prefs = None
    try:
        prefs = bpy.context.preferences.addons[__package__].preferences
    except (KeyError, AttributeError):
        pass
    configured = getattr(prefs, "werkstatt_dir", "") if prefs else ""
    root = model.repo_root(bpy.path.abspath(configured) if configured else None)
    if root is None:
        raise model.WerkstattError("no Werkstatt checkout found: set the folder in the add-on's preferences "
                                   "(Edit > Preferences > Add-ons > Die Kollektion Werkstatt) or WERKSTATT_DIR")
    return root


_branch_cache = {}


def branch(root=None):
    """(branch name, whether vehicles/ has uncommitted changes); asked of git at most every few seconds."""
    root = root or werkstatt_root()
    now = time.monotonic()
    cached = _branch_cache.get(root)
    if cached and now - cached[0] < 3:
        return cached[1]
    _branch_cache[root] = (now, _ask_git(root))
    return _branch_cache[root][1]


def _ask_git(root):
    try:
        r = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=root, capture_output=True, text=True, timeout=10)
        name = r.stdout.strip() if r.returncode == 0 else None
        dirty = subprocess.run(["git", "status", "--porcelain", "--", "vehicles"], cwd=root, capture_output=True, text=True, timeout=10)
        return name, bool(dirty.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        return None, False


def _vehicle():
    v = _state["vehicle"]
    root = scene.root_collection()
    if root is None:
        raise model.WerkstattError("no vehicle is open: open one first (open_vehicle)")
    if v is None or v.name != root.get("werkstatt_vehicle") or v.root != root.get("werkstatt_root"):
        v = model.Vehicle(root["werkstatt_root"], root["werkstatt_vehicle"])
        _state["vehicle"] = v
    return v


def _empty(node):
    if not node:
        obj = bpy.context.view_layer.objects.active
        while obj is not None and not obj.get("werkstatt_node"):
            obj = obj.parent
        if obj is None or obj.get("werkstatt_copy_part"):
            raise model.WerkstattError("select an upgrade item (or name one)")
        return obj
    empties = scene.editable_empties()
    if node in empties:
        return empties[node]
    matches = [p for p in empties if p == node or p.endswith("/" + node)]
    if not matches:
        raise model.WerkstattError(f"no upgrade node matches {node!r}")
    if len(matches) > 1:
        shown = ", ".join(sorted(matches)[:6])
        raise model.WerkstattError(f"{node!r} matches {len(matches)} nodes ({shown}{', ...' if len(matches) > 6 else ''}); give more of the path")
    return empties[matches[0]]


def _describe(empty, vehicle):
    path = empty["werkstatt_node"]
    pl = scene.read_placement(empty)
    node = vehicle.nodes.get(path)
    source = empty.get("werkstatt_source")
    part = (node.part if node else None) or (vehicle.nodes[source].part if source and source in vehicle.nodes else None)
    option = _option_of(empty)
    return {"node": path, "kind": empty.get("werkstatt_kind"), "slot": vehicle.slot_of(source or path),
            "part": (part or {}).get("name"), "shown": scene.is_shown(option) if option else True,
            "offset": model.clean(pl.offset, model.OFFSET_DIGITS), "rotation": model.clean(pl.rotation, model.ROTATION_DIGITS),
            "scale": model.clean(pl.scale, model.SCALE_DIGITS), **({"source": source} if source else {})}


def _option_of(empty):
    e = empty
    while e is not None:
        if e.get("werkstatt_kind") == "option":
            return e
        e = e.parent
    return None


# ---- the calls --------------------------------------------------------------------------------------------

@_api
def status():
    """The checkout, its branch (and whether vehicles/ has uncommitted changes) and the open vehicle."""
    root = werkstatt_root()
    name, dirty = branch(root)
    open_root = scene.root_collection()
    return {"root": root, "branch": name, "uncommitted": dirty,
            "vehicle": open_root.get("werkstatt_vehicle") if open_root else None}


@_api
def vehicles():
    """Every vehicle folder in the checkout: name, codename, donor, built, extracted, placements."""
    return {"vehicles": model.list_vehicles(werkstatt_root())}


@_api
def open_vehicle(name, show=()):
    """Builds the vehicle's scene (parts, attach points, references, upgrades, ghost) from its files."""
    root = werkstatt_root()
    v = model.Vehicle(root, name)
    if not v.manifest.get("patch") and not os.path.isfile(os.path.join(v.folder, "build", "body_LOD0.obj")):
        raise model.WerkstattError(f"{name} isn't built yet: run `make build` (or `make loop V={name}`) in {root}")
    show = [_resolve_option(v, s) for s in show]
    scene.build(v, show)
    _state["vehicle"] = v
    return {"vehicle": name, "codename": v.codename, "donor": v.donor, "options": len(v.options()),
            "placements": len(v.placements), "copies": len(v.copies)}


def _resolve_option(v, name):
    matches = [p for p, n in v.nodes.items() if n.kind == "option" and (p == name or p.endswith("/" + name))]
    if len(matches) != 1:
        raise model.WerkstattError(f"{name!r} matches {len(matches)} upgrade options")
    return matches[0]


@_api
def items(slot=None, kind=None):
    """Placeable nodes with their slot, part, visibility and placement; filter by slot or kind."""
    v = _vehicle()
    out = []
    for path, empty in sorted(scene.editable_empties().items()):
        d = _describe(empty, v)
        if (slot is None or (d["slot"] or "").lower() == slot.lower()) and (kind is None or d["kind"] == kind):
            out.append(d)
    return {"items": out}


@_api
def placement(node=None):
    """One node's placement (offset m, rotation degrees, scale) as the save would write it."""
    return _describe(_empty(node), _vehicle())


@_api
def set_placement(node=None, offset=None, rotation=None, scale=None):
    """Sets a node's placement outright; any value left out keeps its current value."""
    e = _empty(node)
    pl = scene.read_placement(e)
    new = model.Placement(offset if offset is not None else pl.offset, rotation if rotation is not None else pl.rotation,
                          scale if scale is not None else pl.scale, pl.source)
    if any(s <= 0 for s in new.scale):
        raise model.WerkstattError("scale must be above 0")
    scene.apply_placement(e, new)
    return _describe(e, _vehicle())


@_api
def nudge(node=None, axis="y", steps=1, unit="cm"):
    """Moves a node by steps x unit along a game axis (x right, y up, z forward) of its parent's frame."""
    if axis not in AXES or unit not in UNITS:
        raise model.WerkstattError(f"axis is one of x, y, z and unit one of {', '.join(UNITS)}")
    e = _empty(node)
    pl = scene.read_placement(e)
    delta = [a * steps * UNITS[unit] for a in AXES[axis]]
    scene.apply_placement(e, model.Placement(tuple(o + d for o, d in zip(pl.offset, delta)), pl.rotation, pl.scale, pl.source))
    return _describe(e, _vehicle())


@_api
def rotate(node=None, axis="y", steps=1, degrees=1.0):
    """Turns a node by steps x degrees about a game axis of its parent's frame (x pitch, y yaw, z roll), about its pivot."""
    if axis not in AXES:
        raise model.WerkstattError("axis is one of x, y, z")
    e = _empty(node)
    pl = scene.read_placement(e)
    q = model.quat_mul(model.quat_axis(AXES[axis], steps * degrees), model.euler_to_quat(pl.rotation))
    scene.apply_placement(e, model.Placement(pl.offset, model.quat_to_euler(q), pl.scale, pl.source))
    return _describe(e, _vehicle())


@_api
def scale_by(node=None, factor=1.0, axis=None):
    """Multiplies a node's scale, on one game axis or all three."""
    if factor <= 0:
        raise model.WerkstattError("factor must be above 0")
    e = _empty(node)
    pl = scene.read_placement(e)
    s = [v * (factor if axis in (None, a) else 1.0) for v, a in zip(pl.scale, "xyz")]
    scene.apply_placement(e, model.Placement(pl.offset, pl.rotation, s, pl.source))
    return _describe(e, _vehicle())


@_api
def reset(node=None):
    """Puts a node back at its base pose (the donor's, after the reshape); a copy goes back onto its source."""
    e = _empty(node)
    scene.apply_placement(e, model.Placement(source=e.get("werkstatt_source")))
    return _describe(e, _vehicle())


@_api
def show(node, shown=True):
    """Shows or hides an upgrade option (and its pieces and copies) in the viewport and renders."""
    e = _option_of(_empty(node))
    if e is None:
        raise model.WerkstattError(f"{node} isn't inside an upgrade option")
    scene.set_shown(e, shown)
    return {"node": e["werkstatt_node"], "shown": bool(shown)}


@_api
def show_slot(slot, shown=True):
    """Shows or hides every option of a slot (e.g. Roof, FrontBumper, Winch)."""
    v = _vehicle()
    count = 0
    for path, e in scene.editable_empties().items():
        if e.get("werkstatt_kind") == "option" and (v.slot_of(path) or "").lower() == slot.lower():
            scene.set_shown(e, shown)
            count += 1
    if not count:
        raise model.WerkstattError(f"no options in a slot called {slot}")
    return {"slot": slot, "options": count, "shown": bool(shown)}


@_api
def duplicate(node=None):
    """Adds a copy of an option or of a piece inside one, beside its source, shown with it; returns the copy."""
    v = _vehicle()
    e = _empty(node)
    source = e.get("werkstatt_source") or e["werkstatt_node"]
    if e.get("werkstatt_kind") == "copy":
        raise model.WerkstattError("copy the original, not a copy")
    if e.get("werkstatt_kind") == "group" or (e.get("werkstatt_kind") == "piece" and _option_of(e) is None):
        raise model.WerkstattError(f"{source} is a slot group; copy an option or a piece inside one")
    scene.collect(v)
    path = v.next_copy_path(source)
    copy = scene.add_copy(v, path, source)
    option = _option_of(copy)
    scene.set_shown(option, scene.is_shown(option) if option else True)
    v.copies[path] = model.Placement(source=source)
    bpy.context.view_layer.objects.active = copy
    return _describe(copy, v)


@_api
def delete_copy(node=None):
    """Removes a copy (never an original)."""
    e = _empty(node)
    if e.get("werkstatt_kind") != "copy":
        raise model.WerkstattError("only copies can be deleted; reset an original instead")
    path = e["werkstatt_node"]
    for obj in [e] + list(e.children_recursive):
        bpy.data.objects.remove(obj, do_unlink=True)
    _vehicle().copies.pop(path, None)
    return {"node": path, "deleted": True}


@_api
def frame(node=None):
    """Selects a node and points the 3D view at it (when there is one); returns its centre and size in game metres."""
    e = _empty(node)
    for obj in bpy.context.view_layer.objects:
        obj.select_set(False)
    bpy.context.view_layer.update()
    family = [e] + list(e.children_recursive)
    for o in [o for o in family if o.visible_get()] or [e]:
        o.select_set(True)
    bpy.context.view_layer.objects.active = e
    points = [o.matrix_world @ mathutils.Vector(c) for o in family if o.type == "MESH" for c in o.bound_box] or [e.matrix_world.translation]
    lo = [min(p[i] for p in points) for i in range(3)]
    hi = [max(p[i] for p in points) for i in range(3)]
    centre = [(a + b) / 2 for a, b in zip(lo, hi)]
    framed = False
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == "VIEW_3D":
                region = next((r for r in area.regions if r.type == "WINDOW"), None)
                with bpy.context.temp_override(window=window, area=area, region=region):
                    bpy.ops.view3d.view_selected()
                framed = True
    return {"node": e["werkstatt_node"], "centre": model.clean(model.blender_to_game(centre), 4),
            "size": model.clean(model.scale_blender_to_game(tuple(b - a for a, b in zip(lo, hi))), 4), "framed": framed}


@_api
def ghost(shown=True, offset=3.0):
    """Shows the donor's stock body as a wireframe, `offset` metres to the side (0 overlays it)."""
    scene.set_ghost(shown, offset)
    return {"ghost": bool(shown), "offset": offset}


@_api
def save():
    """Writes the open vehicle's placements.json from the scene (only offsets that differ from the base pose).
    Only writes the file: committing it is yours."""
    v = scene.collect(_vehicle())
    result = v.save()
    path = os.path.join(v.folder, model.PLACEMENTS)
    return {"file": os.path.relpath(path, v.root), "result": result, "placements": len(v.placements), "copies": len(v.copies)}


@_api
def run_loop():
    """Runs `make loop V=<vehicle>` in the checkout (build, gates, contact sheet); returns its exit code and last lines."""
    v = _vehicle()
    r = subprocess.run(["make", "loop", f"V={v.name}"], cwd=v.root, capture_output=True, text=True)
    text = (r.stdout + r.stderr).strip()
    block = bpy.data.texts.get("werkstatt-loop.log") or bpy.data.texts.new("werkstatt-loop.log")
    block.from_string(text)
    return {"code": r.returncode, "tail": text.splitlines()[-15:], "log": "werkstatt-loop.log (Blender text)"}
