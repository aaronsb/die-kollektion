"""The test save (`make save-test`): tools/save_unlock.py on synthetic saves, and werkstatt's swap and restore."""
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from unittest import mock

TESTS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TESTS)
sys.path.insert(0, os.path.join(ROOT, "tools"))
import save_unlock as su  # noqa: E402
import werkstatt as ws  # noqa: E402

COSMETIC, UPGRADE, LIVERY, DLC_PLATE = 101, 102, 103, 104
CARS = {
    "Donor": {"itemId": 11, "parts": [
        {"kind": "VehicleCosmetic", "name": "Bullbar", "itemId": COSMETIC, "dlc": 0},
        {"kind": "VehicleUpgrade", "name": "Engine", "itemId": UPGRADE, "dlc": 0},
        {"kind": "Livery", "name": "Donor_livery", "itemId": LIVERY, "dlc": 0},
        {"kind": "VehicleCosmetic", "name": "Plate", "itemId": DLC_PLATE, "dlc": 1}]},
    "Other": {"itemId": 12, "parts": [{"kind": "VehicleCosmetic", "name": "Bullbar", "itemId": COSMETIC, "dlc": 0}]},
    "Hidden[CatalogExcluded]": {"itemId": 13, "parts": []},
}
DERIVED = {3000000001: "Donor"}


def save(items):
    return {"Header": {"Version": 11}, "Profile": {"Name": "P", "Inventory": {"Items": items, "VirtualItems": []}}}


def stock_save():
    return save([
        {"Type": su.VEHICLE_ITEM, "Data": {"ItemId": 12, "Count": 1, "InUse": True, "ToolsetIDs": [1]}},
        {"Type": su.SPECIFIC_ITEM, "Data": {"ItemId": COSMETIC, "VehicleStates": [{"VehicleItemId": 12, "Count": 1, "InUse": True}]}},
        {"Type": su.PLAIN_ITEM, "Data": {"ItemId": LIVERY}},           # Count omitted: 0
    ])


def states(data, item_id):
    for item in data["Profile"]["Inventory"]["Items"]:
        if item["Type"] == su.SPECIFIC_ITEM and item["Data"]["ItemId"] == item_id:
            return {s["VehicleItemId"]: s for s in item["Data"]["VehicleStates"]}
    return {}


class Unlock(unittest.TestCase):
    def test_every_car_owns_every_part_it_offers(self):
        data = stock_save()
        su.unlock(data, CARS, DERIVED)
        self.assertEqual(set(states(data, COSMETIC)), {11, 12, 3000000001})
        self.assertEqual(set(states(data, UPGRADE)), {11, 3000000001})      # Other doesn't offer the upgrade
        self.assertEqual(set(states(data, DLC_PLATE)), {11, 3000000001})

    def test_a_derived_vehicle_offers_its_donors_parts(self):
        self.assertEqual(su.offers(CARS, DERIVED)[3000000001], CARS["Donor"]["parts"])

    def test_existing_entries_keep_their_fields(self):
        data = stock_save()
        su.unlock(data, CARS, DERIVED)
        self.assertEqual(states(data, COSMETIC)[12], {"VehicleItemId": 12, "Count": 1, "InUse": True})
        car = next(i["Data"] for i in data["Profile"]["Inventory"]["Items"] if i["Data"]["ItemId"] == 12)
        self.assertEqual(car, {"ItemId": 12, "Count": 1, "InUse": True, "ToolsetIDs": [1]})

    def test_a_livery_with_count_zero_becomes_owned(self):
        data = stock_save()
        su.unlock(data, CARS, DERIVED)
        livery = [i["Data"] for i in data["Profile"]["Inventory"]["Items"] if i["Data"]["ItemId"] == LIVERY]
        self.assertEqual(livery, [{"ItemId": LIVERY, "Count": 1}])

    def test_catalogue_cars_become_owned_but_not_excluded_ones(self):
        data = stock_save()
        report = su.unlock(data, CARS, DERIVED)
        owned = {i["Data"]["ItemId"] for i in data["Profile"]["Inventory"]["Items"] if i["Type"] == su.VEHICLE_ITEM}
        self.assertEqual(owned, {11, 12, 3000000001})
        self.assertEqual(sorted(report["cars"]), ["Donor", "derived 3000000001"])

    def test_a_second_run_changes_nothing(self):
        data = stock_save()
        su.unlock(data, CARS, DERIVED)
        before = su.dumps(data)
        report = su.unlock(data, CARS, DERIVED)
        self.assertEqual(su.dumps(data), before)
        self.assertEqual((report["states"], report["parts"], report["liveries"], report["cars"]), (0, 0, 0, []))

    def test_the_upgrade_gap_counts_stock_cars_only(self):
        data = stock_save()
        names = su.stock_names(CARS)
        self.assertEqual(names, ["Donor", "Other"])
        self.assertEqual(su.upgrade_gap(data, CARS, names), (1, 1))     # Donor's upgrade; Other offers none
        su.unlock(data, CARS, DERIVED)
        self.assertEqual(su.upgrade_gap(data, CARS, names), (0, 1))

    def test_a_count_lands_where_the_game_writes_it(self):
        data = save([{"Type": su.PLAIN_ITEM, "Data": {"ItemId": LIVERY, "InUse": True}}])
        su.unlock(data, CARS, DERIVED, own_cars=False)
        livery = next(i["Data"] for i in data["Profile"]["Inventory"]["Items"] if i["Data"]["ItemId"] == LIVERY)
        self.assertEqual(list(livery), ["ItemId", "Count", "InUse"])


    def test_written_like_the_game_one_compact_line(self):
        text = su.dumps(stock_save())
        self.assertNotIn("\n", text)
        self.assertNotIn('": ', text)


