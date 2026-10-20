"""Headless test of the Werkstatt add-on: open a vehicle, nudge, turn, copy, save, reopen; the API's refusals; and
every built truck's axles, wheels and arches where the plugin puts them at spawn.

Usage: blender -b --factory-startup --python tests/blender/test_addon.py -- [<vehicle>]
Runs on a scratch copy of the checkout's vehicle folders (the builds and extracted data are linked, read-only), so
the checkout is never written. Needs `make extract` (with upgrades.json) and the vehicle built. Exits non-zero on
any failure. The panel's real draw is tested under Xvfb by tests/blender/test_panel_gui.py.
"""
import json, math, os, shutil, sys, traceback

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "blender", "addons"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy  # noqa: E402
import mathutils  # noqa: E402
import werkstatt_addon  # noqa: E402
from checkout import scratch_checkout  # noqa: E402
from werkstatt_addon import api, model, scene  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
VEHICLE = argv[0] if argv else "megaloceros"
TRUCKS = ("megaloceros", "glyptodon", "mastodon", "megatherium")
failures = []


def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        failures.append(what)


def close(a, b, tol=1e-4):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


def emulate(base, steps):
    """The plugin's Apply over a set of nodes: each step moves its node, then turns it and its subtree about the
    node's pivot. Positions in game space."""
    pos = dict(base)
    for path, offset, turn in steps:
        if path not in pos:
            continue
        for other in pos:                     # moving a node carries its subtree
            if other == path or other.startswith(path + "/"):
                pos[other] = tuple(p + o for p, o in zip(pos[other], offset))
        pivot = pos[path]
        for other in pos:
            if other.startswith(path + "/"):
                rel = tuple(a - b for a, b in zip(pos[other], pivot))
                pos[other] = tuple(p + r for p, r in zip(pivot, model.quat_rotate(turn, rel)))
    return pos


def world_game(empty):
    bpy.context.view_layer.update()
    return model.blender_to_game(tuple(empty.matrix_world.translation))


def write(path, text):
    with open(path, "w") as f:
        f.write(text)


def game_box(objs):
    """(min, max) corners in game space of the objects' meshes, as Blender shows them."""
    bpy.context.view_layer.update()
    pts = [model.blender_to_game(tuple(o.matrix_world @ mathutils.Vector(c))) for o in objs for c in o.bound_box]
    return [min(p[i] for p in pts) for i in range(3)], [max(p[i] for p in pts) for i in range(3)]


def part(path):
    return [o for o in bpy.context.scene.objects if o.type == "MESH" and o.get("werkstatt_node") == path]


def arch(body_points, x, y, z, r, reach=1.0):
    """The wheel arch above a hub: the nearest outer body vertices ahead of and behind it that sit lower than the
    tyre's upper part (the body's side, within 15 cm of the hub's x)."""
    low = [p[2] for p in body_points if p[0] * x > 0 and abs(p[0]) > abs(x) - 0.15 and y < p[1] < y + 0.8 * r and abs(p[2] - z) < reach]
    return max((q for q in low if q < z), default=z - reach), min((q for q in low if q > z), default=z + reach)


