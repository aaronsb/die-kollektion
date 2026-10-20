"""The placements format and the add-on's model (blender/addons/werkstatt_addon/model.py), without Blender.

tools/placement-check runs the plugin's PlacementPlan over the same fixture and expected steps, so the two
implementations are held to one answer.
"""
import json, math, os, random, shutil, sys, tempfile, unittest

TESTS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TESTS)
sys.path.insert(0, os.path.join(ROOT, "blender", "addons"))
from werkstatt_addon import model, wording  # noqa: E402

FIXTURES = os.path.join(TESTS, "placements")


def close(a, b, tol=1e-6):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


class Format(unittest.TestCase):
    def setUp(self):
        with open(os.path.join(FIXTURES, "fixture.json")) as f:
            self.text = f.read()
        self.nodes, self.copies, self.notes = model.parse_placements(self.text)

    def test_fixture_resolves_to_the_expected_steps(self):
        with open(os.path.join(FIXTURES, "expect.json")) as f:
            expected = json.load(f)["steps"]
        got = model.steps(self.nodes, self.copies)
        self.assertEqual([p for p, _, _ in got], [e["path"] for e in expected])
        for (path, offset, turn), e in zip(got, expected):
            self.assertTrue(close(offset, e["offset"], 1e-6), path)
            dot = sum(a * b for a, b in zip(turn, e["turn"]))
            self.assertAlmostEqual(abs(dot), 1.0, places=6, msg=path)

    def test_a_child_offset_turns_with_its_placed_parent(self):
        # The roof group turns 90 degrees about up, so the camper's forward offset ends up pointing right.
        steps = {p: (o, t) for p, o, t in model.steps(self.nodes, self.copies)}
        self.assertTrue(close(steps["Parts/Mammoth_CosmeticParts/Visual/Roof/Camper"][0], (0.1, 0.0, 0.0)))

    def test_a_scaled_parent_stretches_its_childs_offset(self):
        steps = {p: o for p, o, _ in model.steps(self.nodes, self.copies)}
        self.assertTrue(close(steps["Parts/Mammoth_CosmeticParts/Visual/Bed/Party_Bed/AccessoryBeerBarrel"], (0.1, 0.0, -0.24)))

    def test_saving_what_was_read_gives_the_same_bytes(self):
        text = model.dump_placements(self.nodes, self.copies, self.notes)
        self.assertEqual(text, model.dump_placements(*model.parse_placements(text)))
        self.assertTrue(text.endswith("}\n"))

    def test_keys_are_sorted_and_defaults_left_out(self):
        nodes = {"B/c": model.Placement(offset=(0.0, 0.01, 0.0)), "A/b": model.Placement(scale=(1.0, 1.0, 1.0)),
                 "A/a": model.Placement(rotation=(0.0, 0.0, 1e-5))}
        data = json.loads(model.dump_placements(nodes, {}))
        self.assertEqual(list(data["nodes"]), ["B/c"])          # an identity entry is not written
        self.assertEqual(data["nodes"]["B/c"], {"offset": [0.0, 0.01, 0.0]})

    def test_numbers_are_rounded_and_never_minus_zero(self):
        text = model.dump_placements({"A/b": model.Placement(offset=(-0.00001, 0.123456789, -1e-9))}, {})
        self.assertIn("[0.0, 0.1235, 0.0]", text)
        self.assertNotIn("-0.0", text)

    def test_nothing_to_say_removes_the_file(self):
        folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, folder)
        path = os.path.join(folder, "placements.json")
        self.assertEqual(model.write_placements(path, {}, {}), "absent")
        self.assertEqual(model.write_placements(path, {"A/b": model.Placement(offset=(0, 0.02, 0))}, {}), "written")
        self.assertEqual(model.write_placements(path, {"A/b": model.Placement(offset=(0, 0.02, 0))}, {}), "unchanged")
        self.assertEqual(model.write_placements(path, {"A/b": model.Placement()}, {}), "removed")
        self.assertFalse(os.path.exists(path))

    def test_malformed_files_are_refused_for_the_listed_reason(self):
        with open(os.path.join(FIXTURES, "reasons.json")) as f:
            reasons = json.load(f)
        bad = sorted(os.listdir(os.path.join(FIXTURES, "bad")))
        self.assertGreaterEqual(len(bad), 15)
        for name in bad:
            with open(os.path.join(FIXTURES, "bad", name)) as f, self.subTest(name):
                self.assertIn(name, reasons)
                with self.assertRaises(model.WerkstattError) as caught:
                    model.parse_placements(f.read(), name)
                self.assertTrue(any(phrase in str(caught.exception) for phrase in reasons[name]), str(caught.exception))

    def test_a_turned_non_uniformly_scaled_parent_carries_its_childs_offset_exactly(self):
        steps = {p: o for p, o, _ in model.steps(self.nodes, self.copies)}
        # Visual/Side: 30 degrees about up, z doubled; the jerrycan's 0.1 m forward becomes 0.2 m, turned.
        self.assertTrue(close(steps["Parts/Mammoth_CosmeticParts/Visual/Side/Side_Jerrycan"], (0.1, 0.0, 0.2 * math.cos(math.radians(30)))))


