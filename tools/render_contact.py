"""Render a vehicle's contact-sheet tiles headless in Blender, from a spec tools/contact_sheet.py writes.

Usage: blender -b --factory-startup --python tools/render_contact.py -- <spec.json>

Every vehicle gets the same four orthographic isometric corners (front-left, front-right,
rear-left, rear-right; 35.264 degrees elevation) aimed at one fixed target with one fixed ortho
scale, so sheets of different vehicles and builds compare tile for tile. Passes:
- beauty: the LOD0 body (textured with the donor's composite atlas when there is one), axles,
  spare and tyres on a ground plane at the tyres' contact height;
- rig: X-ray, the body ghosted with each connected piece in its own pale colour (piece
  boundaries), axles and the wheel colliders (green discs);
- colliders: Collider/Top (cyan) and Collider/Base (orange) as wireframes on a transparent
  background, for contact_sheet.py to lay over the rig tiles with the attach points it draws from
  projections.json;
- gaps: tools/check_holes.py marks (red: faces the game culls from behind), backface culling off.
Writes <out>/<pass>_<corner>.png and <out>/projections.json: per corner, each point id -> pixel.
Coordinates in the spec are OBJ space (x is the truck's left, y up, z forward); Blender imports
OBJ as (x, -z, y).
"""
import json, math, os, sys

import bmesh
import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector

spec = json.load(open(sys.argv[sys.argv.index("--") + 1]))
CORNERS = {"front_left": (1, 1), "front_right": (-1, 1), "rear_left": (1, -1), "rear_right": (-1, -1)}
PIECE_COLOURS = [(0.93, 0.82, 0.70), (0.72, 0.84, 0.93), (0.80, 0.92, 0.74), (0.93, 0.76, 0.86),
                 (0.88, 0.88, 0.70), (0.76, 0.74, 0.93), (0.70, 0.90, 0.88), (0.95, 0.80, 0.66)]


def blender(p):
    return Vector((p[0], -p[2], p[1]))


def material(name, rgba, image=None):
    m = bpy.data.materials.new(name)
    m.diffuse_color = rgba
    m.use_nodes = True
    bsdf = m.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = rgba
    if image:
        node = m.node_tree.nodes.new("ShaderNodeTexImage")
        node.image = bpy.data.images.load(image)
        node.interpolation = "Closest"
        m.node_tree.links.new(node.outputs["Color"], bsdf.inputs["Base Color"])
    return m


def import_obj(path, offset):
    bpy.ops.wm.obj_import(filepath=path)
    objs = list(bpy.context.selected_objects)
    for o in objs:
        o.location += blender(offset)
    return objs


def colour_pieces(obj, mats):
    obj.data.materials.clear()
    for m in mats:
        obj.data.materials.append(m)
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.faces.ensure_lookup_table()
    seen, island = set(), 0
    for f in bm.faces:
        if f.index in seen:
            continue
        stack = [f]
        seen.add(f.index)
        while stack:
            g = stack.pop()
            g.material_index = island % len(mats)
            for e in g.edges:
                for h in e.link_faces:
                    if h.index not in seen:
                        seen.add(h.index)
                        stack.append(h)
        island += 1
    bm.to_mesh(obj.data)
    bm.free()
    return island


