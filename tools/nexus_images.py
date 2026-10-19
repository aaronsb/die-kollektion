"""Render the Nexus Mods page's images into docs/nexus/images/ (`make nexus-images`).

Usage: .venv/bin/python tools/nexus_images.py [--only <name> ...]

Writes, reproducibly (fixed cameras, Blender's Workbench engine, the contact sheets' look):
- banner-1300x372.jpg: the four trucks lined up with the title, everything important well inside
  the edges so Nexus's cropping keeps it;
- 1920x1080 gallery images: each truck in a three-quarter view (megaloceros, glyptodon, mastodon,
  megatherium), the Ding with the golf-bag canary (from higher up, to see the roof), "how it's built"
  (the Megaloceros's isometric render beside its rig view with colliders and labelled attach points)
  and a contact-sheet showcase (the Megaloceros's four isometric corners in a 2x2 grid).

The vehicles must be built (`make build`); the donors' composite atlases are made here if missing.
Three-quarter views put the donor's own wheel and tyre meshes (extracted locally by
tools/export_game_data.sh) at each hub, scaled to the vehicle's tyre, so tyres read as tyres; the isometric and rig tiles come from
tools/render_contact.py at a larger size. Each subject is cropped to its outline and centred, so
framing doesn't depend on the camera aim. The script runs itself inside Blender for the
three-quarter renders (blender -b --factory-startup --python tools/nexus_images.py -- <spec.json>).
"""
import json, math, os, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "nexus", "images")
WORK = os.path.join(ROOT, "build", "nexus")
TRUCKS = ["megaloceros", "glyptodon", "mastodon", "megatherium"]
NAMES = {"megaloceros": "Das Megaloceros", "glyptodon": "Das Glyptodon", "mastodon": "Das Mastodon",
         "megatherium": "Das Megatherium", "dingding": "The Ding"}
BACKGROUND = ((238, 240, 236), (214, 218, 210))   # top, bottom of a soft vertical gradient
INK = (36, 40, 36)
MUTED = (96, 102, 94)
FONT_BOLD = "/usr/share/fonts/noto/NotoSans-Bold.ttf"
FONT = "/usr/share/fonts/noto/NotoSans-Regular.ttf"
THREE_QUARTER = {"azimuth": 38.0, "elevation": 12.0, "lens": 50.0}
FROM_ABOVE = {"azimuth": 36.0, "elevation": 30.0, "lens": 50.0}

try:
    import bpy  # noqa: F401
    IN_BLENDER = True
except ImportError:
    IN_BLENDER = False


# ---------------------------------------------------------------- inside Blender: one three-quarter render

def render_in_blender(spec):
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
    shading.cavity_type = "BOTH"
    shading.show_shadows = True
    shading.shadow_intensity = 0.3
    shading.color_type = "TEXTURE" if spec["atlas"] else "MATERIAL"
    scene.render.resolution_x, scene.render.resolution_y = spec["res"]
    scene.render.resolution_percentage = 100
    scene.view_settings.view_transform = "Standard"
    scene.render.film_transparent = True
    scene.display.render_aa = "32"
    mats = {"body": material("body", (0.72, 0.70, 0.62, 1), spec["atlas"]),
            "axle": material("axle", (0.26, 0.26, 0.28, 1)),
            "tyre": material("tyre", (0.13, 0.13, 0.13, 1)),
            "rim": material("rim", (0.58, 0.58, 0.55, 1)),
            "spare": material("spare", (0.16, 0.16, 0.16, 1))}
    lo, hi = Vector((1e9, 1e9, 1e9)), Vector((-1e9, -1e9, -1e9))
    for entry in spec["objects"]:
        bpy.ops.wm.obj_import(filepath=entry["file"])
        for o in bpy.context.selected_objects:
            o.location += blender(entry["offset"])
            o.data.materials.clear()
            o.data.materials.append(mats[entry["role"]])
            if entry["role"] == "body":
                bpy.context.view_layer.update()
                for c in o.bound_box:
                    w = o.matrix_world @ Vector(c)
                    lo = Vector(map(min, lo, w))
                    hi = Vector(map(max, hi, w))
    for w in spec.get("cylinders", []):   # wheels when the donor's wheel meshes aren't available
        bpy.ops.mesh.primitive_cylinder_add(radius=w["radius"], depth=w["width"], vertices=48,
                                            location=blender(w["center"]), rotation=(0, math.pi / 2, 0))
        bpy.context.object.data.materials.append(mats["tyre"])
        bpy.ops.mesh.primitive_cylinder_add(radius=w["radius"] * 0.58, depth=w["width"] + 0.02, vertices=32,
                                            location=blender(w["center"]), rotation=(0, math.pi / 2, 0))
        bpy.context.object.data.materials.append(mats["rim"])
    cam_spec = spec["camera"]
    az, el = math.radians(cam_spec["azimuth"]), math.radians(cam_spec["elevation"])
    target = (lo + hi) / 2
    size = (hi - lo).length
    # Front-left of the truck: OBJ +x is its left, +z its front; far enough that the whole truck fits.
    direction = blender([math.sin(az) * math.cos(el), math.sin(el), math.cos(az) * math.cos(el)])
    bpy.ops.object.camera_add(location=target + direction * size * 2.6)
    cam = bpy.context.object
    cam.rotation_euler = (-direction).to_track_quat("-Z", "Y").to_euler()
    cam.data.lens = cam_spec["lens"]
    cam.data.clip_end = 300
    scene.camera = cam
    scene.render.filepath = spec["out"]
    bpy.ops.render.render(write_still=True)


