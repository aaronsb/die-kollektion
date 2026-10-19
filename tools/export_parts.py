"""Write every car's purchasable parts (CarInfo.UpgradesLists) to JSON, for the test save (`make save-test`).

Usage: python3 -I export_parts.py <out.json> <bundle> [<bundle> ...]
       (the scriptableobjects and cars bundles plus the monoscripts bundle, which names each MonoBehaviour's class)

Output: {"cars": {"<CarInfo name>": {"itemId": n, "parts": [{"kind", "name", "itemId", "dlc"}, ...]}}}, kinds
VehicleCosmetic, VehicleUpgrade and Livery; "dlc" is the part's RequiredDlc (0: none). Read from the player's own
install into extracted/, which is never committed.
"""
import json, os, sys, UnityPy

UnityPy.config.FALLBACK_UNITY_VERSION = "6000.0.75f1"
KINDS = ("VehicleCosmetic", "VehicleUpgrade", "Livery")

out, bundles = sys.argv[1], sys.argv[2:]
env = UnityPy.load(*bundles)
parts, lists, cars = {}, {}, []
for obj in env.objects:
    if obj.type.name != "MonoBehaviour":
        continue
    try:
        tree = obj.read_typetree()
        kind = obj.read().m_Script.read().m_ClassName
    except Exception:
        continue
    if kind in KINDS:
        parts[obj.path_id] = {"kind": kind, "name": tree["m_Name"], "itemId": tree["ItemId"], "dlc": tree.get("RequiredDlc", 0)}
    elif kind == "UpgradesLists":
        lists[obj.path_id] = [p["m_PathID"] for p in tree.get("Parts", [])]
    elif kind == "CarInfo":
        cars.append(tree)
result = {}
for car in sorted(cars, key=lambda c: c["m_Name"]):
    ids = lists.get(car["UpgradesLists"]["m_PathID"], [])
    result[car["m_Name"]] = {"itemId": car["ItemId"], "parts": [parts[i] for i in ids if i in parts]}
if not result:
    sys.exit("no CarInfo found: pass the scriptableobjects, cars and monoscripts bundles")
os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
tmp = out + ".tmp"     # a run cut off midway leaves the old file (or none), never a truncated one
with open(tmp, "w", encoding="utf-8") as f:
    json.dump({"cars": result}, f, indent=1)
os.replace(tmp, out)
print(f"{out}: {len(result)} cars, {len(parts)} parts")
