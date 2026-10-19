#!/usr/bin/env python3
"""Versions, CI checks and releases for Die Kollektion Werkstatt. Standard library only.

    python3 tools/release.py check-versions [VERSION]    the plugin, the pack manifest and CHANGELOG.md agree
                                                         (and equal VERSION when given)
    python3 tools/release.py notes VERSION               print that version's CHANGELOG.md section
    python3 tools/release.py ci                          every check that needs no game files (what CI runs)
    python3 tools/release.py build VERSION [--dry-run]   `make release`: check, compile, package, tag, publish
    python3 tools/release.py check-assets VERSION        the GitHub release has its zips and SHA256SUMS, and they match

`build` runs on a maintainer's machine with the game installed, because the plugin compiles against the interop
BepInEx generates from the player's game. It refuses on uncommitted changes, a version mismatch, an existing tag
or a failing gate; it packages dist/die-kollektion-werkstatt-VERSION.zip (the tracked files plus prebuilt/, the
compiled plugin with the game version it was built for), the pack zip (`make pack`), the release notes and
SHA256SUMS; then it tags vVERSION, pushes the tag and creates the GitHub release. --dry-run does everything up to
the tag and prints what it would publish.
"""
import glob
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACK = os.path.join(ROOT, "packs", "die-kollektion")
CHANGELOG = os.path.join(ROOT, "CHANGELOG.md")
NEVER_SHIPPED = ("extracted/", "BepInEx/", "prebuilt/")


