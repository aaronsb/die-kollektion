"""Write a vehicle's contact sheet: renders, attach points, mesh gates and facts, for people and agents.

Usage: python3 tools/contact_sheet.py vehicles/<name> [--no-holes] [--no-render]
       python3 tools/contact_sheet.py --diff <a/contact.json> <b/contact.json> [--out <file.md>]
       python3 tools/contact_sheet.py --changes <old.json|-> <new.json> [--out <file.md>]

Part of Die Kollektion Werkstatt (prototype of `kollektion contact`). Data first: it writes
vehicles/<name>/contact/contact.json, then renders vehicles/<name>/README.md from it, so GitHub
shows the sheet when the vehicle's folder is opened, with the images beside the JSON in contact/:
- iso.png: four isometric corners at LOD0 (tools/render_contact.py; fixed target, scale and angles
  for every vehicle, so sheets compare tile for tile);
- rig.png: the same corners in X-ray, connected pieces in pale colours, colliders, wheel colliders
  and every attach point marked and labelled (ids in the README's table);
- gaps.png: tools/check_holes.py on LOD0, culled faces red, enclosed gaps circled and numbered.
Analysis: check_holes on each body LOD, check_slivers on every mesh the vehicle uses, triangle
counts, and an attach-point check. Facts: kind, base, dimensions, chassis and suspension, and the
listing's family and variant (the real-vehicle data stays in the catalogue, not here).

Attach points come from the donor's node facts (extracted/<donor>/nodes.json, written by
tools/export_node_facts.py from the player's own install) moved the way the plugin reshapes the
prefab at spawn (DerivedVehicles.Reshape: everything behind the body cut moves back by the added
wheelbase, the centre of mass scales with it, wheels move out to the track, then the manifest's
transforms and spare). Points are Unity car-root space (x right); meshes are OBJ space (x left).
The sheet holds pictures and numbers only; marks and specs it needs go to the vehicle's
gitignored build/.
"""
import argparse, json, math, os, subprocess, sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy.spatial import ConvexHull, cKDTree

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import meshlib  # noqa: E402
import check_holes  # noqa: E402
import check_slivers  # noqa: E402

CORNERS = ["front_left", "front_right", "rear_left", "rear_right"]
TILE = (560, 420)
VIEW = {"elevation": 35.264, "ortho_scale": 7.4, "target": [0.0, 1.0, -0.6]}   # OBJ space, every vehicle
HOLE_ARGS = {"pixel": 0.005, "close": 0.02, "min_area": 2.0, "fail_culled": 25.0, "fail_gap": 20.0}
CATEGORY = {   # colour, float tolerance (m; None = not checked for floating)
    "hub": ((20, 150, 40), None), "com": ((200, 20, 20), None), "winch": ((140, 60, 200), 0.15),
    "water": ((20, 110, 220), None), "light": ((230, 160, 0), 0.10), "exhaust": ((90, 90, 90), 0.15),
    "spare": ((0, 0, 0), 0.15), "slot": ((210, 40, 140), 0.30), "gap": ((230, 0, 230), None)}
SLOT_IDS = {"Front": "FS", "Rear": "RS", "Front_Bumper": "FB", "Rear_Bumper": "RB", "Roof": "RF", "Roof_Bar": "RL",
            "Bed": "BD", "Fender": "FN", "Side": "SD", "Side_Step": "ST", "Antenna": "AN", "Rollcage": "RC",
            "Snorkel": "SN", "Winch": "WN"}


def obj_space(p):
    return [-p[0], p[1], p[2]]


def tris_of(path):
    obj = meshlib.Obj.read(path)
    return obj, sum(len(f) - 2 for f in obj.faces)


# ---------------------------------------------------------------- layout and points

def derive_layout(manifest, nodes):
    """Final Unity root-space position of every donor node after the plugin's reshape."""
    pos = {n["path"]: np.array(n["position"], float) for n in nodes}
    children = {}
    for path in pos:
        parent = path.rsplit("/", 1)[0] if "/" in path else ""
        children.setdefault(parent, []).append(path)
    delta = {p: np.zeros(3) for p in pos}

    def move(path, d):
        for p in pos:
            if p == path or p.startswith(path + "/"):
                delta[p] = delta[p] + d

    def z(path):
        return pos[path][2] + delta[path][2]

    front, rear = pos["Axles/WheelMeshes/FL"][2], pos["Axles/WheelMeshes/RL"][2]
    donor_wb = front - rear
    wb = manifest.get("wheelbase", donor_wb)
    shift = -(wb - donor_wb)
    cuts = manifest.get("bodyCut") or []
    cut = max(step[1] for step in cuts) if cuts else -math.inf

    def sweep(parent):
        for child in children.get(parent, []):
            if z(child) < cut:
                move(child, np.array([0, 0, shift]))
            else:
                sweep(child)
    com_target = rear + shift + (pos["CoM"][2] - rear) * (wb / donor_wb)
    sweep("")
    delta["CoM"][2] += com_target - z("CoM")
    half_track = manifest.get("track", 2 * abs(pos["Axles/WheelMeshes/FR"][0])) / 2
    widen = half_track - abs(pos["Axles/WheelMeshes/FR"][0] + delta["Axles/WheelMeshes/FR"][0])
    for corner in ("FL", "FR", "RL", "RR"):
        d = np.array([-widen if corner[1] == "L" else widen, 0, 0])
        for path in (f"Axles/WheelColliders/Wheel{corner}", f"Axles/WheelMeshes/{corner}",
                     f"Effects/TerrainParticles/{corner}Wheel", f"Audio/{corner}Wheel"):
            if path in pos:
                move(path, d)
    for path, placement in (manifest.get("transforms") or {}).items():
        if path in pos and placement.get("position"):
            move(path, np.array(placement["position"], float) - (pos[path] + delta[path]))
    final = {p: pos[p] + delta[p] for p in pos}
    return final, delta, {"donorWheelbase": donor_wb, "shift": shift, "transformCut": cut if cuts else None}