def build(pass_name):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.show_cavity = pass_name == "beauty"
    scene.display.shading.show_shadows = False
    scene.render.resolution_x, scene.render.resolution_y = spec["res"]
    scene.render.film_transparent = pass_name == "colliders"
    scene.world = bpy.data.worlds.new("sky")
    scene.world.color = (0.93, 0.93, 0.91)
    scene.display.shading.background_type = "WORLD"
    atlas = spec.get("atlas") if pass_name == "beauty" else None
    body_mat = material("body", (0.72, 0.70, 0.62, 1), atlas)
    tyre_mat = material("tyre", (0.07, 0.07, 0.07, 1))
    axle_mat = material("axle", (0.25, 0.25, 0.27, 1))
    piece_mats = [material(f"piece{i}", (*c, 1)) for i, c in enumerate(PIECE_COLOURS)]
    role_mats = {"collider_top": material("collider_top", (0.10, 0.75, 0.90, 1)),
                 "collider_base": material("collider_base", (0.95, 0.55, 0.10, 1)),
                 "wheel_collider": material("wheel_collider", (0.15, 0.80, 0.25, 1))}
    pieces = 0
    for entry in spec["objects"]:
        role = entry["role"]
        if pass_name == "gaps":
            if role != "marks":
                continue
        elif pass_name == "colliders":
            if not role.startswith("collider"):
                continue
        elif role == "marks" or role.startswith("collider"):
            continue
        for o in import_obj(entry["file"], entry.get("offset", [0, 0, 0])):
            if role == "marks":
                continue
            if role == "body" and pass_name == "rig":
                pieces += colour_pieces(o, piece_mats)
                continue
            o.data.materials.clear()
            o.data.materials.append({"body": body_mat, "spare": tyre_mat, "axle": axle_mat}.get(role) or role_mats[role])
            if role.startswith("collider"):
                wire = o.modifiers.new("wire", "WIREFRAME")
                wire.thickness = 0.018
                wire.use_replace = True
    if pass_name in ("beauty", "rig"):
        for w in spec["wheels"]:
            bpy.ops.mesh.primitive_cylinder_add(radius=w["radius"], depth=w["width"], vertices=40,
                                                location=blender(w["center"]), rotation=(0, math.pi / 2, 0))
            bpy.context.object.data.materials.append(tyre_mat if pass_name == "beauty" else role_mats["wheel_collider"])
    if pass_name == "beauty":
        bpy.ops.mesh.primitive_plane_add(size=40, location=blender([0, spec["ground_y"], 0]))
        bpy.context.object.data.materials.append(material("ground", (0.62, 0.64, 0.58, 1)))
    if pass_name == "gaps":
        scene.display.shading.color_type = "VERTEX"
        scene.display.shading.show_backface_culling = False
    elif pass_name == "colliders":
        scene.display.shading.color_type = "MATERIAL"
    elif pass_name == "rig":
        scene.display.shading.color_type = "MATERIAL"
        scene.display.shading.show_xray = True
        scene.display.shading.xray_alpha = 0.35
    else:
        scene.display.shading.color_type = "TEXTURE" if atlas else "MATERIAL"
    return scene, pieces


def camera(scene, corner):
    sx, sz = CORNERS[corner]
    el = math.radians(spec["elevation"])
    target = blender(spec["target"])
    direction = blender([sx * math.cos(el) / math.sqrt(2), math.sin(el), sz * math.cos(el) / math.sqrt(2)])
    bpy.ops.object.camera_add(location=target + direction * 30)
    cam = bpy.context.object
    cam.rotation_euler = (-direction).to_track_quat("-Z", "Y").to_euler()
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = spec["ortho_scale"]
    cam.data.clip_end = 100
    scene.camera = cam
    return cam


projections, info = {}, {}
for pass_name in spec["passes"]:
    scene, pieces = build(pass_name)
    if pass_name == "rig":
        info["pieces"] = pieces
    for corner in CORNERS:
        cam = camera(scene, corner)
        scene.render.filepath = os.path.join(spec["out_dir"], f"{pass_name}_{corner}.png")
        bpy.ops.render.render(write_still=True)
        if pass_name == spec["passes"][0]:
            w, h = spec["res"]
            projections[corner] = {}
            for p in spec["points"]:
                c = world_to_camera_view(scene, cam, blender(p["pos"]))
                projections[corner][p["id"]] = [round(c.x * w, 1), round((1 - c.y) * h, 1)]
json.dump({"projections": projections, "info": info}, open(os.path.join(spec["out_dir"], "projections.json"), "w"), indent=1)