def second_round(root, path):
    """The second review of #29: ownership by rule, values Blender's keys can reach, the changed-on-disk guard
    without session state, unsaved compared as values, stricter inputs."""
    keg = "Parts/Mammoth_CosmeticParts/Visual/Bed/Party_Bed/AccessoryBeerBarrel"
    winch = "Parts/Mammoth_CosmeticParts/Performance/Winch/Winch_01"
    if os.path.isfile(path):
        os.remove(path)
    api.open_vehicle(VEHICLE, force=True)
    copy = api.duplicate(keg)["node"]
    check(api.save()["result"] == "written" and copy in open(path).read(), "a copy made in the session is saved")
    api.delete_copy(copy)
    check(api.unsaved()["unsaved"], "deleting a saved copy is an unsaved change")
    saved = api.save()
    check(saved["ok"] and saved["kept"] == 0 and (not os.path.isfile(path) or copy not in open(path).read()),
          f"and the save takes it out of the file: {saved}")

    # Values the plugin refuses, as Blender's G and S keys can leave them.
    api.open_vehicle(VEHICLE, force=True)
    e = api._empty("Winch_01")
    e.location = e.location + mathutils.Vector((0.0, -12.0, 0.0))
    r = api.save()
    check(not r["ok"] and "Winch_01" in r["error"] and "offset" in r["error"], f"save refuses a 12 m drag: {r.get('error')}")
    api.reset("Winch_01")
    e.scale = (-1.0, -1.0, -1.0)
    r = api.save()
    check(not r["ok"] and "mirrored" in r["error"], f"save refuses a mirrored empty (S -1): {r.get('error')}")
    api.reset("Winch_01")
    v = api._vehicle()
    turned = next(p for p, n in sorted(v.nodes.items()) if n.kind == "option" and v.is_turned(p))
    api._empty(turned).scale = (2.0, 1.0, 1.0)
    r = api.save()
    check(not r["ok"] and "non-uniform" in r["error"], f"save refuses S on one axis of a turned node: {r.get('error')}")
    api.reset(turned)

    # The changed-on-disk guard without session state (Reload Scripts, a reopened .blend, a restart).
    api.nudge("Winch_01", "y", 1, "cm")
    api.save()
    api._state["vehicle"], api._state["sha"] = None, {}
    api.nudge("Winch_01", "y", 1, "cm")
    check(api.save()["ok"], "with the session's record gone, the root collection's lets an unchanged file be saved")
    write(path, open(path).read().replace('"Parts', '"Lights/HeadLightL": {"offset": [0, 0.01, 0]},\n    "Parts', 1))
    api._state["vehicle"], api._state["sha"] = None, {}
    api.nudge("Winch_01", "y", 1, "cm")
    r = api.save()
    check(not r["ok"] and "changed on disk" in r["error"], f"and a file changed on disk is still refused: {r.get('error')}")
    del scene.root_collection()["werkstatt_file_sha"]
    api._state["sha"] = {}
    r = api.save()
    check(not r["ok"] and "no record" in r["error"], f"with no record at all, save refuses: {r.get('error')}")
    check(bpy.ops.werkstatt.save(force=True) == {"FINISHED"} and "HeadLightL" in open(path).read(),
          "the panel's Overwrite writes anyway, keeping the hand-added light")

    # Unsaved is compared as values: a hand-formatted file and rotations written another way aren't changes.
    for rotation in ((100.0, 0.0, 0.0), (0.0, 200.0, 0.0), (89.9999, 0.0, 0.0), (-89.95, 30.0, 10.0)):
        write(path, json.dumps({"nodes": {winch: {"offset": [0, 0.05, 0], "rotation": list(rotation)}}}, indent=8))
        api.open_vehicle(VEHICLE, force=True)
        r = api.unsaved()
        check(r["ok"] and not r["unsaved"], f"a pretty-printed file with rotation {rotation} isn't unsaved right after open")
    q = model.euler_to_quat((89.9999, 0.0, 0.0))
    check(model.quat_angle(q, model.euler_to_quat(model.quat_to_euler(q))) < 1e-4, "a pitch of 89.9999° survives the round trip")
    write(path, "{ broken <<<<<<< HEAD")
    r = api.unsaved()
    check(r["ok"] and r["unsaved"] and "why" in r, f"a broken file can't be compared, so it counts as unsaved: {r}")
    r = api.open_vehicle(VEHICLE)
    check(not r["ok"] and "can't tell" in r["error"], f"reopening says why it can't tell: {r.get('error', '')[:100]}")
    check(api.open_vehicle(VEHICLE, force=True)["ok"] is False, "and a broken file still stops the open itself")
    os.remove(path)
    check(api.open_vehicle(VEHICLE, force=True)["ok"], "a removed file opens again")

    # Stricter inputs.
    for value, what in ((b"abc", "bytes"), ({"x": 1, "y": 2, "z": 3}, "a dict"), (["1", 2, 3], "text in a list")):
        r = api.set_placement("Winch_01", offset=value)
        check(not r["ok"], f"an offset given as {what} is refused: {r.get('error')}")
    odd = os.path.join(root, "vehicles", "odd")
    os.makedirs(odd)
    write(os.path.join(odd, "vehicle.json"), "[1, 2]")
    listed = api.vehicles()
    check(listed["ok"] and any(x["name"] == "odd" and "object" in x.get("error", "") for x in listed["vehicles"]),
          "a vehicle.json holding a list is listed with its error")
    shutil.rmtree(odd)