def attach_points(manifest, nodes, final):
    donor = manifest["donor"]
    points = []

    def add(pid, name, category, p):
        points.append({"id": pid, "name": name, "category": category,
                       "unity": [round(float(c), 4) for c in p], "obj": [round(float(c), 4) for c in obj_space(p)]})
    for i, c in enumerate(("FL", "FR", "RL", "RR")):
        add(f"H{c}", f"Axles/WheelColliders/Wheel{c}", "hub", final[f"Axles/WheelColliders/Wheel{c}"])
    add("COM", "CoM", "com", final["CoM"])
    for wid, w in (("WF", "Front"), ("WB", "Rear"), ("WL", "Left"), ("WR", "Right")):
        add(wid, f"Winch/WinchAttachPoints/{w}", "winch", final[f"Winch/WinchAttachPoints/{w}"])
    water = [p for p in final if p.startswith("WaterDetector/")]
    for i, p in enumerate(sorted(water), 1):
        add(f"D{i}", p, "water", final[p])
    lights = [p for p in final if p.startswith("Lights/") and p.count("/") == 1 and p != "Lights/FakeBounceLight"]
    for i, p in enumerate(sorted(lights), 1):
        add(f"L{i}", p, "light", final[p])
    add("EX", "Effects/VehicleParticles/ExhaustParticlesManager", "exhaust", final["Effects/VehicleParticles/ExhaustParticlesManager"])
    spare = manifest.get("spare")
    if spare and spare.get("position"):
        add("SP", f"spare ({spare.get('source', '').rsplit('/', 1)[-1]})", "spare", np.array(spare["position"], float))
    upgrades = {}
    for n in nodes:
        if any(c["type"] == "MB:VehicleUpgradeObject" for c in n["components"]):
            parts = n["path"].split("/")
            if len(parts) >= 4 and parts[1] == f"{donor}_CosmeticParts":
                upgrades.setdefault(parts[3], []).append(final[n["path"]])
    for slot, members in sorted(upgrades.items()):
        add(SLOT_IDS.get(slot, slot[:2].upper()), f"upgrade slot {slot} ({len(members)} options; median pivot)",
            "slot", np.median(np.array(members), axis=0))
    return points


# ---------------------------------------------------------------- meshes

def mesh_file(manifest, vdir, node_path):
    entry = (manifest.get("meshes") or {}).get(node_path)
    if entry is not None and vdir:
        name = entry if isinstance(entry, str) else entry["file"]
        return os.path.join(vdir, "build", name), "built"
    path = os.path.join(ROOT, "extracted", manifest["donor"].lower(), node_path.replace("/", "__") + ".obj")
    return (path, "stock") if os.path.exists(path) else (None, "missing")


def gather_meshes(manifest, vdir, delta):
    donor = manifest["donor"]
    found = {}
    for lod in range(4):
        found[f"body_LOD{lod}"] = (f"Parts/{donor}/{donor}_body_LOD{lod}",) + mesh_file(manifest, vdir, f"Parts/{donor}/{donor}_body_LOD{lod}")
    for side in ("Front", "Rear"):
        path = f"Axles/SuspensionRigid{side}/SuspensionRigidMesh_LOD0"
        found[f"axle_{side.lower()}_LOD0"] = (path,) + mesh_file(manifest, vdir, path)
    for name in ("Top", "Base"):
        found[f"collider_{name.lower()}"] = (f"Collider/{name}",) + mesh_file(manifest, vdir, f"Collider/{name}")
    out = {}
    for key, (node, path, origin) in found.items():
        d = delta.get(node, np.zeros(3))
        out[key] = {"node": node, "file": path, "origin": origin, "offset": obj_space(d)}
    return out


def load_vertices(entry):
    obj = meshlib.Obj.read(entry["file"])
    v = np.array(obj.v, float) + np.array(entry["offset"])
    tri = []
    for f in obj.faces:
        idx = [c[0] for c in f]
        tri += [(idx[0], idx[k], idx[k + 1]) for k in range(1, len(idx) - 1)]
    return v, np.array(tri, int)


def surface_samples(v, tris):
    a, b, c = v[tris[:, 0]], v[tris[:, 1]], v[tris[:, 2]]
    return np.vstack([v, (a + b + c) / 3, (a + b) / 2, (b + c) / 2, (c + a) / 2])


# ---------------------------------------------------------------- analysis

