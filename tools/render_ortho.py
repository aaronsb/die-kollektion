"""Orthographic renders at a fixed scale, for laying over dimensioned drawings and photos.

Usage: blender -b --factory-startup --python tools/render_ortho.py -- <out.png> <view> <px_per_m>
       <centre_a> <centre_b> <width_px> <height_px> <obj> [<obj> ...]

view: side (from the truck's left, front pointing left in the image), front, rear or top (front
pointing left). centre_a/centre_b are the car-root coordinates (metres, OBJ convention: x negated,
y up, z forward) at the image centre: (z, y) for side, (x, y) for front/rear, (z, x) for top.
Vertex colours show through; meshes without them render light grey.
"""
import math, sys
import bpy

out, view, ppm, ca, cb, w, h, *objs = sys.argv[sys.argv.index("--") + 1:]
ppm, ca, cb, w, h = float(ppm), float(ca), float(cb), int(w), int(h)
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
for path in objs:
    bpy.ops.wm.obj_import(filepath=path)
scene.render.engine = "BLENDER_WORKBENCH"
scene.display.shading.light = "STUDIO"
scene.display.shading.color_type = "VERTEX"
scene.display.shading.show_cavity = True
scene.render.resolution_x, scene.render.resolution_y = w, h
scene.render.film_transparent = True

# Blender imports OBJ (x, y, z) as (x, -z, y): OBJ z (forward) is Blender -Y, OBJ y (up) is Blender Z.
far = 50.0
if view == "side":      # from OBJ +x (truck's left): forward (-Y) appears on the image left
    loc, rot = (far, -ca, cb), (math.pi / 2, 0, math.pi / 2)
elif view == "front":   # from ahead, looking back: OBJ +x (truck's left) appears on the image right
    loc, rot = (ca, -far, cb), (math.pi / 2, 0, 0)
elif view == "rear":    # from behind: truck's left appears on the image left
    loc, rot = (ca, far, cb), (math.pi / 2, 0, math.pi)
elif view == "top":     # from above, front pointing left
    loc, rot = (cb, -ca, far), (0, 0, math.pi / 2)
else:
    raise SystemExit(f"unknown view {view}")
bpy.ops.object.camera_add(location=loc, rotation=rot)
cam = bpy.context.object
cam.data.type = "ORTHO"
cam.data.ortho_scale = max(w, h) / ppm
cam.data.clip_end = 200.0
scene.camera = cam
scene.render.filepath = out
bpy.ops.render.render(write_still=True)
