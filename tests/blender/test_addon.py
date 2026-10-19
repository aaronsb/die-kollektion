"""Headless test of the Werkstatt add-on: open a vehicle, nudge, turn, copy, save, reopen.

Usage: blender -b --factory-startup --python tests/blender/test_addon.py -- [<vehicle>]
Runs on a scratch copy of the checkout's vehicle folder (the build and extracted data are linked, read-only), so
the checkout is never written. Needs `make extract` (with upgrades.json) and the vehicle built. Exits non-zero on
any failure.
"""
import json, math, os, shutil, sys, tempfile, traceback

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "blender", "addons"))

import bpy  # noqa: E402
import werkstatt_addon  # noqa: E402
from werkstatt_addon import api, model, scene  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
VEHICLE = argv[0] if argv else "megaloceros"
failures = []


def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        failures.append(what)


def close(a, b, tol=1e-4):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


def scratch_checkout():
    tmp = tempfile.mkdtemp(prefix="werkstatt-addon-")
    open(os.path.join(tmp, "Makefile"), "w").close()
    os.makedirs(os.path.join(tmp, "vehicles"))
    os.symlink(os.path.join(ROOT, "extracted"), os.path.join(tmp, "extracted"))
    src = os.path.join(ROOT, "vehicles", VEHICLE)
    dst = os.path.join(tmp, "vehicles", VEHICLE)
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("build", "contact", "placements.json"))
    os.symlink(os.path.join(src, "build"), os.path.join(dst, "build"))
    return tmp


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


def main():
    root = scratch_checkout()
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