def run_holes(path, marks=None):
    obj, v, tris, owner = check_holes.load(path)
    top = v[tris].reshape(-1, 3)[:, 1].max()
    n_open, nonmanifold, loops = check_holes.topology(v, tris, 0.05)
    culled_faces, gaps = check_holes.visibility(v, tris, HOLE_ARGS["pixel"], HOLE_ARGS["close"], HOLE_ARGS["min_area"])
    groups = check_holes.face_clusters(v, tris, owner, culled_faces)
    if marks:
        check_holes.write_marks(marks, v, tris, set(culled_faces), gaps)
    culled = [{"area_cm2": round(float(g["area"]), 1), "lo": [round(float(c), 3) for c in g["lo"]],
               "hi": [round(float(c), 3) for c in g["hi"]], "region": check_holes.region(g["lo"], g["hi"], top),
               "triangles": len(g["faces"])} for g in sorted(groups, key=lambda g: -g["area"])]
    gap_list = [{"area_cm2": round(float(a), 1), "at": [round(float(c), 3) for c in p],
                 "region": check_holes.region(p, p, top), "views": len(views)} for a, p, views in sorted(gaps, key=lambda g: -g[0])]
    failing = sum(c["area_cm2"] >= HOLE_ARGS["fail_culled"] for c in culled) + sum(g["area_cm2"] >= HOLE_ARGS["fail_gap"] for g in gap_list)
    return {"file": os.path.relpath(path, ROOT), "triangles": int(len(tris)), "open_edges": int(n_open),
            "open_loops": len(loops), "nonmanifold_edges": int(nonmanifold), "culled": culled, "gaps": gap_list,
            "fail": failing > 0, "failing_findings": int(failing)}


def hull_distance(points, hulls):
    """Distance of each point outside the nearest convex hull (0 inside one). The game's mesh
    colliders on a rigidbody are convex, so the hull is the shape physics uses."""
    best = np.full(len(points), np.inf)
    for h in hulls:
        d = (points @ h.equations[:, :3].T + h.equations[:, 3]).max(axis=1)
        best = np.minimum(best, np.maximum(d, 0))
    return best


def measure(points, meshes, wheels):
    """Raw attach-point measurements for one layout: tyre clearance per wheel, the colliders'
    coverage of the LOD0 body, and each point's distance to the nearest body or axle surface."""
    body_v, body_t = load_vertices(meshes["body_LOD0"])
    surfaces = [surface_samples(body_v, body_t)]
    for key in ("axle_front_LOD0", "axle_rear_LOD0"):
        if meshes[key]["file"]:
            surfaces.append(surface_samples(*load_vertices(meshes[key])))
    tree = cKDTree(np.vstack(surfaces))
    colliders = [load_vertices(meshes[k])[0] for k in ("collider_top", "collider_base") if meshes[k]["file"]]
    hulls = [ConvexHull(c) for c in colliders if len(c) >= 4]
    out = {"wheels": {}, "points": {}, "hulls": len(hulls), "collider_bottom": float(min(c[:, 1].min() for c in colliders)) if colliders else None}
    for w in wheels:
        hub = np.array(w["center"])
        # The middle 80% of the tread: tyre shoulders round off, so the band's edges aren't rubber.
        above = (np.abs(body_v[:, 0] - hub[0]) <= 0.4 * w["width"]) & (body_v[:, 1] > hub[1])
        clearance = float((np.hypot(body_v[above, 1] - hub[1], body_v[above, 2] - hub[2]) - w["radius"]).min()) if above.any() else None
        out["wheels"][w["id"]] = {"clearance": clearance, "mesh_offset": float(np.linalg.norm(np.array(w["mesh"]) - hub))}
    d = hull_distance(body_v, hulls) if hulls else np.full(len(body_v), np.inf)
    out["outside_10cm"] = float((d > 0.10).mean())
    out["outside_worst"] = float(d.max())
    for p in points:
        out["points"][p["id"]] = float(tree.query(np.array(p["obj"]))[0])
    return out


def attach_checks(points, mine, stock, wheels):
    """Pass/fail against fixed tolerances where the game's own car meets them, and against the stock
    donor where it doesn't: the stock Mammoth's centre of mass sits below its colliders, its body
    reaches past them, and an upgrade slot's pivot is not on the body, none of which is a defect."""
    checks = []
    for w in wheels:
        m = mine["wheels"][w["id"]]
        c = m["clearance"]
        checks.append({"id": w["id"], "check": "wheel mesh on its collider; tyre clear of the body above the hub (prefab pose)",
                       "value": f"mesh offset {m['mesh_offset'] * 100:.1f} cm, clearance {'n/a' if c is None else f'{c * 100:+.1f} cm'}",
                       "pass": m["mesh_offset"] < 0.01 and (c is None or c > -0.01)})
    com = next(p for p in points if p["id"] == "COM")["obj"]
    hubs = {w["id"]: w["center"] for w in wheels}
    ground = min(w["center"][1] - w["radius"] for w in wheels)
    inside = (abs(com[0]) < abs(hubs["HFL"][0]) and hubs["HRL"][2] < com[2] < hubs["HFL"][2] and ground < com[1])
    below = mine["collider_bottom"]
    checks.append({"id": "COM", "check": "centre of mass between the wheels (inside track and wheelbase, above the ground)",
                   "value": f"x {com[0]:+.2f}, y {com[1]:.2f}, z {com[2]:+.2f} m; {('%+.2f m from the collider bottom' % (com[1] - below)) if below is not None else ''}",
                   "pass": bool(inside)})
    ref = f" (stock {stock['outside_10cm'] * 100:.1f}%, worst {stock['outside_worst'] * 100:.0f} cm)" if stock else ""
    ok = stock is None or (mine["outside_10cm"] <= stock["outside_10cm"] + 0.05 and mine["outside_worst"] <= stock["outside_worst"] + 0.10)
    checks.append({"id": "COL", "check": "colliders (convex hulls) cover the LOD0 body no worse than the stock donor's: share of vertices over 10 cm outside within 5 points, worst within 10 cm",
                   "value": f"{mine['outside_10cm'] * 100:.1f}% over 10 cm outside, worst {mine['outside_worst'] * 100:.0f} cm" + ref,
                   "pass": bool(ok)})
    tyre_width = wheels[0]["width"]
    for p in points:
        tol = CATEGORY[p["category"]][1]
        if tol is None:
            continue
        if p["category"] == "spare":
            tol = tyre_width / 2 + 0.05   # the point is the wheel's centre, half a tyre from its carrier
        d = mine["points"][p["id"]]
        p["surface_distance"] = round(d, 3)
        if p["category"] == "slot":
            s = stock["points"].get(p["id"]) if stock else None
            checks.append({"id": p["id"], "check": "upgrade-slot pivot no further from the body than on the stock donor (+15 cm)",
                           "value": f"{d * 100:.1f} cm" + (f" (stock {s * 100:.1f} cm)" if s is not None else ""),
                           "pass": s is None or d <= s + 0.15})
        else:
            checks.append({"id": p["id"], "check": f"{p['category']} point within {tol * 100:.0f} cm of a body or axle surface",
                           "value": f"{d * 100:.1f} cm", "pass": d <= tol})
    return checks


