#!/usr/bin/env python3
"""The golden outputs: what the Python pipeline makes from the player's game, frozen so the C# port (`kollektion
extract`, `kollektion build`) can be compared with it file by file. Game-derived, so it stays local in build/.

    python3 tools/golden.py snapshot                 copy extracted/ and every vehicle's build/, generated/ and icon
                                                     into build/golden/, with their sha256 in build/golden.json
    python3 tools/golden.py compare DIR [PREFIX]     compare DIR with build/golden/PREFIX (e.g. `extracted`, or
                                                     `vehicles/glyptodon/build`): identical, missing, extra, and for
                                                     each differing file how: OBJ coordinates (largest difference),
                                                     JSON values, PNG pixels (with Pillow from .venv)
Exit 1 when anything differs or is missing.
"""
import hashlib
import json
import math
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOLDEN = os.path.join(ROOT, "build", "golden")


def sha256(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def files_under(root):
    out = {}
    for d, _, files in os.walk(root):
        for f in files:
            p = os.path.join(d, f)
            out[os.path.relpath(p, root).replace(os.sep, "/")] = p
    return out


def snapshot():
    shutil.rmtree(GOLDEN, ignore_errors=True)
    shutil.copytree(os.path.join(ROOT, "extracted"), os.path.join(GOLDEN, "extracted"))
    vehicles = os.path.join(ROOT, "vehicles")
    for name in sorted(os.listdir(vehicles)):
        src = os.path.join(vehicles, name)
        for sub in ("build", "generated"):
            if os.path.isdir(os.path.join(src, sub)):
                shutil.copytree(os.path.join(src, sub), os.path.join(GOLDEN, "vehicles", name, sub))
        for f in ("icon.png", "icon.svg"):
            if os.path.isfile(os.path.join(src, f)):
                os.makedirs(os.path.join(GOLDEN, "vehicles", name), exist_ok=True)
                shutil.copy2(os.path.join(src, f), os.path.join(GOLDEN, "vehicles", name, f))
    hashes = {rel: sha256(p) for rel, p in sorted(files_under(GOLDEN).items())}
    with open(os.path.join(ROOT, "build", "golden.json"), "w") as f:
        json.dump({"notes": "sha256 of the Python pipeline's outputs (make extract, make build), the reference the C# "
                            "port must reproduce. Game-derived: local only.", "files": hashes}, f, indent=1)
    print(f"{len(hashes)} files in build/golden/")
    return 0


def obj_numbers(path):
    """Per line: the keyword and its numbers, so two OBJs compare by value."""
    rows = []
    for line in open(path, encoding="utf-8", errors="replace"):
        parts = line.split()
        if not parts or parts[0].startswith("#"):
            continue
        nums = []
        for p in parts[1:]:
            try:
                nums.append(float(p))
            except ValueError:
                nums.append(p)
        rows.append((parts[0], nums))
    return rows


def diff_obj(a, b):
    ra, rb = obj_numbers(a), obj_numbers(b)
    if len(ra) != len(rb):
        return f"{len(ra)} lines vs {len(rb)} expected"
    worst, where = 0.0, None
    for i, ((ka, na), (kb, nb)) in enumerate(zip(ra, rb)):
        if ka != kb or len(na) != len(nb):
            return f"line {i + 1}: {ka} {len(na)} values vs {kb} {len(nb)} expected"
        for x, y in zip(na, nb):
            if isinstance(x, float) and isinstance(y, float):
                d = abs(x - y)
                if d > worst:
                    worst, where = d, i + 1
            elif x != y:
                return f"line {i + 1}: {x} vs {y} expected"
    return f"same values, largest difference {worst:g} (line {where})" if worst else "same values, different text"


def diff_json(a, b):
    def walk(x, y, path):
        if isinstance(x, dict) and isinstance(y, dict):
            for k in sorted(set(x) | set(y)):
                if k not in x or k not in y:
                    return f"{path}/{k}: {'missing' if k not in x else 'extra'}"
                r = walk(x[k], y[k], f"{path}/{k}")
                if r:
                    return r
        elif isinstance(x, list) and isinstance(y, list):
            if len(x) != len(y):
                return f"{path}: {len(x)} items vs {len(y)} expected"
            for i, (p, q) in enumerate(zip(x, y)):
                r = walk(p, q, f"{path}[{i}]")
                if r:
                    return r
        elif isinstance(x, float) or isinstance(y, float):
            if not (isinstance(x, (int, float)) and isinstance(y, (int, float)) and math.isclose(x, y, abs_tol=1e-9)):
                return f"{path}: {x} vs {y} expected"
        elif x != y:
            return f"{path}: {x!r} vs {y!r} expected"
        return None
    r = walk(json.load(open(a)), json.load(open(b)), "")
    return r or "same values, different text"


def diff_png(a, b):
    try:
        from PIL import Image, ImageChops
    except ImportError:
        return "differs (Pillow not available to compare pixels; run with .venv/bin/python)"
    ia, ib = Image.open(a), Image.open(b)
    if ia.size != ib.size:
        return f"{ia.size} vs {ib.size} expected"
    ia, ib = ia.convert("RGBA"), ib.convert("RGBA")
    # All four channels: getbbox() on RGBA looks at alpha alone unless told otherwise.
    box = ImageChops.difference(ia, ib).getbbox(alpha_only=False)
    if not box:
        return "same pixels, different file"
    a, b = ia.tobytes(), ib.tobytes()
    n = sum(1 for i in range(0, len(a), 4) if a[i:i + 4] != b[i:i + 4])
    return f"{n} pixels differ (within {box})"


def compare(directory, prefix=""):
    want = files_under(os.path.join(GOLDEN, prefix))
    got = files_under(directory)
    if not want:
        print(f"Nothing in build/golden/{prefix}; run `python3 tools/golden.py snapshot` first.")
        return 1
    same, problems = 0, []
    for rel in sorted(set(want) | set(got)):
        if rel not in got:
            problems.append(f"missing    {rel}")
        elif rel not in want:
            problems.append(f"extra      {rel}")
        elif sha256(got[rel]) == sha256(want[rel]):
            same += 1
        else:
            how = {".obj": diff_obj, ".json": diff_json, ".png": diff_png}.get(os.path.splitext(rel)[1])
            problems.append(f"differs    {rel}: {how(got[rel], want[rel]) if how else 'bytes differ'}")
    print(f"{same} of {len(want)} files identical to build/golden/{prefix}")
    for p in problems:
        print("  " + p)
    return 1 if problems else 0


if __name__ == "__main__":
    args = sys.argv[1:]
    if args[:1] == ["snapshot"]:
        sys.exit(snapshot())
    if args[:1] == ["compare"] and len(args) in (2, 3):
        sys.exit(compare(args[1], args[2] if len(args) == 3 else ""))
    print(__doc__)
    sys.exit(2)
