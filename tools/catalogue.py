"""Write Die Kollektion's catalogue from the definitions' listing blocks into the README.

Each in-game name links to its vehicle folder, whose README.md is the vehicle's contact sheet.

Usage: python3 tools/catalogue.py [--check]

The table sits between the <!-- catalogue --> markers in README.md; everything else in the README is
left alone. With --check, exit 1 if the README's table is out of date instead of writing it.
"""
import glob, json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BEGIN, END = "<!-- catalogue -->", "<!-- /catalogue -->"
ORDER = ["Glyptodon", "Megaloceros", "Mastodon", "Megatherium", "Mammoth"]


def cell(text):
    return (text or "").replace("|", "\\|").replace("\n", " ") or "–"


def table():
    rows = []
    for path in glob.glob(os.path.join(ROOT, "vehicles", "*", "vehicle.json")):
        d = json.load(open(path))
        d["_folder"] = os.path.basename(os.path.dirname(path))
        rows.append(d)
    rows.sort(key=lambda d: ORDER.index(d["codename"]) if d["codename"] in ORDER else len(ORDER))
    lines = ["| In game | Family | Variant | Real vehicle | Series | About the real vehicle | How faithful |",
             "|---|---|---|---|---|---|---|"]
    for d in rows:
        lst = d.get("listing", {})
        real = lst.get("real", {})
        name = d.get("displayName") or f"{d['codename']} (patch on the stock car)"
        name = f"[{cell(name)}](vehicles/{d['_folder']}/)"
        vehicle = " ".join(x for x in (real.get("make"), real.get("model")) if x)
        variant = real.get("variant")
        if variant:
            vehicle = f"{vehicle}, {variant}" if vehicle else variant
        years = real.get("years")
        if years:
            vehicle = f"{vehicle} ({years})"
        lines.append("| " + " | ".join([name] + [cell(x) for x in (lst.get("family"), lst.get("variant"), vehicle,
                                                        real.get("series"), real.get("description"), real.get("basis"))]) + " |")
    return "\n".join(lines)


def main():
    readme = os.path.join(ROOT, "README.md")
    text = open(readme).read()
    head, rest = text.split(BEGIN, 1)
    _, tail = rest.split(END, 1)
    new = f"{head}{BEGIN}\n{table()}\n{END}{tail}"
    if "--check" in sys.argv:
        sys.exit(0 if new == text else "README catalogue is out of date: run python3 tools/catalogue.py")
    open(readme, "w").write(new)
    print("README.md: catalogue written")


if __name__ == "__main__":
    main()