def refusals(root, path):
    """The review's findings on #29: reads that write, saves that lose entries, values that raise."""
    winch = api._empty("Winch_01")
    winch.rotation_mode = "XYZ"
    winch.rotation_euler = (0.0, 0.0, 0.1)
    r = api.placement("Winch_01")
    check(r["ok"] and winch.rotation_mode == "XYZ" and abs(r["rotation"][1] + math.degrees(0.1)) < 1e-3,
          f"placement() reads an Euler-mode empty without switching its mode (Blender z is the game's -y): {r.get('rotation')}")
    api.reset("Winch_01")

    for call, what in ((lambda: api.set_placement("Winch_01", offset=(1, 2)), "a two-number offset"),
                       (lambda: api.nudge("Winch_01", "y", "2"), "steps as text"),
                       (lambda: api.set_placement("Winch_01", rotation="10"), "a rotation as text"),
                       (lambda: api.set_placement("Winch_01", offset=(float("nan"), 0, 0)), "a NaN offset"),
                       (lambda: api.set_placement("Winch_01", offset=(20, 0, 0)), "an offset of 20 m"),
                       (lambda: api.show_slot(None), "no slot"),
                       (lambda: api.nudge(5), "a number as the node"),
                       (lambda: api.open_vehicle(["megaloceros"]), "a list as the name"),
                       (lambda: api.scale_by("Winch_01", "2"), "a factor as text")):
        r = call()
        check(isinstance(r, dict) and r.get("ok") is False and r.get("error"), f"{what} comes back as a message: {r.get('error') if isinstance(r, dict) else r}")

    v = api._vehicle()
    turned = next(p for p, n in sorted(v.nodes.items()) if n.kind == "option" and v.is_turned(p))
    straight = next(p for p, n in sorted(v.nodes.items()) if n.kind == "option" and not v.is_turned(p))
    r = api.set_placement(turned, scale=(2, 1, 1))
    check(not r["ok"] and "turned" in r["error"], f"a non-uniform scale on a turned node is refused: {r.get('error')}")
    check(api.set_placement(turned, scale=(1.5, 1.5, 1.5))["ok"] and api.reset(turned)["ok"], "a uniform scale on it is fine")
    check(api.scale_by(straight, 1.2, "x")["ok"] and api.reset(straight)["ok"], "a non-uniform scale on a node that isn't turned is fine")

    # A file's entries the scene doesn't build (outside the upgrade tree) survive a save; a copy deleted here doesn't.
    head = "Lights/HeadLightL"
    keg = "Parts/Mammoth_CosmeticParts/Visual/Bed/Party_Bed/AccessoryBeerBarrel"
    write(path, json.dumps({"nodes": {head: {"offset": [0, 0.05, 0]}, "Parts/Mammoth_CosmeticParts/Performance/Winch/Winch_01": {"offset": [0, 0, 0.02]}},
                            "copies": {keg + "~2": {"source": keg}}}))
    opened = api.open_vehicle(VEHICLE, force=True)
    check(opened["ok"] and opened["not_shown"] == [head], f"open says which entries the scene doesn't show: {opened.get('not_shown')}")
    api.nudge("Winch_01", "y", 1, "cm")
    api.delete_copy(keg + "~2")
    saved = api.save()
    n, c, _ = model.parse_placements(open(path).read())
    check(saved["ok"] and saved["kept"] == 1 and head in n and keg + "~2" not in c and close(n[head].offset, (0, 0.05, 0)),
          f"save keeps {head} and drops the deleted copy: {saved}")

    # The file changed on disk after it was read: save refuses, force overwrites.
    api.nudge("Winch_01", "y", 1, "cm")
    write(path, open(path).read().replace("0.05", "0.06"))
    r = api.save()
    check(not r["ok"] and "changed on disk" in r["error"], f"save refuses a file changed since it was read: {r.get('error')}")
    check(api.save(force=True)["result"] == "written", "save(force=True) writes it anyway")
    # Unsaved nudges stop a reopen; force drops them.
    api.nudge("Winch_01", "y", 1, "cm")
    check(api.unsaved()["unsaved"], "unsaved() sees the nudge")
    r = api.open_vehicle(VEHICLE)
    check(not r["ok"] and "unsaved" in r["error"], f"open refuses to drop unsaved changes: {r.get('error')}")
    check(api.open_vehicle(VEHICLE, force=True)["ok"] and not api.unsaved()["unsaved"], "open(force=True) drops them")

    # Blender's Shift+D on an empty: two empties claim one node, so save refuses; meshes don't move on their own.
    winch = api._empty("Winch_01")
    twin = winch.copy()
    winch.users_collection[0].objects.link(twin)
    r = api.save()
    check(not r["ok"] and "claim" in r["error"], f"save refuses two empties on one node: {r.get('error')}")
    bpy.data.objects.remove(twin, do_unlink=True)
    mesh = next(o for o in winch.children_recursive if o.type == "MESH")
    check(all(mesh.lock_location) and all(mesh.lock_rotation) and all(mesh.lock_scale), "an item's meshes are locked; its empty moves")

    # Another checkout than the scene's: save refuses.
    other = scratch_checkout(())
    os.environ["WERKSTATT_DIR"] = other
    r = api.save()
    check(not r["ok"] and root in r["error"], f"save refuses when the add-on points at another checkout: {r.get('error')}")
    check(api.status().get("vehicle_root") == root, "status names the open vehicle's checkout")
    os.environ["WERKSTATT_DIR"] = root
    shutil.rmtree(other, ignore_errors=True)

    # The panel's status runs no git: a draw must not wait on a subprocess.
    import subprocess
    real_run = subprocess.run
    subprocess.run = lambda *a, **k: (_ for _ in ()).throw(AssertionError("git ran"))
    try:
        r = api.status()
        check(r["ok"] and r["branch"] is None, f"status() asks git nothing (the scratch folder has no .git): {r}")
    finally:
        subprocess.run = real_run

    second_round(root, path)

    # Broken files are messages: a malformed vehicle.json, a malformed placements.json.
    broken = os.path.join(root, "vehicles", "broken")
    os.makedirs(broken)
    write(os.path.join(broken, "vehicle.json"), "{ not json")
    listed = api.vehicles()
    check(listed["ok"] and any(x["name"] == "broken" and x.get("error") for x in listed["vehicles"])
          and any(x["name"] == VEHICLE and not x.get("error") for x in listed["vehicles"]), "one unreadable vehicle.json doesn't hide the others")
    r = api.open_vehicle("broken", force=True)
    check(not r["ok"] and "vehicle.json" in r["error"], f"opening it says what's wrong: {r.get('error')}")
    shutil.rmtree(broken)
    write(path, '{"nodes": {"A/B": {"offset": [0, 0]}}}')
    r = api.open_vehicle(VEHICLE, force=True)
    check(not r["ok"] and "three numbers" in r["error"], f"a malformed placements.json is a message: {r.get('error')}")
    os.remove(path)

    # Only what the add-on made is cleared, and the scene's units stay as the user set them.
    user_mesh = bpy.data.meshes.new("not werkstatt's")
    bpy.context.scene.unit_settings.system = "IMPERIAL"
    api.open_vehicle(VEHICLE, force=True)
    check(bpy.data.meshes.get("not werkstatt's") is not None, "reopening leaves the user's unused meshes alone")
    check(bpy.context.scene.unit_settings.system == "IMPERIAL", "opening a vehicle leaves the scene's units alone")
    bpy.data.meshes.remove(user_mesh)
    bpy.context.scene.unit_settings.system = "METRIC"


