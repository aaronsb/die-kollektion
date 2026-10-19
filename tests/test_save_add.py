"""make save-add: our trucks get their cars, and a state on every cosmetic their donor owns (issue #25)."""
import copy
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

TESTS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TESTS)
sys.path.insert(0, os.path.join(ROOT, "tools"))
import add_vehicle_to_save as av  # noqa: E402
import save_unlock as su  # noqa: E402
import werkstatt as ws  # noqa: E402

DONOR, OTHER, TRUCK, LATER = 11, 12, 3000000004, 3000000002
BULLBAR, ROOF_RACK, SNORKEL, ENGINE, UNOWNED = 201, 202, 203, 204, 205
CARS = {
    "Donor": {"itemId": DONOR, "parts": [
        {"kind": "VehicleCosmetic", "name": "Bullbar", "itemId": BULLBAR, "dlc": 0},
        {"kind": "VehicleCosmetic", "name": "Roof_rack", "itemId": ROOF_RACK, "dlc": 0},
        {"kind": "VehicleCosmetic", "name": "Snorkel", "itemId": SNORKEL, "dlc": 0},
        {"kind": "VehicleUpgrade", "name": "Engine", "itemId": ENGINE, "dlc": 0},
        {"kind": "VehicleCosmetic", "name": "Unowned", "itemId": UNOWNED, "dlc": 0}]},
    "Other": {"itemId": OTHER, "parts": []},
}
TRUCKS = [(TRUCK, "Donor", "Megaloceros")]


def specific(item_id, *states):
    return {"Type": su.SPECIFIC_ITEM, "Data": {"ItemId": item_id, "VehicleStates": [dict(s) for s in states]}}


def fixture():
    """The donor owns three cosmetics and an upgrade; the truck owns one of the cosmetics (unlocked after it was
    registered); another car owns what the catalogue gave it."""
    return {"Header": {"Version": 11}, "Profile": {"Name": "P", "Inventory": {"VirtualItems": [], "Items": [
        {"Type": su.VEHICLE_ITEM, "Data": {"ItemId": DONOR, "Count": 1, "ToolsetIDs": [1]}},
        {"Type": su.VEHICLE_ITEM, "Data": {"ItemId": TRUCK, "Count": 1, "ToolsetIDs": [1]}},
        specific(BULLBAR, {"VehicleItemId": DONOR, "Count": 1}, {"VehicleItemId": OTHER, "Count": 1}),
        specific(ROOF_RACK, {"VehicleItemId": DONOR, "Count": 1}, {"VehicleItemId": OTHER, "Count": 1}),
        specific(SNORKEL, {"VehicleItemId": DONOR, "Count": 1}, {"VehicleItemId": TRUCK, "Count": 1, "InUse": True}),
        specific(ENGINE, {"VehicleItemId": DONOR, "Count": 1}),
        specific(UNOWNED, {"VehicleItemId": OTHER, "Count": 1}),
    ]}}}


def states(save, item_id):
    for item in save["Profile"]["Inventory"]["Items"]:
        if item["Type"] == su.SPECIFIC_ITEM and item["Data"]["ItemId"] == item_id:
            return item["Data"]["VehicleStates"]
    return []


def owned_by(save, vehicle):
    return {i["Data"]["ItemId"] for i in save["Profile"]["Inventory"]["Items"] if i["Type"] == su.SPECIFIC_ITEM
            and any(s["VehicleItemId"] == vehicle and s.get("Count", 0) >= 1 for s in i["Data"]["VehicleStates"])}


class Inherit(unittest.TestCase):
    def test_the_truck_gains_the_donors_cosmetics_it_lacks(self):
        save = fixture()
        lines, changed = av.add(save, [TRUCK], CARS, TRUCKS)
        self.assertTrue(changed)
        self.assertEqual(owned_by(save, TRUCK), {BULLBAR, ROOF_RACK, SNORKEL})       # 3 the donor owns, 1 already
        self.assertIn("Megaloceros: 2 cosmetics from the Donor", lines)

    def test_a_second_run_adds_nothing(self):
        save = fixture()
        av.add(save, [TRUCK], CARS, TRUCKS)
        once = su.dumps(save)
        lines, changed = av.add(save, [TRUCK], CARS, TRUCKS)
        self.assertFalse(changed)
        self.assertEqual(su.dumps(save), once)
        self.assertIn("Megaloceros: already has every cosmetic the Donor has", lines)

    def test_upgrades_and_unowned_cosmetics_stay_out(self):
        save = fixture()
        av.add(save, [TRUCK], CARS, TRUCKS)
        self.assertNotIn(ENGINE, owned_by(save, TRUCK))       # bought per car, with money
        self.assertNotIn(UNOWNED, owned_by(save, TRUCK))      # the donor doesn't own it

    def test_no_other_cars_states_change(self):
        save = fixture()
        before = {i: [s for s in states(save, i) if s["VehicleItemId"] != TRUCK] for i in (BULLBAR, ROOF_RACK, SNORKEL, ENGINE, UNOWNED)}
        av.add(save, [TRUCK], CARS, TRUCKS)
        after = {i: [s for s in states(save, i) if s["VehicleItemId"] != TRUCK] for i in before}
        self.assertEqual(after, before)
        self.assertEqual(next(s for s in states(save, SNORKEL) if s["VehicleItemId"] == TRUCK),
                         {"VehicleItemId": TRUCK, "Count": 1, "InUse": True})   # the truck's own state, untouched

    def test_the_save_is_byte_identical_outside_the_added_states(self):
        original = fixture()
        save = copy.deepcopy(original)
        av.add(save, [TRUCK], CARS, TRUCKS)
        for item_id in (BULLBAR, ROOF_RACK):
            added = states(save, item_id).pop()
            self.assertEqual(added, {"VehicleItemId": TRUCK, "Count": 1})        # the shape the game writes
        self.assertEqual(su.dumps(save), su.dumps(original))

    def test_an_unowned_state_takes_the_donors_count_before_in_use(self):
        save = fixture()
        states(save, BULLBAR).append({"VehicleItemId": TRUCK, "InUse": False, "Count": 0})
        av.add(save, [TRUCK], CARS, TRUCKS)
        state = next(s for s in states(save, BULLBAR) if s["VehicleItemId"] == TRUCK)
        self.assertEqual(list(state.items()), [("VehicleItemId", TRUCK), ("Count", 1), ("InUse", False)])

    def test_a_truck_not_in_the_save_gets_nothing(self):
        save = fixture()
        lines, _ = av.add(save, [TRUCK], CARS, TRUCKS + [(LATER, "Donor", "Mastodon")])
        self.assertEqual(owned_by(save, LATER), set())
        self.assertFalse(any(line.startswith("Mastodon") for line in lines))

    def test_a_truck_added_now_gets_the_cosmetics_too(self):
        save = fixture()
        lines, _ = av.add(save, [TRUCK, LATER], CARS, TRUCKS + [(LATER, "Donor", "Mastodon")])
        self.assertEqual(owned_by(save, LATER), {BULLBAR, ROOF_RACK, SNORKEL})
        self.assertIn("added 3000000002", lines)
        self.assertIn("Mastodon: 3 cosmetics from the Donor", lines)


