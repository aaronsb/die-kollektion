"""Add VehicleItem entries to an Over the Hill save, backing the save up first.

Usage: python3 add_vehicle_to_save.py <Player1.json> <ItemId> [<ItemId> ...]

Close the game first. Steam Cloud may restore the old save on next launch;
if it does, disable cloud sync for the game while testing.
"""
import json, shutil, sys, time

path, ids = sys.argv[1], [int(a) for a in sys.argv[2:]]
shutil.copy2(path, f"{path}.pre-mod-{int(time.time())}")
save = json.load(open(path))
items = save["Profile"]["Inventory"]["Items"]
owned = {i["Data"]["ItemId"] for i in items}
for item_id in ids:
    if item_id in owned:
        print(f"{item_id} already owned")
        continue
    items.append({"Type": "VehicleItem, Assembly-CSharp",
                  "Data": {"ItemId": item_id, "Count": 1, "ToolsetIDs": [2317836723]}})
    print(f"added {item_id}")
json.dump(save, open(path, "w"), indent=1)
