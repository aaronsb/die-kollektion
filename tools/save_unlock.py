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
too; how the game treats one when the DLC isn't owned (hidden, removed on load, or shown) hasn't been checked.
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


def owned(entry):
    return entry.get("Count", 0) >= 1


def set_owned(entry, id_key, count=1):
    """Count `count`, written where the game writes it: right after the id (states in the save carry only the id and
    Count; any other key keeps its place after them)."""
    rest = {k: v for k, v in entry.items() if k not in (id_key, "Count")}
    head = {id_key: entry[id_key], "Count": count}
    entry.clear()
    entry.update(head)
    entry.update(rest)


def stock_names(cars):
    """The stock cars in the catalogue; [CatalogExcluded] cars (owned copies show in the garage through the plugin)
    still get parts, but they aren't counted or added."""
    return sorted(name for name in cars if "[CatalogExcluded]" not in name)


def upgrade_gap(save, cars, names):
    """(missing, total): performance-upgrade ownerships the named stock cars lack. Upgrades cost money and are bought
    one car at a time, so a played save lacks most; a test save owns them all. Our trucks are left out, so a launch
    without the plugin (which drops their states) or a new truck folder doesn't change it. Reads only."""
    items = save["Profile"]["Inventory"]["Items"]
    specific = {i["Data"]["ItemId"]: i["Data"] for i in items if i["Type"] == SPECIFIC_ITEM}
    missing = total = 0
    for name in names:
        car = cars.get(name)
        for part in (car or {}).get("parts", []):
            if part["kind"] != "VehicleUpgrade" or part["dlc"]:
                continue
            total += 1
            states = specific.get(part["itemId"], {}).get("VehicleStates", [])
            missing += not any(s["VehicleItemId"] == car["itemId"] and owned(s) for s in states)
    return missing, total


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
                elif not owned(data):
                    set_owned(data, "ItemId")
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
            elif not owned(state):
                set_owned(state, "VehicleItemId")
                report["states"] += 1
    report["dlc"] = len(dlc)
    return report


def inherit_cosmetics(save, cars, trucks):
    """Give each derived vehicle a state on every cosmetic its donor owns, in place; returns {vehicle ItemId: count added}.
    A reward that unlocks a cosmetic writes a state for every car in the catalogue at that moment, so cosmetics
    unlocked before a derived vehicle was registered miss it. `trucks`: {vehicle ItemId: donor CarInfo name}. Only
    VehicleCosmetic parts on the donor's list: performance upgrades are bought one car at a time. No other car's
    states change; a state the vehicle already owns is left as it is."""
    items = save["Profile"]["Inventory"]["Items"]
    specific = {i["Data"]["ItemId"]: i["Data"] for i in items if i["Type"] == SPECIFIC_ITEM}
    added = {}
    for vehicle, donor in trucks.items():
        car = cars.get(donor)
        added[vehicle] = 0
        if not car:
            continue
        for part in car["parts"]:
            data = specific.get(part["itemId"]) if part["kind"] == "VehicleCosmetic" else None
            if data is None:
                continue
            source = next((s for s in data["VehicleStates"] if s["VehicleItemId"] == car["itemId"] and owned(s)), None)
            if source is None:
                continue
            state = next((s for s in data["VehicleStates"] if s["VehicleItemId"] == vehicle), None)
            if state is None:
                data["VehicleStates"].append({"VehicleItemId": vehicle, "Count": source["Count"]})
            elif not owned(state):
                set_owned(state, "VehicleItemId", source["Count"])
            else:
                continue
            added[vehicle] += 1
    return added


def dumps(save):
    """The save as the game writes it: compact one-line JSON."""
    return json.dumps(save, ensure_ascii=False, separators=(",", ":"))
