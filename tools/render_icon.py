"""Flat side view for a vehicle-select icon: white body, red bed, black glass.

Usage: blender -b --factory-startup --python tools/render_icon.py -- <out.png> <px_per_m>
       <centre_z> <centre_y> <width_px> <height_px> <line_px> <crease_deg> <min_stroke_px>
       <glass.obj> <bed.obj> <body.obj> [<body.obj> ...]

Seen from the truck's right (OBJ -x), so the front points right as in the stock icons. The caller
passes only the camera-side half of the truck; back faces are culled, so an opening without glass
shows through instead of showing the inside of the shell. Emission only, no shading: the caller
reads white as body, red as bed, black or empty as a hole. With line_px > 0, Freestyle also draws
black lines at silhouettes, borders, creases sharper than crease_deg and glass boundaries (the bed
gets its outer contour only), dropping strokes shorter than min_stroke_px.
"""
import math, sys
import bpy

out, ppm, cz, cy, w, h, line_px, crease, min_stroke, glass, bed, *bodies = sys.argv[sys.argv.index("--") + 1:]
ppm, cz, cy, w, h = float(ppm), float(cz), float(cy), int(w), int(h)
line_px, crease, min_stroke = float(line_px), float(crease), float(min_stroke)
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene


def flat(name, rgb):
    mat = bpy.data.materials.new(name)
    nodes = mat.node_tree.nodes
    nodes.clear()
    emit = nodes.new("ShaderNodeEmission")
    emit.inputs["Color"].default_value = (*rgb, 1.0)
    output = nodes.new("ShaderNodeOutputMaterial")
    mat.node_tree.links.new(emit.outputs[0], output.inputs[0])
    mat.use_backface_culling = True
    return mat


white, black, red = flat("body", (1, 1, 1)), flat("glass", (0, 0, 0)), flat("bed", (1, 0, 0))
bed_collection = bpy.data.collections.new("bed")
scene.collection.children.link(bed_collection)
for path, mat in [(glass, black), (bed, red)] + [(b, white) for b in bodies]:
    bpy.ops.wm.obj_import(filepath=path)
    for obj in bpy.context.selected_objects:
        obj.data.materials.clear()
        obj.data.materials.append(mat)
        if mat is red:
            for c in list(obj.users_collection):
                c.objects.unlink(obj)
            bed_collection.objects.link(obj)

scene.render.engine = "BLENDER_EEVEE"
scene.view_settings.view_transform = "Standard"
scene.render.film_transparent = True
scene.render.resolution_x, scene.render.resolution_y = w, h
if line_px > 0:
    scene.render.use_freestyle = True
    scene.render.line_thickness_mode = "ABSOLUTE"
    scene.render.line_thickness = 1.0
    layer = scene.view_layers[0]
    layer.use_freestyle = True
    settings = layer.freestyle_settings
    settings.crease_angle = math.radians(crease)
    style = bpy.data.linestyles.new("icon")
    style.color = (0, 0, 0)
    style.thickness = line_px
    style.thickness_position = "CENTER"
    style.caps = "ROUND"
    style.use_length_min = True
    style.length_min = min_stroke
    for lineset in list(settings.linesets):
        settings.linesets.remove(lineset)
    for name, edges, bed_only in (("detail", ("silhouette", "border", "crease", "material_boundary"), False),
                                  ("bed", ("external_contour",), True)):
        lineset = settings.linesets.new(name)
        lineset.linestyle = style
        lineset.select_by_visibility = True
        lineset.visibility = "VISIBLE"
        lineset.select_by_edge_types = True
        for edge in ("silhouette", "border", "crease", "material_boundary", "external_contour"):
            setattr(lineset, f"select_{edge}", edge in edges)
        lineset.select_by_collection = True
        lineset.collection = bed_collection
        lineset.collection_negation = "INCLUSIVE" if bed_only else "EXCLUSIVE"

# Blender imports OBJ (x, y, z) as (x, -z, y); from OBJ -x, OBJ +z (forward) appears on the image right.
bpy.ops.object.camera_add(location=(-50.0, -cz, cy), rotation=(math.pi / 2, 0, -math.pi / 2))
cam = bpy.context.object
cam.data.type = "ORTHO"
cam.data.ortho_scale = max(w, h) / ppm
cam.data.clip_end = 200.0
scene.camera = cam
scene.render.filepath = out
bpy.ops.render.render(write_still=True)
