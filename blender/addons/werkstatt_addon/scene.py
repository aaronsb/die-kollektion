"""The scene layer: a model.Vehicle built into Blender, and the placements read back out of it.

Structure (docs/vehicle_factory.md's vehicle as parts, attach points and references), under one collection named
"Werkstatt: <Codename>":
  Part: <name>            one collection per part (body, colliders, axles), its LOD0 mesh inside; custom
                          properties werkstatt_part, werkstatt_node (the prefab node path) and werkstatt_source
  Attach points           empties at the vehicle's attach points (winch points, lights, wheel hubs, CoM),
                          parented to the body part
  References              the donor's live parts (wheels and tyres) the game keeps: shown, not selectable
  Upgrades/<slot>         an empty per upgrade node (slot groups, options, pieces, copies) mirroring the prefab
                          tree, each option's meshes parented to its pieces; the empties carry the placements
  Ghost                   the donor's stock body, for comparison

An editable empty carries werkstatt_node (its node path), werkstatt_kind (group, option, piece, copy),
werkstatt_rest (its location at the base pose, relative to its parent empty, in Blender axes) and, for a copy,
werkstatt_source. Its location minus rest, rotation and scale are the node's placement in Blender axes. Meshes
under the empties, and the pieces inside a copy, have their transforms locked: the empty is what moves.

The scene owns, by rule (model.Vehicle.is_built), every slot group, option and piece and every copy of one, in it
now or not (a copy deleted or undone); a save keeps the file's entries for anything else as they are. The root
collection carries werkstatt_file_sha, the placements file's hash when it was last read or written, so a save
can tell a file changed on disk even after an undo, a reload of the add-on or a restart.
"""
import os

import bpy
import mathutils

from . import model

ROOT_PREFIX = "Werkstatt: "
# The donor's wheel and tyre meshes are in the asset's units; their node in the prefab scales them by 100.
WHEEL_MESH_SCALE = 100.0
KIND_COLOURS = {"body": (0.62, 0.62, 0.58, 1.0), "collider": (0.2, 0.6, 0.9, 1.0), "axle": (0.25, 0.25, 0.25, 1.0),
                "reference": (0.05, 0.05, 0.05, 1.0), "ghost": (0.9, 0.5, 0.1, 1.0)}
SLOT_COLOURS = [(0.85, 0.25, 0.2, 1.0), (0.2, 0.7, 0.3, 1.0), (0.25, 0.45, 0.9, 1.0), (0.9, 0.75, 0.15, 1.0),
                (0.7, 0.3, 0.8, 1.0), (0.15, 0.75, 0.75, 1.0), (0.9, 0.5, 0.15, 1.0)]


# ---- OBJ reading (positions and faces only; our OBJs carry extension lines Blender's importer warns about)

def read_obj(path):
    """{object name: (vertices, faces)} with vertices in Blender axes; one entry per 'o' block, '' for none."""
    out, verts, faces, name, base = {}, [], [], "", 0
    all_verts = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.startswith("v "):
                x, y, z = (float(v) for v in line.split()[1:4])
                all_verts.append((x, -z, y))           # OBJ (x, y up, z forward) -> Blender
            elif line.startswith("f "):
                faces.append([int(p.split("/")[0]) - 1 for p in line.split()[1:]])
            elif line.startswith("o "):
                if faces:
                    out[name] = _gather(all_verts, faces)
                name, faces = line[2:].strip(), []
    if faces:
        out[name] = _gather(all_verts, faces)
    return out


def _gather(all_verts, faces):
    used = sorted({i for face in faces for i in face})
    index = {old: new for new, old in enumerate(used)}
    return [all_verts[i] for i in used], [[index[i] for i in face] for face in faces]


def material(name, rgba):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.diffuse_color = rgba
    return m


def mesh_object(name, verts, faces, collection, colour_name, rgba, offset=(0.0, 0.0, 0.0)):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([(v[0] - offset[0], v[1] - offset[1], v[2] - offset[2]) for v in verts], [], faces)
    mesh.update()
    mesh.materials.append(material(colour_name, rgba))
    mesh["werkstatt"] = True
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    return obj


def pose_matrix(pose):
    """A reshape pose (q, t) in game space as a Blender matrix."""
    (x, y, z, w), t = pose
    qx, qy, qz, qw = model.quat_game_to_blender((x, y, z, w))
    return (mathutils.Matrix.Translation(model.game_to_blender(t))
            @ mathutils.Quaternion((qw, qx, qy, qz)).to_matrix().to_4x4())


def posed(vehicle, path, verts):
    """Blender-space vertices of a mesh at the node path, where the reshape puts them."""
    q, t = vehicle.pose(path)
    if q == model.IDENTITY_POSE[0]:
        dx, dy, dz = model.game_to_blender(t)
        return [(v[0] + dx, v[1] + dy, v[2] + dz) for v in verts]
    return [model.game_to_blender(vehicle.place(path, model.blender_to_game(v))) for v in verts]


