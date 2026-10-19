#!/usr/bin/env python3
"""Werkstatt's setup, gates and deploy helper, behind the Makefile.

Standard library only, so it runs before the Python environment exists. Usage:

    python3 tools/werkstatt.py start            the next setup step, in plain words (`make start`)
    python3 tools/werkstatt.py doctor           every check, with what is missing and how to get it
    python3 tools/werkstatt.py require          exit 1 with the next step unless setup is done up to building
    python3 tools/werkstatt.py game-dir         print the game folder (GAME_DIR, else Steam's libraries)
    python3 tools/werkstatt.py bepinex          install BepInEx from tools/bepinex.json and set its config
    python3 tools/werkstatt.py gates            run every gate; exit 1 if any fails
    python3 tools/werkstatt.py preflight-deploy [--deploy-dir D]   refuse unsafe deploys, clear the old one
    python3 tools/werkstatt.py record-deploy [--deploy-dir D]      write deployed.json after a deploy
    python3 tools/werkstatt.py undeploy [--deploy-dir D] [--force] remove exactly what deployed.json lists
    python3 tools/werkstatt.py status [--deploy-dir D]             repo, build and game folder side by side
    python3 tools/werkstatt.py save-add [ItemId ...]               add our trucks to the save (backs up first)

Environment: GAME_DIR (the game folder), BEPINEX_ARCHIVE (a downloaded BepInEx zip to install from),
PROFILE (save profile name, default Player1), FORCE=1 (undeploy files that changed since the deploy).
"""
import concurrent.futures
import datetime
import glob
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import urllib.request
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_ID = "2929250"
GAME_FOLDER = "over the hill"
EXE_LINUX = "over the hill.x86_64"
EXE_WINDOWS = "over the hill.exe"
WINDOWS = platform.system() == "Windows"
VENV_PY = os.path.join(ROOT, ".venv", "Scripts" if WINDOWS else "bin", "python.exe" if WINDOWS else "python")
LAUNCH_OPTION = '"./run_bepinex.sh" %command%'
LAUNCH_CLICKS = "In Steam: Library → right-click Over the Hill → Properties → General → Launch Options"
ITEM_IDS = {"Megatherium": 3000000001, "Mastodon": 3000000002, "Glyptodon": 3000000003, "Megaloceros": 3000000004}


# ---------------------------------------------------------------- where things are