def stock_reference(manifest, nodes):
    """The same measurements on the unmodified donor, from the player's extracted copy."""
    donor = manifest["donor"]
    stock_manifest = {"donor": donor, "meshes": {}}
    final = {n["path"]: np.array(n["position"], float) for n in nodes}
    meshes = gather_meshes(stock_manifest, None, {})
    if not all(meshes[k]["file"] for k in ("body_LOD0", "collider_top", "collider_base")):
        return None
    points = attach_points(stock_manifest, nodes, final)
    wheels = wheels_of(stock_manifest, final)
    return measure(points, meshes, wheels)


def wheels_of(manifest, final):
    tyre = dict(manifest.get("wheel", {}), **(manifest.get("tyre") or {}))
    wheels = []
    for c in ("FL", "FR", "RL", "RR"):
        wheels.append({"id": f"H{c}", "center": obj_space(final[f"Axles/WheelColliders/Wheel{c}"]),
                       "mesh": obj_space(final[f"Axles/WheelMeshes/{c}"]),
                       "radius": tyre.get("radius", 0.52), "width": tyre.get("width", 0.36)})
    return wheels


def slivers_of(files):
    out = []
    for f in files:
        found = check_slivers.slivers(meshlib.Obj.read(f), 1.5, 0.01)
        out.append({"file": os.path.relpath(f, ROOT), "slivers": len(found)})
    return out


# ---------------------------------------------------------------- rendering

def font(size):
    return ImageFont.load_default(size=size)


def render(vdir, spec, points, gaps):
    work = os.path.join(vdir, "build", "contact")
    os.makedirs(work, exist_ok=True)
    spec["out_dir"] = work
    spec_path = os.path.join(work, "spec.json")
    json.dump(spec, open(spec_path, "w"), indent=1)
    log = os.path.join(work, "blender.log")
    with open(log, "w") as f:
        subprocess.run(["blender", "-b", "--factory-startup", "--python", os.path.join(ROOT, "tools/render_contact.py"), "--", spec_path],
                       stdout=f, stderr=subprocess.STDOUT, check=True)
    proj = json.load(open(os.path.join(work, "projections.json")))
    out_dir = os.path.join(vdir, "contact")
    os.makedirs(out_dir, exist_ok=True)
    titles = {c: c.replace("_", " ") for c in CORNERS}

    def row(pass_name, overlay=None, layer=None):
        w, h = TILE
        sheet = Image.new("RGB", (w * 4, h), "white")
        for i, corner in enumerate(CORNERS):
            tile = Image.open(os.path.join(work, f"{pass_name}_{corner}.png")).convert("RGBA")
            if layer:
                tile = Image.alpha_composite(tile, Image.open(os.path.join(work, f"{layer}_{corner}.png")).convert("RGBA"))
            tile = tile.convert("RGB")
            if overlay:
                overlay(tile, proj["projections"][corner])
            ImageDraw.Draw(tile).text((10, 8), titles[corner], fill=(30, 30, 30), font=font(15))
            sheet.paste(tile, (i * w, 0))
            if i:
                ImageDraw.Draw(sheet).line([(i * w, 0), (i * w, h)], fill=(180, 180, 180))
        return sheet

    def mark_points(tile, pts):
        d = ImageDraw.Draw(tile)
        taken = []
        for p in points:
            if p["id"] not in pts:
                continue
            x, y = pts[p["id"]]
            colour = CATEGORY[p["category"]][0]
            if p["category"] == "slot":
                d.rectangle([x - 5, y - 5, x + 5, y + 5], outline=colour, width=2)
            else:
                d.ellipse([x - 4, y - 4, x + 4, y + 4], fill=colour, outline="white")
            box = d.textbbox((x + 6, y - 7), p["id"], font=font(11))
            if any(not (box[2] < b[0] or box[0] > b[2] or box[3] < b[1] or box[1] > b[3]) for b in taken):
                continue
            taken.append(box)
            d.rectangle(box, fill=(255, 255, 255))
            d.text((x + 6, y - 7), p["id"], fill=colour, font=font(11))

    def mark_gaps(tile, pts):
        d = ImageDraw.Draw(tile)
        for g in gaps:
            if g["id"] in pts:
                x, y = pts[g["id"]]
                r = 7 + min(10, g["area_cm2"] ** 0.5)
                d.ellipse([x - r, y - r, x + r, y + r], outline=(230, 0, 230), width=2)
                d.text((x + r + 2, y - 7), g["id"], fill=(160, 0, 160), font=font(11))

    images = {"iso": row("beauty"), "rig": row("rig", mark_points, layer="colliders")}
    if "gaps" in spec["passes"]:
        images["gaps"] = row("gaps", mark_gaps)
    for name, im in images.items():
        im.quantize(colors=256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE).save(
            os.path.join(out_dir, f"{name}.png"), optimize=True)
    return {name: f"contact/{name}.png" for name in images}, proj["info"]


