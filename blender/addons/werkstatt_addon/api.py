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
import functools, hashlib, os, subprocess

import bpy
import mathutils

from . import model, review, scene

UNITS = {"mm": 0.001, "cm": 0.01, "dm": 0.1, "m": 1.0}
AXES = {"x": (1.0, 0.0, 0.0), "y": (0.0, 1.0, 0.0), "z": (0.0, 0.0, 1.0)}
MAX_STEPS = 1000

# The open vehicle's model; per (checkout, vehicle) the placements file's hash when this session last read or
# wrote it (the root collection keeps one too, which survives a reload or a restart); per checkout whether
# vehicles/ has uncommitted changes, once git was asked.
_state = {"vehicle": None, "sha": {}, "dirty": {}}


def _api(fn=None, *, undo=None):
    """Wraps a call: a problem comes back as {"ok": False, "error": ...}, never as a traceback. A call that
    changes the scene pushes an undo step named `undo`, however it was called: from a script, over MCP or by a
    panel operator (which carry no UNDO flag of their own, since Blender pushes none for operators run from
    Python)."""
    if fn is None:
        return functools.partial(_api, undo=undo)

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            result = fn(*args, **kwargs)
        except model.WerkstattError as e:
            return {"ok": False, "error": str(e)}
        except Exception as e:      # a bug, or a value the checks missed: still a message, not a traceback
            return {"ok": False, "error": f"{fn.__name__} failed: {type(e).__name__}: {e}"}
        if undo:
            _undo_push(f"Werkstatt: {undo}")
        if isinstance(result, dict):
            return {"ok": True, **result}
        return result
    return wrapper


def _undo_push(message):
    """One undo step for a call made outside an operator (a script, the MCP server's code, which runs from a timer
    with no window in its context)."""
    windows = bpy.context.window_manager.windows if bpy.context.window_manager else ()
    try:
        if bpy.context.window is None and windows:
            with bpy.context.temp_override(window=windows[0]):
                bpy.ops.ed.undo_push(message=message)
        else:
            bpy.ops.ed.undo_push(message=message)
    except RuntimeError:            # no undo stack (background mode)
        pass


def _text(value, name, optional=False):
    if value is None and optional:
        return None
    if not isinstance(value, str) or not value:
        raise model.WerkstattError(f"{name} must be a name (text), got {value!r}")
    return value


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


def branch(root):
    """The checkout's branch, read from .git/HEAD (no git process: the panel asks on every redraw); None when
    it isn't a git checkout, the commit when HEAD is detached."""
    git = os.path.join(root, ".git")
    try:
        if os.path.isfile(git):                              # a worktree: "gitdir: <path>"
            with open(git, encoding="utf-8") as f:
                git = os.path.join(root, f.read().split(":", 1)[1].strip())
        with open(os.path.join(git, "HEAD"), encoding="utf-8") as f:
            head = f.read().strip()
    except (OSError, IndexError):
        return None
    return head[len("ref: refs/heads/"):] if head.startswith("ref: refs/heads/") else head[:12]