def steam_roots():
    home = os.path.expanduser("~")
    if WINDOWS:
        cands = [os.path.join(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"), "Steam")]
    else:
        cands = [os.path.join(home, p) for p in (
            ".local/share/Steam", ".steam/steam", ".steam/debian-installation",
            ".var/app/com.valvesoftware.Steam/.local/share/Steam")]
    seen, out = set(), []
    for c in cands:
        if os.path.isdir(c):
            real = os.path.realpath(c)
            if real not in seen:
                seen.add(real)
                out.append(c)
    return out


def vdf_load(path):
    """Parse a Valve KeyValues text file into nested dicts with lower-cased keys."""
    text = open(path, encoding="utf-8", errors="replace").read()
    tokens = re.findall(r'"((?:[^"\\]|\\.)*)"|([{}])', text)
    stack, cur, key = [], {}, None
    for quoted, brace in tokens:
        if brace == "{":
            new = {}
            cur[key.lower()] = new
            stack.append(cur)
            cur, key = new, None
        elif brace == "}":
            cur = stack.pop() if stack else cur
        elif key is None:
            key = quoted
        else:
            cur[key.lower()] = quoted.replace('\\"', '"').replace("\\\\", "\\")
            key = None
    return cur


def game_dir():
    if os.environ.get("GAME_DIR"):
        return os.environ["GAME_DIR"]
    for root in steam_roots():
        libraries = [root]
        vdf = os.path.join(root, "steamapps", "libraryfolders.vdf")
        if os.path.isfile(vdf):
            try:
                for entry in vdf_load(vdf).get("libraryfolders", {}).values():
                    if isinstance(entry, dict) and entry.get("path"):
                        libraries.append(entry["path"])
            except (OSError, IndexError):
                pass
        for lib in libraries:
            cand = os.path.join(lib, "steamapps", "common", GAME_FOLDER)
            if os.path.isfile(os.path.join(cand, EXE_LINUX)) or os.path.isfile(os.path.join(cand, EXE_WINDOWS)):
                return cand
    return None


def launch_options():
    """Every Steam user's launch option for the game (read-only)."""
    found = []
    for root in steam_roots():
        for cfg in glob.glob(os.path.join(root, "userdata", "*", "config", "localconfig.vdf")):
            try:
                apps = (vdf_load(cfg).get("userlocalconfigstore", {}).get("software", {})
                        .get("valve", {}).get("steam", {}).get("apps", {}))
                found.append(apps.get(APP_ID, {}).get("launchoptions", ""))
            except (OSError, IndexError, AttributeError):
                pass
    return found


def my_games():
    docs = os.path.join(os.path.expanduser("~"), "Documents") if WINDOWS else os.path.expanduser("~")
    return os.path.join(docs, "My Games", GAME_FOLDER)


def game_running():
    if WINDOWS:
        out = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {EXE_WINDOWS}"], capture_output=True, text=True).stdout
        return EXE_WINDOWS.lower() in out.lower()
    # By process name, not command line: a shell or file manager whose arguments mention the game must not count.
    for pid in os.listdir("/proc"):
        if not pid.isdigit() or int(pid) == os.getpid():
            continue
        try:
            comm = open(f"/proc/{pid}/comm").read().strip()
            argv0 = open(f"/proc/{pid}/cmdline", "rb").read().split(b"\0")[0].decode(errors="replace")
        except OSError:
            continue
        if comm == EXE_LINUX[:15] or os.path.basename(argv0) == EXE_LINUX:
            return True
    return False


def distro():
    info = {}
    try:
        for line in open("/etc/os-release"):
            if "=" in line:
                k, v = line.rstrip().split("=", 1)
                info[k] = v.strip('"')
    except OSError:
        return "other", "your system"
    ids = (info.get("ID", "") + " " + info.get("ID_LIKE", "")).split()
    for family in ("arch", "fedora", "debian", "ubuntu"):
        if family in ids:
            return ("debian" if family == "ubuntu" else family), info.get("PRETTY_NAME", family)
    return "other", info.get("PRETTY_NAME", "your system")


INSTALL = {   # tool -> per-family package install command
    "venv": {"arch": "sudo pacman -S python", "debian": "sudo apt install python3-venv",
             "fedora": "sudo dnf install python3"},
    "rsvg-convert": {"arch": "sudo pacman -S librsvg", "debian": "sudo apt install librsvg2-bin",
                     "fedora": "sudo dnf install librsvg2-tools"},
    "potrace": {"arch": "sudo pacman -S potrace", "debian": "sudo apt install potrace",
                "fedora": "sudo dnf install potrace"},
    "dotnet": {"arch": "sudo pacman -S dotnet-sdk", "debian": "sudo apt install dotnet-sdk-8.0",
               "fedora": "sudo dnf install dotnet-sdk-8.0"},
    "blender": {"arch": "sudo pacman -S blender", "debian": "sudo snap install blender --classic",
                "fedora": "sudo dnf install blender"},
}
INSTALL_HELP = {
    "dotnet": "https://learn.microsoft.com/dotnet/core/install/linux",
    "blender": "https://www.blender.org/download/",
}


def install_hint(tool):
    family, name = distro()
    cmd = INSTALL.get(tool, {}).get(family)
    if cmd:
        return f"On {name}, install it with:\n    {cmd}"
    url = INSTALL_HELP.get(tool)
    return f"Install it with your system's package manager" + (f", or see {url}" if url else "") + "."


# ---------------------------------------------------------------- small helpers

def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def which(tool):
    return shutil.which(tool)


def vehicles():
    return sorted(os.path.dirname(p) for p in glob.glob(os.path.join(ROOT, "vehicles", "*", "vehicle.json")))


def manifest(folder):
    return json.load(open(os.path.join(folder, "vehicle.json")))


def bepinex_pin():
    return json.load(open(os.path.join(ROOT, "tools", "bepinex.json")))


def bepinex_installed_version(game):
    dll = os.path.join(game, "BepInEx", "core", "BepInEx.Core.dll")
    if not os.path.isfile(dll):
        return None
    m = re.search(rb"6\.0\.0-be\.\d+\+[0-9a-f]{7,40}", open(dll, "rb").read())
    return m.group(0).decode() if m else "unknown"


def cfg_path(game):
    return os.path.join(game, "BepInEx", "config", "BepInEx.cfg")


def cfg_log_listening_off(game):
    try:
        return re.search(r"^\s*UnityLogListening\s*=\s*false\s*$", open(cfg_path(game)).read(), re.M) is not None
    except OSError:
        return False


def default_deploy_dir(game):
    return os.path.join(game, "BepInEx", "plugins", "VehicleMods")


def say(title, body=None):
    print(title)
    if body:
        for line in body.splitlines():
            print("    " + line if line else "")


# ---------------------------------------------------------------- the setup checks, in order

class Step:
    """One setup check: `title` states the done condition, `action` is the instruction when it isn't."""
    ACTIONS = {
        "python": "Install Python 3.10 or newer", "game": "Install Over the Hill", "closed": "Quit the game",
        "setup": "Install Werkstatt's Python packages", "rsvg-convert": "Install rsvg-convert",
        "potrace": "Install potrace", "dotnet": "Install the .NET SDK", "blender": "Install Blender 5 (optional)",
        "bepinex": "Install BepInEx", "bepinex-version": "Update BepInEx", "cfg": "Turn off BepInEx's Unity log listener",
        "launch": "Tell Steam to start the game through BepInEx", "interop": "Start the game once",
        "extract": "Copy the parts Werkstatt needs from your game", "build": "Build the vehicles",
        "deploy": "Install the mod into the game",
    }

    def __init__(self, key, title, ok, what, todo, blocking=True):
        self.key, self.title, self.ok, self.what, self.todo, self.blocking = key, title, ok, what, todo, blocking
        self.action = self.ACTIONS.get(key, title)


def steps():
    out = []
    game = game_dir()
    py_ok = sys.version_info >= (3, 10)
    out.append(Step("python", "Python 3.10 or newer", py_ok,
                    "Python runs Werkstatt's tools.",
                    f"This is Python {platform.python_version()}. " + install_hint("venv")))
    out.append(Step("game", "Over the Hill is installed", bool(game),
                    "Werkstatt builds on your own copy of the game and installs into its folder.",
                    "Install Over the Hill in Steam (Library → Over the Hill → Install), or if it is installed "
                    "somewhere unusual, tell Werkstatt where:\n    make start GAME_DIR=\"/path/to/over the hill\""))
    running = game_running()
    out.append(Step("closed", "The game is closed", not running,
                    "Installing files into a running game breaks it.",
                    "Quit Over the Hill, then run `make start` again."))
    venv_ok = os.path.isfile(VENV_PY) and run([VENV_PY, "-c", "import UnityPy, PIL, numpy, scipy"]).returncode == 0
    venv_cmd_ok = run([sys.executable, "-c", "import venv, ensurepip"]).returncode == 0
    out.append(Step("setup", "Werkstatt's Python packages are installed", venv_ok,
                    "A private Python environment in .venv/ with the packages the tools use (reading game files, images, maths).",
                    "Run:\n    make setup" if venv_cmd_ok else
                    "Python's environment module is missing first. " + install_hint("venv") + "\nThen run:\n    make setup"))
    for tool, what in (("rsvg-convert", "Turns the vehicles' SVG icons into the PNGs the game shows."),
                       ("potrace", "Traces the icons of the trucks built from the stock Mammoth.")):
        out.append(Step(tool, f"{tool} is installed", bool(which(tool)), what, install_hint(tool)))
    sdks = run(["dotnet", "--list-sdks"]).stdout if which("dotnet") else ""
    sdk_ok = any(int(m.group(1)) >= 6 for m in re.finditer(r"^(\d+)\.", sdks, re.M))
    out.append(Step("dotnet", "The .NET SDK (6 or newer) is installed", sdk_ok,
                    "Compiles the Werkstatt plugin that runs inside the game.", install_hint("dotnet")))
    blender = run(["blender", "--version"]).stdout if which("blender") else ""
    m = re.search(r"Blender (\d+)\.(\d+)", blender)
    out.append(Step("blender", "Blender 5 is installed (optional)", bool(m and int(m.group(1)) >= 5),
                    "Only needed for contact sheets, previews and editing models; deploying works without it.",
                    install_hint("blender"), blocking=False))
    if not game:
        return out
    pin = bepinex_pin()
    version = bepinex_installed_version(game)
    bep_ok = bool(version) and all(os.path.exists(os.path.join(game, p)) for p in
                                  (("BepInEx/core/BepInEx.Unity.IL2CPP.dll", "dotnet") if WINDOWS else
                                   ("BepInEx/core/BepInEx.Unity.IL2CPP.dll", "run_bepinex.sh", "libdoorstop.so", "dotnet")))
    entry = pin["win-x64" if WINDOWS else "linux-x64"]
    bep_todo = "Run:\n    make bepinex" if entry.get("sha256") else (
        "Werkstatt can't download it for you yet, so do it by hand:\n"
        f"  1. Download {entry['file']} from\n       {entry['url']}\n"
        f"  2. Unzip it into the game folder (or extract it there with your file manager):\n"
        f"       unzip -o ~/Downloads/{entry['file']} -d \"{game}\"\n"
        "  3. Run:\n       make bepinex\n     (it sets BepInEx's config; the download itself is done)")
    out.append(Step("bepinex", f"BepInEx {pin['version']} is installed in the game folder", bep_ok,
                    "BepInEx is the mod loader: it starts with the game and loads the Werkstatt plugin.", bep_todo))
    if bep_ok and version != "unknown" and pin["version"] not in version:
        out.append(Step("bepinex-version", f"BepInEx is version {pin['version']}", False,
                        f"The installed BepInEx is {version}; Werkstatt is tested with {pin['version']}.",
                        "Run:\n    make bepinex FORCE=1", blocking=False))
    out.append(Step("cfg", "BepInEx's Unity log listener is off", cfg_log_listening_off(game),
                    "With it on, this game crashes at start (BepInEx/config/BepInEx.cfg: UnityLogListening = false).",
                    "Run:\n    make bepinex"))
    if not WINDOWS:
        opts = launch_options()
        lo_ok = any("run_bepinex.sh" in o for o in opts)
        out.append(Step("launch", "Steam starts the game through BepInEx", lo_ok,
                        "On Linux, Steam has to start the game through BepInEx's script, or BepInEx never runs.",
                        f"{LAUNCH_CLICKS}, paste this exactly, then close the window:\n    {LAUNCH_OPTION}\n"
                        "(If Steam is open, it saves the setting when the window closes; `make start` reads it from disk, "
                        "so if it still shows this step, quit Steam once to make it save.)"))
    interop = os.path.isfile(os.path.join(game, "BepInEx", "interop", "Assembly-CSharp.dll"))
    out.append(Step("interop", "BepInEx has prepared the game once", interop,
                    "On its first start BepInEx reads the game and writes files the plugin is compiled against "
                    "(BepInEx/interop/). This takes a few minutes, once.",
                    "Start Over the Hill from Steam, wait until the main menu shows (the first start is slow), "
                    "then quit the game and run `make start` again."))
    extracted = all(os.path.isfile(os.path.join(ROOT, "extracted", p)) for p in (
        "mammoth/nodes.json", "merchant/Merchant_LOD0.obj", "textures/Mammoth_skin00.png", "icons/Mammoth.png"))
    out.append(Step("extract", "The parts Werkstatt needs are copied from your game", extracted,
                    "The trucks reuse parts of the game's own Mammoth; they are read from your install into extracted/ "
                    "(never shared or committed).", "Run:\n    make extract"))
    stale = []
    for v in vehicles():
        body = os.path.join(v, "build", "body_LOD0.obj")
        if not os.path.isfile(body) or os.path.getmtime(body) < os.path.getmtime(os.path.join(v, "vehicle.json")):
            stale.append(os.path.basename(v))
    out.append(Step("build", "The vehicles are built", not stale,
                    "Builds each vehicle's meshes and icons from its folder in vehicles/."
                    + (f" Not built or out of date: {', '.join(stale)}." if stale else ""),
                    "Run:\n    make build"))
    dep = deploy_state(default_deploy_dir(game))
    out.append(Step("deploy", "The mod is installed in the game and up to date", dep == "current",
                    {"none": "Nothing is installed yet.",
                     "legacy": "An installation not made by `make deploy` is there; deploying moves it aside.",
                     "stale": "The installed files are older than what you have built.",
                     "modified": "Installed files were changed by hand since the last deploy."}.get(dep, ""),
                    "Run:\n    make deploy"))
    return out


def cmd_start(_args):
    all_steps = steps()
    done = [s for s in all_steps if s.ok]
    todo = [s for s in all_steps if not s.ok and s.blocking]
    print(f"Werkstatt setup: {len(done)} of {len(all_steps)} checks done.\n")
    if not todo:
        say("Everything is ready.",
            "Start Over the Hill from Steam. The Die Kollektion trucks are at the merchant.\n"
            "Optional: put all four in your garage without buying them (game closed):\n    make save-add\n"
            "Before you play with them for long, back up your save folder: " + os.path.join(my_games(), "Saves"))
        optional = [s for s in all_steps if not s.ok and not s.blocking]
        for s in optional:
            print(f"\n(Optional) {s.title}: {s.what}")
        return 0
    s = todo[0]
    say(f"Next step: {s.action}.", f"{s.what}\n\n{s.todo}\n\nThen run `make start` again.")
    return 0


def cmd_require(_args):
    """Stop `make all` early, with the plain next step, unless everything before building is set up."""
    before_build = ("python", "game", "closed", "setup", "rsvg-convert", "potrace", "dotnet",
                    "bepinex", "cfg", "launch", "interop")
    todo = [s for s in steps() if not s.ok and s.blocking and s.key in before_build]
    if not todo:
        return 0
    s = todo[0]
    say(f"Not ready to build yet. Next step: {s.action}.", f"{s.what}\n\n{s.todo}\n\nThen run `make start` again.")
    return 1


def cmd_doctor(_args):
    for s in steps():
        mark = "ok  " if s.ok else ("MISS" if s.blocking else "warn")
        print(f"[{mark}] {s.title}")
        if not s.ok:
            for line in (s.what + "\n" + s.todo).splitlines():
                print("         " + line)
    game = game_dir()
    print(f"\nGame folder: {game or 'not found'}")
    print(f"Saves: {os.path.join(my_games(), 'Saves')}")
    return 0


def cmd_game_dir(_args):
    g = game_dir()
    if not g:
        print("Over the Hill not found; set GAME_DIR", file=sys.stderr)
        return 1
    print(g)
    return 0


# ---------------------------------------------------------------- BepInEx

MINIMAL_CFG = """[Logging]

## Enables showing unity log messages in the BepInEx logging system.
# Setting type: Boolean
# Default value: true
UnityLogListening = false
"""


def set_cfg(game):
    path = cfg_path(game)
    if os.path.isfile(path):
        text = open(path).read()
        new, n = re.subn(r"^(\s*UnityLogListening\s*=\s*)\S+", r"\1false", text, flags=re.M)
        if n == 0:
            new = text.rstrip("\n") + "\n\n" + MINIMAL_CFG if "[Logging]" not in text else \
                text.replace("[Logging]\n", "[Logging]\n\nUnityLogListening = false\n", 1)
        if new == text:
            return "already set in"
        open(path, "w").write(new)
        return "updated"
    # BepInEx writes its full config on first start and keeps values already in the file, so a file holding
    # only this setting is enough to have the listener off from the very first start.
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w").write(MINIMAL_CFG)
    return "created"


def cmd_bepinex(_args):
    game = game_dir()
    if not game:
        print("Over the Hill not found. Install it in Steam first, or set GAME_DIR.")
        return 1
    if game_running():
        print("The game is running. Quit it first.")
        return 1
    pin = bepinex_pin()
    key = "win-x64" if WINDOWS else "linux-x64"
    entry = pin[key]
    version = bepinex_installed_version(game)
    force = os.environ.get("FORCE") == "1"
    if version and pin["version"] in version and not force:
        print(f"BepInEx {version} is already installed in {game}.")
    else:
        if not entry.get("sha256"):
            print(f"The BepInEx download isn't pinned to a checksum yet (tools/bepinex.json has no sha256 for {key}),\n"
                  "so Werkstatt won't install it. Until it is pinned, install BepInEx by hand as the README describes.")
            return 1
        archive = os.environ.get("BEPINEX_ARCHIVE") or os.path.join(
            os.path.expanduser("~"), ".cache", "werkstatt", entry["file"])
        if not os.path.isfile(archive):
            mb = entry["size"] / 1e6
            print(f"Werkstatt needs to download BepInEx {pin['version']} ({key}, {mb:.0f} MB) from\n    {entry['url']}")
            if not sys.stdin.isatty():
                print("Run `make bepinex` in a terminal to confirm the download, or download it yourself and run\n"
                      "    make bepinex BEPINEX_ARCHIVE=/path/to/" + entry["file"])
                return 1
            if input("Download it now? [y/N] ").strip().lower() not in ("y", "yes"):
                print("Not downloaded.")
                return 1
            os.makedirs(os.path.dirname(archive), exist_ok=True)
            urllib.request.urlretrieve(entry["url"], archive + ".part")
            os.replace(archive + ".part", archive)
        digest = sha256(archive)
        if digest != entry["sha256"]:
            print(f"Checksum mismatch for {archive}:\n    expected {entry['sha256']}\n    got      {digest}\n"
                  "Not installing. Delete the file and try again.")
            return 1
        with zipfile.ZipFile(archive) as z:
            for info in z.infolist():
                target = os.path.join(game, info.filename)
                if not os.path.realpath(target).startswith(os.path.realpath(game) + os.sep):
                    print(f"Refusing an archive entry outside the game folder: {info.filename}")
                    return 1
            z.extractall(game)
            for info in z.infolist():
                mode = (info.external_attr >> 16) & 0o777
                if mode and not info.is_dir():
                    os.chmod(os.path.join(game, info.filename), mode)
        print(f"Installed BepInEx {pin['version']} into {game}.")
    print(f"BepInEx config: {set_cfg(game)} {cfg_path(game)} (UnityLogListening = false).")
    if not WINDOWS:
        print(f"\nNow set Steam to start the game through BepInEx:\n    {LAUNCH_CLICKS}\n    {LAUNCH_OPTION}")
    print("\nThen start the game once from Steam, wait for the main menu, and quit. Then run `make start`.")
    return 0


# ---------------------------------------------------------------- gates

def holes(obj, culled, gap):
    py = VENV_PY if os.path.isfile(VENV_PY) else sys.executable
    r = run([py, os.path.join(ROOT, "tools", "check_holes.py"), obj, "--quiet",
             "--fail-culled", str(culled), "--fail-gap", str(gap)], cwd=ROOT)
    last = (r.stdout.strip().splitlines() or [r.stderr.strip()])[-1].strip()
    return obj, r.returncode, last


def cmd_gates(_args):
    py = VENV_PY if os.path.isfile(VENV_PY) else sys.executable
    failed = []
    jobs = []
    for v in vehicles():
        name = os.path.basename(v)
        bodies = sorted(glob.glob(os.path.join(v, "build", "body_LOD*.obj")))
        if not bodies:
            failed.append(f"{name}: not built (run `make build`)")
            continue
        gates = manifest(v).get("gates", {})
        for b in bodies:
            jobs.append((b, gates.get("failCulledCm2", 25), gates.get("failGapCm2", 20)))
    with concurrent.futures.ThreadPoolExecutor(max_workers=os.cpu_count() or 4) as ex:
        for obj, code, last in ex.map(lambda j: holes(*j), jobs):
            rel = os.path.relpath(obj, ROOT)
            print(f"holes    {'ok  ' if code == 0 else 'FAIL'} {rel}: {last}")
            if code:
                failed.append(f"holes: {rel}")
    for v in vehicles():
        objs = sorted(glob.glob(os.path.join(v, "build", "*.obj")))
        if not objs:
            continue
        allow = [a for box in manifest(v).get("gates", {}).get("sliverAllow", [])
                 for a in ("--allow", ",".join(str(x) for x in box))]
        r = run([py, os.path.join(ROOT, "tools", "check_slivers.py")] + objs + allow, cwd=ROOT)
        counts = [l for l in r.stdout.splitlines() if "sliver faces" in l and not l.split(": ", 1)[1].startswith("0 ")]
        name = os.path.basename(v)
        print(f"slivers  {'ok  ' if r.returncode == 0 else 'FAIL'} {name}: {len(objs)} meshes"
              + "".join("\n           " + os.path.relpath(l.split(':')[0], ROOT) + ":" + l.split(':', 1)[1] for l in counts))
        if r.returncode:
            failed.append(f"slivers: {name}")
    for label, cmd in (("names   ", [sys.executable, "tools/check_names.py"]),
                       ("catalog ", [sys.executable, "tools/catalogue.py", "--check"])):
        r = run(cmd, cwd=ROOT)
        print(f"{label} {'ok  ' if r.returncode == 0 else 'FAIL'} {(r.stdout + r.stderr).strip().splitlines()[-1] if (r.stdout + r.stderr).strip() else ''}")
        if r.returncode:
            failed.append(label.strip())
    if failed:
        print("\nGates failed: " + "; ".join(failed))
        return 1
    print("\nAll gates pass.")
    return 0


# ---------------------------------------------------------------- deploy bookkeeping

def deploy_dir_arg(args):
    if "--deploy-dir" in args:
        return os.path.abspath(args[args.index("--deploy-dir") + 1])
    if os.environ.get("DEPLOY_DIR"):
        return os.path.abspath(os.environ["DEPLOY_DIR"])
    g = game_dir()
    return default_deploy_dir(g) if g else None


def expected_sources():
    """What a deploy copies, mirroring the csproj's VehicleDeployFiles task: destination -> repo source."""
    out = {"VehicleMods.dll": os.path.join(ROOT, "plugins", "VehicleMods", "bin", "Release", "net6.0", "VehicleMods.dll")}
    for v in vehicles():
        name = os.path.basename(v)
        out[f"vehicles/{name}.json"] = os.path.join(v, "vehicle.json")
        for obj in glob.glob(os.path.join(v, "build", "*.obj")):
            out[f"vehicles/{name}/{os.path.basename(obj)}"] = obj
        icon = os.path.join(v, "icon.png")
        code = manifest(v).get("codename")
        if os.path.isfile(icon) and code:
            out[f"icons/{code}.png"] = icon
    return out


def listing(folder):
    files = {}
    for dirpath, _dirs, names in os.walk(folder):
        for n in names:
            p = os.path.join(dirpath, n)
            rel = os.path.relpath(p, folder).replace(os.sep, "/")
            if rel != "deployed.json":
                files[rel] = p
    return files


def deploy_state(folder):
    record = os.path.join(folder, "deployed.json")
    if not os.path.isdir(folder) or not os.listdir(folder):
        return "none"
    if not os.path.isfile(record):
        return "legacy"
    rec = json.load(open(record))
    for f in rec["files"]:
        p = os.path.join(folder, f["path"])
        if not os.path.isfile(p) or sha256(p) != f["sha256"]:
            return "modified"
    sources = expected_sources()
    recorded = {f["path"]: f for f in rec["files"]}
    if set(sources) != set(recorded):
        return "stale"
    for dest, src in sources.items():
        if not os.path.isfile(src) or sha256(src) != recorded[dest]["sha256"]:
            return "stale"
    return "current"


def remove_recorded(folder, force):
    rec = json.load(open(os.path.join(folder, "deployed.json")))
    changed = [f["path"] for f in rec["files"]
               if os.path.isfile(os.path.join(folder, f["path"])) and sha256(os.path.join(folder, f["path"])) != f["sha256"]]
    if changed and not force:
        print("These installed files changed since the last deploy; not removing them:\n  " + "\n  ".join(changed)
              + "\nRun with FORCE=1 to remove them anyway.")
        return False
    for f in rec["files"]:
        p = os.path.join(folder, f["path"])
        if os.path.isfile(p):
            os.remove(p)
    os.remove(os.path.join(folder, "deployed.json"))
    for dirpath, _dirs, _names in sorted(os.walk(folder), key=lambda t: -len(t[0])):
        if not os.listdir(dirpath):
            os.rmdir(dirpath)
    left = listing(folder) if os.path.isdir(folder) else {}
    if left:
        print("Left in place (not made by `make deploy`):\n  " + "\n  ".join(sorted(left)))
    return True


def cmd_preflight_deploy(args):
    game = game_dir()
    folder = deploy_dir_arg(args)
    if not game or not folder:
        print("Over the Hill not found. Install it in Steam, or set GAME_DIR.")
        return 1
    into_game = os.path.realpath(folder).startswith(os.path.realpath(game) + os.sep)
    if into_game and game_running():
        print("The game is running. Quit it, then deploy.")
        return 1
    if not os.path.isfile(os.path.join(game, "BepInEx", "interop", "Assembly-CSharp.dll")):
        print("BepInEx hasn't prepared the game yet (no BepInEx/interop/), so the plugin can't be compiled.\n"
              "Run `make start` and follow it.")
        return 1
    state = deploy_state(folder)
    if state in ("current", "stale"):
        remove_recorded(folder, force=False)
    elif state == "modified":
        if not remove_recorded(folder, force=os.environ.get("FORCE") == "1"):
            return 1
    elif state == "legacy":
        parent = os.path.dirname(folder)
        # BepInEx loads every DLL under plugins/, so the old copy goes one level up, next to plugins/.
        if os.path.basename(parent) == "plugins":
            parent = os.path.dirname(parent)
        aside = os.path.join(parent, f"{os.path.basename(folder)}.replaced-{datetime.datetime.now():%Y%m%d-%H%M%S}")
        shutil.move(folder, aside)
        print(f"An installation not made by `make deploy` was there; moved it aside to\n    {aside}\n"
              "(outside the plugins folder, so BepInEx doesn't load it). Delete it once the new one works.")
    return 0


def cmd_record_deploy(args):
    folder = deploy_dir_arg(args)
    files = listing(folder)
    sources = expected_sources()
    missing = sorted(set(sources) - set(files))
    if missing:
        print("The deploy is missing files it should have copied:\n  " + "\n  ".join(missing))
        return 1
    head = run(["git", "rev-parse", "HEAD"], cwd=ROOT).stdout.strip()
    dirty = bool(run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=ROOT).stdout.strip())
    record = {
        "notes": "Written by `make deploy`. `make undeploy` removes exactly these files; `make status` compares them with the repo.",
        "tool": "werkstatt",
        "deployedAt": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "repoCommit": head + ("+dirty" if dirty else ""),
        "files": [{"path": rel, "sha256": sha256(p),
                   "source": os.path.relpath(sources[rel], ROOT).replace(os.sep, "/") if rel in sources else None}
                  for rel, p in sorted(files.items())],
    }
    json.dump(record, open(os.path.join(folder, "deployed.json"), "w"), indent=1)
    extra = sorted(set(files) - set(sources))
    print(f"Deployed {len(files)} files to {folder}" + (f" ({len(extra)} not from the repo: {', '.join(extra)})" if extra else "") + ".")
    return 0


def cmd_undeploy(args):
    folder = deploy_dir_arg(args)
    if not folder or not os.path.isdir(folder):
        print("Nothing installed.")
        return 0
    game = game_dir()
    if game and os.path.realpath(folder).startswith(os.path.realpath(game) + os.sep) and game_running():
        print("The game is running. Quit it first.")
        return 1
    if not os.path.isfile(os.path.join(folder, "deployed.json")):
        print(f"{folder} wasn't made by `make deploy` (no deployed.json); not touching it.")
        return 1
    if not remove_recorded(folder, force=os.environ.get("FORCE") == "1" or "--force" in args):
        return 1
    print(f"Removed the deployed files from {folder}.")
    return 0


def cmd_status(args):
    game = game_dir()
    print(f"Game folder:  {game or 'not found'}")
    if game:
        print(f"Game running: {'yes' if game_running() else 'no'}")
        print(f"BepInEx:      {bepinex_installed_version(game) or 'not installed'}"
              f" (pinned {bepinex_pin()['version']}); log listener {'off' if cfg_log_listening_off(game) else 'ON'}")
        print(f"Interop:      {'generated' if os.path.isfile(os.path.join(game, 'BepInEx', 'interop', 'Assembly-CSharp.dll')) else 'missing'}")
    folder = deploy_dir_arg(args)
    if folder:
        state = deploy_state(folder)
        print(f"Deployed:     {state} ({folder})")
        rec_path = os.path.join(folder, "deployed.json")
        if state in ("stale", "modified") and os.path.isfile(rec_path):
            rec = {f["path"]: f for f in json.load(open(rec_path))["files"]}
            for dest, src in sorted(expected_sources().items()):
                if dest not in rec:
                    print(f"  new, not deployed: {dest}")
                elif not os.path.isfile(src) or sha256(src) != rec[dest]["sha256"]:
                    print(f"  changed since deploy: {dest}")
            for dest in sorted(set(rec) - set(expected_sources())):
                print(f"  deployed, no longer built: {dest}")
            for dest, f in sorted(rec.items()):
                p = os.path.join(folder, dest)
                if not os.path.isfile(p) or sha256(p) != f["sha256"]:
                    print(f"  changed in the game folder: {dest}")
    for v in vehicles():
        body = os.path.join(v, "build", "body_LOD0.obj")
        built = os.path.isfile(body)
        fresh = built and os.path.getmtime(body) >= os.path.getmtime(os.path.join(v, "vehicle.json"))
        print(f"Vehicle {os.path.basename(v):12s} {'built' if fresh else ('out of date' if built else 'not built')}")
    return 0


def cmd_save_add(args):
    if game_running():
        print("The game is running. Quit it first: the game overwrites the save when it quits.")
        return 1
    save = os.path.join(my_games(), "Saves", os.environ.get("PROFILE", "Player1") + ".json")
    if not os.path.isfile(save):
        print(f"No save at {save}. Start the game once and play past the start, then quit and try again.")
        return 1
    ids = [a for a in args if a.isdigit()] or [str(i) for i in ITEM_IDS.values()]
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "add_vehicle_to_save.py"), save] + ids)
    return r.returncode


COMMANDS = {
    "start": cmd_start, "require": cmd_require, "doctor": cmd_doctor, "game-dir": cmd_game_dir, "bepinex": cmd_bepinex,
    "gates": cmd_gates, "preflight-deploy": cmd_preflight_deploy, "record-deploy": cmd_record_deploy,
    "undeploy": cmd_undeploy, "status": cmd_status, "save-add": cmd_save_add,
}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(__doc__)
        sys.exit(2)
    sys.exit(COMMANDS[sys.argv[1]](sys.argv[2:]))