# ---------------------------------------------------------------- the sheet

def build_sheet(vdir, args):
    vdir = os.path.abspath(vdir)
    manifest = json.load(open(os.path.join(vdir, "vehicle.json")))
    donor = manifest["donor"]
    nodes_path = os.path.join(ROOT, "extracted", donor.lower(), "nodes.json")
    if not os.path.exists(nodes_path):
        raise SystemExit(f"{nodes_path} missing: run tools/export_game_data.sh (it calls tools/export_node_facts.py)")
    needed = [os.path.join(vdir, "build", e if isinstance(e, str) else e["file"]) for e in (manifest.get("meshes") or {}).values()]
    if not all(os.path.exists(p) for p in needed):
        subprocess.run([sys.executable, os.path.join(ROOT, "tools/build_vehicle.py"), os.path.join(vdir, "vehicle.json")], check=True)
    nodes = json.load(open(nodes_path))["nodes"]
    final, delta, layout = derive_layout(manifest, nodes)
    points = attach_points(manifest, nodes, final)
    meshes = gather_meshes(manifest, vdir, delta)
    wheels = wheels_of(manifest, final)
    ground_y = min(w["center"][1] - w["radius"] for w in wheels)

    analysis = {"thresholds": dict(HOLE_ARGS, sliver_length_m=1.5, sliver_area_m2=0.01)}
    marks = os.path.join(vdir, "build", "contact", "marks_LOD0.obj")
    os.makedirs(os.path.dirname(marks), exist_ok=True)
    if args.no_holes:
        analysis["holes"] = []
    else:
        analysis["holes"] = [run_holes(meshes[f"body_LOD{lod}"]["file"], marks if lod == 0 else None) for lod in range(4)]
    used = sorted({e["file"] for e in meshes.values() if e["file"]} | {p for p in needed if os.path.exists(p)})
    analysis["slivers"] = slivers_of(used)
    analysis["triangles"] = {key: tris_of(e["file"])[1] for key, e in meshes.items() if e["file"]}
    mine = measure(points, meshes, wheels)
    stock = stock_reference(manifest, nodes)
    analysis["attach_points"] = attach_checks(points, mine, stock, wheels)
    check_info = {"collider_hulls": mine["hulls"], "stock_reference": stock is not None}

    body_v, _ = load_vertices(meshes["body_LOD0"])
    axle_v = np.vstack([load_vertices(meshes[k])[0] for k in ("axle_front_LOD0", "axle_rear_LOD0") if meshes[k]["file"]])
    solid = np.vstack([body_v, axle_v])
    wheel_x = [w["center"][0] + s * w["width"] / 2 for w in wheels for s in (-1, 1)]
    wheel_z = [w["center"][2] + s * w["radius"] for w in wheels for s in (-1, 1)]
    hubs = {w["id"]: w["center"] for w in wheels}
    facts = {
        "codename": manifest["codename"], "displayName": manifest.get("displayName", manifest["codename"]),
        "kind": manifest.get("kind"), "base": manifest.get("base"), "donor": donor, "itemId": manifest.get("itemId"),
        "listing": {k: v for k, v in (manifest.get("listing") or {}).items() if k != "real"},
        "dimensions_m": {
            "length": round(max(solid[:, 2].max(), max(wheel_z)) - min(solid[:, 2].min(), min(wheel_z)), 3),
            "width": round(max(solid[:, 0].max(), max(wheel_x)) - min(solid[:, 0].min(), min(wheel_x)), 3),
            "height": round(float(solid[:, 1].max()) - ground_y, 3),
            "wheelbase": round(hubs["HFL"][2] - hubs["HRL"][2], 3),
            "track": round(abs(hubs["HFL"][0] - hubs["HFR"][0]), 3),
            "ground_clearance_prefab_pose": round(float(solid[:, 1].min()) - ground_y, 3)},
        "chassis": {k: manifest.get(k) for k in ("wheelbase", "track", "maxSteerAngle", "wheel", "tyre", "suspension", "bodyCut") if k in manifest},
        "layout": {k: (round(v, 4) if isinstance(v, float) else v) for k, v in layout.items()},
        "meshes": {k: {"node": e["node"], "origin": e["origin"], "offset": [round(c, 4) for c in e["offset"]],
                       "file": os.path.relpath(e["file"], ROOT) if e["file"] else None} for k, e in meshes.items()},
    }
    gaps = []
    if analysis["holes"]:
        for i, g in enumerate(analysis["holes"][0]["gaps"], 1):
            gaps.append({"id": f"G{i}", "area_cm2": g["area_cm2"], "pos": g["at"]})
    sheet = {"generator": "Die Kollektion Werkstatt, tools/contact_sheet.py (prototype of `kollektion contact`)",
             "view": dict(VIEW, tile=list(TILE), corners=CORNERS), "facts": facts, "points": points,
             "colliders": check_info, "analysis": analysis, "images": {}}
    if not args.no_render:
        objects = [{"file": meshes["body_LOD0"]["file"], "offset": meshes["body_LOD0"]["offset"], "role": "body"}]
        for k in ("axle_front_LOD0", "axle_rear_LOD0"):
            if meshes[k]["file"]:
                objects.append({"file": meshes[k]["file"], "offset": meshes[k]["offset"], "role": "axle"})
        for k in ("collider_top", "collider_base"):
            if meshes[k]["file"]:
                objects.append({"file": meshes[k]["file"], "offset": meshes[k]["offset"], "role": k})
        preview = (manifest.get("spare") or {}).get("preview")
        if preview and os.path.exists(os.path.join(vdir, preview)):
            objects.append({"file": os.path.join(vdir, preview), "offset": [0, 0, 0], "role": "spare"})
        if os.path.exists(marks) and not args.no_holes:
            objects.append({"file": marks, "offset": meshes["body_LOD0"]["offset"], "role": "marks"})
        atlas = os.path.join(ROOT, "extracted", "textures", f"{donor}_composite.png")
        spec = dict(VIEW, res=list(TILE), passes=["beauty", "rig", "colliders"] + ([] if args.no_holes else ["gaps"]), objects=objects, wheels=wheels,
                    ground_y=ground_y, atlas=atlas if os.path.exists(atlas) else None,
                    points=[{"id": p["id"], "pos": p["obj"]} for p in points] + [{"id": g["id"], "pos": g["pos"]} for g in gaps])
        sheet["images"], info = render(vdir, spec, points, gaps)
        facts["pieces_lod0"] = info.get("pieces")
    os.makedirs(os.path.join(vdir, "contact"), exist_ok=True)
    with open(os.path.join(vdir, "contact", "contact.json"), "w") as f:
        json.dump(sheet, f, indent=1, ensure_ascii=False)
    with open(os.path.join(vdir, "README.md"), "w") as f:
        f.write(markdown(sheet, gaps))
    return sheet


