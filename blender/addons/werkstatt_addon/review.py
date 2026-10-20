"""What an agent (or a careful human) checks between nudges: how far an item is from the vehicle, and the same four
renders of it every time.

clearance() measures in game metres with BVH trees against the obstacles: the body and axle parts, the wheels and
tyres, and every other option that is shown. It reports the gap between the item and the nearest of them, or,
when the item crosses one or sits inside one, the smallest move along one truck axis that clears it.
review_views() renders front, side, top and three-quarter views framed on the item at a fixed resolution and
with fixed lighting and output settings, so successive nudges compare like with like.
"""
import os

import bpy
import mathutils
from mathutils.bvhtree import BVHTree

from . import model, scene

PART_KINDS = ("body", "axle")
VIEW_RESOLUTION = (1200, 900)


def _world_mesh(objects):
    """(vertices, faces, owner per face) of the objects' meshes in world space."""
    verts, faces, owners = [], [], []
    deps = bpy.context.evaluated_depsgraph_get()
    for obj in objects:
        ev = obj.evaluated_get(deps)
        mesh = ev.to_mesh()
        base = len(verts)
        m = obj.matrix_world
        verts.extend(m @ v.co for v in mesh.vertices)
        for poly in mesh.polygons:
            faces.append([base + i for i in poly.vertices])
            owners.append(obj)
        ev.to_mesh_clear()
    return verts, faces, owners


def item_meshes(empty):
    """The meshes an item shows: its own, and those of the options under it that are shown (a slot group's
    hidden options don't count). The item itself counts even when it is hidden."""
    out = []

    def walk(obj):
        for child in obj.children:
            if child.type == "MESH":
                out.append(child)
            elif child.get("werkstatt_kind") == "option" and not scene.is_shown(child):
                continue
            else:
                walk(child)
    walk(empty)
    return out


def _option_root(empty):
    """The option an item belongs to (itself when it is one), or the item for a slot group."""
    e = empty
    while e is not None:
        if e.get("werkstatt_kind") == "option":
            return e
        e = e.parent
    return empty


def obstacles(empty):
    """What an item can hit: the body and axle parts, the wheels and tyres, and the meshes of every shown option
    other than the item's own."""
    own = _option_root(empty)
    mine = {o.name for o in [own] + list(own.children_recursive)}
    out = []
    for obj in bpy.context.scene.objects:
        if obj.type != "MESH" or obj.name in mine:
            continue
        if obj.get("werkstatt_part") in PART_KINDS or obj.get("werkstatt_reference"):
            out.append(obj)
        elif obj.get("werkstatt_mesh_of") or obj.parent is not None and obj.parent.get("werkstatt_node"):
            option = _option_root(obj.parent)
            if option.get("werkstatt_kind") == "option" and scene.is_shown(option):
                out.append(obj)
    return out


def _part_name(obj):
    if obj.get("werkstatt_reference"):
        return obj.name
    option = _option_root(obj.parent) if obj.parent is not None else None
    if option is not None and option.get("werkstatt_node"):
        return option["werkstatt_node"].rsplit("/", 1)[-1]
    return obj.users_collection[0].name.replace("Part: ", "") if obj.users_collection else obj.name


AXIS_DIRECTIONS = {     # truck direction -> Blender direction
    "up": (0.0, 0.0, 1.0), "down": (0.0, 0.0, -1.0), "forward": (0.0, -1.0, 0.0), "back": (0.0, 1.0, 0.0),
    "right": (-1.0, 0.0, 0.0), "left": (1.0, 0.0, 0.0)}


def _exit_depth(points, tree, direction, reach):
    """The furthest any point must travel along direction to leave the mesh: a point is inside when a ray along
    direction first meets a face it is leaving (the face's normal points along the ray)."""
    deepest = 0.0
    for p in points:
        loc, normal, index, dist = tree.ray_cast(p, direction, reach)
        if loc is not None and normal.dot(direction) > 0 and dist > deepest:
            deepest = dist
    return deepest


def _clearing_move(verts, faces, tree, direction, start, reach, inside_ray, step=0.002):
    """The smallest move along direction, from start, after which the item no longer overlaps the obstacles and
    its points are outside them (not inside a hollow body's shell), or None within reach."""
    t = start + 0.001
    while t <= reach:
        moved = [v + direction * t for v in verts]
        moved_tree = BVHTree.FromPolygons(moved, faces, all_triangles=False)
        if not moved_tree.overlap(tree) and not _any_inside(moved, tree, inside_ray):
            return round(t, 4)
        t += step
    return None