def lock(obj):
    """Blender's G, R and S do nothing on obj; its empty carries the placement."""
    obj.lock_location = obj.lock_rotation = obj.lock_scale = (True, True, True)
    obj.lock_rotation_w = True
    obj.lock_rotations_4d = True


def child_collection(parent, name):
    c = bpy.data.collections.new(name)
    parent.children.link(c)
    return c


# ---- building the scene ----------------------------------------------------------------------------------

def clear():
    """Removes any Werkstatt vehicle from the scene (only what this add-on built)."""
    scene = bpy.context.scene
    for c in list(scene.collection.children):
        if c.name.startswith(ROOT_PREFIX):
            _remove_collection(c)
    for mesh in list(bpy.data.meshes):
        if mesh.users == 0 and mesh.get("werkstatt"):
            bpy.data.meshes.remove(mesh)
    for mat in list(bpy.data.materials):
        if mat.users == 0 and mat.name.startswith("werkstatt."):
            bpy.data.materials.remove(mat)


def _remove_collection(c):
    for child in list(c.children):
        _remove_collection(child)
    for obj in list(c.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    bpy.data.collections.remove(c)


def build(vehicle, show=()):
    """Builds the vehicle's scene; returns the root collection. Options in `show` start visible."""
    clear()
    scene = bpy.context.scene
    root = bpy.data.collections.new(ROOT_PREFIX + vehicle.codename)
    scene.collection.children.link(root)
    root["werkstatt_vehicle"] = vehicle.name
    root["werkstatt_root"] = vehicle.root

    body_obj = None
    for name, path, file, kind in vehicle.part_files():
        part = child_collection(root, f"Part: {name}")
        part["werkstatt_part"] = kind
        part["werkstatt_node"] = path
        part["werkstatt_source"] = os.path.relpath(file, vehicle.root)
        for obj_name, (verts, faces) in read_obj(file).items():
            obj = mesh_object(name, verts, faces, part, f"werkstatt.{kind}", KIND_COLOURS[kind])
            # Built meshes are in the donor's root space, and the plugin maps them through the donor's layout
            # before the reshape moves their node (the rear axle and its springs go back with the sweep).
            obj.matrix_world = pose_matrix(vehicle.pose(path))
            obj["werkstatt_part"] = kind
            obj["werkstatt_node"] = path
            if kind == "collider":
                obj.display_type = "WIRE"
                obj.hide_set(True)
                obj.hide_render = True
            elif kind == "body" and body_obj is None:
                body_obj = obj

    points = child_collection(root, "Attach points")
    for path, position in sorted(vehicle.attach_points.items()):
        empty = bpy.data.objects.new(path.replace("/", " / "), None)
        empty.empty_display_type = "SPHERE"
        empty.empty_display_size = 0.04
        empty.location = model.game_to_blender(position)
        empty["werkstatt_attach"] = path
        points.objects.link(empty)
        if body_obj is not None:
            empty.parent = body_obj

    refs = child_collection(root, "References (donor, read-only)")
    refs["werkstatt_reference"] = True
    wheel_file = os.path.join(vehicle.extracted, f"{vehicle.donor}_wheel_LOD0.obj")
    tyre_file = os.path.join(vehicle.extracted, f"{vehicle.donor}_tyre_LOD0.obj")
    donor_radius, donor_width = vehicle.donor_wheel()
    for corner, position, radius, width in vehicle.wheels():
        for file in (wheel_file, tyre_file):
            if not os.path.isfile(file):
                continue
            for _, (verts, faces) in read_obj(file).items():
                at = model.game_to_blender(position)
                mirror = -1.0 if corner[1] == "L" else 1.0        # the left wheels face out the other way
                # As the plugin's ScaleTyres: the fitted tyre over the donor's, radius on y and z, width on x.
                k = WHEEL_MESH_SCALE * radius / donor_radius
                kx = WHEEL_MESH_SCALE * width / donor_width * mirror
                verts = [(v[0] * kx + at[0], v[1] * k + at[1], v[2] * k + at[2]) for v in verts]
                if mirror < 0:
                    faces = [list(reversed(face)) for face in faces]
                obj = mesh_object(f"{corner} {os.path.basename(file)[:-4]}", verts, faces, refs, "werkstatt.reference", KIND_COLOURS["reference"])
                obj.hide_select = True
                obj["werkstatt_reference"] = os.path.relpath(file, vehicle.root)

    _build_upgrades(vehicle, child_collection(root, "Upgrades"), set(show))

    ghost = child_collection(root, "Ghost")
    ghost["werkstatt_ghost"] = True
    donor = vehicle.donor_body()
    if donor:
        for _, (verts, faces) in read_obj(donor).items():
            obj = mesh_object(f"Ghost {vehicle.donor}", verts, faces, ghost, "werkstatt.ghost", KIND_COLOURS["ghost"])
            obj.display_type = "WIRE"
            obj.hide_select = True
            obj["werkstatt_ghost"] = True
    set_ghost(False, 3.0)
    return root


def _build_upgrades(vehicle, upgrades, show):
    nodes = vehicle.nodes
    wanted = {p for p in nodes if vehicle.is_built(p)}
    slots, empties = {}, {}

    def empty_parent(path):
        p = model.parent_path(path)
        while p and p not in empties:
            p = model.parent_path(p)
        return empties.get(p)

    def base(path):
        return model.game_to_blender(nodes[path].position)

    def make_empty(path, kind, collection, parent, rest, source=None):
        e = bpy.data.objects.new(path.rsplit("/", 1)[-1], None)
        e.empty_display_type = {"group": "PLAIN_AXES", "option": "ARROWS", "piece": "CUBE", "copy": "CUBE"}[kind]
        e.empty_display_size = {"group": 0.15, "option": 0.12, "piece": 0.05, "copy": 0.05}[kind]
        e.rotation_mode = "QUATERNION"
        collection.objects.link(e)
        e.parent = parent
        e.matrix_parent_inverse = mathutils.Matrix.Identity(4)
        e.location = rest
        e["werkstatt_node"] = path
        e["werkstatt_kind"] = kind
        e["werkstatt_rest"] = list(rest)
        if source:
            e["werkstatt_source"] = source
        return e

    for path in sorted(wanted, key=lambda p: (p.count("/"), p)):
        node = nodes[path]
        slot = vehicle.slot_of(path) if node.kind != "group" or path.count("/") > vehicle.cosmetic_root.count("/") + 1 else None
        collection = upgrades
        if slot:
            if slot not in slots:
                slots[slot] = child_collection(upgrades, slot)
            collection = slots[slot]
        parent = empty_parent(path)
        here = base(path)
        rest = here if parent is None else tuple(a - b for a, b in zip(here, base(parent["werkstatt_node"])))
        empties[path] = make_empty(path, node.kind, collection, parent, rest)

    colour_of = {}
    for option in vehicle.options():
        if not option.file:
            continue
        slot = vehicle.slot_of(option.path)
        colour_of.setdefault(slot, SLOT_COLOURS[len(colour_of) % len(SLOT_COLOURS)])
        file = vehicle.option_file(option)
        if not os.path.isfile(file):
            continue
        for mesh_path, (verts, faces) in read_obj(file).items():
            owner = empties.get(mesh_path) or empty_parent(mesh_path)
            if owner is None:
                continue
            verts = posed(vehicle, mesh_path, verts)
            owner_base = base(owner["werkstatt_node"])
            obj = mesh_object(mesh_path.rsplit("/", 1)[-1], verts, faces, owner.users_collection[0],
                              f"werkstatt.slot.{slot}", colour_of[slot], owner_base)
            obj.parent = owner
            obj.matrix_parent_inverse = mathutils.Matrix.Identity(4)
            obj["werkstatt_mesh_of"] = mesh_path
            lock(obj)

    # A copy of a node the scene doesn't show stays out of it; save keeps its entry as the file has it.
    for path, pl in sorted(vehicle.copies.items(), key=lambda kv: (kv[0].count("/"), kv[0])):
        if pl.source in empties:
            add_copy(vehicle, path, pl.source, empties)

    for path, pl in vehicle.placements.items():
        if path in empties:
            apply_placement(empties[path], pl)
    for path, pl in vehicle.copies.items():
        if path in empties:
            apply_placement(empties[path], pl)

    for option in vehicle.options():
        set_shown(empties.get(option.path), option.path in show)


def add_copy(vehicle, path, source, empties=None):
    """Builds a copy of an option or piece at its source's base pose; returns its empty. As in the plugin, a path
    inside its source makes the copy the source's child, any other path its sibling."""
    empties = empties if empties is not None else editable_empties()
    src = empties.get(source)
    if src is None:
        raise model.WerkstattError(f"{source} isn't in the scene, so it can't be copied")
    inside = model.parent_path(path) == source
    parent = src if inside else src.parent
    rest = (0.0, 0.0, 0.0) if inside else tuple(src["werkstatt_rest"])
    e = bpy.data.objects.new(path.rsplit("/", 1)[-1], None)
    e.empty_display_type = "CUBE"
    e.empty_display_size = 0.06
    e.rotation_mode = "QUATERNION"
    src.users_collection[0].objects.link(e)
    e.parent = parent
    e.matrix_parent_inverse = mathutils.Matrix.Identity(4)
    e.location = rest
    e["werkstatt_node"] = path
    e["werkstatt_kind"] = "copy"
    e["werkstatt_rest"] = list(rest)
    e["werkstatt_source"] = source
    _copy_subtree(vehicle, src, e, source)
    empties[path] = e
    return e


def _copy_subtree(vehicle, src, dst, source_path):
    """Gives a copy the source's meshes and pieces at their base pose (a source's own placements don't apply)."""
    for child in src.children:
        if child.get("werkstatt_kind") == "copy":
            continue
        if child.type == "MESH":
            obj = bpy.data.objects.new(child.name, child.data)
            dst.users_collection[0].objects.link(obj)
            obj.parent = dst
            obj.matrix_parent_inverse = mathutils.Matrix.Identity(4)
            lock(obj)
        elif child.type == "EMPTY" and child.get("werkstatt_node"):
            e = bpy.data.objects.new(child.name, None)
            e.empty_display_type = child.empty_display_type
            e.empty_display_size = child.empty_display_size
            dst.users_collection[0].objects.link(e)
            e.parent = dst
            e.matrix_parent_inverse = mathutils.Matrix.Identity(4)
            e.location = tuple(child["werkstatt_rest"])
            e["werkstatt_copy_part"] = True
            lock(e)
            _copy_subtree(vehicle, child, e, child["werkstatt_node"])


# ---- placements <-> transforms -----------------------------------------------------------------------------

def apply_placement(empty, pl):
    rest = mathutils.Vector(empty["werkstatt_rest"])
    empty.location = rest + mathutils.Vector(model.game_to_blender(pl.offset))
    x, y, z, w = model.quat_game_to_blender(model.euler_to_quat(pl.rotation))
    empty.rotation_mode = "QUATERNION"
    empty.rotation_quaternion = mathutils.Quaternion((w, x, y, z))
    empty.scale = model.scale_game_to_blender(pl.scale)


def read_placement(empty):
    """The empty's placement, read without writing to it (the panel calls this while Blender draws, where writing
    to an object is refused), whatever rotation mode Blender's R key or a script left it in."""
    rest = mathutils.Vector(empty["werkstatt_rest"])
    offset = model.blender_to_game(tuple(empty.location - rest))
    _, q, scale = empty.matrix_basis.decompose()
    rotation = model.quat_to_euler(model.quat_blender_to_game((q.x, q.y, q.z, q.w)))
    return model.Placement(offset, rotation, model.scale_blender_to_game(tuple(scale)), empty.get("werkstatt_source"))


def _placeable(obj):
    return obj.type == "EMPTY" and obj.get("werkstatt_node") and not obj.get("werkstatt_copy_part")


def editable_empties():
    """{node path: empty} for every placeable node in the scene."""
    return {obj["werkstatt_node"]: obj for obj in bpy.context.scene.objects if _placeable(obj)}


def shared_nodes():
    """{node path: [object names]} for node paths more than one empty claims (Blender's Shift+D copies one)."""
    seen = {}
    for obj in bpy.context.scene.objects:
        if _placeable(obj):
            seen.setdefault(obj["werkstatt_node"], []).append(obj.name)
    return {path: sorted(names) for path, names in seen.items() if len(names) > 1}


def collect(vehicle, base_nodes, base_copies):
    """What save writes: (nodes, copies, kept). The scene's own placements, plus the file's entries (base_*) for
    nodes the scene doesn't build (kept, as the file has them). An entry the scene owns but no longer shows, such
    as a deleted copy, is dropped."""
    empties = editable_empties()
    nodes = {p: pl for p, pl in base_nodes.items() if p not in empties and not vehicle.is_built(p)}
    copies = {p: pl for p, pl in base_copies.items() if p not in empties and not vehicle.is_built(p, pl.source)}
    kept = len(nodes) + len(copies)
    for path, empty in empties.items():
        pl = read_placement(empty)
        if empty.get("werkstatt_kind") == "copy":
            copies[path] = pl
        elif not pl.is_identity():
            nodes[path] = pl
    return nodes, copies, kept


# ---- visibility ----------------------------------------------------------------------------------------

def set_shown(empty, shown):
    if empty is None:
        return
    empty["werkstatt_shown"] = bool(shown)
    for obj in [empty] + list(empty.children_recursive):
        obj.hide_set(not shown)
        obj.hide_render = not shown


def is_shown(empty):
    return bool(empty.get("werkstatt_shown"))


def set_ghost(shown, offset):
    for obj in bpy.context.scene.objects:
        if obj.get("werkstatt_ghost"):
            obj.hide_set(not shown)
            obj.hide_render = not shown
            obj.location = (offset, 0.0, 0.0)


def root_collection():
    for c in bpy.context.scene.collection.children:
        if c.name.startswith(ROOT_PREFIX):
            return c
    return None