def yes(ok):
    return "pass" if ok else "**FAIL**"


def markdown(sheet, gaps):
    f, a = sheet["facts"], sheet["analysis"]
    kind = f["kind"] or "unknown"
    base = (f.get("base") or {}).get("car")
    listing = f.get("listing") or {}
    what = {"novel": "A new vehicle with all its own parts", "based": f"A new vehicle built from the game's {base}",
            "patch": f"A patch: changes to the game's own {base}"}.get(kind, kind)
    lines = [f"# {f['displayName']}", "",
             f"**Kind:** {kind}" + (f" · **Base:** {base}" if base else "") + (f" · **Item:** {f['itemId']}" if f.get("itemId") and kind != "patch" else ""), "",
             what + (f" ({listing.get('family')} family, {listing.get('variant')})." if listing.get("family") else "."), ""]
    if kind in ("based", "patch"):
        lines += [f"The renders show geometry built from the player's own copy of the {base}. This sheet ships pictures and numbers only, no mesh data.", ""]
    lines += ["## Isometric", "", "![Isometric views](contact/iso.png)", "",
              "## Rig", "", f"Body in X-ray with each connected piece in its own colour ({f.get('pieces_lod0', '?')} pieces at LOD0); Collider/Top cyan, Collider/Base orange, wheel colliders green; attach points marked by id (table below; squares are upgrade-slot pivots).", "",
              "![Rig views](contact/rig.png)", "",
              "| Id | Point | Category | Position (Unity root, m) | Nearest surface |", "|---|---|---|---|---|"]
    for p in sheet["points"]:
        dist = f"{p['surface_distance'] * 100:.1f} cm" if "surface_distance" in p else ""
        lines.append(f"| {p['id']} | `{p['name']}` | {p['category']} | ({p['unity'][0]:+.3f}, {p['unity'][1]:+.3f}, {p['unity'][2]:+.3f}) | {dist} |")
    lines += ["", "## Analysis", "", "### Attach points", "", "| Id | Check | Result | |", "|---|---|---|---|"]
    for c in a["attach_points"]:
        lines.append(f"| {c['id']} | {c['check']} | {c['value']} | {yes(c['pass'])} |")
    lines += ["", "### Mesh gaps and culled faces", "",
              f"`tools/check_holes.py` per body LOD: a culled patch is where the nearest surface is a back face the game doesn't draw; a gap is an enclosed hole with no surface. Fails at {a['thresholds']['fail_culled']:g} cm² culled or {a['thresholds']['fail_gap']:g} cm² gap.", ""]
    if a["holes"]:
        lines += ["![Gaps and culled faces, LOD0](contact/gaps.png)", "",
                  "| LOD | Triangles | Open edges | Culled patches (largest) | Gaps (largest) | |", "|---|---|---|---|---|---|"]
        for lod, h in enumerate(a["holes"]):
            cmax = f"{len(h['culled'])} ({h['culled'][0]['area_cm2']:g} cm²)" if h["culled"] else "0"
            gmax = f"{len(h['gaps'])} ({h['gaps'][0]['area_cm2']:g} cm²)" if h["gaps"] else "0"
            lines.append(f"| {lod} | {h['triangles']} | {h['open_edges']} | {cmax} | {gmax} | {yes(not h['fail'])} |")
        if gaps:
            lines += ["", "| Gap (LOD0) | Area | At (OBJ, m) | Region |", "|---|---|---|---|"]
            for g, h in zip(gaps, a["holes"][0]["gaps"]):
                lines.append(f"| {g['id']} | {h['area_cm2']:g} cm² | ({h['at'][0]:+.3f}, {h['at'][1]:+.3f}, {h['at'][2]:+.3f}) | {h['region']} |")
        culled = a["holes"][0]["culled"][:8]
        if culled:
            lines += ["", "| Culled patch (LOD0), along z | Area | Triangles | Region |", "|---|---|---|---|"]
            for c in culled:
                lines.append(f"| {c['lo'][2]:+.2f}..{c['hi'][2]:+.2f} m | {c['area_cm2']:g} cm² | {c['triangles']} | {c['region']} |")
    else:
        lines += ["Not run for this sheet."]
    sl = [s for s in a["slivers"] if s["slivers"]]
    lines += ["", "### Slivers and triangles", "",
              f"Slivers (faces over {a['thresholds']['sliver_length_m']} m long with under {a['thresholds']['sliver_area_m2']} m² area): "
              + (", ".join(f"`{os.path.basename(s['file'])}` {s['slivers']}" for s in sl) if sl else f"none in {len(a['slivers'])} meshes") + ".", "",
              "| Mesh | Triangles | Source |", "|---|---|---|"]
    for key, n in a["triangles"].items():
        lines.append(f"| {key} | {n} | {f['meshes'][key]['origin']} |")
    d = f["dimensions_m"]
    lines += ["", "## Facts", "",
              "| Length | Width | Height | Wheelbase | Track | Ground clearance |", "|---|---|---|---|---|---|",
              f"| {d['length']:.2f} m | {d['width']:.2f} m | {d['height']:.2f} m | {d['wheelbase']:.2f} m | {d['track']:.2f} m | {d['ground_clearance_prefab_pose']:.2f} m |", "",
              "Height and ground clearance are in the prefab pose (wheels at their modelled hub height, tyres on the ground); suspension sag at rest is not modelled.", "",
              "| Chassis | Value |", "|---|---|"]
    for k, v in f["chassis"].items():
        lines.append(f"| {k} | `{json.dumps(v)}` |")
    lines += ["", f"Generated by {sheet['generator']} from [`contact/contact.json`](contact/contact.json). The real vehicle this one is modelled on is listed in the catalogue in the [main README](../../README.md).", ""]
    return "\n".join(lines)