# ---------------------------------------------------------------- outside Blender: specs, renders, layouts

def cs():
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    import contact_sheet
    return contact_sheet


def vehicle_scene(name):
    """The meshes, wheels and atlas of a built vehicle, laid out the way contact_sheet.py does."""
    c = cs()
    vdir = os.path.join(ROOT, "vehicles", name)
    manifest = json.load(open(os.path.join(vdir, "vehicle.json")))
    donor = manifest["donor"]
    nodes = json.load(open(os.path.join(ROOT, "extracted", donor.lower(), "nodes.json")))["nodes"]
    final, delta, _ = c.derive_layout(manifest, nodes)
    meshes = c.gather_meshes(manifest, vdir, delta)
    wheels = c.wheels_of(manifest, final)
    points = c.attach_points(manifest, nodes, final)
    atlas = os.path.join(ROOT, "extracted", "textures", f"{donor}_composite.png")
    if not os.path.exists(atlas):
        subprocess.run([sys.executable, os.path.join(ROOT, "tools", "composite_atlas.py"), donor], cwd=ROOT, check=True)
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
    return {"vdir": vdir, "manifest": manifest, "donor": donor, "meshes": meshes, "wheels": wheels,
            "points": points, "objects": objects, "atlas": atlas if os.path.exists(atlas) else None}


def road_wheels(scene, work):
    """The donor's own wheel and tyre meshes at each hub (extracted locally), scaled to the vehicle's tyre
    when its manifest sets one; rimmed cylinders when the donor's wheel meshes aren't extracted."""
    donor = scene["donor"]
    raw = os.path.join(ROOT, "extracted", donor.lower())
    tyre_obj, rim_obj = (os.path.join(raw, f"{donor}_{k}_LOD0.obj") for k in ("tyre", "wheel"))
    if not (os.path.exists(tyre_obj) and os.path.exists(rim_obj)):
        return [], scene["wheels"]
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    import spare_part, meshlib
    v = meshlib.Obj.read(tyre_obj).v
    raw_width = max(p[0] for p in v) - min(p[0] for p in v)
    raw_radius = (max(p[1] for p in v) - min(p[1] for p in v)) / 2
    tyre = dict(scene["manifest"].get("wheel", {}), **(scene["manifest"].get("tyre") or {}))
    # The prefab draws the raw meshes at x100; a manifest's tyre size, when given, overrides that.
    sx = tyre["width"] / raw_width if "width" in tyre else spare_part.PREFAB_SCALE
    sr = tyre["radius"] / raw_radius if "radius" in tyre else spare_part.PREFAB_SCALE
    objects = []
    for w in scene["wheels"]:
        left = w["mesh"][0] > 0            # OBJ +x is the truck's left; the mesh's outer face is +x
        for src, kind, role in ((tyre_obj, "tyre", "tyre"), (rim_obj, "wheel", "rim")):
            part = spare_part._transformed(src, sx, sr, 0.0, 0.0 if left else math.pi, w["mesh"], [0, 0, 0])
            path = os.path.join(work, f"{w['id']}_{kind}.obj")
            meshlib.Obj.write(part, path)
            objects.append({"file": path, "offset": [0, 0, 0], "role": role})
    return objects, []


