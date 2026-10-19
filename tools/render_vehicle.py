"""Render a vehicle definition's built meshes from four views, headless in Blender.

Usage: blender -b --factory-startup --python tools/render_vehicle.py -- <definition.json> <mesh dir> <out prefix>
Writes <out prefix>_{side,top,rear,three_quarter}.png. Wheels are drawn as discs at the
definition's axle positions and track, and a "spare" from its preview OBJ; the body cut is drawn as
red lines in the side and top views. The body is textured through its UVs with
data/textures/<Donor>_composite.png when tools/composite_atlas.py has made one (the livery as the
game's car shader shows it, glass dark), so lamps and lenses read as in game; otherwise flat grey.
OBJ axes (x lateral, y up, z forward) import to Blender as (x, -z, y).
"""
import json, math, os, sys
import bpy

definition_path, mesh_dir, out_prefix = sys.argv[sys.argv.index("--") + 1:]
definition = json.load(open(definition_path))

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
atlas = os.path.join(ROOT, "data/textures", f"{definition['donor']}_composite.png")


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


body = material("body", (0.72, 0.70, 0.62, 1), atlas if os.path.exists(atlas) else None)
tire = material("tire", (0.06, 0.06, 0.06, 1))
cut = material("cut", (0.9, 0.15, 0.1, 1))
ground = material("ground", (0.35, 0.38, 0.33, 1))

for node_path, entry in definition["meshes"].items():
    file_name = entry if isinstance(entry, str) else entry["file"]
    if not node_path.startswith("Parts/") or not file_name.endswith("LOD0.obj"):
        continue
    bpy.ops.wm.obj_import(filepath=os.path.join(mesh_dir, file_name))
    for obj in bpy.context.selected_objects:
        obj.data.materials.clear()
        obj.data.materials.append(body)

# A spare wheel the plugin clones from the donor's wheel visual: drawn from its preview OBJ
# (meshes/<preview>, at the in-game pose) in the tyre colour.
preview = definition.get("spare", {}).get("preview")
if preview:
    bpy.ops.wm.obj_import(filepath=os.path.join(ROOT, "meshes", preview))
    for obj in bpy.context.selected_objects:
        obj.data.materials.clear()
        obj.data.materials.append(tire)

wheel = dict(definition["wheel"], **definition.get("tyre", {}))   # a fitted tyre keeps the donor's hub height
front = definition["donorAxleZ"]["front"]
rear = front - definition["wheelbase"]
half_track = definition["track"] / 2
for z in (front, rear):
    for x in (-half_track, half_track):
        bpy.ops.mesh.primitive_cylinder_add(radius=wheel["radius"], depth=wheel["width"], location=(x, -z, wheel["y"]), rotation=(0, math.pi / 2, 0))
        bpy.context.object.data.materials.append(tire)

cut_markers = []
steps = sorted(definition["bodyCut"])
for i, (y0, z) in enumerate(steps):
    y1 = steps[i + 1][0] if i + 1 < len(steps) else 2.6
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, -z, (y0 + y1) / 2), scale=(2.4, 0.012, y1 - y0))
    marker = bpy.context.object
    marker.data.materials.append(cut)
    marker.visible_shadow = False
    cut_markers.append(marker)

bpy.ops.mesh.primitive_plane_add(size=30, location=(0, 0, 0))
bpy.context.object.data.materials.append(ground)

scene.render.engine = "BLENDER_WORKBENCH"
scene.display.shading.light = "STUDIO"
scene.display.shading.color_type = "TEXTURE" if os.path.exists(atlas) else "MATERIAL"
scene.display.shading.show_cavity = True
scene.display.shading.show_shadows = True
scene.render.resolution_x, scene.render.resolution_y = 1200, 700

views = {
    # name: (location, rotation, ortho scale or None for perspective, show cut markers)
    "side": ((15, 0, 1.3), (math.pi / 2, 0, math.pi / 2), 7.0, True),
    "top": ((0, 0, 15), (0, 0, math.pi / 2), 7.0, True),
    "rear": ((0, 15, 1.2), (math.pi / 2, 0, math.pi), 4.6, False),
    "three_quarter": ((8.5, -7.0, 4.0), (math.radians(72), 0, math.radians(50)), None, False),
}
for name, (location, rotation, ortho, show_cut) in views.items():
    for marker in cut_markers:
        marker.hide_render = not show_cut
    bpy.ops.object.camera_add(location=location, rotation=rotation)
    cam = bpy.context.object
    if ortho:
        cam.data.type = "ORTHO"
        cam.data.ortho_scale = ortho
    else:
        cam.data.lens = 40
    scene.camera = cam
    scene.render.filepath = f"{out_prefix}_{name}.png"
    bpy.ops.render.render(write_still=True)