# ---------------------------------------------------------------- diff

def diff(a_path, b_path):
    a, b = json.load(open(a_path)), json.load(open(b_path))
    rows = ["| | A | B |", "|---|---|---|"]

    def row(name, va, vb):
        if va != vb:
            rows.append(f"| {name} | {va} | {vb} |")
    fa, fb = a["facts"], b["facts"]
    row("vehicle", fa["displayName"], fb["displayName"])
    row("kind", fa["kind"], fb["kind"])
    for k in sorted(set(fa["dimensions_m"]) | set(fb["dimensions_m"])):
        row(f"{k} (m)", fa["dimensions_m"].get(k), fb["dimensions_m"].get(k))
    for k in sorted(set(fa["chassis"]) | set(fb["chassis"])):
        row(k, json.dumps(fa["chassis"].get(k)), json.dumps(fb["chassis"].get(k)))
    for k in sorted(set(a["analysis"]["triangles"]) | set(b["analysis"]["triangles"])):
        row(f"triangles {k}", a["analysis"]["triangles"].get(k), b["analysis"]["triangles"].get(k))
    for lod, (ha, hb) in enumerate(zip(a["analysis"]["holes"], b["analysis"]["holes"])):
        row(f"LOD{lod} culled patches", len(ha["culled"]), len(hb["culled"]))
        row(f"LOD{lod} gaps", len(ha["gaps"]), len(hb["gaps"]))
        row(f"LOD{lod} gate", yes(not ha["fail"]), yes(not hb["fail"]))
    ca = {c["id"] + c["check"]: c for c in a["analysis"]["attach_points"]}
    cb = {c["id"] + c["check"]: c for c in b["analysis"]["attach_points"]}
    for k in sorted(set(ca) | set(cb)):
        x, y = ca.get(k), cb.get(k)
        row(f"check {(x or y)['id']}", x and f"{x['value']} {yes(x['pass'])}", y and f"{y['value']} {yes(y['pass'])}")
    pa = {p["id"]: p for p in a["points"]}
    pb = {p["id"]: p for p in b["points"]}
    for k in sorted(set(pa) | set(pb)):
        x, y = pa.get(k), pb.get(k)
        if x and y and np.linalg.norm(np.array(x["unity"]) - np.array(y["unity"])) < 0.01:
            continue
        row(f"point {k}", x and x["unity"], y and y["unity"])
    da, db = os.path.dirname(os.path.abspath(a_path)), os.path.dirname(os.path.abspath(b_path))
    out = [f"# Contact sheet diff: {fa['displayName']} vs {fb['displayName']}", "",
           f"A: `{os.path.relpath(a_path)}`  ", f"B: `{os.path.relpath(b_path)}`", ""]
    out += rows if len(rows) > 2 else ["No differences in facts, gates or points."]
    for name in ("iso", "rig", "gaps"):
        ia, ib = os.path.join(da, f"{name}.png"), os.path.join(db, f"{name}.png")
        if os.path.exists(ia) and os.path.exists(ib):
            out += ["", f"### {name}", "", "| A | B |", "|---|---|", f"| ![A]({os.path.relpath(ia)}) | ![B]({os.path.relpath(ib)}) |"]
    return "\n".join(out) + "\n"