def three_quarter(name, camera, res=(2600, 1600)):
    """A transparent three-quarter render of one vehicle, cropped to its outline (PIL RGBA)."""
    from PIL import Image
    scene = vehicle_scene(name)
    work = os.path.join(WORK, name)
    os.makedirs(work, exist_ok=True)
    wheels, cylinders = road_wheels(scene, work)
    out = os.path.join(work, f"three_quarter_{camera['elevation']:g}.png")
    spec = {"objects": scene["objects"] + wheels, "cylinders": cylinders, "atlas": scene["atlas"],
            "res": list(res), "camera": camera, "out": out}
    spec_path = os.path.join(work, "spec.json")
    json.dump(spec, open(spec_path, "w"), indent=1)
    with open(os.path.join(work, "blender.log"), "w") as log:
        subprocess.run(["blender", "-b", "--factory-startup", "--python", os.path.abspath(__file__), "--", spec_path],
                       stdout=log, stderr=subprocess.STDOUT, check=True)
    im = Image.open(out).convert("RGBA")
    return im.crop(im.split()[3].getbbox())


def contact_tiles(name, res=(1200, 900)):
    """tools/render_contact.py's tiles at a larger size: the beauty pass with the donor's real wheels (tyres in
    tyre black, rims in axle grey), the rig and collider passes with the wheel colliders; plus point pixels."""
    c = cs()
    scene = vehicle_scene(name)
    work = os.path.join(WORK, name, "contact")
    os.makedirs(work, exist_ok=True)
    wheel_objs, _ = road_wheels(scene, os.path.join(WORK, name))
    wheel_objs = [dict(o, role="spare" if o["role"] == "tyre" else "axle") for o in wheel_objs]
    colliders = [{"file": scene["meshes"][k]["file"], "offset": scene["meshes"][k]["offset"], "role": k}
                 for k in ("collider_top", "collider_base") if scene["meshes"][k]["file"]]
    base = dict(c.VIEW, res=list(res), ground_y=min(w["center"][1] - w["radius"] for w in scene["wheels"]),
                atlas=scene["atlas"], points=[{"id": p["id"], "pos": p["obj"]} for p in scene["points"]], out_dir=work)
    runs = [dict(base, passes=["beauty"], objects=scene["objects"] + wheel_objs, wheels=[] if wheel_objs else scene["wheels"]),
            dict(base, passes=["rig", "colliders"], objects=scene["objects"] + colliders, wheels=scene["wheels"])]
    for i, spec in enumerate(runs):
        spec_path = os.path.join(work, f"spec{i}.json")
        json.dump(spec, open(spec_path, "w"), indent=1)
        with open(os.path.join(work, f"blender{i}.log"), "w") as log:
            subprocess.run(["blender", "-b", "--factory-startup", "--python", os.path.join(ROOT, "tools", "render_contact.py"),
                            "--", spec_path], stdout=log, stderr=subprocess.STDOUT, check=True)
    return work, json.load(open(os.path.join(work, "projections.json")))["projections"], scene["points"]


def font(size, bold=False):
    from PIL import ImageFont
    try:
        return ImageFont.truetype(FONT_BOLD if bold else FONT, size)
    except OSError:
        return ImageFont.load_default(size=size)


def backdrop(size):
    from PIL import Image
    w, h = size
    top, bottom = BACKGROUND
    im = Image.new("RGB", size)
    px = im.load()
    for y in range(h):
        t = y / max(1, h - 1)
        col = tuple(round(a + (b - a) * t) for a, b in zip(top, bottom))
        for x in range(w):
            px[x, y] = col
    return im.convert("RGBA")


