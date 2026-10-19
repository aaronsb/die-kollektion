"""Add VehicleItem entries to an Over the Hill save, backing the save up first.

Usage: python3 add_vehicle_to_save.py <Player1.json> <ItemId> [<ItemId> ...]

Close the game first. The save is only written (and backed up) when an ItemId is missing. Backups go to
DieKollektion/backups/ beside the Saves folder, not into Saves/, which Steam Cloud syncs; the last ten per
profile are kept. Steam Cloud may restore the old save on next launch; if it does, disable cloud sync for the
game while testing.
"""
import glob, json, os, shutil, sys, time

KEEP = 10

path, ids = sys.argv[1], [int(a) for a in sys.argv[2:]]
save = json.load(open(path, encoding="utf-8"))
items = save["Profile"]["Inventory"]["Items"]
owned = {i["Data"]["ItemId"] for i in items}
added = []
for item_id in ids:
    if item_id in owned:
        print(f"{item_id} already owned")
        continue
    items.append({"Type": "VehicleItem, Assembly-CSharp",
                  "Data": {"ItemId": item_id, "Count": 1, "ToolsetIDs": [2317836723]}})
    added.append(item_id)
    print(f"added {item_id}")
if not added:
    print("Nothing to add; the save is unchanged.")
    sys.exit(0)

profile = os.path.splitext(os.path.basename(path))[0]
backups = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(path))), "DieKollektion", "backups")
os.makedirs(backups, exist_ok=True)
backup = os.path.join(backups, f"{profile}-{time.strftime('%Y%m%d-%H%M%S')}.json")
shutil.copy2(path, backup)
for old in sorted(glob.glob(os.path.join(backups, f"{profile}-*.json")))[:-KEEP]:
    os.remove(old)
print(f"Backed up the save to {backup}")

tmp = path + ".werkstatt-tmp"
with open(tmp, "w", encoding="utf-8") as f:
    json.dump(save, f, indent=1, ensure_ascii=False)
os.replace(tmp, path)
