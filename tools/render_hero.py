"""Render a vehicle's README hero image: one wide, textured three-quarter view.

Usage: .venv/bin/python -I tools/render_hero.py vehicles/<name> <out.png> [--width 1600 --height 700]
       .venv/bin/python -I tools/render_hero.py --thumbs docs/images/thumbs
The second form crops each vehicle's front-left contact-sheet tile (vehicles/<name>/contact/iso.png)
into a small thumbnail for the README's vehicle gallery.

The vehicle must be built (make build) and its donor's composite atlas made (make contact does it).
The scene is the contact sheet's (tools/contact_sheet.py lays out the meshes, axles, spare and
wheels the same way; Workbench, studio light, the donor atlas on the body), seen through a fixed
perspective camera from the front-left at a low angle, on a flat light background with a soft
contact shadow, so the image is reproducible. The script runs
itself inside Blender (blender -b --factory-startup --python tools/render_hero.py -- <spec.json>).
"""
import json, math, os, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

try:
    import bpy  # noqa: F401
    IN_BLENDER = True
except ImportError:
    IN_BLENDER = False

CAMERA = {"azimuth": 40.0, "elevation": 11.0, "distance": 13.8, "lens": 50.0, "target": [0.0, 1.05, -0.7]}


def write_spec(vdir, out, width, height):
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    import contact_sheet as cs
    vdir = os.path.abspath(vdir)
    manifest = json.load(open(os.path.join(vdir, "vehicle.json")))
    donor = manifest["donor"]
    nodes = json.load(open(os.path.join(ROOT, "extracted", donor.lower(), "nodes.json")))["nodes"]
    final, delta, _ = cs.derive_layout(manifest, nodes)
    meshes = cs.gather_meshes(manifest, vdir, delta)
    wheels = cs.wheels_of(manifest, final)
    objects = [{"file": meshes["body_LOD0"]["file"], "offset": meshes["body_LOD0"]["offset"], "role": "body"}]
    for k in ("axle_front_LOD0", "axle_rear_LOD0"):
        if meshes[k]["file"]:
            objects.append({"file": meshes[k]["file"], "offset": meshes[k]["offset"], "role": "axle"})
    preview = (manifest.get("spare") or {}).get("preview")
    if preview and os.path.exists(os.path.join(vdir, preview)):
        objects.append({"file": os.path.join(vdir, preview), "offset": [0, 0, 0], "role": "spare"})
    missing = [o["file"] for o in objects if not os.path.exists(o["file"])]
    if missing:
        raise SystemExit(f"not built: {missing[0]} (run make build)")
    atlas = os.path.join(ROOT, "extracted", "textures", f"{donor}_composite.png")
    spec = {"objects": objects, "wheels": wheels, "ground_y": min(w["center"][1] - w["radius"] for w in wheels),
            "atlas": atlas if os.path.exists(atlas) else None, "res": [width, height],
            "camera": CAMERA, "out": os.path.abspath(out)}
    work = os.path.join(vdir, "build", "hero")
    os.makedirs(work, exist_ok=True)
    path = os.path.join(work, "spec.json")
    json.dump(spec, open(path, "w"), indent=1)
    return path