def _any_inside(points, tree, ray):
    """Whether any of the points (a sample of up to 200) sits inside an obstacle: straight up, it first meets a
    face it is leaving. The ray runs the obstacles' whole height, so an item buried deep still counts."""
    up = mathutils.Vector((0.0, 0.0, 1.0))
    for p in points[::max(1, len(points) // 200)]:
        hit = tree.ray_cast(p, up, ray)
        if hit[0] is not None and hit[1].dot(up) > 0:
            return True
    return False


def _ancestors(obj):
    out, e = [], obj.parent
    while e is not None:
        out.append(e)
        e = e.parent
    return out


def _nudge_frame(mover):
    """Blender's map from a nudge of `mover` (an offset in its parent's frame, as api.nudge applies it) to the
    world: the parent's turns and scales."""
    return mover.parent.matrix_world.to_3x3() if mover.parent is not None else mathutils.Matrix.Identity(3)


def _move_for(mover, world_move):
    """(offset delta in game axes of mover's nudge frame, [axis, sign] when that is along one axis, else None, and
    the nudge's length along that axis in metres, which a scaled frame makes differ from the move)."""
    local = model.blender_to_game(tuple(_nudge_frame(mover).inverted_safe() @ world_move))
    size = max(abs(v) for v in local)
    if size == 0:
        return [0.0, 0.0, 0.0], None, None
    axes = [i for i, v in enumerate(local) if abs(v) > 1e-6 * max(1.0, size)]
    if len(axes) != 1:
        return model.clean(local, model.OFFSET_DIGITS), None, None
    return (model.clean(local, model.OFFSET_DIGITS), ["xyz"[axes[0]], 1 if local[axes[0]] > 0 else -1],
            round(abs(local[axes[0]]), model.OFFSET_DIGITS))


def clearance(empty, reach=0.5, mover=None):
    """How an item sits against the obstacles (see obstacles()), in game metres.

    Clear: {"intersecting": False, "inside": False, "gap", "touches": the nearest obstacle, "at": the point}. The
    gap is measured from vertices to surfaces both ways, so where an edge passes an edge it can be a little more
    than the true gap.
    Crossing an obstacle ("intersecting") or sitting inside one ("inside", e.g. a rack buried in a roof):
    {"penetration": the smallest move along one truck axis that clears it, "direction": "up", "forward", ...,
    "offset_delta": that move as an offset change of `mover` (default: the item, or one of its parents) in its
    nudge frame, "clear_by": [axis, sign] and "nudge_by": metres for api.nudge on `mover` when the move is along
    one of its axes (a scaled frame makes nudge_by differ from penetration), "depths": every direction's move,
    "touches", "at"}. Inside is told by ray casts, so it needs the obstacles' faces to point outward."""
    bpy.context.view_layer.update()
    mover = mover or empty
    if mover is not empty and mover not in _ancestors(empty):
        raise model.WerkstattError(f"{mover['werkstatt_node'].rsplit('/', 1)[-1]} isn't "
                                   f"{empty['werkstatt_node'].rsplit('/', 1)[-1]} or one of its parents, so moving it "
                                   "doesn't move the item")
    items = item_meshes(empty)
    if not items:
        raise model.WerkstattError(f"{empty['werkstatt_node']} shows no meshes to measure (show one of its options)")
    blockers = obstacles(empty)
    if not blockers:
        raise model.WerkstattError("the vehicle has no body part to measure against")
    iv, ifaces, _ = _world_mesh(items)
    bv, bfaces, bowners = _world_mesh(blockers)
    item_tree = BVHTree.FromPolygons(iv, ifaces, all_triangles=False)
    body_tree = BVHTree.FromPolygons(bv, bfaces, all_triangles=False)
    ray = (mathutils.Vector([max(v[i] for v in bv) for i in range(3)]) - mathutils.Vector([min(v[i] for v in bv) for i in range(3)])).length + 1.0
    pairs = item_tree.overlap(body_tree)
    inside = not pairs and _any_inside(iv, body_tree, ray)
    lo = mathutils.Vector([min(p[i] for p in iv) - reach for i in range(3)])
    hi = mathutils.Vector([max(p[i] for p in iv) + reach for i in range(3)])
    near_body = [v for v in bv if all(lo[k] <= v[k] <= hi[k] for k in range(3))]

    nearest, nearest_at, nearest_index = None, None, None
    for v in iv:
        loc, normal, index, dist = body_tree.find_nearest(v, reach)
        if loc is not None and (nearest is None or dist < nearest):
            nearest, nearest_at, nearest_index = dist, loc, index
    for v in near_body:
        loc, normal, index, dist = item_tree.find_nearest(v, reach)
        if loc is not None and (nearest is None or dist < nearest):
            found = body_tree.find_nearest(v, 1e-6)
            nearest, nearest_at, nearest_index = dist, v, found[2] if found[0] is not None else nearest_index
    out = {"node": empty["werkstatt_node"], "intersecting": bool(pairs), "inside": inside}
    if inside and nearest_index is None:              # buried deeper than reach: name what the ray met
        nearest_index = body_tree.ray_cast(iv[0], mathutils.Vector((0.0, 0.0, 1.0)), ray)[2]
    part = bowners[pairs[0][1]] if pairs else (bowners[nearest_index] if nearest_index is not None else None)
    out["touches"] = _part_name(part) if part else None
    if pairs or inside:
        depths = {}
        for name, d in AXIS_DIRECTIONS.items():
            d = mathutils.Vector(d)
            # the item's points leaving the obstacles along d, and the obstacles' points leaving the item the other
            # way: a lower bound, checked by moving the item and testing again (a hollow body's shell can be
            # crossed into its inside, which is no fit, and an edge can cross a face with no point inside)
            start = max(_exit_depth(iv, body_tree, d, reach), _exit_depth(near_body, item_tree, -d, reach))
            depths[name] = _clearing_move(iv, ifaces, body_tree, d, start, reach, ray)
        clearing = {k: v for k, v in depths.items() if v is not None}
        direction = min(clearing, key=lambda k: (clearing[k], list(AXIS_DIRECTIONS).index(k))) if clearing else None
        delta, single, along = (_move_for(mover, mathutils.Vector(AXIS_DIRECTIONS[direction]) * clearing[direction])
                                if direction else (None, None, None))
        out.update({"penetration": clearing[direction] if direction else None, "direction": direction,
                    "offset_delta": delta, "clear_by": single, "nudge_by": along, "depths": depths, "gap": None,
                    "at": model.clean(model.blender_to_game(tuple(nearest_at or iv[0])), 4),
                    **({} if direction else {"note": f"no move along one axis up to {reach} m clears it"})})
        if direction and single is None:
            out["note"] = (f"{mover['werkstatt_node'].rsplit('/', 1)[-1]}'s frame is turned: set_placement its offset "
                           "plus offset_delta")
    elif nearest is None:
        out.update({"penetration": None, "gap": None, "at": None, "note": f"nothing within {reach} m"})
    else:
        out.update({"penetration": None, "gap": round(nearest, 4), "at": model.clean(model.blender_to_game(tuple(nearest_at)), 4)})
    return out


# ---- fixed review views ----------------------------------------------------------------------------------

VIEWS = {   # direction from the item's centre to the camera, in Blender axes (front = -Y, right = -X, up = +Z)
    "front": ((0.0, -1.0, 0.0), False),
    "side": ((-1.0, 0.0, 0.0), False),
    "top": ((0.0, 0.0, 1.0), False),
    "three_quarter": ((-0.8, -1.0, 0.65), True),
}


def _bounds(objects):
    pts = [o.matrix_world @ mathutils.Vector(c) for o in objects for c in o.bound_box]
    lo = mathutils.Vector([min(p[i] for p in pts) for i in range(3)])
    hi = mathutils.Vector([max(p[i] for p in pts) for i in range(3)])
    return lo, hi


# Everything about the output a scene can change: pinned for the views, put back afterwards. (owner, attribute,
# value) with the owner as a function of the scene.
PINNED = [
    (lambda sc: sc.render, "engine", "BLENDER_WORKBENCH"),
    (lambda sc: sc.render, "resolution_x", VIEW_RESOLUTION[0]),
    (lambda sc: sc.render, "resolution_y", VIEW_RESOLUTION[1]),
    (lambda sc: sc.render, "resolution_percentage", 100),
    (lambda sc: sc.render, "pixel_aspect_x", 1.0),
    (lambda sc: sc.render, "pixel_aspect_y", 1.0),
    (lambda sc: sc.render, "use_border", False),
    (lambda sc: sc.render, "film_transparent", False),
    (lambda sc: sc.render, "dither_intensity", 0.0),     # dither is random noise: two renders of one pose would differ
    (lambda sc: sc.render, "use_file_extension", True),
    (lambda sc: sc.render.image_settings, "file_format", "PNG"),
    (lambda sc: sc.render.image_settings, "color_mode", "RGB"),
    (lambda sc: sc.render.image_settings, "color_depth", "8"),
    (lambda sc: sc.render.image_settings, "compression", 15),
    (lambda sc: sc.render.image_settings, "color_management", "FOLLOW_SCENE"),
    (lambda sc: sc.render, "use_compositing", False),
    (lambda sc: sc.render, "use_sequencer", False),
    (lambda sc: sc.view_settings, "view_transform", "Standard"),
    (lambda sc: sc.view_settings, "look", "None"),
    (lambda sc: sc.view_settings, "exposure", 0.0),
    (lambda sc: sc.view_settings, "gamma", 1.0),
    (lambda sc: sc.view_settings, "use_curve_mapping", False),
    (lambda sc: sc.display_settings, "display_device", "sRGB"),
    (lambda sc: sc.sequencer_colorspace_settings, "name", "sRGB"),
    (lambda sc: sc.display.shading, "light", "STUDIO"),
    (lambda sc: sc.display.shading, "color_type", "MATERIAL"),
    (lambda sc: sc.display.shading, "show_cavity", True),
    (lambda sc: sc.display.shading, "show_xray", False),
    (lambda sc: sc.display.shading, "show_shadows", False),
    (lambda sc: sc.display.shading, "show_object_outline", False),
    (lambda sc: sc.display, "render_aa", "8"),
]


def _pin(sc):
    """Pins the output settings; returns what to put back."""
    # Every old value is read before any is set: setting the file format resets the colour mode and depth.
    saved = [(owner(sc), attr, getattr(owner(sc), attr)) for owner, attr, _ in PINNED if hasattr(owner(sc), attr)]
    for owner, attr, value in PINNED:
        try:
            setattr(owner(sc), attr, value)
        except (AttributeError, TypeError, ValueError):   # a setting this Blender lacks or names differently
            pass
    for k in dir(sc.render):                             # nor a date or render time in the PNG's metadata
        if k.startswith("use_stamp"):
            saved.append((sc.render, k, getattr(sc.render, k)))
            setattr(sc.render, k, False)
    shading = sc.display.shading
    saved.append((shading, "studio_light", shading.studio_light))
    try:
        shading.studio_light = "Default"
    except TypeError:          # a Blender without that studio light keeps its own
        pass
    return saved


def review_views(empty, out_dir, margin=0.6):
    """Renders the four views of the item into out_dir as PNGs; returns {view: path}."""
    bpy.context.view_layer.update()
    items = item_meshes(empty)
    if not items:
        raise model.WerkstattError(f"{empty['werkstatt_node']} shows no meshes to frame (show one of its options)")
    os.makedirs(out_dir, exist_ok=True)
    sc = bpy.context.scene
    saved_camera, saved_path = sc.camera, sc.render.filepath
    hidden = []
    for obj in items:                        # the item shows even if its option is hidden
        if obj.hide_render:
            hidden.append(obj)
            obj.hide_render = False
    lo, hi = _bounds(items)
    centre = (lo + hi) / 2
    size = max((hi - lo).length, 0.1)
    cam_data = bpy.data.cameras.new("werkstatt.review")
    cam = bpy.data.objects.new("werkstatt.review", cam_data)
    sc.collection.objects.link(cam)
    paths = {}
    saved = []
    try:
        saved = _pin(sc)
        sc.camera = cam
        for name, (direction, perspective) in VIEWS.items():
            d = mathutils.Vector(direction).normalized()
            span = size * (1 + margin)
            if perspective:
                cam_data.type = "PERSP"
                cam_data.lens = 50
                cam.location = centre + d * span * 2.2
            else:
                cam_data.type = "ORTHO"
                cam_data.ortho_scale = span
                cam.location = centre + d * (span + 5.0)
            cam_data.clip_start, cam_data.clip_end = 0.01, 100.0
            if name == "top":     # looking straight down, the front of the truck at the top of the image
                cam.rotation_euler = mathutils.Euler((0.0, 0.0, 3.141592653589793))
            else:
                cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
            path = os.path.join(out_dir, f"{name}.png")
            sc.render.filepath = path
            bpy.ops.render.render(write_still=True)
            paths[name] = path
    finally:
        bpy.data.objects.remove(cam, do_unlink=True)
        bpy.data.cameras.remove(cam_data)
        for obj in hidden:
            obj.hide_render = True
        sc.camera, sc.render.filepath = saved_camera, saved_path
        # In pin order: the file format first, since setting it resets the colour mode and depth that follow.
        for target, attr, old in saved:
            try:
                setattr(target, attr, old)
            except (TypeError, ValueError):     # a value its format no longer offers
                pass
    return paths
