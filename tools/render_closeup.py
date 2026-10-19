"""Perspective close-ups of car-root-space OBJs, headless in Blender, for comparing with photos.

Usage: blender -b --factory-startup --python tools/render_closeup.py -- [--texture <png>] <out.png>
       <target x,y,z> <camera x,y,z> <lens mm> <obj> [<obj> ...]

Target and camera are in OBJ space (metres, +x the truck's left, y up, z forward). Vertex colours
show through, and meshes without them render grey; with --texture every mesh is drawn with that
image through its UVs instead (e.g. extracted/textures/Mammoth_skin00.png, to see atlas graphics).
"""
import sys
import bpy
from mathutils import Vector

args = sys.argv[sys.argv.index("--") + 1:]
texture = None
if args[0] == "--texture":
    texture, args = args[1], args[2:]
out, target, camera, lens, *objs = args
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
for path in objs:
    bpy.ops.wm.obj_import(filepath=path)
scene.render.engine = "BLENDER_WORKBENCH"
scene.display.shading.light = "STUDIO"
scene.display.shading.color_type = "VERTEX"
if texture:
    image = bpy.data.images.load(texture)
    material = bpy.data.materials.new("atlas")
    material.use_nodes = True
    node = material.node_tree.nodes.new("ShaderNodeTexImage")
    node.image = image
    node.interpolation = "Closest"
    material.node_tree.links.new(node.outputs["Color"], material.node_tree.nodes["Principled BSDF"].inputs["Base Color"])
    for obj in scene.objects:
        if obj.type == "MESH":
            obj.data.materials.clear()
            obj.data.materials.append(material)
    scene.display.shading.color_type = "TEXTURE"
scene.display.shading.show_cavity = True
scene.render.resolution_x, scene.render.resolution_y = 1600, 1000


def blender(p):
    """OBJ (x, y, z) imports as Blender (x, -z, y)."""
    x, y, z = (float(c) for c in p.split(","))
    return Vector((x, -z, y))


t, c = blender(target), blender(camera)
bpy.ops.object.camera_add(location=c)
cam = bpy.context.object
cam.rotation_euler = (t - c).to_track_quat("-Z", "Y").to_euler()
cam.data.lens = float(lens)
scene.camera = cam
scene.render.filepath = out
bpy.ops.render.render(write_still=True)
