"""The test save (`make save-test`): tools/save_unlock.py on synthetic saves, and werkstatt's swap and restore."""
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
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

    def test_written_like_the_game_one_compact_line(self):
        text = su.dumps(stock_save())
        self.assertNotIn("\n", text)
        self.assertNotIn('": ', text)


class SwapAndRestore(unittest.TestCase):
    """werkstatt's save-test and save-real against a temporary My Games folder."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="werkstatt-save-")
        self.addCleanup(shutil.rmtree, self.tmp)
        saves = os.path.join(self.tmp, "Saves")
        os.makedirs(saves)
        self.save = os.path.join(saves, "Player1.json")
        self.real = json.dumps(stock_save())
        open(self.save, "w").write(self.real)
        open(self.save + ".bak", "w").write("previous")
        env = mock.patch.dict(os.environ, {"MY_GAMES": self.tmp, "PROFILE": ""})
        env.start()
        self.addCleanup(env.stop)
        for p in (mock.patch.object(ws, "game_running", return_value=False),
                  mock.patch.object(ws, "parts_catalogue", return_value=CARS),
                  mock.patch.object(ws, "vehicles", return_value=["v"]),
                  mock.patch.object(ws, "manifest", return_value={"itemId": 3000000001, "donor": "Donor"})):
            p.start()
            self.addCleanup(p.stop)

    def run_quiet(self, command):
        with contextlib.redirect_stdout(io.StringIO()):
            return command([])

    def test_swap_then_restore_gives_back_the_real_save(self):
        self.assertEqual(self.run_quiet(ws.cmd_save_test), 0)
        self.assertEqual(set(states(json.load(open(self.save)), COSMETIC)), {11, 12, 3000000001})
        open(self.save + ".bak", "w").write("the game's backup of the test save")
        self.assertEqual(self.run_quiet(ws.cmd_save_real), 0)
        self.assertEqual(open(self.save).read(), self.real)
        self.assertEqual(open(self.save + ".bak").read(), "previous")
        self.assertIsNone(ws.test_save_status())

    def test_a_second_swap_refuses(self):
        self.run_quiet(ws.cmd_save_test)
        self.assertEqual(self.run_quiet(ws.cmd_save_test), 1)

    def test_nothing_happens_while_the_game_runs(self):
        with mock.patch.object(ws, "game_running", return_value=True):
            self.assertEqual(self.run_quiet(ws.cmd_save_test), 1)
        self.assertEqual(open(self.save).read(), self.real)
        self.assertIsNone(ws.test_save_status())

    def test_restore_without_a_test_save_is_a_no_op(self):
        self.assertEqual(self.run_quiet(ws.cmd_save_real), 0)
        self.assertEqual(open(self.save).read(), self.real)


if __name__ == "__main__":
    unittest.main()
