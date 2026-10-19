#!/usr/bin/env python3
"""Check a pack's manifest and build its shareable zip.

Usage: python3 tools/pack.py check [packs/<name>]     validate every pack manifest (or one) with the game's rules
       python3 tools/pack.py build packs/<name>       write dist/<name>-<version>.zip

Standard library only. A pack's `manifest.json` follows the game's official livery manifest (strict JSON,
`liveries` entries need `car` and `texture`, an entry pointing at a missing file is an error) and extends it
with `pack`, `groups`, `vehicles` and `patches` (docs/vehicle_factory.md, "Manifests follow the official
pattern"). Paths in it are relative to the repository root.

The zip holds the manifest, the pack's README, the licences, and the tracked files of each vehicle and patch
folder: manifests, own meshes and Blender masters, icons drawn here, contact sheets, liveries. Nothing that
git ignores goes in (extracted/, each vehicle's build/ and generated/, icons traced from the game's own), and
the build refuses any file whose bytes match a file in extracted/: game assets never ship.
"""
import glob
import hashlib
import json
import os
import subprocess
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def packs(arg=None):
    if arg:
        return [os.path.join(ROOT, arg.rstrip("/"))]
    return sorted(os.path.dirname(p) for p in glob.glob(os.path.join(ROOT, "packs", "*", "manifest.json")))


def problems(folder):
    """Everything wrong with one pack manifest, by the game's rules plus ours; empty when it is valid."""
    path = os.path.join(folder, "manifest.json")
    try:
        # Python's json rejects comments and trailing commas, as the game's loader does.
        m = json.load(open(path))
    except (OSError, ValueError) as e:
        return [f"{os.path.relpath(path, ROOT)}: not valid strict JSON ({e}); the game would skip the whole pack"]
    out = []
    pack = m.get("pack", {})
    for k in ("id", "name", "version", "schema"):
        if k not in pack:
            out.append(f"pack.{k} is missing")
    groups = {g.get("id") for g in m.get("groups", [])}
    for i, g in enumerate(m.get("groups", [])):
        if not g.get("id") or not g.get("name"):
            out.append(f"groups[{i}] needs id and name")
    for kind in ("vehicles", "patches"):
        for i, e in enumerate(m.get(kind, [])):
            p = e.get("path")
            if not p or not os.path.isfile(os.path.join(ROOT, p, "vehicle.json")):
                out.append(f"{kind}[{i}]: {p!r} has no vehicle.json")
            if kind == "vehicles" and e.get("group") not in groups:
                out.append(f"vehicles[{i}]: group {e.get('group')!r} is not one of the pack's groups {sorted(groups)}")
            if kind == "patches" and not e.get("car"):
                out.append(f"patches[{i}]: needs `car`, the stock car it changes")
    for i, e in enumerate(m.get("liveries", [])):
        if not e.get("car") or not e.get("texture"):
            out.append(f"liveries[{i}]: needs `car` and `texture` (the game skips the entry)")
        elif not glob.glob(os.path.join(folder, "**", e["texture"]), recursive=True):
            out.append(f"liveries[{i}]: texture {e['texture']!r} is not in the pack (the game skips the entry)")
    return out


def cmd_check(args):
    bad = 0
    for folder in packs(args[0] if args else None):
        found = problems(folder)
        rel = os.path.relpath(folder, ROOT)
        print(f"pack {rel}: " + ("ok" if not found else "\n  " + "\n  ".join(found)))
        bad += bool(found)
    return 1 if bad else 0


def tracked(path):
    r = subprocess.run(["git", "ls-files", "-z", "--", path], cwd=ROOT, capture_output=True, text=True)
    if r.returncode == 0:
        return [f for f in r.stdout.split("\0") if f]
    # A release zip has no git; it lists the files it ships (tools/release.py).
    listed = os.path.join(ROOT, "RELEASE-FILES.txt")
    prefix = path.rstrip("/") + "/"
    return [f for f in open(listed).read().splitlines() if f.startswith(prefix)] if os.path.isfile(listed) else []


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def cmd_build(args):
    if not args:
        print("Usage: python3 tools/pack.py build packs/<name>")
        return 2
    folder = packs(args[0])[0]
    found = problems(folder)
    if found:
        print("The pack manifest has problems; not building:\n  " + "\n  ".join(found))
        return 1
    m = json.load(open(os.path.join(folder, "manifest.json")))
    rel_pack = os.path.relpath(folder, ROOT)
    files = tracked(rel_pack) + [f for f in ("LICENSE", "COPYING.md", "LICENSES/CC-BY-SA-4.0.txt")
                                 if os.path.isfile(os.path.join(ROOT, f))]
    for e in m.get("vehicles", []) + m.get("patches", []):
        files += tracked(e["path"])
    files = sorted(set(files))
    game_hashes = {sha(p) for p in glob.glob(os.path.join(ROOT, "extracted", "**", "*"), recursive=True) if os.path.isfile(p)}
    refused = [f for f in files if f.startswith("extracted/") or "/build/" in f or "/generated/" in f
               or sha(os.path.join(ROOT, f)) in game_hashes]
    if refused:
        print("These files are game assets or built from them; a pack never ships them:\n  " + "\n  ".join(refused))
        return 1
    if not game_hashes:
        print("(extracted/ is empty, so files could only be checked by path, not by content.)")
    os.makedirs(os.path.join(ROOT, "dist"), exist_ok=True)
    name = os.path.basename(folder)
    out = os.path.join(ROOT, "dist", f"{name}-{m['pack']['version']}.zip")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for f in files:
            # The pack's own folder becomes the zip's root, so manifest.json sits at the top as the game expects.
            arc = os.path.relpath(f, rel_pack) if f.startswith(rel_pack + "/") else f
            z.write(os.path.join(ROOT, f), arc)
    size = os.path.getsize(out)
    print(f"Wrote {os.path.relpath(out, ROOT)}: {len(files)} files, {size / 1e6:.1f} MB.")
    return 0


if __name__ == "__main__":
    commands = {"check": cmd_check, "build": cmd_build}
    if len(sys.argv) < 2 or sys.argv[1] not in commands:
        print(__doc__)
        sys.exit(2)
    sys.exit(commands[sys.argv[1]](sys.argv[2:]))