def axles(root):
    """Each built truck as the plugin spawns it: the rear axle and springs moved back by the sweep, the wheels at
    the wheelbase and track, and the body's wheel arches over the hubs."""
    for name in TRUCKS:
        if not os.path.isdir(os.path.join(root, "vehicles", name)):
            print(f"skip {name}: not built")
            continue
        r = api.open_vehicle(name, force=True)
        check(r["ok"], f"{name} opens: {r.get('error')}")
        v = api._vehicle()
        m = v.manifest
        for which, axle_z in (("Front", m["donorAxleZ"]["front"]), ("Rear", m["donorAxleZ"]["rear"] + v.shift)):
            objs = part(f"Axles/SuspensionRigid{which}/SuspensionRigidMesh_LOD0")
            lo, hi = game_box(objs)
            mid = (lo[2] + hi[2]) / 2
            check(objs and abs(mid - axle_z) < 0.03, f"{name}: {which.lower()} axle and springs centred at z {mid:.3f}, the plugin's {axle_z:.3f}")
        body = part("Parts/Mammoth/Mammoth_body_LOD0")[0]
        bpy.context.view_layer.update()
        points = [model.blender_to_game(tuple(body.matrix_world @ vert.co)) for vert in body.data.vertices]
        refs = {o.name.split()[0]: o for o in bpy.context.scene.objects if o.get("werkstatt_reference")}
        for corner, hub, radius, _width in v.wheels():
            lo, hi = game_box([o for o in bpy.context.scene.objects if o.get("werkstatt_reference") and o.name.startswith(corner + " ")])
            centre = [(a + b) / 2 for a, b in zip(lo, hi)]
            check(close(centre, hub, 0.03), f"{name}: the {corner} wheel sits on its hub {tuple(round(c, 3) for c in hub)}")
            back, front = arch(points, *hub, radius)
            check(abs((back + front) / 2 - hub[2]) < 0.05 and front - back > radius,
                  f"{name}: the {corner} hub sits under the body's wheel arch (arch {back:.3f} to {front:.3f}, hub {hub[2]:.3f})")
            point = v.attach_points.get(f"Axles/WheelMeshes/{corner}")
            check(point is not None and close(point, (hub[0], point[1], hub[2]), 0.01), f"{name}: the {corner} wheel's attach point is on the hub")
        check(len(refs) >= 4, f"{name}: four wheels shown")
        transformed(name, v)