def changes(old, new):
    """What a change did to one vehicle, in the order a reviewer reads it: facts, points, gates, triangles.

    `old` may be None (a vehicle the change adds). Written by `make loop` as the vehicle's
    contact/CHANGES.md and gathered into the pull request's description by `make pr`."""
    name = new["facts"]["displayName"]
    if old is None:
        return f"### {name}\n\nNew vehicle: no earlier contact sheet to compare with.\n"
    out = []
    fo, fn = old["facts"], new["facts"]
    facts = []
    for group in ("dimensions_m", "chassis"):
        for k in sorted(set(fo.get(group, {})) | set(fn.get(group, {}))):
            a, b = fo.get(group, {}).get(k), fn.get(group, {}).get(k)
            if a != b:
                facts.append(f"| {k}{' (m)' if group == 'dimensions_m' else ''} | {json.dumps(a)} | {json.dumps(b)} |")
    for k in ("kind", "base", "itemId"):
        if fo.get(k) != fn.get(k):
            facts.append(f"| {k} | {json.dumps(fo.get(k))} | {json.dumps(fn.get(k))} |")
    if facts:
        out += ["**Facts**", "", "| | before | after |", "|---|---|---|"] + facts + [""]
    po, pn = {p["id"]: p for p in old["points"]}, {p["id"]: p for p in new["points"]}
    moved = []
    for k in sorted(set(po) | set(pn)):
        a, b = po.get(k), pn.get(k)
        if a and b:
            d = float(np.linalg.norm(np.array(a["unity"]) - np.array(b["unity"])))
            if d >= 0.005:
                moved.append(f"| {k} | {b['name']} | {a['unity']} | {b['unity']} | {d * 100:.1f} cm |")
        else:
            moved.append(f"| {k} | {(a or b)['name']} | {a and a['unity']} | {b and b['unity']} | {'added' if b else 'removed'} |")
    if moved:
        out += ["**Points moved** (Unity car-root metres, x right)", "",
                "| id | point | before | after | moved |", "|---|---|---|---|---|"] + moved + [""]
    gates = []
    co = {c["id"] + c["check"]: c for c in old["analysis"]["attach_points"]}
    cn = {c["id"] + c["check"]: c for c in new["analysis"]["attach_points"]}
    for k in sorted(set(co) | set(cn)):
        a, b = co.get(k), cn.get(k)
        if (a and a["pass"], a and a["value"]) != (b and b["pass"], b and b["value"]):
            gates.append(f"| {(a or b)['id']} | {a and a['value']} {yes(a['pass']) if a else ''} | {b and b['value']} {yes(b['pass']) if b else ''} |")
    for lod, (a, b) in enumerate(zip(old["analysis"]["holes"], new["analysis"]["holes"])):
        if (a["fail"], len(a["culled"]), len(a["gaps"])) != (b["fail"], len(b["culled"]), len(b["gaps"])):
            gates.append(f"| holes LOD{lod} | {len(a['culled'])} culled, {len(a['gaps'])} gaps {yes(not a['fail'])} "
                         f"| {len(b['culled'])} culled, {len(b['gaps'])} gaps {yes(not b['fail'])} |")
    if gates:
        out += ["**Checks changed**", "", "| check | before | after |", "|---|---|---|"] + gates + [""]
    to, tn = old["analysis"]["triangles"], new["analysis"]["triangles"]
    tris = [f"| {k} | {to.get(k)} | {tn.get(k)} |" for k in sorted(set(to) | set(tn)) if to.get(k) != tn.get(k)]
    if tris:
        out += ["**Triangles**", "", "| mesh | before | after |", "|---|---|---|"] + tris + [""]
    still = [c["id"] for c in new["analysis"]["attach_points"] if not c["pass"]] + \
            [f"LOD{i}" for i, h in enumerate(new["analysis"]["holes"]) if h["fail"]]
    body = "\n".join(out) if out else "No change to facts, points, checks or triangles (renders may differ by noise).\n"
    return f"### {name}\n\n{body}\n" + (f"Still failing: {', '.join(still)}.\n" if still else "All checks pass.\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("vehicle", nargs="?")
    ap.add_argument("--diff", nargs=2, metavar=("A", "B"))
    ap.add_argument("--changes", nargs=2, metavar=("OLD", "NEW"),
                    help="summarise what changed between two contact.json files (OLD may be '-' for none)")
    ap.add_argument("--out")
    ap.add_argument("--no-holes", action="store_true")
    ap.add_argument("--no-render", action="store_true")
    args = ap.parse_args()
    if args.changes:
        old = None if args.changes[0] == "-" else json.load(open(args.changes[0]))
        text = changes(old, json.load(open(args.changes[1])))
        if args.out:
            open(args.out, "w").write(text)
        print(text)
        return
    if args.diff:
        text = diff(*args.diff)
        if args.out:
            open(args.out, "w").write(text)
        print(text)
        return
    if not args.vehicle:
        ap.error("give a vehicle folder or --diff")
    sheet = build_sheet(args.vehicle, args)
    a = sheet["analysis"]
    failed = [c["id"] for c in a["attach_points"] if not c["pass"]] + [f"LOD{i}" for i, h in enumerate(a["holes"]) if h["fail"]]
    print(f"{sheet['facts']['displayName']}: README.md and contact/ written; "
          + (f"failing: {', '.join(failed)}" if failed else "all checks pass"))


if __name__ == "__main__":
    main()