class SwapAndRestore(unittest.TestCase):
    """werkstatt's save-test and save-real against a temporary My Games folder, kill points included."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="werkstatt-save-")
        self.addCleanup(shutil.rmtree, self.tmp)
        self.saves = os.path.join(self.tmp, "Saves")
        os.makedirs(os.path.join(self.saves, "FogOfWar"))
        self.save = os.path.join(self.saves, "Player1.json")
        self.real = json.dumps(stock_save())
        self.write(self.save, self.real)
        self.write(self.save + ".bak", "previous")
        self.write(os.path.join(self.saves, "FogOfWar", "Player1_R1A1.fow"), "explored")
        self.before = self.tree(self.saves)
        env = mock.patch.dict(os.environ, {"MY_GAMES": self.tmp, "PROFILE": "", "FORCE": ""})
        env.start()
        self.addCleanup(env.stop)
        for p in (mock.patch.object(ws, "game_running", return_value=False),
                  mock.patch.object(ws, "parts_catalogue", return_value=CARS),
                  mock.patch.object(ws, "vehicles", return_value=["v"]),
                  mock.patch.object(ws, "manifest", return_value={"itemId": 3000000001, "donor": "Donor"})):
            p.start()
            self.addCleanup(p.stop)
        self.paths = ws.test_save_paths()

    def write(self, path, text):
        with open(path, "w") as f:
            f.write(text)

    def tree(self, top, fresh=()):
        """Every file under top: (relative path, content, mtime); the files in `fresh` without their mtime."""
        out = []
        for folder, _dirs, files in os.walk(top):
            for name in files:
                path = os.path.join(folder, name)
                rel = os.path.relpath(path, top)
                out.append((rel, open(path).read(), None if rel in fresh else os.stat(path).st_mtime_ns))
        return sorted(out)

    def restored(self):
        """The real folder is back: every file exact, the save's own mtime made fresh."""
        return self.tree(self.saves, fresh=("Player1.json",)) == [
            (rel, text, None if rel == "Player1.json" else mtime) for rel, text, mtime in self.before]

    def run_quiet(self, command):
        with contextlib.redirect_stdout(io.StringIO()):
            return command([])

    def filed(self):
        backups = self.paths["backups"]
        return sorted(os.listdir(backups)) if os.path.isdir(backups) else []

    def test_swap_then_restore_gives_back_the_real_folder_exactly(self):
        self.assertEqual(self.run_quiet(ws.cmd_save_test), 0)
        self.assertEqual(set(states(json.load(open(self.save)), COSMETIC)), {11, 12, 3000000001})
        self.assertEqual(self.tree(self.paths["parked"]), self.before)
        self.write(self.save + ".bak", "the game's backup of the test save")
        self.assertEqual(self.run_quiet(ws.cmd_save_real), 0)
        self.assertTrue(self.restored())          # renamed back: contents and mtimes
        self.assertEqual(len([n for n in self.filed() if "-test-save-" in n]), 1)   # the played test save, kept
        self.assertIsNone(ws.test_save_status())

    def test_a_second_swap_refuses(self):
        self.run_quiet(ws.cmd_save_test)
        self.assertEqual(self.run_quiet(ws.cmd_save_test), 1)
        self.assertEqual(self.tree(self.paths["parked"]), self.before)

    def test_a_save_that_already_looks_like_a_test_save_isnt_parked(self):
        data = stock_save()
        su.unlock(data, CARS, DERIVED)
        self.write(self.save, su.dumps(data))
        self.assertEqual(self.run_quiet(ws.cmd_save_test), 1)
        self.assertFalse(os.path.exists(self.paths["parked"]))

    def test_nothing_happens_while_the_game_runs(self):
        with mock.patch.object(ws, "game_running", return_value=True):
            self.assertEqual(self.run_quiet(ws.cmd_save_test), 1)
        self.assertEqual(self.tree(self.saves), self.before)
        self.assertIsNone(ws.test_save_status())

    def test_the_game_starting_during_the_swap_changes_nothing(self):
        calls = iter([False, True])                                   # free at the check, running at the rename
        with mock.patch.object(ws, "game_running", side_effect=lambda: next(calls, True)):
            self.assertEqual(self.run_quiet(ws.cmd_save_test), 1)
        self.assertEqual(self.tree(self.saves), self.before)
        self.assertFalse(os.path.exists(self.paths["note"]))
        self.assertFalse(os.path.exists(self.paths["building"]))

    def test_restore_without_a_test_save_is_a_no_op(self):
        self.assertEqual(self.run_quiet(ws.cmd_save_real), 0)
        self.assertEqual(self.tree(self.saves), self.before)

    def test_save_real_refuses_when_the_save_in_place_isnt_the_test_save(self):
        self.run_quiet(ws.cmd_save_test)
        self.write(self.save, json.dumps(stock_save()) + " ")         # e.g. Steam Cloud put a real save back
        replaced = self.tree(self.saves)
        self.assertEqual(self.run_quiet(ws.cmd_save_real), 1)
        self.assertEqual(self.tree(self.saves), replaced)
        self.assertEqual(self.tree(self.paths["parked"]), self.before)
        with mock.patch.dict(os.environ, {"FORCE": "1"}):
            self.assertEqual(self.run_quiet(ws.cmd_save_real), 0)
        self.assertTrue(self.restored())
        replaced_folder = [n for n in self.filed() if "-replaced-" in n]
        self.assertEqual(len(replaced_folder), 1)                     # named for what it holds
        filed = os.path.join(self.paths["backups"], replaced_folder[0])
        self.assertEqual([f for f in self.tree(filed) if f[0] != "test-save.json"], replaced)   # kept, with its note

    def test_a_played_test_save_is_still_recognised(self):
        self.run_quiet(ws.cmd_save_test)
        data = json.load(open(self.save))
        data["Profile"]["Name"] = "played"
        self.write(self.save, su.dumps(data))
        self.assertEqual(self.run_quiet(ws.cmd_save_real), 0)
        self.assertTrue(self.restored())

    def test_a_missing_note_still_restores_and_still_blocks_a_second_swap(self):
        self.run_quiet(ws.cmd_save_test)
        os.remove(self.paths["note"])
        self.assertEqual(self.run_quiet(ws.cmd_save_test), 1)
        self.assertEqual(self.run_quiet(ws.cmd_save_real), 0)
        self.assertTrue(self.restored())

    def test_save_test_cut_off_after_parking_finishes_or_rolls_back(self):
        for finish in (ws.cmd_save_test, ws.cmd_save_real):
            with self.subTest(next_command=finish.__name__):
                with mock.patch.object(ws, "_land_test_save", side_effect=KeyboardInterrupt):
                    with self.assertRaises(KeyboardInterrupt):
                        self.run_quiet(ws.cmd_save_test)
                self.assertFalse(os.path.exists(self.saves))
                self.assertEqual(self.tree(self.paths["parked"]), self.before)
                self.assertEqual(self.run_quiet(finish), 0)
                if finish is ws.cmd_save_test:
                    self.assertEqual(set(states(json.load(open(self.save)), COSMETIC)), {11, 12, 3000000001})
                    self.assertEqual(self.run_quiet(ws.cmd_save_real), 0)
                self.assertTrue(self.restored())
                self.before = self.tree(self.saves)      # the restore made the save's mtime fresh

    def test_save_real_cut_off_between_its_renames_finishes_next_time(self):
        self.run_quiet(ws.cmd_save_test)
        real_rename = ws.rename_or_explain
        calls = []

        def rename_then_die(src, dst, **kw):
            calls.append(src)
            if len(calls) == 2:
                raise KeyboardInterrupt
            return real_rename(src, dst, **kw)
        with mock.patch.object(ws, "rename_or_explain", side_effect=rename_then_die):
            with self.assertRaises(KeyboardInterrupt):
                self.run_quiet(ws.cmd_save_real)
        self.assertFalse(os.path.exists(self.saves))
        self.assertEqual(self.tree(self.paths["parked"]), self.before)
        self.assertEqual(self.run_quiet(ws.cmd_save_real), 0)
        self.assertTrue(self.restored())
        self.assertEqual(len([n for n in self.filed() if "-test-save-" in n]), 1)
        self.assertEqual(len([n for n in self.filed() if "-real-" in n]), 2)     # one per run, both kept

    def test_two_restores_in_the_same_second_file_two_folders(self):
        with mock.patch.object(ws.time, "strftime", return_value="20261019-120000"):
            for _ in range(2):
                self.assertEqual(self.run_quiet(ws.cmd_save_test), 0)
                self.assertEqual(self.run_quiet(ws.cmd_save_real), 0)
        self.assertEqual([n for n in self.filed() if "test-save" in n],
                         ["Player1-test-save-20261019-120000", "Player1-test-save-20261019-120000-2"])
        self.assertTrue(self.restored())

    def test_save_real_keeps_a_copy_of_the_real_save_and_makes_it_the_newest(self):
        self.run_quiet(ws.cmd_save_test)
        started = time.time_ns()
        self.assertEqual(self.run_quiet(ws.cmd_save_real), 0)
        copies = [n for n in self.filed() if n.startswith("Player1-real-")]
        self.assertEqual(len(copies), 1)
        copy = os.path.join(self.paths["backups"], copies[0])
        self.assertEqual(open(os.path.join(copy, "Player1.json")).read(), self.real)
        self.assertEqual(open(os.path.join(copy, "Player1.json.bak")).read(), "previous")
        self.assertEqual(open(self.save).read(), self.real)
        self.assertGreaterEqual(os.stat(self.save).st_mtime_ns, started)

    def test_a_launch_without_the_plugin_still_counts_as_the_test_save(self):
        self.run_quiet(ws.cmd_save_test)
        data = json.load(open(self.save))
        for item in data["Profile"]["Inventory"]["Items"]:      # the game drops states of cars it doesn't know
            if item["Type"] == su.SPECIFIC_ITEM:
                item["Data"]["VehicleStates"] = [st for st in item["Data"]["VehicleStates"] if st["VehicleItemId"] != 3000000001]
        self.write(self.save, su.dumps(data))
        self.assertEqual(self.run_quiet(ws.cmd_save_real), 0)
        self.assertTrue(self.restored())

    def test_a_new_truck_or_a_new_stock_car_doesnt_break_the_check(self):
        self.run_quiet(ws.cmd_save_test)
        self.write(self.save, open(self.save).read() + " ")      # played
        more = dict(CARS, NewCar={"itemId": 14, "parts": [{"kind": "VehicleUpgrade", "name": "Winch", "itemId": 105, "dlc": 0}]})
        with mock.patch.object(ws, "parts_catalogue", return_value=more), \
             mock.patch.object(ws, "manifest", return_value={"itemId": 3000000009, "donor": "Donor"}):
            self.assertEqual(self.run_quiet(ws.cmd_save_real), 0)
        self.assertTrue(self.restored())

    def test_save_add_refuses_while_a_test_save_is_in_place(self):
        self.run_quiet(ws.cmd_save_test)
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertTrue(ws.save_add_blocked())
        self.assertIn("make save-real", out.getvalue())

    def test_the_status_line_says_untouched_then_played(self):
        self.run_quiet(ws.cmd_save_test)
        self.assertIn("untouched", ws.test_save_status())
        self.write(self.save, open(self.save).read() + " ")
        self.assertIn("played", ws.test_save_status())


class SaveAddPrune(unittest.TestCase):
    """add_vehicle_to_save.py keeps the last ten of its own backups and leaves other files alone."""

    def test_its_new_backup_survives_test_save_copies(self):
        tmp = tempfile.mkdtemp(prefix="werkstatt-prune-")
        self.addCleanup(shutil.rmtree, tmp)
        saves, backups = os.path.join(tmp, "Saves"), os.path.join(tmp, "DieKollektion", "backups")
        os.makedirs(saves)
        os.makedirs(backups)
        for n in range(12):
            open(os.path.join(backups, f"Player1-test-save-202610{n:02d}-120000.json"), "w").write("{}")
        save_path = os.path.join(saves, "Player1.json")
        open(save_path, "w").write(json.dumps(stock_save()))
        import subprocess
        r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "add_vehicle_to_save.py"), save_path, "3000000002"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        names = os.listdir(backups)
        self.assertEqual(len([n for n in names if n.startswith("Player1-test-save-")]), 12)
        # The save held no trucks, so this first add's backup is the never-pruned original.
        self.assertEqual(len([n for n in names if n.startswith("Player1-original-")]), 1)


if __name__ == "__main__":
    unittest.main()