class Maths(unittest.TestCase):
    def test_euler_matches_unity(self):
        # Quaternion.Euler(0, 90, 0) * forward == right; Euler(-90, 0, 0) * forward == up.
        self.assertTrue(close(model.quat_rotate(model.euler_to_quat((0, 90, 0)), (0, 0, 1)), (1, 0, 0)))
        self.assertTrue(close(model.quat_rotate(model.euler_to_quat((-90, 0, 0)), (0, 0, 1)), (0, 1, 0)))

    def test_euler_round_trip(self):
        rng = random.Random(7)
        for _ in range(500):
            e = (rng.uniform(-89, 89), rng.uniform(-179, 179), rng.uniform(-179, 179))
            q = model.euler_to_quat(e)
            self.assertTrue(close(model.quat_to_euler(q), e, 1e-6))

    def test_game_and_blender_frames_agree(self):
        rng = random.Random(11)
        for _ in range(200):
            q = model.euler_to_quat((rng.uniform(-80, 80), rng.uniform(-180, 180), rng.uniform(-180, 180)))
            v = (rng.random(), rng.random(), rng.random())
            lhs = model.quat_rotate(model.quat_game_to_blender(q), model.game_to_blender(v))
            self.assertTrue(close(lhs, model.game_to_blender(model.quat_rotate(q, v)), 1e-9))
            self.assertTrue(close(model.quat_blender_to_game(model.quat_game_to_blender(q)), q, 1e-12))
        self.assertEqual(model.game_to_blender((1, 2, 3)), (-1, -3, 2))      # x right -> -X, z forward -> -Y, y up -> Z
        self.assertEqual(model.blender_to_game(model.game_to_blender((1, 2, 3))), (1, 2, 3))