class Command(unittest.TestCase):
    """add_vehicle_to_save.py run as make save-add runs it: backup first, one compact line, idempotent."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="werkstatt-saveadd-")
        self.addCleanup(shutil.rmtree, self.tmp)
        os.makedirs(os.path.join(self.tmp, "Saves"))
        self.save = os.path.join(self.tmp, "Saves", "Player1.json")
        with open(self.save, "w", encoding="utf-8") as f:
            f.write(su.dumps(fixture()))
        self.parts = os.path.join(self.tmp, "parts.json")
        json.dump({"cars": CARS}, open(self.parts, "w"))

    def run_tool(self):
        return subprocess.run([sys.executable, os.path.join(ROOT, "tools", "add_vehicle_to_save.py"), self.save, str(TRUCK),
                               "--parts", self.parts, "--truck", f"{TRUCK}:Donor:Megaloceros"], capture_output=True, text=True)

    def sha(self):
        return hashlib.sha256(open(self.save, "rb").read()).hexdigest()

    def test_first_run_backs_up_and_adds_second_run_changes_nothing(self):
        original = self.sha()
        r = self.run_tool()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Megaloceros: 2 cosmetics from the Donor", r.stdout)
        backups = os.listdir(os.path.join(self.tmp, "DieKollektion", "backups"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(hashlib.sha256(open(os.path.join(self.tmp, "DieKollektion", "backups", backups[0]), "rb").read()).hexdigest(), original)
        text = open(self.save, encoding="utf-8").read()
        self.assertNotIn("\n", text)                                             # one line, as the game writes it
        first = self.sha()
        r = self.run_tool()
        self.assertIn("Nothing to add; the save is unchanged.", r.stdout)
        self.assertEqual(self.sha(), first)
        self.assertEqual(len(os.listdir(os.path.join(self.tmp, "DieKollektion", "backups"))), 1)


class SaveAdd(unittest.TestCase):
    """werkstatt.py save-add hands the trucks and the parts list to the tool, or says why it can't."""

    def run_save_add(self, cars):
        tmp = tempfile.mkdtemp(prefix="werkstatt-saveadd-ws-")
        self.addCleanup(shutil.rmtree, tmp)
        os.makedirs(os.path.join(tmp, "Saves"))
        open(os.path.join(tmp, "Saves", "Player1.json"), "w").write(su.dumps(fixture()))
        with mock.patch.dict(os.environ, {"MY_GAMES": tmp, "PROFILE": ""}), \
             mock.patch.object(ws, "parts_catalogue", return_value=cars), \
             mock.patch.object(ws, "game_running", return_value=False), \
             mock.patch.object(ws, "save_add_blocked", return_value=False), \
             mock.patch.object(ws.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)) as run, \
             mock.patch("sys.stdout"):
            self.assertEqual(ws.cmd_save_add([]), 0)
        return run.call_args.args[0]

    def test_it_passes_each_truck_and_its_donor(self):
        cmd = self.run_save_add({"Mammoth": {"itemId": 1, "parts": []}})
        self.assertIn("--parts", cmd)
        trucks = [cmd[i + 1] for i, a in enumerate(cmd) if a == "--truck"]
        self.assertEqual(sorted(trucks), sorted(f"{i}:Mammoth:{n}" for n, i in ws.ITEM_IDS.items()))

    def test_without_the_parts_list_it_adds_the_cars_only(self):
        cmd = self.run_save_add(None)
        self.assertNotIn("--parts", cmd)
        self.assertNotIn("--truck", cmd)


if __name__ == "__main__":
    unittest.main()
