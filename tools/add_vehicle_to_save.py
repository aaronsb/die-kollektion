"""Add VehicleItem entries to an Over the Hill save, and give each derived vehicle its donor's cosmetics, backing the
save up first.

Usage: python3 add_vehicle_to_save.py <Player1.json> <ItemId> [<ItemId> ...] [--parts <parts.json>
                                      --truck <ItemId>:<donor CarInfo name>:<name> ...]

Close the game first. The save is only written (and backed up) when something changes: a missing ItemId, or, with
--parts, a cosmetic the donor owns that the derived vehicle doesn't (cosmetics unlocked before it was registered;
save_unlock.inherit_cosmetics). Running it again adds only what is still missing. Backups go to
DieKollektion/backups/ beside the Saves folder, not into Saves/, which Steam Cloud syncs; the last ten per profile
are kept. The save is written as the game writes it (one compact line). Steam Cloud may restore the old save on next
launch; if it does, disable cloud sync for the game while testing.
"""
import argparse, glob, json, os, shutil, sys, time

import save_unlock

KEEP = 10


def add(save, ids, cars=None, trucks=()):
    """Edit `save` in place; returns the lines to print and whether anything changed."""
    items = save["Profile"]["Inventory"]["Items"]
    owned = {i["Data"]["ItemId"] for i in items if i["Type"] == save_unlock.VEHICLE_ITEM}
    lines, changed = [], False
    for item_id in ids:
        if item_id in owned:
            lines.append(f"{item_id} already owned")
            continue
        items.append({"Type": save_unlock.VEHICLE_ITEM,
                      "Data": {"ItemId": item_id, "Count": 1, "ToolsetIDs": list(save_unlock.DEFAULT_TOOLSET)}})
        owned.add(item_id)
        changed = True
        lines.append(f"added {item_id}")
    if cars is not None:
        mine = {item_id: (donor, name) for item_id, donor, name in trucks if item_id in owned}
        counts = save_unlock.inherit_cosmetics(save, cars, {i: d for i, (d, _) in mine.items()})
        for item_id, (donor, name) in mine.items():
            n = counts.get(item_id, 0)
            changed |= n > 0
            lines.append(f"{name}: {n} cosmetic{'s' if n != 1 else ''} from the {donor}" if n
                         else f"{name}: already has every cosmetic the {donor} has")
    return lines, changed


def write(path, save):
    """Back the save up beside Saves/, then replace it atomically."""
    profile = os.path.splitext(os.path.basename(path))[0]
    backups = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(path))), "DieKollektion", "backups")
    os.makedirs(backups, exist_ok=True)
    backup = os.path.join(backups, f"{profile}-{time.strftime('%Y%m%d-%H%M%S')}.json")
    shutil.copy2(path, backup)
    for old in sorted(glob.glob(os.path.join(backups, f"{profile}-[0-9]*.json")))[:-KEEP]:
        os.remove(old)
    print(f"Backed up the save to {backup}")
    tmp = path + ".werkstatt-tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(save_unlock.dumps(save))
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def truck(text):
    item_id, donor, name = text.split(":", 2)
    return int(item_id), donor, name


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("save")
    ap.add_argument("ids", nargs="+", type=int)
    ap.add_argument("--parts", help="extracted/parts.json: each car's parts, to give derived vehicles their donor's cosmetics")
    ap.add_argument("--truck", action="append", type=truck, default=[], help="<ItemId>:<donor CarInfo name>:<name>")
    args = ap.parse_args(argv)
    save = json.load(open(args.save, encoding="utf-8"))
    cars = json.load(open(args.parts, encoding="utf-8"))["cars"] if args.parts else None
    lines, changed = add(save, args.ids, cars, args.truck)
    print("\n".join(lines))
    if not changed:
        print("Nothing to add; the save is unchanged.")
        return 0
    write(args.save, save)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