class Vehicles(unittest.TestCase):
    """A tiny checkout: one donor's extracted node facts and upgrades, and a longer vehicle on it."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="werkstatt-model-")
        self.addCleanup(shutil.rmtree, self.root)
        open(os.path.join(self.root, "Makefile"), "w").close()
        cosmetic = "Parts/Car_CosmeticParts"
        facts = [{"path": p, "position": pos, "rotation": [0, 0, 0, 1], "scale": [1, 1, 1], "active": True, "components": c}
                 for p, pos, c in (("Parts", [0, 0, 0], []), (cosmetic, [0, 0, 0], []),
                                   (f"{cosmetic}/Visual", [0, 0, 0], []),
                                   (f"{cosmetic}/Visual/Front", [0, 0.8, 2.0], []),
                                   (f"{cosmetic}/Visual/Front/Bullbar", [0, 0.8, 2.0], [{"type": "MB:VehicleUpgradeObject"}]),
                                   (f"{cosmetic}/Visual/Front/Builtin", [0, 0.8, 2.1], [{"type": "MB:VehicleUpgradeObject"}]),
                                   (f"{cosmetic}/Visual/Bed", [0, 1.2, -1.9], []),
                                   (f"{cosmetic}/Visual/Bed/Kegs", [0, 1.2, -1.9], [{"type": "MB:VehicleUpgradeObject"}]),
                                   (f"{cosmetic}/Visual/Bed/Kegs/Keg", [0.3, 1.3, -1.8], [{"type": "LODGroup"}]),
                                   (f"{cosmetic}/Performance", [0, 0, 0], []),
                                   (f"{cosmetic}/Performance/Rollcage", [0, 1.0, 0.1], []),
                                   (f"{cosmetic}/Performance/Rollcage/rollcage", [0, 1.0, 0.1], [{"type": "MB:VehicleUpgradeObject"}, {"type": "LODGroup"}]),
                                   (f"{cosmetic}/Performance/Winch", [0, 0.6, 2.2], []),
                                   (f"{cosmetic}/Performance/Winch/Winch_01", [0, 0.6, 2.2], [{"type": "MB:VehicleUpgradeObject"}, {"type": "LODGroup"}]),
                                   ("Winch", [0, 0, 0], []),
                                   ("Winch/WinchAttachPoints", [0, 0, 0], []),
                                   ("Winch/WinchAttachPoints/Front", [0, 0.8, 2.1], [{"type": "MB:CarWinchPoint"}]),
                                   ("Winch/WinchAttachPoints/Rear", [0, 0.9, -2.2], [{"type": "MB:CarWinchPoint"}]))]
        upgrades = {"root": "Car_Car", "cosmeticRoot": cosmetic, "nodes": [
            {"path": f["path"], "parent": model.parent_path(f["path"]), "position": f["position"], "rotation": [0, 0, 0, 1],
             "scale": [1, 1, 1], **({"part": {"name": f["path"].rsplit("/", 1)[1], "cosmeticType": "Bed" if "Bed" in f["path"] else "FrontSection"}}
                                    if any(c["type"] == "MB:VehicleUpgradeObject" for c in f["components"]) else {}),
             **({"lodGroup": True} if any(c["type"] == "LODGroup" for c in f["components"]) else {}), "active": True}
            for f in facts if f["path"].startswith(cosmetic)]}
        for n in upgrades["nodes"]:
            if "part" in n:
                n["active"] = False                 # an option waits, inactive, for its item
            if ("/Performance/" in n["path"] or n["path"].endswith("/Builtin")) and "part" in n:
                n["part"] = {"name": None}          # as the exporter writes a node with no part reference
            if n["path"].endswith("/Builtin"):
                n["active"] = True                  # a part-less node the prefab shows: always there
        os.makedirs(os.path.join(self.root, "extracted", "car"))
        with open(os.path.join(self.root, "extracted", "car", "nodes.json"), "w") as f:
            json.dump({"root": "Car_Car", "nodes": facts}, f)
        with open(os.path.join(self.root, "extracted", "car", "upgrades.json"), "w") as f:
            json.dump(upgrades, f)
        self.folder = os.path.join(self.root, "vehicles", "longcar")
        os.makedirs(self.folder)
        with open(os.path.join(self.folder, "vehicle.json"), "w") as f:
            json.dump({"codename": "Longcar", "donor": "Car", "donorAxleZ": {"front": 1.5, "rear": -1.5}, "wheelbase": 3.5,
                       "track": 1.6, "bodyCut": [[0.0, -0.5]], "meshes": {}}, f)
        self.cosmetic = cosmetic

    def test_nodes_behind_the_cut_move_with_the_wheelbase(self):
        v = model.Vehicle(self.root, "longcar")
        self.assertAlmostEqual(v.nodes[f"{self.cosmetic}/Visual/Front/Bullbar"].position[2], 2.0)
        self.assertAlmostEqual(v.nodes[f"{self.cosmetic}/Visual/Bed/Kegs/Keg"].position[2], -2.3)   # 0.5 m longer
        self.assertAlmostEqual(v.attach_points["Winch/WinchAttachPoints/Rear"][2], -2.7)
        self.assertEqual(v.nodes[f"{self.cosmetic}/Visual/Bed"].kind, "group")
        self.assertEqual(v.nodes[f"{self.cosmetic}/Visual/Bed/Kegs"].kind, "option")
        self.assertEqual(v.nodes[f"{self.cosmetic}/Visual/Bed/Kegs/Keg"].kind, "piece")
        self.assertEqual(v.slot_of(f"{self.cosmetic}/Visual/Bed/Kegs/Keg"), "Bed")

    def test_copies_get_the_next_free_name_beside_or_inside_their_source(self):
        v = model.Vehicle(self.root, "longcar")
        keg = f"{self.cosmetic}/Visual/Bed/Kegs/Keg"
        self.assertEqual(v.next_copy_path(keg), f"{keg}~2")
        v.copies[f"{keg}~2"] = model.Placement(source=keg)
        self.assertEqual(v.next_copy_path(keg), f"{keg}~3")
        option = f"{self.cosmetic}/Visual/Bed/Kegs"
        self.assertEqual(v.next_copy_path(option), f"{option}/Kegs~2")

    def test_save_writes_only_the_vehicles_placements_file(self):
        v = model.Vehicle(self.root, "longcar")
        v.placements[f"{self.cosmetic}/Visual/Front/Bullbar"] = model.Placement(offset=(0.0, 0.0, 0.05))
        self.assertEqual(v.save(), "written")
        self.assertEqual(sorted(os.listdir(self.folder)), ["placements.json", "vehicle.json"])
        again = model.Vehicle(self.root, "longcar")
        self.assertEqual(again.placement(f"{self.cosmetic}/Visual/Front/Bullbar").offset, (0.0, 0.0, 0.05))
        self.assertEqual(again.save(), "unchanged")

    def test_a_missing_extraction_says_what_to_run(self):
        os.remove(os.path.join(self.root, "extracted", "car", "upgrades.json"))
        with self.assertRaises(model.WerkstattError) as caught:
            model.Vehicle(self.root, "longcar")
        self.assertIn("make extract", str(caught.exception))

    def test_a_donor_without_upgrade_nodes_still_opens(self):
        with open(os.path.join(self.root, "extracted", "car", "upgrades.json"), "w") as f:
            json.dump({"root": "Car_Car", "cosmeticRoot": None, "nodes": [], "notes": "no Parts/*_CosmeticParts node"}, f)
        v = model.Vehicle(self.root, "longcar")
        self.assertEqual(v.options(), [])
        self.assertIn("Winch/WinchAttachPoints/Front", v.attach_points)

    def manifest(self, **changes):
        path = os.path.join(self.folder, "vehicle.json")
        with open(path) as f:
            m = json.load(f)
        m.update(changes)
        with open(path, "w") as f:
            json.dump(m, f)

    def test_an_option_without_a_part_is_never_shown(self):
        v = model.Vehicle(self.root, "longcar")
        rollcage = f"{self.cosmetic}/Performance/Rollcage"
        self.assertEqual(v.in_game(f"{self.cosmetic}/Visual/Bed/Kegs"), ("item", ()))
        self.assertEqual(v.in_game(f"{self.cosmetic}/Visual/Bed/Kegs/Keg"), ("item", ()))      # a piece goes with its option
        self.assertEqual(v.in_game(f"{rollcage}/rollcage"), ("never", ()))
        self.assertEqual(v.in_game(rollcage), ("never", ()))                    # a slot group whose options never show
        self.assertEqual(v.in_game(f"{self.cosmetic}/Performance/Winch/Winch_01"), ("never", ()))
        self.assertEqual(v.in_game(f"{self.cosmetic}/Performance"), ("never", ()))
        self.assertEqual(v.in_game(f"{self.cosmetic}/Visual"), ("item", ()))  # mixed: no mark
        self.assertEqual(v.in_game(self.cosmetic), ("item", ()))
        self.assertEqual(v.options_below(rollcage), [v.nodes[f"{rollcage}/rollcage"]])

    def test_an_option_without_a_part_the_prefab_shows_is_always_shown(self):
        v = model.Vehicle(self.root, "longcar")
        self.assertEqual(v.in_game(f"{self.cosmetic}/Visual/Front/Builtin"), ("always", ()))
        self.assertEqual(v.in_game(f"{self.cosmetic}/Visual/Front/Bullbar"), ("item", ()))     # inactive too, but with a part

    def test_tool_nodes_show_an_option_with_its_tool(self):
        winch = f"{self.cosmetic}/Performance/Winch/Winch_01"
        self.manifest(toolNodes={"notes": "the bumper winch", winch: 2317836723})
        v = model.Vehicle(self.root, "longcar")
        self.assertEqual(v.in_game(winch), ("tool", (2317836723,)))
        self.assertEqual(v.in_game(f"{self.cosmetic}/Performance/Winch"), ("tool", (2317836723,)))
        self.assertEqual(v.in_game(f"{self.cosmetic}/Performance/Rollcage/rollcage"), ("never", ()))
        self.assertEqual(v.in_game(f"{self.cosmetic}/Performance"), ("item", ()))   # never and tool: mixed

    def test_tool_nodes_on_any_node_of_the_path_count(self):
        # The plugin shows or hides whatever node toolNodes names: a group, a piece, an option without a part.
        bed, keg = f"{self.cosmetic}/Visual/Bed", f"{self.cosmetic}/Visual/Bed/Kegs/Keg"
        rollcage = f"{self.cosmetic}/Performance/Rollcage"
        builtin = f"{self.cosmetic}/Visual/Front/Builtin"
        self.manifest(toolNodes={bed: 3771754783, keg: 2317836723, rollcage: 2317836723, builtin: 3771754783})
        v = model.Vehicle(self.root, "longcar")
        self.assertEqual(v.in_game(f"{bed}/Kegs"), ("item", (3771754783,)))
        self.assertEqual(v.in_game(keg), ("item", (2317836723, 3771754783)))
        self.assertEqual(v.in_game(f"{rollcage}/rollcage"), ("never", ()))      # its own node stays inactive
        self.assertEqual(v.in_game(builtin), ("tool", (3771754783,)))

    def test_tool_nodes_are_ignored_as_the_plugin_ignores_them(self):
        winch = f"{self.cosmetic}/Performance/Winch/Winch_01"
        for block, patch in (({winch: 2317836723}, True), ({winch: 0}, False), ({winch: "2317836723"}, False),
                             ({winch: 2317836723, "A//B": 1}, False), ([winch], False)):
            self.manifest(toolNodes=block, patch=patch)
            self.assertEqual(model.Vehicle(self.root, "longcar").in_game(winch), ("never", ()), (block, patch))

    def test_a_tool_nodes_block_with_a_repeated_key_is_ignored(self):
        winch = f"{self.cosmetic}/Performance/Winch/Winch_01"
        self.manifest(toolNodes={winch: 2317836723})
        path = os.path.join(self.folder, "vehicle.json")
        with open(path) as f:
            text = f.read()
        with open(path, "w") as f:
            f.write(text.replace(f'"{winch}": 2317836723', f'"{winch}": 2317836723, "{winch}": 2317836723'))
        self.assertEqual(model.Vehicle(self.root, "longcar").in_game(winch), ("never", ()))
        with open(path, "w") as f:
            f.write(text.replace('"codename": "Longcar"', '"codename": "Longcar", "codename": "Longcar"'))
        self.assertEqual(model.Vehicle(self.root, "longcar").in_game(winch), ("tool", (2317836723,)))  # elsewhere: no matter

    def test_the_panels_words(self):
        self.assertEqual(wording.note("never", ()), "Not shown in game")
        self.assertEqual(wording.note("always", ()), "Always shown")
        self.assertEqual(wording.note("item", ()), "")
        self.assertEqual(wording.note("tool", (2317836723,)), "Shown with the portable winch")
        self.assertEqual(wording.note("tool", (1234,)), "Shown with tool 1234")
        self.assertEqual(wording.note("item", (3771754783,)), "Shown with its item and the portable plank")
        self.assertEqual([wording.mark(h, t) for h, t in (("never", ()), ("always", ()), ("tool", (1,)), ("item", (1,)), ("item", ()))],
                         ["never", "always", "tool", "tool", None])

    def test_listing_vehicles(self):
        listed = model.list_vehicles(self.root)
        self.assertEqual([v["name"] for v in listed], ["longcar"])
        self.assertTrue(listed[0]["extracted"])


if __name__ == "__main__":
    unittest.main()
