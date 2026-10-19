"""tools/export_upgrades.py's search for a car's cosmetic-parts node, over stand-in transforms (no game files)."""
import os, sys, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import export_upgrades  # noqa: E402


class Ref:
    def __init__(self, target):
        self.target = target

    def read(self):
        return self.target


class Node:
    """Duck-types what the search reads of a UnityPy Transform: m_Children and m_GameObject.m_Name."""

    def __init__(self, name, *children):
        self.m_GameObject = Ref(type("GameObject", (), {"m_Name": name})())
        self.m_Children = [Ref(c) for c in children]


def car(*parts_children):
    return Node("Car_X", Node("Axles"), Node("Parts", *parts_children), Node("Lights"))


class CosmeticRoot(unittest.TestCase):
    def test_the_mammoths_name(self):
        self.assertEqual(export_upgrades.find_cosmetic_root(car(Node("Mammoth"), Node("Mammoth_CosmeticParts"))),
                         "Parts/Mammoth_CosmeticParts")

    def test_a_name_other_than_the_cars(self):
        # The Ding's node is DingDing_SUV_CosmeticParts; the Trailrat's is cased TrailRat_CosmeticParts.
        self.assertEqual(export_upgrades.find_cosmetic_root(car(Node("DingDing"), Node("DingDing_SUV_CosmeticParts"))),
                         "Parts/DingDing_SUV_CosmeticParts")
        self.assertEqual(export_upgrades.find_cosmetic_root(car(Node("TrailRat_CosmeticParts"))), "Parts/TrailRat_CosmeticParts")

    def test_a_car_without_one(self):
        self.assertIsNone(export_upgrades.find_cosmetic_root(car(Node("Thing"))))
        self.assertIsNone(export_upgrades.find_cosmetic_root(Node("Car_X", Node("Axles"))))


class Enums(unittest.TestCase):
    def test_the_interops_upgrade_type_order(self):
        # decomp UpgradeType.cs: Default, Drone, Engine, ..., Winch, Protection; the snorkels' part is WaterResistance (8).
        self.assertEqual(export_upgrades.UPGRADE_TYPES[8], "WaterResistance")
        self.assertEqual(export_upgrades.UPGRADE_TYPES[10], "Winch")
        self.assertEqual(export_upgrades.COSMETIC_TYPES[7], "Roof")


if __name__ == "__main__":
    unittest.main()
