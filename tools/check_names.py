"""Fails if a real manufacturer or model name appears anywhere but Die Kollektion's catalogue.

Usage: python3 tools/check_names.py

Nothing real reaches the game, and file, part and tool names are fictional too. Real vehicle data
lives only in each definition's "listing" block (written by a generator's "listing" dict, or by hand)
and in the README catalogue that tools/catalogue.py generates from it (between the <!-- catalogue -->
markers). Checked, for every tracked file:
- in-game strings: each definition's displayName, description and names;
- paths;
- contents: text files (definitions with their listing removed, Python outside "listing" dict
  entries, the README outside the catalogue) and the strings inside the Blender masters.
The deny list is the fixed one below plus each definition's listing.real make and model. Exits 1 on
any hit.
"""
import ast, json, os, re, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DENY = [r"mercedes", r"\bbenz\b", r"daimler", r"unimog", r"\bu ?1[0-9]{3} ?l?\b", r"\bdoka\b",
        r"\b(406|411|416|425|435)[- ]series\b", r"\bseries (406|411|416|425|435)\b", r"camperbasis", r"\brhino\b", r"\b3dm\b"]
SELF = "tools/check_names.py"
BEGIN, END = "<!-- catalogue -->", "<!-- /catalogue -->"


def tracked():
    try:
        out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
        return out.split()
    except (OSError, subprocess.CalledProcessError):
        # A release zip has no git, but lists the files it ships (tools/release.py); the rest of the folder is
        # the player's own (.venv/, extracted/, build output) and isn't checked.
        listed = os.path.join(ROOT, "RELEASE-FILES.txt")
        if os.path.isfile(listed):
            return [l for l in open(listed).read().splitlines() if l and os.path.isfile(os.path.join(ROOT, l))]
        return [os.path.relpath(os.path.join(d, f), ROOT) for d, _, fs in os.walk(ROOT) if ".git" not in d for f in fs]


def blend_strings(path):
    raw = open(path, "rb").read()
    if raw[:4] == b"\x28\xb5\x2f\xfd":
        try:
            from compression import zstd
            raw = zstd.decompress(raw)
        except ImportError:
            raw = subprocess.run(["zstd", "-dc", path], capture_output=True, check=True).stdout
    return "\n".join(m.decode() for m in re.findall(rb"[\x20-\x7e]{5,}", raw))


def listing_lines(source):
    """Line numbers of every "listing": {...} entry in a Python file's dict literals."""
    lines = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if isinstance(key, ast.Constant) and key.value == "listing":
                    lines.update(range(key.lineno, value.end_lineno + 1))
    return lines


def main():
    files = tracked()
    definitions = {f: json.load(open(os.path.join(ROOT, f))) for f in files if f.startswith("vehicles/") and f.endswith("/vehicle.json")}
    deny = list(DENY)
    for d in definitions.values():
        real = d.get("listing", {}).get("real", {})
        deny += [re.escape(real[k]) for k in ("make", "model") if real.get(k)]
    pattern = re.compile("|".join(deny), re.IGNORECASE)
    hits = []

    def scan(where, text, allowed=frozenset()):
        for n, line in enumerate(text.splitlines(), 1):
            if n in allowed:
                continue
            for m in pattern.finditer(line):
                hits.append(f"{where}:{n}: {m.group(0)!r}")

    for f, d in definitions.items():
        in_game = {k: d[k] for k in ("displayName", "description", "names", "category") if k in d}
        scan(f"{f} (in-game strings)", json.dumps(in_game, ensure_ascii=False))
    for f in files:
        scan(f"{f} (path)", f)
        if f == SELF or f.startswith("LICENSE"):
            continue
        path = os.path.join(ROOT, f)
        if f in definitions:
            scan(f, json.dumps({k: v for k, v in definitions[f].items() if k != "listing"}, indent=2, ensure_ascii=False))
        elif f.endswith(".blend"):
            scan(f, blend_strings(path))
        else:
            try:
                text = open(path, encoding="utf-8").read()
            except UnicodeDecodeError:
                continue
            if f == "README.md" and BEGIN in text and END in text:
                text = text[:text.index(BEGIN)] + text[text.index(END):]
            scan(f, text, listing_lines(text) if f.endswith(".py") else frozenset())
    for h in hits:
        print(h)
    print(f"check_names: {len(hits)} real names outside the catalogue in {len(files)} files")
    sys.exit(1 if hits else 0)


if __name__ == "__main__":
    main()
