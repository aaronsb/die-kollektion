"""Renders tools/check_holes.py marks as the game would draw them, headless in Blender.

Usage: blender -b --factory-startup --python tools/render_holes.py -- <marks.obj> <out prefix>
       <name>:<target x,y,z>:<camera x,y,z>:<lens mm> [...]

Back faces are culled, as in the game, so a culled patch shows as missing; the marks file colours
it red where an editor would draw it, which this render cannot show, so each view is rendered twice:
<prefix>_<name>_game.png with culling on a bright green background (what the player sees: green
inside the truck's outline is a see-through hole) and
<prefix>_<name>_marked.png without culling (red faces are the ones the game drops, magenta cubes
are gaps where no surface exists). Coordinates are OBJ space: +x the truck's left, y up, z forward.
"""
import sys

import bpy
from mathutils import Vector

args = sys.argv[sys.argv.index("--") + 1:]
marks, prefix, views = args[0], args[1], args[2:]
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
bpy.ops.wm.obj_import(filepath=marks)
scene.render.engine = "BLENDER_WORKBENCH"
scene.display.shading.light = "STUDIO"
scene.display.shading.color_type = "VERTEX"
scene.display.shading.show_cavity = False
scene.render.resolution_x, scene.render.resolution_y = 1200, 800
scene.world = bpy.data.worlds.new("sky")
scene.world.color = (0.55, 0.75, 0.95)
scene.display.shading.background_type = "WORLD"
camera = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
scene.collection.objects.link(camera)
scene.camera = camera


def blender(p):
    """OBJ (x, y, z) to Blender's z-up space, as the OBJ importer maps it."""
    return Vector((p[0], -p[2], p[1]))


for view in views:
    name, target, eye, lens = view.split(":")
    target = blender([float(c) for c in target.split(",")])
    eye = blender([float(c) for c in eye.split(",")])
    camera.location = eye
    camera.rotation_euler = (target - eye).to_track_quat("-Z", "Y").to_euler()
    camera.data.lens = float(lens)
    camera.data.clip_start = 0.01
    for culled, tag in ((True, "game"), (False, "marked")):
        scene.display.shading.show_backface_culling = culled
        scene.world.color = (0.1, 0.9, 0.2) if culled else (0.55, 0.75, 0.95)
        scene.render.filepath = f"{prefix}_{name}_{tag}.png"
        bpy.ops.render.render(write_still=True)