def render(spec):
    import bpy
    from mathutils import Vector

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

    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    shading = scene.display.shading
    shading.light = "STUDIO"
    shading.show_cavity = True
    shading.show_shadows = True
    shading.shadow_intensity = 0.35
    shading.color_type = "TEXTURE" if spec["atlas"] else "MATERIAL"
    scene.render.resolution_x, scene.render.resolution_y = spec["res"]
    scene.render.resolution_percentage = 100
    scene.view_settings.view_transform = "Standard"
    scene.render.film_transparent = True
    scene.display.render_aa = "32"
    scene.world = bpy.data.worlds.new("sky")
    scene.world.color = (0.86, 0.87, 0.85)
    shading.background_type = "WORLD"
    mats = {"body": material("body", (0.72, 0.70, 0.62, 1), spec["atlas"]),
            "axle": material("axle", (0.25, 0.25, 0.27, 1)), "spare": material("tyre", (0.07, 0.07, 0.07, 1))}
    for entry in spec["objects"]:
        bpy.ops.wm.obj_import(filepath=entry["file"])
        for o in bpy.context.selected_objects:
            o.location += blender(entry["offset"])
            o.data.materials.clear()
            o.data.materials.append(mats[entry["role"]])
    for w in spec["wheels"]:
        bpy.ops.mesh.primitive_cylinder_add(radius=w["radius"], depth=w["width"], vertices=48,
                                            location=blender(w["center"]), rotation=(0, math.pi / 2, 0))
        bpy.context.object.data.materials.append(mats["spare"])

    cam_spec = spec["camera"]
    az, el = math.radians(cam_spec["azimuth"]), math.radians(cam_spec["elevation"])
    target = blender(cam_spec["target"])
    # Front-left of the truck: OBJ +x is its left, +z its front.
    direction = blender([math.sin(az) * math.cos(el), math.sin(el), math.cos(az) * math.cos(el)])
    bpy.ops.object.camera_add(location=target + direction * cam_spec["distance"])
    cam = bpy.context.object
    cam.rotation_euler = (-direction).to_track_quat("-Z", "Y").to_euler()
    cam.data.lens = cam_spec["lens"]
    cam.data.clip_end = 200
    scene.camera = cam
    scene.render.filepath = spec["out"]
    bpy.ops.render.render(write_still=True)


def thumbs(out_dir, size=(280, 210)):
    from PIL import Image
    os.makedirs(out_dir, exist_ok=True)
    for vdir in sorted(os.listdir(os.path.join(ROOT, "vehicles"))):
        iso = os.path.join(ROOT, "vehicles", vdir, "contact", "iso.png")
        if not os.path.exists(iso):
            continue
        im = Image.open(iso).convert("RGB")
        tile = im.crop((0, 0, im.width // 4, im.height))    # front-left corner
        tile = tile.crop((0, 28, tile.width, tile.height))  # drop the corner label
        tile.thumbnail(size, Image.LANCZOS)
        path = os.path.join(out_dir, f"{vdir}.png")
        tile.quantize(colors=128, method=Image.Quantize.MEDIANCUT).save(path, optimize=True)
        print(f"{path}: {os.path.getsize(path) // 1024} KB")


def main():
    if not IN_BLENDER and "--thumbs" in sys.argv:
        thumbs(sys.argv[sys.argv.index("--thumbs") + 1])
        return
    if IN_BLENDER:
        render(json.load(open(sys.argv[sys.argv.index("--") + 1])))
        return
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("vehicle")
    ap.add_argument("out")
    ap.add_argument("--width", type=int, default=1600)
    ap.add_argument("--height", type=int, default=700)
    args = ap.parse_args()
    spec = write_spec(args.vehicle, args.out, args.width, args.height)
    with open(os.path.join(os.path.dirname(spec), "blender.log"), "w") as log:
        subprocess.run(["blender", "-b", "--factory-startup", "--python", os.path.abspath(__file__), "--", spec],
                       stdout=log, stderr=subprocess.STDOUT, check=True)
    from PIL import Image
    # The render has a transparent background; lay it on a flat light background with a soft
    # contact shadow under the truck, so the image reads cleanly on GitHub's light and dark themes.
    from PIL import ImageFilter
    car = Image.open(args.out).convert("RGBA")
    alpha = car.split()[3]
    shadow = Image.new("L", car.size, 0)
    box = alpha.getbbox()
    if box:
        from PIL import ImageDraw
        x0, y0, x1, y1 = box
        ImageDraw.Draw(shadow).ellipse([x0 + (x1 - x0) * 0.04, y1 - (y1 - y0) * 0.07, x1 - (x1 - x0) * 0.04, y1 + (y1 - y0) * 0.02], fill=90)
        shadow = shadow.filter(ImageFilter.GaussianBlur(18))
    im = Image.new("RGBA", car.size, (236, 238, 234, 255))
    im = Image.composite(Image.new("RGBA", car.size, (150, 152, 146, 255)), im, shadow)
    im = Image.alpha_composite(im, car).convert("RGB")
    im.quantize(colors=192, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.FLOYDSTEINBERG).save(args.out, optimize=True)
    print(f"{args.out}: {os.path.getsize(args.out) // 1024} KB")


if __name__ == "__main__":
    main()
