"""What an agent (or a careful human) checks between nudges: how far an item is from the vehicle's body, and the
same four renders of it every time.

clearance() measures in game metres with BVH trees: the minimum gap between the item's meshes and the body's when
they don't touch, or how deep the item sits inside the body when they intersect, and which part it touches.
review_views() renders front, side, top and three-quarter views framed on the item at a fixed resolution and
with fixed lighting, so successive nudges compare like with like.
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
    return [o for o in [empty] + list(empty.children_recursive) if o.type == "MESH"]


def body_meshes():
    return [o for o in bpy.context.scene.objects if o.type == "MESH" and o.get("werkstatt_part") in PART_KINDS]


def _part_name(obj):
    return obj.users_collection[0].name.replace("Part: ", "") if obj.users_collection else obj.name


AXIS_DIRECTIONS = {     # game axis label -> Blender direction
    "up": (0.0, 0.0, 1.0), "down": (0.0, 0.0, -1.0), "forward": (0.0, -1.0, 0.0), "back": (0.0, 1.0, 0.0),
    "right": (-1.0, 0.0, 0.0), "left": (1.0, 0.0, 0.0)}
NUDGE_FOR = {"up": ("y", 1), "down": ("y", -1), "forward": ("z", 1), "back": ("z", -1), "right": ("x", 1), "left": ("x", -1)}


def _exit_depth(points, tree, direction, reach):
    """The furthest any point must travel along direction to leave the mesh: a point is inside when a ray along
    direction first meets a face it is leaving (the face's normal points along the ray)."""
    deepest = 0.0
    for p in points:
        loc, normal, index, dist = tree.ray_cast(p, direction, reach)
        if loc is not None and normal.dot(direction) > 0 and dist > deepest:
            deepest = dist
    return deepest


def _clearing_move(verts, faces, body_tree, direction, start, reach, step=0.002):
    """The smallest move along direction, from start, after which the item no longer overlaps the body and its
    points are outside it (not inside a hollow body's shell), or None within reach."""
    t = start + 0.001
    while t <= reach:
        moved = [v + direction * t for v in verts]
        tree = BVHTree.FromPolygons(moved, faces, all_triangles=False)
        if not tree.overlap(body_tree) and not _any_inside(moved[::max(1, len(moved) // 200)], body_tree, reach):
            return round(t, 4)
        t += step
    return None


def _any_inside(points, tree, reach):
    """Whether any point sits inside the body: straight up, it first meets a face it is leaving."""
    up, down = mathutils.Vector((0.0, 0.0, 1.0)), mathutils.Vector((0.0, 0.0, -1.0))
    for p in points:
        hit_up = tree.ray_cast(p, up, reach)
        if hit_up[0] is not None and hit_up[1].dot(up) > 0:
            return True
    return False


def clearance(empty, reach=0.5):
    """How an item sits against the body parts, in game metres.

    Clear: {"intersecting": False, "gap": the minimum distance, "touches": the nearest part, "at": the point}.
    Intersecting: {"intersecting": True, "penetration": the smallest move along one truck axis that clears the
    body, "clear_by": [axis, sign] for api.nudge, "direction": "up", "forward", ..., "depths": every direction's
    move, "touches", "at"}. Inside is told by ray casts, so it needs the body's faces to point outward."""
    bpy.context.view_layer.update()
    items = item_meshes(empty)
    if not items:
        raise model.WerkstattError(f"{empty['werkstatt_node']} has no meshes to measure")
    bodies = body_meshes()
    if not bodies:
        raise model.WerkstattError("the vehicle has no body part to measure against")
    iv, ifaces, _ = _world_mesh(items)
    bv, bfaces, bowners = _world_mesh(bodies)
    item_tree = BVHTree.FromPolygons(iv, ifaces, all_triangles=False)
    body_tree = BVHTree.FromPolygons(bv, bfaces, all_triangles=False)
    pairs = item_tree.overlap(body_tree)
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
    out = {"node": empty["werkstatt_node"], "intersecting": bool(pairs)}
    part = bowners[pairs[0][1]] if pairs else (bowners[nearest_index] if nearest_index is not None else None)
    out["touches"] = _part_name(part) if part else None
    if pairs:
        depths = {}
        for name, d in AXIS_DIRECTIONS.items():
            d = mathutils.Vector(d)
            # the item's points leaving the body along d, and the body's points leaving the item the other way:
            # a lower bound, checked by moving the item and testing again (a hollow body's shell can be crossed
            # into its inside, which is no fit, and an edge can cross a face with no point inside)
            depths[name] = _clearing_move(iv, ifaces, body_tree, d, max(_exit_depth(iv, body_tree, d, reach),
                                                                        _exit_depth(near_body, item_tree, -d, reach)), reach)
        clearing = {k: v for k, v in depths.items() if v is not None}
        direction = min(clearing, key=lambda k: (clearing[k], list(AXIS_DIRECTIONS).index(k))) if clearing else None
        out.update({"penetration": clearing[direction] if direction else None, "direction": direction,
                    "clear_by": list(NUDGE_FOR[direction]) if direction else None, "depths": depths, "gap": None,
                    "at": model.clean(model.blender_to_game(tuple(nearest_at or iv[0])), 4),
                    **({} if direction else {"note": f"no move along one axis up to {reach} m clears the body"})})
    elif nearest is None:
        out.update({"penetration": None, "gap": None, "at": None, "note": f"nothing of the body within {reach} m"})
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


def review_views(empty, out_dir, margin=0.6):
    """Renders the four views of the item into out_dir; returns {view: path}."""
    bpy.context.view_layer.update()
    items = item_meshes(empty)
    if not items:
        raise model.WerkstattError(f"{empty['werkstatt_node']} has no meshes to frame")
    os.makedirs(out_dir, exist_ok=True)
    sc = bpy.context.scene
    saved = (sc.camera, sc.render.engine, sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage,
             sc.render.filepath, sc.render.film_transparent, sc.render.dither_intensity)
    stamps = {k: getattr(sc.render, k) for k in dir(sc.render) if k.startswith("use_stamp")}
    shading = sc.display.shading
    saved_shading = (shading.light, shading.color_type, shading.show_cavity, shading.studio_light)
    hidden = []
    for obj in item_meshes(empty):           # the item shows even if its option is hidden
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
    try:
        sc.render.engine = "BLENDER_WORKBENCH"
        sc.render.resolution_x, sc.render.resolution_y = VIEW_RESOLUTION
        sc.render.resolution_percentage = 100
        sc.render.film_transparent = False
        sc.render.dither_intensity = 0.0       # dither is random noise: two renders of the same thing would differ
        for k in stamps:                       # nor a date or render time in the PNG's metadata
            setattr(sc.render, k, False)
        shading.light = "STUDIO"
        try:
            shading.studio_light = "Default"
        except TypeError:          # a Blender without that studio light keeps its own
            pass
        shading.color_type = "MATERIAL"
        shading.show_cavity = True
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
        (sc.camera, sc.render.engine, sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage,
         sc.render.filepath, sc.render.film_transparent, sc.render.dither_intensity) = saved
        for k, v in stamps.items():
            setattr(sc.render, k, v)
        shading.light, shading.color_type, shading.show_cavity, shading.studio_light = saved_shading
    return paths