def werkstatt():
    spec = importlib.util.spec_from_file_location("werkstatt", os.path.join(ROOT, "tools", "werkstatt.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sh(*cmd, check=True, capture=True):
    r = subprocess.run(cmd, cwd=ROOT, capture_output=capture, text=True)
    if check and r.returncode:
        sys.exit(f"{' '.join(cmd)} failed:\n{(r.stdout or '') + (r.stderr or '')}")
    return r


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def changelog_sections():
    """[(version, date, body)] in file order, skipping [Unreleased]."""
    text = open(CHANGELOG).read()
    heads = list(re.finditer(r"^## \[([^\]]+)\](?: - (\S+))?\s*$", text, re.M))
    out = []
    for i, m in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        if m.group(1).lower() != "unreleased":
            out.append((m.group(1), m.group(2), text[m.end():end].strip()))
    return out


def versions():
    ws = werkstatt()
    pack = json.load(open(os.path.join(PACK, "manifest.json")))["pack"]["version"]
    sections = changelog_sections()
    return {"plugin (plugins/VehicleMods/Plugin.cs)": ws.plugin_version(),
            "pack (packs/die-kollektion/manifest.json)": pack,
            "CHANGELOG.md (latest release)": sections[0][0] if sections else None}


def cmd_check_versions(args):
    found = versions()
    want = args[0] if args else None
    values = set(found.values())
    bad = len(values) != 1 or None in values or (want and values != {want})
    for k, v in found.items():
        print(f"{'ok  ' if not bad else '    '} {k}: {v}")
    if bad:
        print("Versions disagree" + (f" with {want}" if want else "") + ": bump all three together.")
        return 1
    return 0


def cmd_notes(args):
    for version, date, body in changelog_sections():
        if version == args[0]:
            print(body)
            return 0
    print(f"CHANGELOG.md has no section for {args[0]}", file=sys.stderr)
    return 1


def cmd_ci(_args):
    """Everything that can be checked without the game: what .github/workflows run."""
    steps = [
        ("python tools compile", [sys.executable, "-m", "py_compile"] + sorted(glob.glob(os.path.join(ROOT, "tools", "*.py")))),
        ("versions agree", [sys.executable, "tools/release.py", "check-versions"]),
        ("real names stay in the catalogue", [sys.executable, "tools/check_names.py"]),
        ("the catalogue is current", [sys.executable, "tools/catalogue.py", "--check"]),
        ("pack manifests", [sys.executable, "tools/pack.py", "check"]),
        ("hook-page placement", ["dotnet", "run", "--project", "tools/near-plan", "-v", "quiet", "--"]
         + sorted(glob.glob(os.path.join(ROOT, "tests", "maps", "*.maps")))),
    ]
    failed = []
    for name, cmd in steps:
        r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
        print(f"{'ok  ' if r.returncode == 0 else 'FAIL'} {name}")
        if r.returncode:
            print("     " + (r.stdout + r.stderr).strip().replace("\n", "\n     "))
            failed.append(name)
    return 1 if failed else 0


def tracked_files():
    out = sh("git", "ls-files", "-z").stdout
    return [f for f in out.split("\0") if f and os.path.isfile(os.path.join(ROOT, f))]


def game_hashes():
    return {sha256(p) for p in glob.glob(os.path.join(ROOT, "extracted", "**", "*"), recursive=True) if os.path.isfile(p)}


def cmd_build(args):
    dry = "--dry-run" in args
    args = [a for a in args if a != "--dry-run"]
    if not args or not re.fullmatch(r"\d+\.\d+\.\d+", args[0]):
        print("Name the version: make release VERSION=x.y.z [DRY_RUN=1]")
        return 2
    version, tag = args[0], f"v{args[0]}"
    ws = werkstatt()

    # 1. Refusals.
    dirty = sh("git", "status", "--porcelain").stdout.strip()
    if dirty:
        print("Uncommitted changes; a release is built from a clean checkout:\n" + dirty)
        return 1
    if cmd_check_versions([version]):
        return 1
    if sh("git", "rev-parse", "-q", "--verify", f"refs/tags/{tag}", check=False).returncode == 0 or \
            sh("git", "ls-remote", "--tags", "origin", tag, check=False).stdout.strip():
        print(f"{tag} already exists.")
        return 1
    game = ws.game_dir()
    if not game or not ws.game_fingerprint(game):
        print("A release compiles the plugin against BepInEx's interop for the installed game; run `make start` "
              "until BepInEx has prepared the game.")
        return 1
    print("Running the gates (vehicles must be built: `make all` first) ...")
    if subprocess.run([sys.executable, "tools/werkstatt.py", "gates"], cwd=ROOT).returncode:
        print("Gates failed; nothing released.")
        return 1

    # 2. Compile the plugin and describe it.
    print("Compiling the plugin ...")
    if subprocess.run(["dotnet", "build", "-c", "Release", "-nologo", "-v", "minimal", "-p:Deploy=false",
                       f"-p:GameDir={game}"], cwd=os.path.join(ROOT, "plugins", "VehicleMods")).returncode:
        return 1
    head = sh("git", "rev-parse", "HEAD").stdout.strip()
    info = {
        "notes": "The Werkstatt plugin compiled by `make release`. `make deploy` installs it instead of compiling "
                 "when its version matches the source and the game's assembly hash matches gameAssemblyHash; "
                 "otherwise it compiles from source, which needs the .NET SDK.",
        "version": version,
        "sha256": sha256(ws.SOURCE_DLL),
        "builtFrom": head,
        "builtAgainst": {"gameAssemblyHash": ws.game_fingerprint(game), "steamBuild": ws.steam_build(game),
                         "bepinex": ws.bepinex_installed_version(game)},
    }

    # 3. The release zip: tracked files plus prebuilt/, nothing from the game.
    files = tracked_files()
    refused = [f for f in files if f.startswith(NEVER_SHIPPED) or "/build/" in f or "/generated/" in f]
    hashes = game_hashes()
    refused += [f for f in files if hashes and sha256(os.path.join(ROOT, f)) in hashes]
    if refused:
        print("These are game assets or built from them; a release never ships them:\n  " + "\n  ".join(sorted(set(refused))))
        return 1
    dist = os.path.join(ROOT, "dist")
    os.makedirs(dist, exist_ok=True)
    prefix = f"die-kollektion-werkstatt-{version}"
    werk_zip = os.path.join(dist, f"{prefix}.zip")
    with zipfile.ZipFile(werk_zip, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(files):
            z.write(os.path.join(ROOT, f), f"{prefix}/{f}")
        # Without git, the name gate and `make pack` read the shipped file list from here.
        z.writestr(f"{prefix}/RELEASE-FILES.txt", "\n".join(sorted(files)) + "\n")
        z.write(ws.SOURCE_DLL, f"{prefix}/prebuilt/VehicleMods.dll")
        z.writestr(f"{prefix}/prebuilt/VehicleMods.json", json.dumps(info, indent=1) + "\n")
    print(f"Wrote {os.path.relpath(werk_zip, ROOT)} ({len(files)} tracked files + prebuilt plugin)")

    # 4. The pack zip, the notes, the checksums.
    if subprocess.run([sys.executable, "tools/pack.py", "build", "packs/die-kollektion"], cwd=ROOT).returncode:
        return 1
    pack_zip = os.path.join(dist, f"die-kollektion-{version}.zip")
    notes_path = os.path.join(dist, f"release-notes-{version}.md")
    body = next(b for v, _d, b in changelog_sections() if v == version)
    open(notes_path, "w").write(
        body + "\n\n---\n**Downloads.** `die-kollektion-werkstatt-" + version + ".zip` is Werkstatt with the plugin "
        "ready-made: unzip it, open a terminal in the folder and run `make start`. `die-kollektion-" + version +
        ".zip` is the Die Kollektion pack on its own (our files only). `SHA256SUMS` checks both.\n")
    sums_path = os.path.join(dist, "SHA256SUMS")
    assets = [werk_zip, pack_zip]
    open(sums_path, "w").write("".join(f"{sha256(a)}  {os.path.basename(a)}\n" for a in assets))
    print(f"Wrote {os.path.relpath(notes_path, ROOT)} and {os.path.relpath(sums_path, ROOT)}")

    # 5. Publish.
    publish = [["git", "tag", "-a", tag, "-m", f"Die Kollektion Werkstatt {version}"],
               ["git", "push", "origin", tag],
               ["gh", "release", "create", tag, *assets, sums_path, "--verify-tag",
                "--title", f"Die Kollektion Werkstatt {version}", "--notes-file", notes_path]]
    if dry:
        print("\nDRY RUN: built everything; would now run:")
        for cmd in publish:
            print("  " + " ".join(f'"{c}"' if " " in c else os.path.relpath(c, ROOT) if c.startswith(ROOT) else c for c in cmd))
        return 0
    for cmd in publish:
        if subprocess.run(cmd, cwd=ROOT).returncode:
            print(f"Stopped at: {' '.join(cmd)}")
            return 1
    print(f"Released {tag}: https://github.com/aaronsb/die-kollektion/releases/tag/{tag}")
    return 0


def cmd_check_assets(args):
    """For the release workflow: wait for the release, then check its assets against its SHA256SUMS."""
    version, tag = args[0], f"v{args[0]}"
    want = {f"die-kollektion-werkstatt-{version}.zip", f"die-kollektion-{version}.zip", "SHA256SUMS"}
    names = set()
    for _ in range(30):  # `gh release create` pushes the tag before it uploads the assets
        r = subprocess.run(["gh", "release", "view", tag, "--json", "assets"], cwd=ROOT, capture_output=True, text=True)
        names = {a["name"] for a in json.loads(r.stdout)["assets"]} if r.returncode == 0 else set()
        if want <= names:
            break
        time.sleep(20)
    if not want <= names:
        print(f"Release {tag} is missing: {', '.join(sorted(want - names))}")
        return 1
    with tempfile.TemporaryDirectory() as tmp:
        sh("gh", "release", "download", tag, "--dir", tmp, "--pattern", "*")
        bad = []
        for line in open(os.path.join(tmp, "SHA256SUMS")):
            digest, name = line.split()
            if sha256(os.path.join(tmp, name)) != digest:
                bad.append(name)
        with zipfile.ZipFile(os.path.join(tmp, f"die-kollektion-werkstatt-{version}.zip")) as z:
            listed = z.namelist()
            info = json.loads(z.read(f"die-kollektion-werkstatt-{version}/prebuilt/VehicleMods.json"))
        leaked = [n for n in listed if any(f"/{p}" in n for p in NEVER_SHIPPED if p != "prebuilt/")]
    if bad or leaked or info.get("version") != version:
        print(f"Checksum mismatch: {bad}; game files in the zip: {leaked[:5]}; prebuilt version {info.get('version')}")
        return 1
    print(f"{tag}: {', '.join(sorted(want))} present; checksums match; prebuilt plugin {version}")
    return 0


COMMANDS = {"check-versions": cmd_check_versions, "notes": cmd_notes, "ci": cmd_ci, "build": cmd_build,
            "check-assets": cmd_check_assets}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(__doc__)
        sys.exit(2)
    sys.exit(COMMANDS[sys.argv[1]](sys.argv[2:]))