def transformed(name, v):
    """The definition's transforms, which the plugin applies after the sweep: each node at its position, an upgrade
    group's items and meshes carried along, and the centre of mass at its share of the new wheelbase. Expected
    values come from vehicle.json and the extracted files, not from the add-on's model."""
    raw = {n["path"]: n for n in json.load(open(os.path.join(v.extracted, "upgrades.json")))["nodes"]}
    facts = {f["path"]: f for f in json.load(open(os.path.join(v.extracted, "nodes.json")))["nodes"]}
    empties = scene.editable_empties()
    bpy.context.view_layer.update()
    m = v.manifest
    for path, t in m.get("transforms", {}).items():
        if "position" not in t:
            continue
        if path in empties:
            at = world_game(empties[path])
            check(close(at, t["position"], 1e-3), f"{name}: {path.rsplit('/', 1)[-1]} at its transform {t['position']} ({tuple(round(a, 3) for a in at)})")
            kids = [p for p in raw if model.parent_path(p) == path and p in empties]
            moved = [p for p in kids if close(tuple(a - b for a, b in zip(world_game(empties[p]), at)),
                                              tuple(a - b for a, b in zip(raw[p]["position"], raw[path]["position"])), 1e-3)]
            check(kids and moved == kids, f"{name}: its {len(kids)} items keep their offsets from it")
            option = next((p for p in kids if raw[p].get("file") and raw[p].get("part")), None)
            if option:
                own = scene.read_obj(v.option_file(v.nodes[option]))       # the option's own meshes, not nested options'
                meshes = [o for o in empties[option].children_recursive if o.type == "MESH" and o.get("werkstatt_mesh_of") in own]
                lo, hi = game_box(meshes)
                centre = [(a + b) / 2 for a, b in zip(lo, hi)]
                verts = [model.blender_to_game(p) for _, (vs, _f) in own.items() for p in vs]
                donor_centre = [(min(p[i] for p in verts) + max(p[i] for p in verts)) / 2 for i in range(3)]
                shift = [a - b for a, b in zip(world_game(empties[option]), raw[option]["position"])]
                check(close(centre, [c + d for c, d in zip(donor_centre, shift)], 2e-3),
                      f"{name}: {option.rsplit('/', 1)[-1]}'s meshes move with it ({[round(c, 3) for c in centre]} vs {[round(c + d, 3) for c, d in zip(donor_centre, shift)]})")
        elif path in facts and path in v.attach_points:
            check(close(v.attach_points[path], t["position"], 1e-4), f"{name}: the attach point {path} at its transform")
    front, rear = facts["Axles/WheelMeshes/FL"]["position"][2], facts["Axles/WheelMeshes/RL"]["position"][2]
    shift = -(m["wheelbase"] - (front - rear))
    target = rear + shift + (facts["CoM"]["position"][2] - rear) * m["wheelbase"] / (front - rear)
    check(abs(v.attach_points["CoM"][2] - target) < 1e-4, f"{name}: the centre of mass at z {v.attach_points['CoM'][2]:.3f}, the plugin's {target:.3f}")