def place(canvas, car, box, shadow=True):
    """Scale `car` (RGBA, cropped) to fit `box` (x0, y0, x1, y1), centre it, with a soft contact shadow."""
    from PIL import Image, ImageDraw, ImageFilter
    x0, y0, x1, y1 = box
    scale = min((x1 - x0) / car.width, (y1 - y0) / car.height)
    car = car.resize((round(car.width * scale), round(car.height * scale)), Image.LANCZOS)
    left = x0 + ((x1 - x0) - car.width) // 2
    top = y0 + ((y1 - y0) - car.height) // 2
    if shadow:
        layer = Image.new("L", canvas.size, 0)
        ImageDraw.Draw(layer).ellipse([left + car.width * 0.08, top + car.height * 0.86,
                                       left + car.width * 0.94, top + car.height * 1.0], fill=125)
        layer = layer.filter(ImageFilter.GaussianBlur(max(6, car.height // 30)))
        canvas.paste(Image.new("RGBA", canvas.size, (120, 124, 116, 255)), (0, 0), layer)
    canvas.alpha_composite(car, (left, top))
    return canvas


def save(im, name):
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, name)
    im.convert("RGB").save(path, "JPEG", quality=90, optimize=True, progressive=True)
    kb = os.path.getsize(path) // 1024
    print(f"{os.path.relpath(path, ROOT)}: {im.width}x{im.height}, {kb} KB")
    if kb > 2000:
        raise SystemExit(f"{name} is over 2 MB")


def label(canvas, title, subtitle=None):
    from PIL import ImageDraw
    d = ImageDraw.Draw(canvas)
    d.text((72, canvas.height - 112), title, fill=INK, font=font(46, bold=True))
    if subtitle:
        d.text((74, canvas.height - 56), subtitle, fill=MUTED, font=font(24))


def gallery_truck(name, subtitle, camera=THREE_QUARTER):
    car = three_quarter(name, camera)
    canvas = place(backdrop((1920, 1080)), car, (190, 90, 1730, 880))
    label(canvas, NAMES[name], subtitle)
    save(canvas, f"{name}-1920x1080.jpg")


def banner():
    from PIL import ImageDraw
    canvas = backdrop((1300, 372))
    cars = [three_quarter(n, THREE_QUARTER) for n in ["glyptodon", "megaloceros", "megatherium", "mastodon"]]
    # One scale for all four, so their sizes compare; the row sits inside a safe area clear of the edges.
    height = 190
    scaled = [c.resize((round(c.width * height / c.height), height)) for c in cars]
    gap = 18
    row = sum(c.width for c in scaled) + gap * (len(scaled) - 1)
    if row > 1080:
        f = 1080 / row
        scaled = [c.resize((round(c.width * f), round(c.height * f))) for c in scaled]
        row = sum(c.width for c in scaled) + gap * (len(scaled) - 1)
    x = (1300 - row) // 2
    for c in scaled:
        place(canvas, c, (x, 150, x + c.width, 150 + c.height))
        x += c.width + gap
    d = ImageDraw.Draw(canvas)
    title = "Die Kollektion Werkstatt"
    f = font(54, bold=True)
    w = d.textlength(title, font=f)
    d.text(((1300 - w) / 2, 46), title, fill=INK, font=f)
    sub = "A vehicle mod system for Over the Hill"
    fs = font(22)
    d.text(((1300 - d.textlength(sub, font=fs)) / 2, 112), sub, fill=MUTED, font=fs)
    save(canvas, "banner-1300x372.jpg")


def how_its_built(name="megaloceros"):
    from PIL import Image, ImageDraw
    work, proj, points = contact_tiles(name)
    c = cs()
    beauty = Image.open(os.path.join(work, "beauty_front_left.png")).convert("RGBA")
    rig = Image.alpha_composite(Image.open(os.path.join(work, "rig_front_left.png")).convert("RGBA"),
                                Image.open(os.path.join(work, "colliders_front_left.png")).convert("RGBA"))
    d = ImageDraw.Draw(rig)
    taken = []
    for p in points:
        if p["id"] not in proj["front_left"]:
            continue
        x, y = proj["front_left"][p["id"]]
        colour = c.CATEGORY[p["category"]][0]
        if p["category"] == "slot":
            d.rectangle([x - 8, y - 8, x + 8, y + 8], outline=colour, width=3)
        else:
            d.ellipse([x - 6, y - 6, x + 6, y + 6], fill=colour, outline="white", width=2)
        box = d.textbbox((x + 10, y - 11), p["id"], font=font(18, bold=True))
        if any(not (box[2] < b[0] or box[0] > b[2] or box[3] < b[1] or box[1] > b[3]) for b in taken):
            continue
        taken.append(box)
        d.rectangle([box[0] - 2, box[1] - 1, box[2] + 2, box[3] + 1], fill=(255, 255, 255, 230))
        d.text((x + 10, y - 11), p["id"], fill=colour, font=font(18, bold=True))
    canvas = backdrop((1920, 1080))
    tile_w, tile_h = 880, 660
    for i, (tile, caption) in enumerate(((beauty, "The truck"), (rig, "Its rig: colliders, wheel colliders and attach points"))):
        x = 60 + i * (tile_w + 40)
        canvas.alpha_composite(tile.resize((tile_w, tile_h), Image.LANCZOS), (x, 240))
        ImageDraw.Draw(canvas).rectangle([x, 240, x + tile_w - 1, 240 + tile_h - 1], outline=(190, 194, 186), width=2)
        ImageDraw.Draw(canvas).text((x, 916), caption, fill=MUTED, font=font(26))
    ImageDraw.Draw(canvas).text((60, 120), "How it's built", fill=INK, font=font(52, bold=True))
    ImageDraw.Draw(canvas).text((62, 186), f"{NAMES[name]} from its contact sheet: every vehicle's GitHub page shows both views and the checks",
                                fill=MUTED, font=font(24))
    save(canvas, "how-its-built-1920x1080.jpg")


def showcase(name="megaloceros"):
    from PIL import Image, ImageDraw
    work, _proj, _points = contact_tiles(name)
    canvas = backdrop((1920, 1080))
    tw, th = 608, 456
    x0, y0 = (1920 - 2 * tw - 20) // 2, 44
    corners = ["front_left", "front_right", "rear_left", "rear_right"]
    for i, corner in enumerate(corners):
        tile = Image.open(os.path.join(work, f"beauty_{corner}.png")).convert("RGBA").resize((tw, th), Image.LANCZOS)
        x, y = x0 + (i % 2) * (tw + 20), y0 + (i // 2) * (th + 20)
        canvas.alpha_composite(tile, (x, y))
        ImageDraw.Draw(canvas).rectangle([x, y, x + tw - 1, y + th - 1], outline=(190, 194, 186), width=2)
        ImageDraw.Draw(canvas).text((x + 14, y + 10), corner.replace("_", " "), fill=MUTED, font=font(20))
    d = ImageDraw.Draw(canvas)
    caption = f"The contact sheet: {NAMES[name]} from its four corners. Every vehicle gets one, rendered the same way."
    d.text(((1920 - d.textlength(caption, font=font(24))) / 2, y0 + 2 * th + 20 + 30), caption, fill=INK, font=font(24))
    save(canvas, "contact-sheet-1920x1080.jpg")


JOBS = {
    "banner": banner,
    "megaloceros": lambda: gallery_truck("megaloceros", "The square cab as a crew cab, on a long wheelbase"),
    "glyptodon": lambda: gallery_truck("glyptodon", "The square-cab two-door with a drop-side bed"),
    "mastodon": lambda: gallery_truck("mastodon", "A round-cab two-door on a stretched chassis"),
    "megatherium": lambda: gallery_truck("megatherium", "The round-cab crew cab"),
    "dingding": lambda: gallery_truck("dingding", "The canary: a golf bag strapped to a stock car's roof", FROM_ABOVE),
    "how-its-built": how_its_built,
    "contact-sheet": showcase,
}


def main():
    if IN_BLENDER:
        render_in_blender(json.load(open(sys.argv[sys.argv.index("--") + 1])))
        return
    only = sys.argv[sys.argv.index("--only") + 1:] if "--only" in sys.argv else list(JOBS)
    for name in only:
        JOBS[name]()


if __name__ == "__main__":
    main()