def uncommitted(root, refresh=False):
    """Whether vehicles/ has uncommitted changes, or None before git was asked. Git is asked only on refresh
    (open, save, the panel's refresh button), never while Blender draws."""
    if not refresh:
        return _state["dirty"].get(root)
    try:
        r = subprocess.run(["git", "status", "--porcelain", "--", "vehicles"], cwd=root, capture_output=True,
                           text=True, timeout=10)
        _state["dirty"][root] = r.returncode == 0 and bool(r.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        _state["dirty"][root] = False
    return _state["dirty"][root]


def _vehicle():
    v = _state["vehicle"]
    root = scene.root_collection()
    if root is None:
        raise model.WerkstattError("no vehicle is open: open one first (open_vehicle)")
    if v is None or v.name != root.get("werkstatt_vehicle") or v.root != root.get("werkstatt_root"):
        v = model.Vehicle(root["werkstatt_root"], root["werkstatt_vehicle"])
        _state["vehicle"] = v
    return v


def _placements_file(v):
    return os.path.join(v.folder, model.PLACEMENTS)


WM_RECORD = "werkstatt_file_sha"


def _wm_record():
    """The hashes kept on the window manager, which Blender's undo never rolls back and Reload Scripts keeps; it is
    saved with the .blend too. {_record_key(vehicle): sha}."""
    wm = bpy.context.window_manager
    if wm is None:
        return None
    if WM_RECORD not in wm:
        wm[WM_RECORD] = {}
    return wm[WM_RECORD]


def _record_key(v):
    """A key for the vehicle in the window manager's record. Blender limits property names to 63 characters, which
    a checkout's path alone can pass, so the key is the vehicle's name (cut short) and a digest of path and name."""
    digest = hashlib.sha1(f"{v.root}|{v.name}".encode("utf-8")).hexdigest()[:16]
    return f"{v.name[:40]}-{digest}"


def _read(v, sha):
    """Records that the scene's vehicle matches its placements file as it is now (on open and save)."""
    _state["sha"][(v.root, v.name)] = sha
    scene.root_collection()["werkstatt_file_sha"] = sha
    record = _wm_record()
    if record is not None:
        record[_record_key(v)] = sha


def _known_file(v):
    """Whether the placements file is one this scene has read or written: its hash matches the one this session
    recorded, the window manager's (which an undo past a save doesn't roll back), or the root collection's (a
    .blend opened elsewhere)."""
    now = model.file_hash(_placements_file(v))
    record = _wm_record()
    known = {_state["sha"].get((v.root, v.name)), scene.root_collection().get("werkstatt_file_sha"),
             record.get(_record_key(v)) if record is not None else None} - {None}
    if not known:
        raise model.WerkstattError(f"the scene has no record of reading {v.name}'s placements file: open the vehicle "
                                   "again, or overwrite the file (Overwrite in the panel, save(force=True) in a script)")
    return now in known


def _pending(v, force=False):
    """(nodes, copies, kept) a save would write now, from the file as it is on disk (with force, an unreadable
    file counts as empty)."""
    try:
        base_nodes, base_copies, _ = model.read_placements(_placements_file(v))
    except model.WerkstattError:
        if not force:
            raise
        base_nodes, base_copies = {}, {}
    return scene.collect(v, base_nodes, base_copies)


def _unsaved(v):
    """Whether the scene holds placements the file doesn't, compared as values (a hand-formatted file, or a
    rotation written another way, is not a change)."""
    nodes, copies, _ = _pending(v)
    old_nodes, old_copies, _ = model.read_placements(_placements_file(v))
    moved = lambda entries: {p: pl for p, pl in entries.items() if not pl.is_identity()}   # noqa: E731
    nodes, old_nodes = moved(nodes), moved(old_nodes)
    return not (model.same_entries(nodes, old_nodes) and model.same_entries(copies, old_copies))


def _invalid(v):
    """Problems with what the scene would save, as messages: values the plugin's reader refuses (Blender's G or
    S can go past them), a mirrored empty, a non-uniform scale on a turned node."""
    problems = []
    for path, empty in sorted(scene.editable_empties().items()):
        name = path.rsplit("/", 1)[-1]
        if empty.matrix_basis.to_3x3().determinant() <= 0:
            problems.append(f"{name} is mirrored (a negative scale)")
            continue
        pl = scene.read_placement(empty)
        try:
            model.vector3(pl.offset, "offset", -model.MAX_OFFSET, model.MAX_OFFSET)
            model.vector3(pl.scale, "scale", model.MIN_SCALE, model.MAX_SCALE)
        except model.WerkstattError as e:
            problems.append(f"{name}: {e}")
            continue
        if max(pl.scale) - min(pl.scale) > 1e-6 and v.is_turned(empty.get("werkstatt_source") or path):
            problems.append(f"{name}: a non-uniform scale on a node the car turns")
    return problems


def _empty(node):
    _text(node, "node", optional=True)
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
def status(refresh=False):
    """The checkout, its branch, whether vehicles/ has uncommitted changes (asked of git on refresh) and the open
    vehicle; "vehicle_root" names another checkout when the open vehicle came from one (save refuses then).
    Reads only: the panel calls it on every redraw."""
    root = werkstatt_root()
    open_root = scene.root_collection()
    out = {"root": root, "branch": branch(root), "uncommitted": uncommitted(root, refresh),
           "vehicle": open_root.get("werkstatt_vehicle") if open_root else None}
    if open_root is not None and open_root.get("werkstatt_root") != root:
        out["vehicle_root"] = open_root.get("werkstatt_root")
    return out


@_api
def vehicles():
    """Every vehicle folder in the checkout: name, codename, donor, built, extracted, placements (and "error" for
    a folder whose files can't be read)."""
    return {"vehicles": model.list_vehicles(werkstatt_root())}


@_api
def unsaved():
    """Whether the open vehicle has changes its placements.json doesn't hold yet. When the file can't be read,
    that can't be told: unsaved is True and "why" says so."""
    if scene.root_collection() is None:
        return {"unsaved": False}
    try:
        return {"unsaved": _unsaved(_vehicle())}
    except model.WerkstattError as e:
        return {"unsaved": True, "why": str(e)}


@_api
def changed_on_disk():
    """Whether the open vehicle's placements.json changed since the scene read or wrote it (True too when the
    scene has no record of reading it): what makes save refuse without force."""
    try:
        return {"changed": not _known_file(_vehicle())}
    except model.WerkstattError as e:
        return {"changed": True, "why": str(e)}


@_api(undo="open vehicle")
def open_vehicle(name, show=(), force=False):
    """Builds the vehicle's scene (parts, attach points, references, upgrades, ghost) from its files. Refuses to
    replace an open vehicle with unsaved changes unless force=True."""
    _text(name, "name")
    if isinstance(show, str) or not all(isinstance(s, str) for s in show):
        raise model.WerkstattError(f"show must be a list of option names, got {show!r}")
    root = werkstatt_root()
    if not force:
        state = unsaved()
        if state.get("unsaved"):
            raise model.WerkstattError(f"{_vehicle().name} has unsaved changes" + (f" (can't tell: {state['why']})" if state.get("why") else "")
                                       + ": save them, or open with force=True to drop them")
    v = model.Vehicle(root, name)
    if not v.manifest.get("patch") and not os.path.isfile(os.path.join(v.folder, "build", "body_LOD0.obj")):
        raise model.WerkstattError(f"{name} isn't built yet: run `make build` (or `make loop V={name}`) in {root}")
    show = [_resolve_option(v, s) for s in show]
    sha = model.file_hash(_placements_file(v))
    scene.build(v, show)
    _state["vehicle"] = v
    _read(v, sha)
    uncommitted(root, refresh=True)
    # Entries on nodes the scene doesn't build (outside the upgrade tree, or a copy of one): save keeps them.
    return {"vehicle": name, "codename": v.codename, "donor": v.donor, "options": len(v.options()),
            "placements": len(v.placements), "copies": len(v.copies),
            "not_shown": sorted([p for p in v.placements if not v.is_built(p)]
                                + [p for p, pl in v.copies.items() if not v.is_built(p, pl.source)])}


def _resolve_option(v, name):
    matches = [p for p, n in v.nodes.items() if n.kind == "option" and (p == name or p.endswith("/" + name))]
    if len(matches) != 1:
        raise model.WerkstattError(f"{name!r} matches {len(matches)} upgrade options")
    return matches[0]


@_api
def items(slot=None, kind=None):
    """Placeable nodes with their slot, part, visibility and placement; filter by slot or kind."""
    _text(slot, "slot", optional=True)
    _text(kind, "kind", optional=True)
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


def _place(e, pl):
    """Puts a placement on an empty after the file format's checks, and the scale check below."""
    model.vector3(pl.offset, "offset", -model.MAX_OFFSET, model.MAX_OFFSET)
    model.vector3(pl.rotation, "rotation", -model.MAX_ROTATION, model.MAX_ROTATION)
    model.vector3(pl.scale, "scale", model.MIN_SCALE, model.MAX_SCALE)
    v = _vehicle()
    turned = e.get("werkstatt_source") or e["werkstatt_node"]
    if max(pl.scale) - min(pl.scale) > 1e-6 and v.is_turned(turned):
        raise model.WerkstattError(f"{turned.rsplit('/', 1)[-1]} is turned on the car, and the game scales it along "
                                   "its own axes, which the add-on can't show yet: scale it the same on x, y and z")
    scene.apply_placement(e, pl)
    return _describe(e, v)


@_api(undo="set placement")
def set_placement(node=None, offset=None, rotation=None, scale=None):
    """Sets a node's placement outright; any value left out keeps its current value."""
    e = _empty(node)
    pl = scene.read_placement(e)
    return _place(e, model.Placement(
        model.vector3(offset, "offset") if offset is not None else pl.offset,
        model.vector3(rotation, "rotation") if rotation is not None else pl.rotation,
        model.vector3(scale, "scale") if scale is not None else pl.scale, pl.source))


def _axis(axis):
    if axis not in AXES:
        raise model.WerkstattError(f"axis is one of x, y, z, got {axis!r}")
    return AXES[axis]


@_api(undo="nudge")
def nudge(node=None, axis="y", steps=1, unit="cm"):
    """Moves a node by steps x unit along a game axis (x right, y up, z forward) of its parent's frame."""
    direction = _axis(axis)
    if unit not in UNITS:
        raise model.WerkstattError(f"unit is one of {', '.join(UNITS)}, got {unit!r}")
    model.number(steps, "steps", -MAX_STEPS, MAX_STEPS)
    e = _empty(node)
    pl = scene.read_placement(e)
    delta = [a * steps * UNITS[unit] for a in direction]
    return _place(e, model.Placement(tuple(o + d for o, d in zip(pl.offset, delta)), pl.rotation, pl.scale, pl.source))


@_api(undo="rotate")
def rotate(node=None, axis="y", steps=1, degrees=1.0):
    """Turns a node by steps x degrees about a game axis of its parent's frame (x pitch, y yaw, z roll), about its pivot."""
    direction = _axis(axis)
    model.number(steps, "steps", -MAX_STEPS, MAX_STEPS)
    model.number(degrees, "degrees", -model.MAX_ROTATION, model.MAX_ROTATION)
    e = _empty(node)
    pl = scene.read_placement(e)
    q = model.quat_mul(model.quat_axis(direction, steps * degrees), model.euler_to_quat(pl.rotation))
    return _place(e, model.Placement(pl.offset, model.quat_to_euler(q), pl.scale, pl.source))


@_api(undo="scale")
def scale_by(node=None, factor=1.0, axis=None):
    """Multiplies a node's scale, on one game axis or all three. A node the game turns on the car takes the same
    factor on all three only (the game scales along the node's own axes)."""
    model.number(factor, "factor", 0.0, model.MAX_SCALE)
    if factor <= 0:
        raise model.WerkstattError("factor must be above 0")
    if axis is not None:
        _axis(axis)
    e = _empty(node)
    pl = scene.read_placement(e)
    s = [v * (factor if axis in (None, a) else 1.0) for v, a in zip(pl.scale, "xyz")]
    return _place(e, model.Placement(pl.offset, pl.rotation, s, pl.source))


@_api(undo="reset")
def reset(node=None):
    """Puts a node back at its base pose (the donor's, after the reshape); a copy goes back onto its source."""
    e = _empty(node)
    scene.apply_placement(e, model.Placement(source=e.get("werkstatt_source")))
    return _describe(e, _vehicle())


@_api(undo="show")
def show(node, shown=True):
    """Shows or hides an upgrade option (and its pieces and copies) in the viewport and renders."""
    e = _option_of(_empty(node))
    if e is None:
        raise model.WerkstattError(f"{node} isn't inside an upgrade option")
    scene.set_shown(e, shown)
    return {"node": e["werkstatt_node"], "shown": bool(shown)}


@_api(undo="show slot")
def show_slot(slot, shown=True):
    """Shows or hides every option of a slot (e.g. Roof, FrontBumper, Winch)."""
    _text(slot, "slot")
    v = _vehicle()
    count = 0
    for path, e in scene.editable_empties().items():
        if e.get("werkstatt_kind") == "option" and (v.slot_of(path) or "").lower() == slot.lower():
            scene.set_shown(e, shown)
            count += 1
    if not count:
        raise model.WerkstattError(f"no options in a slot called {slot}")
    return {"slot": slot, "options": count, "shown": bool(shown)}


@_api(undo="duplicate")
def duplicate(node=None):
    """Adds a copy of an option or of a piece inside one, beside its source, shown with it; returns the copy."""
    v = _vehicle()
    e = _empty(node)
    source = e.get("werkstatt_source") or e["werkstatt_node"]
    if e.get("werkstatt_kind") == "copy":
        raise model.WerkstattError("copy the original, not a copy")
    if e.get("werkstatt_kind") == "group" or (e.get("werkstatt_kind") == "piece" and _option_of(e) is None):
        raise model.WerkstattError(f"{source} is a slot group; copy an option or a piece inside one")
    path = v.next_copy_path(source, taken=set(scene.editable_empties()))
    copy = scene.add_copy(v, path, source)
    option = _option_of(copy)
    scene.set_shown(option, scene.is_shown(option) if option else True)
    bpy.context.view_layer.objects.active = copy
    return _describe(copy, v)


@_api(undo="delete copy")
def delete_copy(node=None):
    """Removes a copy (never an original)."""
    e = _empty(node)
    if e.get("werkstatt_kind") != "copy":
        raise model.WerkstattError("only copies can be deleted; reset an original instead")
    path = e["werkstatt_node"]
    for obj in [e] + list(e.children_recursive):
        bpy.data.objects.remove(obj, do_unlink=True)
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
def clearance(node=None, reach=0.5, move=None):
    """How the item sits against the vehicle (body, axles, wheels, other shown options), in game metres:
    {"intersecting", "inside", "gap" (when clear), "penetration" (the move that clears it, when it crosses or sits
    inside something), "clear_by" ([axis, sign] for nudge) with "nudge_by" (metres), "offset_delta", "touches",
    "at"}. clear_by, nudge_by and offset_delta are for nudging `move` (default: the item; else one of its parents,
    e.g. its slot group). Drive a penetration to a small
    positive gap: nudge until intersecting and inside are False and the gap is a few millimetres."""
    model.number(reach, "reach", 0.01, 5.0)
    return review.clearance(_empty(node), reach, _empty(move) if move else None)


@_api
def review_views(node=None, out_dir=None):
    """Renders front, side, top and three-quarter views framed on the item, at a fixed resolution and with the
    same lighting every time, into out_dir (default: a folder named after the item in the system's temp
    folder); returns {"views": {name: path}}."""
    e = _empty(node)
    if out_dir is None:
        import tempfile
        out_dir = os.path.join(tempfile.gettempdir(), "werkstatt-review", e["werkstatt_node"].rsplit("/", 1)[-1])
    return {"node": e["werkstatt_node"], "views": review.review_views(e, out_dir)}


@_api(undo="ghost")
def ghost(shown=True, offset=3.0):
    """Shows the donor's stock body as a wireframe, `offset` metres to the side (0 overlays it)."""
    model.number(offset, "offset", -100.0, 100.0)
    scene.set_ghost(shown, offset)
    return {"ghost": bool(shown), "offset": offset}


@_api
def save(force=False):
    """Writes the open vehicle's placements.json from the scene (only offsets that differ from the base pose),
    keeping the file's entries for nodes the scene doesn't show ("kept"). Refuses when the file changed on disk
    since the vehicle was opened or last saved (force=True writes anyway), when the vehicle came from another
    checkout than the add-on's, when two empties claim one node, and when an item's values are ones the plugin
    would refuse. Only writes the file: committing it is yours."""
    v = _vehicle()
    root = werkstatt_root()
    if v.root != root:
        raise model.WerkstattError(f"the open vehicle came from {v.root}, but the add-on works on {root}: open it again")
    shared = scene.shared_nodes()
    if shared:
        path, names = next(iter(sorted(shared.items())))
        raise model.WerkstattError(f"{len(names)} empties claim {path} ({', '.join(names)}), as Blender's Shift+D makes "
                                   "them: delete the extra ones (Werkstatt's Duplicate makes copies the game knows)")
    problems = _invalid(v)
    if problems:
        raise model.WerkstattError(f"not saved, {len(problems)} item(s) the game would refuse: " + "; ".join(problems[:5])
                                   + ("; ..." if len(problems) > 5 else "") + " (Reset them, or move them back)")
    path = _placements_file(v)
    if not force and not _known_file(v):
        raise model.WerkstattError(f"{os.path.relpath(path, v.root)} changed on disk since it was read: open the vehicle "
                                   "again to see the change, or overwrite it (Overwrite in the panel, save(force=True) in a script)")
    nodes, copies, kept = _pending(v, force)
    v.placements, v.copies = nodes, copies
    result = v.save()
    _read(v, model.file_hash(path))
    uncommitted(root, refresh=True)
    return {"file": os.path.relpath(path, v.root), "result": result, "placements": len(nodes), "copies": len(copies),
            "kept": kept}


@_api
def run_loop():
    """Runs `make loop V=<vehicle>` in the checkout (build, gates, contact sheet); returns its exit code and last lines."""
    v = _vehicle()
    r = subprocess.run(["make", "loop", f"V={v.name}"], cwd=v.root, capture_output=True, text=True)
    text = (r.stdout + r.stderr).strip()
    block = bpy.data.texts.get("werkstatt-loop.log") or bpy.data.texts.new("werkstatt-loop.log")
    block.from_string(text)
    return {"code": r.returncode, "tail": text.splitlines()[-15:], "log": "werkstatt-loop.log (Blender text)"}