def main():
    root = scratch_checkout(sorted(set(TRUCKS + (VEHICLE,))))
    os.environ["WERKSTATT_DIR"] = root
    werkstatt_addon.register()
    try:
        s = api.status()
        check(s["ok"] and s["root"] == root, f"status finds the checkout ({s.get('root')})")
        listed = api.vehicles()
        check(listed["ok"] and any(v["name"] == VEHICLE and v["extracted"] for v in listed["vehicles"]), "vehicles() lists the vehicle, extracted")

        bad = api.open_vehicle("nosuchtruck")
        check(not bad["ok"] and "nosuchtruck" in bad["error"], f"a wrong name gives a message: {bad.get('error')}")
        opened = api.open_vehicle(VEHICLE, show=["Winch_01"])
        check(opened["ok"] and opened["options"] > 150, f"open_vehicle builds the scene: {opened}")
        root_c = scene.root_collection()
        names = {c.name for c in root_c.children}
        for want in ("Attach points", "Upgrades", "References (donor, read-only)", "Ghost"):
            check(want in names, f"scene has '{want}'")
        check(any(n.startswith("Part: ") for n in names), "scene has part collections")
        check(any(c.get("werkstatt_node") for c in root_c.children if c.name.startswith("Part: ")), "parts carry their node path")

        v = api._vehicle()
        winch = "Parts/Mammoth_CosmeticParts/Performance/Winch/Winch_01"
        roof = "Parts/Mammoth_CosmeticParts/Visual/Roof"
        spare = f"{roof}/RoofSpare"
        rack = f"{spare}/RoofrackFlatA"
        keg = "Parts/Mammoth_CosmeticParts/Visual/Bed/Party_Bed/AccessoryBeerBarrel"
        empties = scene.editable_empties()
        for path in (winch, roof, spare, rack, keg):
            check(path in empties, f"empty for {path.rsplit('/', 1)[-1]}")
        check(close(world_game(empties[winch]), v.nodes[winch].position), "the winch empty sits at the node's pose after the reshape")
        check(all(not o.hide_get() for o in empties[winch].children_recursive), "the shown option's meshes are visible")
        check(empties[rack].hide_get(), "options not asked for start hidden")
        check(any(o.type == "MESH" for o in empties[winch].children_recursive), "the winch has its mesh")

        ambiguous = api.nudge("AccessoryBeerBarrel", "y", 1, "cm")
        check(not ambiguous["ok"] and "matches" in ambiguous["error"], f"an ambiguous name says so: {ambiguous.get('error', '')[:80]}")
        r = api.nudge("Winch_01", "z", 5, "cm")
        r = api.nudge("Winch_01", "y", 1, "cm")
        r = api.rotate("Winch_01", "y", 2, 1.0)
        check(r["ok"] and close(r["offset"], (0, 0.01, 0.05)) and close(r["rotation"], (0, 2, 0), 1e-3), f"nudge and rotate: {r}")
        check(close(world_game(empties[winch]), tuple(a + b for a, b in zip(v.nodes[winch].position, (0, 0.01, 0.05)))),
              "the winch moved 5 cm forward and 1 cm up in game space")
        r = bpy.ops.werkstatt.nudge(node="Winch_01", axis="x", steps=-3, unit="mm")
        check(r == {"FINISHED"} and close(api.placement("Winch_01")["offset"], (-0.003, 0.01, 0.05)), "the operator nudges with plain arguments")

        # A slot group and a child under it: the child's offset turns with the group, as in the plugin.
        api.set_placement(roof, offset=(0.0, 0.02, 0.0), rotation=(0.0, 10.0, 0.0))
        api.set_placement(spare, offset=(0.0, 0.0, 0.1), rotation=(3.0, 0.0, 0.0))
        dup = api.duplicate(keg)
        check(dup["ok"] and dup["node"] == keg + "~2" and dup["kind"] == "copy", f"duplicate makes {dup.get('node')}")
        api.nudge(dup["node"], "z", 4, "dm")
        dup_option = api.duplicate("Party_Bed")
        check(dup_option["ok"] and dup_option["node"].endswith("Party_Bed/Party_Bed~2"), f"an option copy goes inside it: {dup_option.get('node')}")
        api.set_placement(dup_option["node"], offset=(0.3, 0.0, 0.0))
        empties = scene.editable_empties()
        party = empties[model.parent_path(keg)]
        check(empties[dup_option["node"]].parent == party and empties[keg + "~2"].parent == party,
              "a copy whose path is inside its source is its child, any other its sibling (the plugin's rule)")
        check(not any(o.name.startswith("AccessoryBeerBarrel~") for o in empties[dup_option["node"]].children_recursive),
              "a copy is made from its untouched source: Party_Bed~2 carries no copy of the keg copy, as in game")

        nodes = {winch: model.Placement((-0.003, 0.01, 0.05), (0, 2, 0)), roof: model.Placement((0, 0.02, 0), (0, 10, 0)),
                 spare: model.Placement((0, 0, 0.1), (3, 0, 0))}
        copies = {keg + "~2": model.Placement((0, 0, 0.4), source=keg)}
        base = {p: v.nodes[p].position for p in (winch, roof, spare, rack, keg)}
        base[keg + "~2"] = v.nodes[keg].position
        expected = emulate(base, model.steps(nodes, copies))
        empties = scene.editable_empties()
        for path in (winch, roof, spare, rack, keg + "~2"):
            check(close(world_game(empties[path]), expected[path], 1e-4), f"scene matches the plugin's steps at {path.rsplit('/', 1)[-1]}: {world_game(empties[path])} vs {expected[path]}")

        saved = api.save()
        check(saved["ok"] and saved["result"] == "written", f"save writes the file: {saved}")
        path = os.path.join(root, "vehicles", VEHICLE, "placements.json")
        text = open(path).read()
        n, c, _ = model.parse_placements(text)
        check(set(n) == {winch, roof, spare} and set(c) == {keg + "~2", dup_option["node"]}, f"the file holds exactly the edits ({sorted(n)}, {sorted(c)})")
        check(api.save()["result"] == "unchanged", "saving again changes nothing")
        check(len(text.splitlines()) == 1 + 1 + 1 + 3 + 1 + 1 + 2 + 1 + 1, "one line per entry")

        reopened = api.open_vehicle(VEHICLE)
        check(reopened["placements"] == 3 and reopened["copies"] == 2, f"reopening reads the file back: {reopened}")
        check(close(api.placement("Winch_01")["offset"], (-0.003, 0.01, 0.05)), "the winch keeps its placement after reopening")
        check(api.save()["result"] == "unchanged", "a reopened, untouched vehicle saves to the same bytes")
        check(close(api.placement("Visual/Roof")["offset"], (0, 0.02, 0)), "a unique end of a path names a node (Visual/Roof)")
        check(api.delete_copy(keg + "~2")["ok"] and api.reset("Winch_01")["ok"], "delete a copy, reset an item")
        api.save()
        n, c, _ = model.parse_placements(open(path).read())
        check(winch not in n and keg + "~2" not in c, "reset and deleted entries leave the file")
        # The panel draws without errors and every property and operator it names exists.
        from werkstatt_addon import ui
        problems = []

        class FakeLayout:
            def __getattr__(self, name):
                def call(*args, **kwargs):
                    if name == "prop":
                        data, prop = args[0], args[1]
                        if prop not in data.bl_rna.properties:
                            problems.append(f"no property {prop}")
                    if name == "operator":
                        idname = args[0]
                        group, op = idname.split(".")
                        if not hasattr(getattr(bpy.ops, group), op):
                            problems.append(f"no operator {idname}")
                        return type("Props", (), {})()
                    if name == "template_list":
                        if args[3] not in args[2].bl_rna.properties:
                            problems.append(f"no list {args[3]}")
                    return FakeLayout()
                return call

        panel = type("P", (), {"layout": FakeLayout()})()
        api.frame("Winch_01")
        ui.WERKSTATT_PT_panel.draw(panel, bpy.context)
        ui.refresh_items(bpy.context)
        check(not problems and len(bpy.context.scene.werkstatt.items) > 150, f"the panel draws and lists the items ({problems})")
        check(len(ui._vehicle_items(None, bpy.context)) >= 1, "the vehicle list fills")
        f = api.frame("RoofSpare/RoofrackFlatA")
        check(f["ok"] and close(f["centre"], v.nodes[rack].position, 0.6) and f["size"][0] > 0.5, f"frame finds the item's centre and size: {f}")
        check(not api.delete_copy("Winch_01")["ok"], "an original can't be deleted")
        refusals(root, path)
        axles(root)
        # Reload Scripts re-runs the package's __init__, which reloads every submodule too.
        import importlib
        werkstatt_addon.unregister()
        before = (model.parse_placements, scene.build, api.nudge, werkstatt_addon.ui.register)
        importlib.reload(werkstatt_addon)
        after = (model.parse_placements, scene.build, api.nudge, werkstatt_addon.ui.register)
        check(all(a is not b for a, b in zip(before, after)), "reloading the add-on reloads model, scene, api and ui")
        werkstatt_addon.register()
    finally:
        werkstatt_addon.unregister()
        shutil.rmtree(root, ignore_errors=True)


try:
    main()
except Exception:
    traceback.print_exc()
    failures.append("exception")
print(f"\n{'FAILED: ' + str(len(failures)) if failures else 'all checks passed'}")
sys.exit(1 if failures else 0)
