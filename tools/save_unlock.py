"""Build a test save in which every car owns every part it offers, so the garage can preview each one on it.

`make save-test` uses this (tools/werkstatt.py swaps the result in for the real save and keeps the real one
aside; `make save-real` puts it back). The game keeps no "unlocked" flag: what the garage offers on a car is what
the save says that car owns (`InventoryUtility.IsOwned(item, vehicleItemId)`):
- a cosmetic or performance upgrade is a `VehicleSpecificItem` whose `VehicleStates` hold one
  `{"VehicleItemId", "Count"}` per car that owns it; the game adds a state for every car in the catalogue when a
  reward unlocks a cosmetic, and for one car when an upgrade is bought;
- a livery is an `InventoryItem` with a `Count`.
Parts come from each car's `CarInfo.UpgradesLists` (extracted/parts.json, tools/export_parts.py); a derived
vehicle offers its donor's list, since the plugin clones the donor's CarInfo. Parts that need a DLC are added
too: the game's own entitlement check removes them on load when the DLC isn't owned.
"""
import json

VEHICLE_ITEM = "VehicleItem, Assembly-CSharp"
SPECIFIC_ITEM = "VehicleSpecificItem, Assembly-CSharp"
PLAIN_ITEM = "InventoryItem, Assembly-CSharp"
DEFAULT_TOOLSET = [2317836723]     # Portable_winch: what a newly owned car carries in the stock saves


def offers(cars, derived):
    """{vehicle ItemId: its parts}: every stock car in the catalogue, plus each derived vehicle with its donor's."""
    result = {car["itemId"]: car["parts"] for car in cars.values()}
    for item_id, donor in derived.items():
        result[item_id] = cars[donor]["parts"]
    return result


def unlock(save, cars, derived, own_cars=True):
    """Make every car own every part it offers, in place; returns a report of what changed.
    `cars`: parts.json's "cars"; `derived`: {vehicle ItemId: donor CarInfo name}. With `own_cars`, every stock car
    in the catalogue (names marked [CatalogExcluded] only when already owned) and every derived vehicle becomes
    owned too, so a part can be compared across cars."""
    items = save["Profile"]["Inventory"]["Items"]
    by_type = lambda kind: {i["Data"]["ItemId"]: i["Data"] for i in items if i["Type"] == kind}
    specific, plain, vehicles = by_type(SPECIFIC_ITEM), by_type(PLAIN_ITEM), by_type(VEHICLE_ITEM)
    report = {"states": 0, "parts": 0, "liveries": 0, "cars": [], "dlc": 0}

    if own_cars:
        wanted = [(name, car["itemId"]) for name, car in cars.items() if "[CatalogExcluded]" not in name]
        wanted += [(f"derived {item_id}", item_id) for item_id in derived]
        for name, item_id in wanted:
            if item_id not in vehicles:
                data = {"ItemId": item_id, "Count": 1, "ToolsetIDs": list(DEFAULT_TOOLSET)}
                items.append({"Type": VEHICLE_ITEM, "Data": data})
                vehicles[item_id] = data
                report["cars"].append(name)

    dlc = set()
    for vehicle, parts in offers(cars, derived).items():
        for part in parts:
            item_id = part["itemId"]
            if part["dlc"]:
                dlc.add(item_id)
            if part["kind"] == "Livery":
                data = plain.get(item_id)
                if data is None:
                    data = plain[item_id] = {"ItemId": item_id, "Count": 1}
                    items.append({"Type": PLAIN_ITEM, "Data": data})
                    report["liveries"] += 1
                elif data.get("Count", 0) < 1:
                    data["Count"] = 1
                    report["liveries"] += 1
                continue
            data = specific.get(item_id)
            if data is None:
                data = specific[item_id] = {"ItemId": item_id, "VehicleStates": []}
                items.append({"Type": SPECIFIC_ITEM, "Data": data})
                report["parts"] += 1
            state = next((s for s in data["VehicleStates"] if s["VehicleItemId"] == vehicle), None)
            if state is None:
                data["VehicleStates"].append({"VehicleItemId": vehicle, "Count": 1})
                report["states"] += 1
            elif state.get("Count", 0) < 1:
                state["Count"] = 1
                report["states"] += 1
    report["dlc"] = len(dlc)
    return report


def dumps(save):
    """The save as the game writes it: compact one-line JSON."""
    return json.dumps(save, ensure_ascii=False, separators=(",", ":"))
