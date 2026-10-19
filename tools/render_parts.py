"""Inspect car-root-space OBJs from four views, coloured by their vertex colours, headless in Blender.

Usage: blender -b --factory-startup --python tools/render_parts.py -- <out prefix> <obj> [<obj> ...]
Writes <out prefix>_{side,top,front,three_quarter}.png framed on the bulk of the vertices. Vertex colours
(e.g. the bone colours export_car_mesh.py writes for skinned meshes) show through; meshes
without them render grey.
"""
import math, sys
import bpy
from mathutils import Vector

out_prefix, *objs = sys.argv[sys.argv.index("--") + 1:]
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
for path in objs:
    bpy.ops.wm.obj_import(filepath=path)

# Frame on the 1st-99th percentile of vertices so a few stray points cannot shrink the subject.
points = [o.matrix_world @ v.co for o in scene.objects if o.type == "MESH" for v in o.data.vertices]
def percentile(axis, q):
    values = sorted(p[axis] for p in points)
    return values[min(len(values) - 1, int(q * len(values)))]
lo = Vector(tuple(percentile(i, 0.01) for i in range(3)))
hi = Vector(tuple(percentile(i, 0.99) for i in range(3)))
center, size = (lo + hi) / 2, max((hi - lo).length, 1e-4)

scene.render.engine = "BLENDER_WORKBENCH"
scene.display.shading.light = "STUDIO"
scene.display.shading.color_type = "VERTEX"
scene.display.shading.show_cavity = True
scene.render.resolution_x, scene.render.resolution_y = 1200, 800

views = {
    "side": (Vector((1, 0, 0)), (math.pi / 2, 0, math.pi / 2)),
    "top": (Vector((0, 0, 1)), (0, 0, math.pi / 2)),
    "front": (Vector((0, -1, 0)), (math.pi / 2, 0, 0)),
    "three_quarter": (Vector((0.8, -0.7, 0.45)).normalized(), None),
}
for name, (direction, rotation) in views.items():
    bpy.ops.object.camera_add(location=center + direction * size * 4)
    cam = bpy.context.object
    if rotation:
        cam.rotation_euler = rotation
        cam.data.type = "ORTHO"
        cam.data.ortho_scale = size * 1.15
    else:
        cam.rotation_euler = (-direction).to_track_quat("-Z", "Y").to_euler()
        cam.data.lens = 50
        cam.location = center + direction * size * 2.2
    scene.camera = cam
    scene.render.filepath = f"{out_prefix}_{name}.png"
    bpy.ops.render.render(write_still=True)
