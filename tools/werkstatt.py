#!/usr/bin/env python3
"""Werkstatt's setup, gates and deploy helper, behind the Makefile.

Standard library only, so it runs before the Python environment exists. Usage:

    python3 tools/werkstatt.py start            the next setup step, in plain words (`make start`)
    python3 tools/werkstatt.py doctor           every check, with what is missing and how to get it
    python3 tools/werkstatt.py require          exit 1 with the next step unless setup is done up to building
    python3 tools/werkstatt.py game-dir         print the game folder (GAME_DIR, else Steam's libraries)
    python3 tools/werkstatt.py bepinex          install BepInEx from tools/bepinex.json and set its config
    python3 tools/werkstatt.py gates [vehicle ...]  run every gate (mesh gates for the named vehicles only); exit 1 if any fails
    python3 tools/werkstatt.py preflight-deploy [--deploy-dir D]   refuse unsafe deploys, clear the old one
    python3 tools/werkstatt.py compile-plugin                      compile the plugin, unless the release's prebuilt one fits
    python3 tools/werkstatt.py copy-deploy [--deploy-dir D]        copy the plugin and the built vehicles into the game
    python3 tools/werkstatt.py record-deploy [--deploy-dir D]      write deployed.json after a deploy
    python3 tools/werkstatt.py undeploy [--deploy-dir D] [--force] remove exactly what deployed.json lists
    python3 tools/werkstatt.py status [--deploy-dir D]             repo, build and game folder side by side
    python3 tools/werkstatt.py update [--deploy-dir D]             after a game update: rebuild and reinstall the plugin
    python3 tools/werkstatt.py deploy [--deploy-dir D]             preflight, compile, copy and record (`make deploy`)
    python3 tools/werkstatt.py launch-before | launch-after [--log F]  run_werkstatt.sh's steps around a launch
    python3 tools/werkstatt.py save-add [ItemId ...]               add our trucks to the save (backs up first)
    python3 tools/werkstatt.py save-test | save-real               swap in a test save where every car owns every part
                                                                   (the real one kept aside), and put the real one back
    python3 tools/werkstatt.py loop <vehicle>                      build one vehicle, run its gates, redo its contact
                                                                   sheet, write its CHANGES.md (`make loop V=...`)

Environment: GAME_DIR (the game folder), MY_GAMES (the game's documents folder holding Saves/, default
~/My Games/over the hill), BEPINEX_ARCHIVE (a downloaded BepInEx zip to install from), PROFILE (save profile
name, default Player1), FORCE=1 (undeploy files that changed since the deploy).
"""
import concurrent.futures
import contextlib
import datetime
import errno
import glob
import hashlib
import json
import os
import platform
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile

try:
    import fcntl
except ImportError:  # Windows: no advisory locks; Werkstatt's launch script is Linux-only anyway
    fcntl = None

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_ID = "2929250"
GAME_FOLDER = "over the hill"
EXE_LINUX = "over the hill.x86_64"
EXE_WINDOWS = "over the hill.exe"
WINDOWS = platform.system() == "Windows"
VENV_PY = os.path.join(ROOT, ".venv", "Scripts" if WINDOWS else "bin", "python.exe" if WINDOWS else "python")
LAUNCH_OPTION = '"./run_werkstatt.sh" %command%'
# tools/run_werkstatt.sh, installed into the game folder: starts the game through run_bepinex.sh, and after a
# game update keeps the old plugin out of that launch and rebuilds it once the game has exited.
LAUNCH_SCRIPT = "run_werkstatt.sh"
LAUNCH_SOURCE = os.path.join(ROOT, "tools", LAUNCH_SCRIPT)
LAUNCH_CLICKS = "In Steam: Library → right-click Over the Hill → Properties → General → Launch Options"
PLUGIN_SOURCE = os.path.join(ROOT, "plugins", "VehicleMods", "Plugin.cs")
SOURCE_DLL = os.path.join(ROOT, "plugins", "VehicleMods", "bin", "Release", "net6.0", "VehicleMods.dll")
# A release zip carries the plugin ready-made here (`make release`), so a player needs no .NET SDK.
PREBUILT_DIR = os.path.join(ROOT, "prebuilt")
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
    if os.environ.get("MY_GAMES"):
        return os.environ["MY_GAMES"]
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
    return "Install it with your system's package manager" + (f", or see {url}" if url else "") + "."


# ---------------------------------------------------------------- small helpers

def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def git(*args):
    """A git command's output in the repo, or None when git is missing or the repo isn't a git checkout
    (a "Download ZIP" copy works everywhere git would only add information)."""
    if not which("git"):
        return None
    r = run(["git", *args], cwd=ROOT)
    return r.stdout.strip() if r.returncode == 0 else None


def checkout():
    """(commit, branch, uncommitted changes?) of the repo, or None outside a git checkout."""
    head = git("rev-parse", "HEAD")
    if not head:
        return None
    return head, git("rev-parse", "--abbrev-ref", "HEAD"), bool(git("status", "--porcelain", "--untracked-files=no"))


def which(tool):
    return shutil.which(tool)


def vehicles():
    return sorted(os.path.dirname(p) for p in glob.glob(os.path.join(ROOT, "vehicles", "*", "vehicle.json")))


def manifest(folder):
    return json.load(open(os.path.join(folder, "vehicle.json")))


def bepinex_pin():
    return json.load(open(os.path.join(ROOT, "tools", "bepinex.json")))


def plugin_version():
    m = re.search(r'BepInPlugin\("[^"]+",\s*"[^"]+",\s*"([^"]+)"\)', open(PLUGIN_SOURCE).read())
    return m.group(1) if m else None


def interop_hash(game):
    """BepInEx's hash of the game assemblies its interop was generated from: the plugin is compiled against
    that interop, so a plugin built for one value can hang the game at another (seen after a game update)."""
    p = os.path.join(game, "BepInEx", "interop", "assembly-hash.txt") if game else ""
    return open(p).read().strip() if p and os.path.isfile(p) else None


def steam_manifest(game):
    """The game's Steam app manifest (steamapps/appmanifest_<id>.acf, two levels above the game folder), or {}."""
    p = os.path.join(game, "..", "..", f"appmanifest_{APP_ID}.acf") if game else ""
    try:
        return vdf_load(p).get("appstate", {}) if p and os.path.isfile(p) else {}
    except (OSError, IndexError, AttributeError):
        return {}


def steam_build(game):
    return steam_manifest(game).get("buildid")


def dotnet_sdk_major():
    sdks = run(["dotnet", "--list-sdks"]).stdout if which("dotnet") else ""
    return max((int(m.group(1)) for m in re.finditer(r"^(\d+)\.", sdks, re.M)), default=0)


def prebuilt_plugin(game):
    """(dll, None) when the release's prebuilt plugin fits this checkout and this game, else (None, why not)."""
    dll, info_path = os.path.join(PREBUILT_DIR, "VehicleMods.dll"), os.path.join(PREBUILT_DIR, "VehicleMods.json")
    if not (os.path.isfile(dll) and os.path.isfile(info_path)):
        return None, "there is no prebuilt plugin here (a source checkout builds its own)"
    info = json.load(open(info_path))
    if info.get("version") != plugin_version():
        return None, f"the prebuilt plugin is {info.get('version')} but the source is {plugin_version()}"
    if sha256(dll) != info.get("sha256"):
        return None, "the prebuilt plugin doesn't match its recorded checksum"
    built_for = info.get("builtAgainst", {}).get("gameAssemblyHash")
    now = interop_hash(game)
    if built_for and now and built_for != now:
        return None, ("the prebuilt plugin was built for another version of the game (the game has updated since "
                      "this release), and a plugin built for another version can hang the game at start")
    return dll, None


def plugin_dll(game=None):
    """The plugin a deploy installs: the release's prebuilt one when it fits, else the one compiled here."""
    dll, _why = prebuilt_plugin(game if game is not None else game_dir())
    return dll or SOURCE_DLL


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


def run_script_ready(game):
    """run_bepinex.sh is executable and names the game's executable, as the tested install has it.

    The archive ships it with executable_name="" and without the execute bit; Steam's launch option runs it
    directly, so it needs both."""
    path = os.path.join(game, "run_bepinex.sh")
    try:
        text = open(path).read()
    except OSError:
        return False
    return os.access(path, os.X_OK) and f'executable_name="{EXE_LINUX}"' in text


def prepare_run_script(game):
    path = os.path.join(game, "run_bepinex.sh")
    text = open(path).read()
    new = re.sub(r'^executable_name=".*"$', f'executable_name="{EXE_LINUX}"', text, count=1, flags=re.M)
    if new != text:
        open(path, "w").write(new)
    os.chmod(path, os.stat(path).st_mode | 0o755)


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
        "bepinex": "Install BepInEx", "bepinex-version": "Update BepInEx", "runscript": "Finish BepInEx's setup", "launchscript": "Install Werkstatt's launch script", "cfg": "Turn off BepInEx's Unity log listener",
        "launch": "Tell Steam to start the game through BepInEx", "interop": "Start the game once",
        "extract": "Copy the parts Werkstatt needs from your game", "build": "Build the vehicles",
        "deploy": "Install the mod into the game", "update": "Rebuild the plugin for the updated game",
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
    ready, why = prebuilt_plugin(game)
    if ready:
        out.append(Step("dotnet", "The plugin comes ready-made in this release (no .NET SDK needed)", True,
                        "This release carries the Werkstatt plugin already compiled for your game.", ""))
    else:
        out.append(Step("dotnet", "The .NET SDK (6 or newer) is installed", dotnet_sdk_major() >= 6,
                        "Compiles the Werkstatt plugin that runs inside the game"
                        + ("." if "source checkout" in why else f": {why}."), install_hint("dotnet")))
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
    if bep_ok and not WINDOWS:
        out.append(Step("runscript", "BepInEx's start script is ready", run_script_ready(game),
                        "Steam starts the game through run_bepinex.sh (by way of Werkstatt's launch script); it must be "
                        "executable and name the game.",
                        "Run:\n    make bepinex"))
        target = launch_script_target(game)
        uses_it = any(LAUNCH_SCRIPT in o for o in launch_options())
        out.append(Step("launchscript", "Werkstatt's launch script is installed and points at this folder",
                        bool(target) and os.path.realpath(target) == os.path.realpath(ROOT),
                        (f"{LAUNCH_SCRIPT} in the game folder points at another Werkstatt folder ({target}); after a game "
                         "update it rebuilds the plugin from there." if target else
                         f"{LAUNCH_SCRIPT} starts the game through BepInEx and rebuilds the plugin after a game update."
                         + (" Steam's launch option uses it, so the game won't start without it." if uses_it else "")),
                        "Run, from this folder:\n    make bepinex", blocking=uses_it and not target))
    out.append(Step("cfg", "BepInEx's Unity log listener is off", cfg_log_listening_off(game),
                    "With it on, this game crashes at start (BepInEx/config/BepInEx.cfg: UnityLogListening = false).",
                    "Run:\n    make bepinex"))
    if not WINDOWS:
        opts = launch_options()
        lo_ok = any(LAUNCH_SCRIPT in o for o in opts)
        old = not lo_ok and any("run_bepinex.sh" in o for o in opts)
        out.append(Step("launch", "Steam starts the game through Werkstatt's launch script", lo_ok,
                        ("Steam starts the game through run_bepinex.sh directly. That works until the game updates; "
                         f"then a plugin built for the old game can hang it at start. {LAUNCH_SCRIPT} starts BepInEx "
                         "the same way, and after an update starts the game without the old plugin and rebuilds it."
                         if old else
                         "On Linux, Steam has to start the game through BepInEx's script, or BepInEx never runs. "
                         f"Werkstatt's {LAUNCH_SCRIPT} starts it, and after a game update rebuilds the plugin."),
                        f"{LAUNCH_CLICKS}, {'replace what is there with this' if old else 'paste this exactly'}, then close the window:"
                        f"\n    {LAUNCH_OPTION}\n"
                        "(If Steam is open, it saves the setting when the window closes; `make start` reads it from disk, "
                        "so if it still shows this step, quit Steam once to make it save.)", blocking=not old))
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
    update_state, update_text = update_report(game, default_deploy_dir(game))
    if update_state in ("needed", "rebuilt"):
        out.append(Step("update", "The plugin is built for this version of the game", update_state == "rebuilt",
                        update_text[0].upper() + update_text[1:] + ".",
                        "Run:\n    make update\n(Or start the game from Steam: through the launch script it runs without "
                        "Die Kollektion once, and the plugin is rebuilt after you quit.)"))
    dep = deploy_state(default_deploy_dir(game))
    out.append(Step("deploy", "The mod is installed in the game and up to date", dep == "current",
                    {"none": "Nothing is installed yet.",
                     "legacy": "An installation not made by `make deploy` is there; deploying moves it aside.",
                     "stale": "The installed files are older than what you have built.",
                     "modified": "Installed files were changed by hand since the last deploy."}.get(dep, ""),
                    "Run:\n    make deploy FORCE=1\n(FORCE=1 replaces the files you changed by hand; `make status` lists them.)"
                    if dep == "modified" else "Run:\n    make deploy"))
    test_save = test_save_status()
    if test_save:
        out.append(Step("testsave", "A test save is in place", False, test_save[0].upper() + test_save[1:] + ".",
                        "When you are done testing, quit the game and run:\n    make save-real", blocking=False))
    return out


def cmd_start(_args):
    all_steps = steps()
    setup_steps = [s for s in all_steps if s.key != "testsave"]
    done = [s for s in setup_steps if s.ok]
    todo = [s for s in all_steps if not s.ok and s.blocking]
    print(f"Werkstatt setup: {len(done)} of {len(setup_steps)} checks done.\n")
    if not todo:
        say("Everything is ready.",
            "Start Over the Hill from Steam. The Die Kollektion trucks are at the merchant.\n"
            "Optional: put all four in your garage without buying them (game closed):\n    make save-add\n"
            "Before you play with them for long, back up your save folder: " + os.path.join(my_games(), "Saves"))
        for s in all_steps:
            if s.key in ("update", "testsave"):
                print(f"\n{s.what}")
        optional = [s for s in all_steps if not s.ok and not s.blocking and s.key != "testsave"]
        for s in optional:
            print(f"\n(Optional) {s.title}: {s.what}")
        return 0
    s = todo[0]
    if s.key == "extract" and all(t.key in ("extract", "build", "deploy") for t in todo):
        # Everything left is Werkstatt's own work: one command does it all.
        say("Next step: build the mod and install it into the game.",
            "Setup is done; what's left is Werkstatt's own work: copy the game parts it needs, build the vehicles, "
            "check them and install the mod into the game. One command does all of it (about a minute):\n"
            "    make all")
        return 0
    say(f"Next step: {s.action}.", s.what + "\n\n" + s.todo +
        ("" if "make start" in s.todo else "\n\nThen run `make start` again."))
    return 0


def cmd_require(_args):
    """Stop `make all` early, with the plain next step, unless everything before building is set up."""
    before_build = ("python", "game", "closed", "setup", "rsvg-convert", "potrace", "dotnet",
                    "bepinex", "runscript", "launchscript", "cfg", "launch", "interop")
    todo = [s for s in steps() if not s.ok and s.blocking and s.key in before_build]
    if not todo:
        return 0
    s = todo[0]
    say(f"Not ready to build yet. Next step: {s.action}.", f"{s.what}\n\n{s.todo}\n\nThen run `make start` again.")
    return 1


def cmd_doctor(_args):
    for s in steps():
        if s.key == "testsave":
            print(f"[note] {s.what}")
            continue
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
            # The build server answers Python's default user agent with 403 Forbidden.
            request = urllib.request.Request(
                entry["url"], headers={"User-Agent": "Werkstatt/1 (+https://github.com/aaronsb/die-kollektion)"})
            try:
                with urllib.request.urlopen(request, timeout=60) as response, open(archive + ".part", "wb") as out:
                    shutil.copyfileobj(response, out)
            except OSError as error:
                print(f"Download failed: {error}\n"
                      f"Download it yourself from the link above (a browser works), then run\n"
                      f"    make bepinex BEPINEX_ARCHIVE=/path/to/{entry['file']}")
                return 1
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
    if not WINDOWS:
        prepare_run_script(game)
        print(f"Start script: {os.path.join(game, 'run_bepinex.sh')} is executable and starts {EXE_LINUX}.")
        print(f"Launch script: {install_launch_script(game)} starts it, and rebuilds the plugin after a game update.")
    print(f"BepInEx config: {set_cfg(game)} {cfg_path(game)} (UnityLogListening = false).")
    if not WINDOWS:
        print(f"\nNow set Steam to start the game through Werkstatt's launch script:\n    {LAUNCH_CLICKS}\n    {LAUNCH_OPTION}")
    print("\nThen start the game once from Steam, wait for the main menu, and quit. Then run `make start`.")
    return 0


# ---------------------------------------------------------------- gates

def holes(obj, culled, gap):
    py = VENV_PY if os.path.isfile(VENV_PY) else sys.executable
    r = run([py, os.path.join(ROOT, "tools", "check_holes.py"), obj, "--quiet",
             "--fail-culled", str(culled), "--fail-gap", str(gap)], cwd=ROOT)
    last = (r.stdout.strip().splitlines() or [r.stderr.strip()])[-1].strip()
    return obj, r.returncode, last


# Set for the gates' own test run: a test that reaches cmd_gates gets a refusal instead of a nested run of the tests.
IN_TESTS = "WERKSTATT_IN_TESTS"


def cmd_gates(args):
    """Every gate, or only the named vehicles' mesh gates plus the repo-wide ones (`make loop` passes one)."""
    if os.environ.get(IN_TESTS):
        print("Gates refused: a test reached the real gates (they run the tests, which would run them again).")
        return 1
    py = VENV_PY if os.path.isfile(VENV_PY) else sys.executable
    chosen = [v for v in vehicles() if not args or os.path.basename(v) in args]
    failed = []
    jobs = []
    for v in chosen:
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
    for v in chosen:
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
    if dotnet_sdk_major() >= 10:
        maps = sorted(glob.glob(os.path.join(ROOT, "tests", "maps", "*.maps")))
        r = run(["dotnet", "run", "--project", "tools/near-plan", "-v", "quiet", "--"] + maps, cwd=ROOT)
        print(f"nearplan {'ok  ' if r.returncode == 0 else 'FAIL'} {len(maps)} memory layouts")
        if r.returncode:
            print(r.stdout + r.stderr)
            failed.append("nearplan")
    else:
        print("nearplan skip the plugin's hook-page placement test needs the .NET 10 SDK; it tests the plugin's "
              "source, which CI and every release already ran")
    # The tests build fake game folders; the Makefile's exported folders and FORCE stay out of their way.
    test_env = {k: v for k, v in os.environ.items() if k not in ("DEPLOY_DIR", "FORCE", "GAME_DIR", "MY_GAMES")}
    test_env[IN_TESTS] = "1"
    for label, cmd in (("updates ", [sys.executable, "-W", "ignore", "-m", "unittest", "discover", "-s", "tests"]),
                       ("names   ", [sys.executable, "tools/check_names.py"]),
                       ("catalog ", [sys.executable, "tools/catalogue.py", "--check"]),
                       ("packs   ", [sys.executable, "tools/pack.py", "check"])):
        r = run(cmd, cwd=ROOT, env=test_env)
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
    out = {"VehicleMods.dll": plugin_dll()}
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
    if into_game:
        # After a game update the plugin must be compiled against the interop BepInEx regenerates on the next
        # start; deploying before that would record the new game with a plugin built for the old one. Without a
        # record (deploys before it existed) the game's code files newer than BepInEx's last start tell.
        settle(game, folder)
        rec = deploy_record(folder) if os.path.isdir(folder) else None
        recorded = (rec or {}).get("game")
        changed = game_changed(recorded, game_record(game, known=recorded)) if recorded else not game_prepared(game)
        if rec and changed and not move_aside(game, folder, "The game has changed since the last deploy"):
            return 1
        aside = aside_dir(folder)
        # A plugin that fits the game needs no proof from BepInEx's log (which may be switched off).
        prepared = (aside_prepared(game, aside) if os.path.isdir(aside) else
                    True if recorded and not changed else game_prepared(game))
        if not prepared:
            print("The game has changed since BepInEx last started it, so the plugin can't be built for it yet.\n"
                  "Start the game once from Steam (it runs without Die Kollektion this time), quit, then deploy again.")
            return 1
        if os.path.isdir(aside):
            retire_aside(aside)
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


def cmd_compile_plugin(_args):
    """Use the release's prebuilt plugin when it fits this game; otherwise compile it with the .NET SDK."""
    return compile_plugin(game_dir())


def cmd_copy_deploy(args):
    """Copy what expected_sources() lists (the plugin and each vehicle's manifest, meshes and icon) into place."""
    folder = deploy_dir_arg(args)
    sources = expected_sources()
    missing = sorted(dest for dest, src in sources.items() if not os.path.isfile(src))
    if missing:
        print("Not built yet, so not deployed:\n  " + "\n  ".join(missing) + "\nRun `make all`.")
        return 1
    for dest, src in sorted(sources.items()):
        target = os.path.join(folder, *dest.split("/"))
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copyfile(src, target)
    return 0


def cmd_record_deploy(args):
    """Write deployed.json: every file and its sha256, where it came from, and the game's version it was built for."""
    folder = deploy_dir_arg(args)
    files = listing(folder)
    sources = expected_sources()
    missing = sorted(set(sources) - set(files))
    if missing:
        print("The deploy is missing files it should have copied:\n  " + "\n  ".join(missing))
        return 1
    head, branch, dirty = checkout() or (None, None, False)
    record = {
        "notes": "Written by `make deploy`. `make undeploy` removes exactly these files; `make status` compares them with the repo.",
        "tool": "werkstatt",
        "deployedAt": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        # The repo's commit and branch when it is a git checkout, else null.
        "repoCommit": head + ("+dirty" if dirty else "") if head else None,
        "branch": branch,
        "plugin": "prebuilt" if expected_sources()["VehicleMods.dll"] != SOURCE_DLL else "compiled",
        # What run_werkstatt.sh and `make update` compare with the game to notice an update.
        "game": game_record(game) if (game := game_dir()) else None,
        "files": [{"path": rel, "sha256": sha256(p),
                   "source": os.path.relpath(sources[rel], ROOT).replace(os.sep, "/") if rel in sources else None}
                  for rel, p in sorted(files.items())],
    }
    write_json(os.path.join(folder, "deployed.json"), record)
    if game and not WINDOWS and os.path.realpath(folder).startswith(os.path.realpath(game) + os.sep):
        install_launch_script(game)
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


# ---------------------------------------------------------------- game updates

# A Steam update replaces GameAssembly.so and global-metadata.dat; BepInEx regenerates its interop from them on
# the next start, and a plugin compiled against the old interop can hang the game at start. Each deploy records
# these files, `run_werkstatt.sh` and `make update` compare them with the game, and on a difference the plugin
# folder is moved aside (outside plugins/, so that launch runs stock and BepInEx regenerates the interop). Once
# BepInEx has prepared the game, the DLL is rebuilt against the new interop, put together with the vehicle files
# from the aside folder (gated when they were deployed) in a staging folder, and renamed into place.
GAME_FILES = {"gameAssembly": "GameAssembly.so", "globalMetadata": "*_Data/il2cpp_data/Metadata/global-metadata.dat"}
ASIDE_NOTE = "aside.json"
LOG_CAP = 256 * 1024


def write_atomic(path, text, mode=0o644):
    """Write through a temp file in the same folder and os.replace: a reader sees the old file or the new one."""
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path) or ".", prefix=f".{os.path.basename(path)}.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def write_json(path, data):
    write_atomic(path, json.dumps(data, indent=1) + "\n")


def rename_dir(src, dst):
    """Move a folder with one rename, so it is never half moved; across filesystems (EXDEV) it refuses."""
    try:
        os.rename(src, dst)
    except OSError as error:
        if error.errno == errno.EXDEV:
            raise RuntimeError(f"{src} and {dst} are on different filesystems") from error
        raise


@contextlib.contextmanager
def werkstatt_lock(game, wait=0.0):
    """One Werkstatt step at a time on a game folder (a launch's checks, a rebuild, `make update`, `make deploy`).
    Yields False when another step still holds BepInEx/werkstatt.lock after `wait` seconds."""
    if fcntl is None or not game:
        yield True
        return
    path = os.path.join(game, "BepInEx", "werkstatt.lock")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a") as f:
        deadline = time.monotonic() + wait
        while True:
            try:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    yield False
                    return
                time.sleep(0.5)
        try:
            yield True
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def game_file_paths(game):
    out = {}
    for key, pattern in GAME_FILES.items():
        found = sorted(glob.glob(os.path.join(glob.escape(game), pattern)))
        out[key] = found[0] if found else None
    return out


def game_record(game, known=None):
    """The game's version as a deploy records it. `known` (an earlier record) lets unchanged files skip hashing:
    a file with the same size and modification time keeps its recorded sha256."""
    known_files = (known or {}).get("files", {})
    files = {}
    for key, path in game_file_paths(game).items():
        if not path:
            files[key] = None
            continue
        st = os.stat(path)
        entry = {"size": st.st_size, "mtime": st.st_mtime_ns}
        old = known_files.get(key) or {}
        same = old.get("size") == entry["size"] and old.get("mtime") == entry["mtime"] and old.get("sha256")
        entry["sha256"] = old["sha256"] if same else sha256(path)
        files[key] = entry
    manifest_ = steam_manifest(game)
    updated = manifest_.get("lastupdated")
    return {"steamBuild": manifest_.get("buildid"),
            "steamUpdated": int(updated) if updated and updated.isdigit() else None,
            "files": files, "interopHash": interop_hash(game)}


def game_changed(recorded, live):
    """True when the game's code files differ from the recorded ones. The Steam build alone doesn't count:
    an update that leaves GameAssembly.so and global-metadata.dat alone needs no rebuild."""
    for key in GAME_FILES:
        old, new = (recorded.get("files") or {}).get(key), (live.get("files") or {}).get(key)
        if (old or {}).get("sha256") != (new or {}).get("sha256"):
            return True
    return False


def files_touched(recorded, live):
    """Same content, new size or time (a Steam verify rewrites files): worth saving, so the next check skips hashing."""
    return any(((recorded.get("files") or {}).get(k) or {}).get("mtime") != ((live.get("files") or {}).get(k) or {}).get("mtime")
               for k in GAME_FILES)


def launch_decision(deployed, record_game, live_game, aside, prepared=True):
    """What run_werkstatt.sh does before a launch: "plain" (start the game as it is), "move-aside" (the game
    changed since the deploy: start it without the plugin, rebuild after) or "pending" (the plugin is aside from
    an earlier launch or `make update`: start without it, try the rebuild after). A deploy that predates the
    record can't be compared; then `prepared` (game_prepared) decides: BepInEx hasn't run since the game's code
    files changed means the plugin's interop is older than the game."""
    if aside:
        return "pending"
    if not deployed:
        return "plain"
    if not record_game:
        return "plain" if prepared else "move-aside"
    return "move-aside" if game_changed(record_game, live_game) else "plain"


def rebuild_ready(note, live_interop, log_written, log_text):
    """BepInEx has prepared the updated game: its interop hash changed since the plugin was moved aside, or it
    started the game since then and got past interop generation (its hash may not cover what the update changed)."""
    if note.get("interopHash") and live_interop and live_interop != note["interopHash"]:
        return True
    return bool(log_written and log_written > note.get("movedAt", float("inf")) and "Chainloader initialized" in log_text)


def bepinex_log(game):
    """(modification time, text) of BepInEx's log of its last start, or (None, "")."""
    path = os.path.join(game, "BepInEx", "LogOutput.log")
    try:
        with open(path, errors="replace") as f:
            return os.path.getmtime(path), f.read()
    except OSError:
        return None, ""


def game_prepared(game):
    """BepInEx has started the game since its code files last changed and got past interop generation, so the
    interop on disk is the game's own: what a plugin may be compiled against."""
    newest = max((os.path.getmtime(p) for p in game_file_paths(game).values() if p), default=0)
    written, text = bepinex_log(game)
    return bool(interop_hash(game)) and rebuild_ready({"movedAt": newest}, None, written, text)


def aside_dir(folder):
    # BepInEx loads every DLL under plugins/, so the folder goes one level up, next to plugins/. Next to the
    # real plugins/ when it is a symlink: on the same filesystem, so moving it there is a rename.
    parent = os.path.realpath(os.path.dirname(folder))
    if os.path.basename(os.path.dirname(folder)) == "plugins":
        parent = os.path.dirname(parent)
    return os.path.join(parent, f"{os.path.basename(folder)}.aside")


def replaced_dir(folder):
    return f"{aside_dir(folder)[:-len('.aside')]}.replaced-{datetime.datetime.now():%Y%m%d-%H%M%S}"


def deploy_record(folder):
    p = os.path.join(folder, "deployed.json")
    try:
        with open(p) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def stamp(message):
    print(f"{datetime.datetime.now().astimezone():%Y-%m-%d %H:%M:%S} {message}", flush=True)


def date_of(timestamp):
    return datetime.datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d") if timestamp else "an unknown date"


def move_aside(game, folder, why):
    aside = aside_dir(folder)
    if os.path.exists(aside):
        stamp(f"{aside} already exists; not moving {folder} over it")
        return False
    built_for = (deploy_record(folder) or {}).get("game") or {}
    try:
        rename_dir(folder, aside)
    except (OSError, RuntimeError) as error:
        stamp(f"Couldn't move the plugin aside ({error}); the game starts with it")
        return False
    # The interop the plugin was built against: a different one on disk means BepInEx has regenerated it.
    write_json(os.path.join(aside, ASIDE_NOTE), {
        "notes": "Written by Werkstatt when the game updated: the plugin waits here, outside plugins/, until "
                 "`make update` or run_werkstatt.sh rebuilds it for the new game.",
        "movedAt": datetime.datetime.now().timestamp(), "why": why,
        "interopHash": built_for.get("interopHash"), "steamBuild": built_for.get("steamBuild")})
    stamp(f"{why}: moved the plugin aside to {aside} for now")
    return True


def aside_note(aside):
    """move_aside's note. Missing or unreadable (cut off before it was written), what it would say is recovered:
    the interop from the plugin's own deployed.json, and the folder's time as the time of the move."""
    try:
        with open(os.path.join(aside, ASIDE_NOTE)) as f:
            note = json.load(f)
        if isinstance(note, dict) and note.get("movedAt"):
            return note
    except (OSError, ValueError):
        pass
    built_for = (deploy_record(aside) or {}).get("game") or {}
    return {"interopHash": built_for.get("interopHash"), "steamBuild": built_for.get("steamBuild"),
            "movedAt": os.stat(aside).st_mtime}


def aside_prepared(game, aside):
    """BepInEx has prepared the game since the plugin was moved aside (rebuild_ready), or since the game's code
    files last changed (game_prepared)."""
    written, text = bepinex_log(game)
    return rebuild_ready(aside_note(aside), interop_hash(game), written, text) or game_prepared(game)


def retire_aside(aside):
    """Remove the old plugin folder once a new one is installed, unless it holds the player's own changes:
    a file changed or added by hand since the deploy keeps the whole folder, renamed next to it."""
    record = deploy_record(aside) or {}
    files = listing(aside)
    files.pop(ASIDE_NOTE, None)
    recorded = {f["path"]: f["sha256"] for f in record.get("files", [])}
    if record and set(files) == set(recorded) and all(sha256(p) == recorded[rel] for rel, p in files.items()):
        shutil.rmtree(aside)
        return
    kept = replaced_dir(aside[:-len(".aside")])
    rename_dir(aside, kept)
    stamp(f"The old plugin folder held files changed or added by hand; kept it as {kept}")


def settle(game, folder):
    """Finish what an interrupted install left: both the plugin folder and the aside folder exist when a rebuild
    was cut off between renaming the new plugin into place and retiring the old one. A plugin that fits the game
    is the finished rebuild, and the aside folder goes; one that doesn't is stale and leaves plugins/, so the
    game runs without it until the rebuild."""
    aside = aside_dir(folder)
    if not (os.path.isdir(aside) and os.path.isdir(folder)):
        return
    recorded = (deploy_record(folder) or {}).get("game")
    if recorded and not game_changed(recorded, game_record(game, known=recorded)):
        retire_aside(aside)
        stamp("An earlier install was cut off before it finished; the installed plugin fits the game, so it stays")
        return
    kept = replaced_dir(folder)
    rename_dir(folder, kept)
    stamp(f"Both a plugin and the one waiting aside were there, and the installed one doesn't fit the game; moved it to {kept}")


def rebuild_refusal(record):
    """Why the automatic rebuild won't compile this checkout, or None. It replaces only the DLL and keeps the
    deployed vehicle files, so the plugin's source must be the one that deploy was built from."""
    deployed = (record.get("repoCommit") or "").replace("+dirty", "") or None
    repo = checkout()
    head = repo[0] if repo else None
    if deployed != head:
        return (f"the plugin was deployed from {deployed[:7] if deployed else 'a copy without git'}, "
                f"and {ROOT} is now at {head[:7] if head else 'no commit'}")
    # Untracked files count: the project compiles every .cs file in the folder (build output is gitignored).
    if repo and git("status", "--porcelain", "--untracked-files=normal", "--", "plugins/VehicleMods"):
        return f"plugins/VehicleMods in {ROOT} has uncommitted changes"
    return None


def compile_plugin(game, isolated=False):
    """The release's prebuilt plugin when it fits this game, else a compile with the .NET SDK. `isolated` leaves
    no MSBuild or compiler server running afterwards (a rebuild after a launch must not keep processes alive)."""
    ready, why = prebuilt_plugin(game)
    if ready:
        print("Using the plugin that comes ready-made in this release (built for your version of the game).")
        return 0
    if dotnet_sdk_major() < 6:
        say("The plugin has to be compiled here, and the .NET SDK isn't installed.",
            f"Why compile: {why}.\n\n{install_hint('dotnet')}\n\nThen run the same command again.")
        return 1
    cmd = ["dotnet", "build", "-c", "Release", "-nologo", "-v", "minimal", "-p:Deploy=false", f"-p:GameDir={game}"]
    env = None
    if isolated:
        cmd += ["-nodeReuse:false", "-p:UseSharedCompilation=false"]
        env = {**os.environ, "MSBUILDDISABLENODEREUSE": "1", "DOTNET_CLI_USE_MSBUILD_SERVER": "0"}
    return subprocess.run(cmd, cwd=os.path.join(ROOT, "plugins", "VehicleMods"), env=env).returncode


def rebuild_from_aside(game, folder, automatic):
    """Rebuild the DLL of the plugin moved aside after a game update and install it again, with the vehicle files
    from the aside folder: "rebuilt", "nothing" (no plugin aside), "waiting" (BepInEx hasn't prepared the updated
    game yet), "redeploy" (this checkout isn't what was deployed: `make update` deploys it in full, with the gates)
    or "failed". The new install is put together in a staging folder and renamed into place; until then the
    plugin stays aside and the game runs stock."""
    settle(game, folder)
    aside = aside_dir(folder)
    if not os.path.isdir(aside):
        return "nothing"
    if not aside_prepared(game, aside):
        stamp("BepInEx hasn't prepared the updated game yet. Start the game once (it runs without Die Kollektion "
              "this time), quit, and the plugin is rebuilt: by run_werkstatt.sh on its own, or with `make update`")
        return "waiting"
    record = deploy_record(aside)
    refusal = rebuild_refusal(record) if record else "the plugin waiting aside has no deployed.json"
    if refusal:
        if automatic:
            stamp(f"Not rebuilding on its own: {refusal}. Run `make update` in the Werkstatt folder; it deploys "
                  "the checkout in full, with the gates")
            return "failed"
        return "redeploy"
    stamp("Rebuilding the plugin for the updated game")
    if compile_plugin(game, isolated=True) != 0:
        stamp(f"The plugin couldn't be built (above); it stays aside in {aside} and the game runs without it")
        return "failed"
    if game_running():
        stamp("The game was started again during the rebuild; the plugin stays aside until the next `make update` or launch")
        return "failed"
    if os.path.exists(folder):
        stamp(f"{folder} exists again (deployed since?); leaving the old plugin aside in {aside}")
        return "failed"
    staging = aside_dir(folder)[:-len(".aside")] + ".staging"
    try:
        if os.path.exists(staging):
            shutil.rmtree(staging)
        shutil.copytree(aside, staging, ignore=lambda d, names: [n for n in names if d == aside and n in (ASIDE_NOTE, "deployed.json")])
        dll = plugin_dll(game)
        shutil.copyfile(dll, os.path.join(staging, "VehicleMods.dll"))
        sources = {f["path"]: f.get("source") for f in record.get("files", [])}
        write_json(os.path.join(staging, "deployed.json"), {
            **record,
            "plugin": "prebuilt" if dll != SOURCE_DLL else "compiled",
            "game": game_record(game),
            "afterUpdate": {"fromBuild": (record.get("game") or {}).get("steamBuild") or aside_note(aside).get("steamBuild"),
                            "rebuiltAt": datetime.datetime.now().astimezone().isoformat(timespec="seconds")},
            "files": [{"path": rel, "sha256": sha256(p), "source": sources.get(rel)} for rel, p in sorted(listing(staging).items())],
        })
        rename_dir(staging, folder)
    except Exception as error:
        stamp(f"Installing the rebuilt plugin failed ({error}); it stays aside in {aside}")
        shutil.rmtree(staging, ignore_errors=True)
        return "failed"
    retire_aside(aside)
    stamp(f"Rebuilt the plugin for Steam build {steam_build(game) or '?'} and installed it in {folder}")
    return "rebuilt"


def update_report(game, folder):
    """One line on whether the deployed plugin fits the game, for `make status` and `make start`:
    (state, text) with state "current", "rebuilt", "needed" or "unknown". It reads, and changes nothing."""
    updated = steam_manifest(game).get("lastupdated", "")
    when = date_of(int(updated) if updated.isdigit() else None)
    needed = (f"the game updated on {when}; a rebuild is still needed (run `make update`, or launch once through "
              f"{LAUNCH_SCRIPT}), and until then the game runs without Die Kollektion")
    rec = deploy_record(folder) if os.path.isdir(folder) else None
    recorded = (rec or {}).get("game")
    fits = bool(recorded) and not game_changed(recorded, game_record(game, known=recorded))
    if os.path.isdir(aside_dir(folder)) and not fits:
        return "needed", needed
    if not rec:
        return "unknown", "nothing deployed"
    if not recorded:
        if not game_prepared(game):
            return "needed", needed
        return "unknown", "not recorded (deployed before Werkstatt recorded the game's version; `make deploy` records it)"
    if not fits:
        return "needed", needed
    if rec.get("afterUpdate"):
        return "rebuilt", f"the game updated on {when}; rebuilt {rec['afterUpdate'].get('rebuiltAt', '')}".rstrip()
    return "current", f"the plugin fits this game (Steam build {recorded.get('steamBuild') or '?'})"


def shell_quote(text):
    return "'" + text.replace("'", "'\\''") + "'"


def launch_script_target(game):
    """The Werkstatt folder the game's run_werkstatt.sh points at, "" when its line is empty, None when it isn't installed."""
    path = os.path.join(game, LAUNCH_SCRIPT)
    try:
        with open(path) as f:
            m = re.search(r"^WERKSTATT_DIR=(.*)$", f.read(), re.M)
    except OSError:
        return None
    if not (m and os.access(path, os.X_OK)):
        return None
    try:
        return (shlex.split(m.group(1)) or [""])[0]
    except ValueError:
        return None


def launch_script_ready(game):
    return bool(launch_script_target(game))


def install_launch_script(game):
    """Copy tools/run_werkstatt.sh into the game folder, pointed at this Werkstatt folder."""
    with open(LAUNCH_SOURCE) as f:
        text = f.read()
    text = re.sub(r"^WERKSTATT_DIR=.*$", lambda _m: f"WERKSTATT_DIR={shell_quote(ROOT)}", text, count=1, flags=re.M)
    path = os.path.join(game, LAUNCH_SCRIPT)
    try:
        with open(path) as f:
            same = f.read() == text
    except OSError:
        same = False
    if not same or not os.access(path, os.X_OK):
        write_atomic(path, text, 0o755)
    return path


def deploy_steps(args):
    for step in (cmd_preflight_deploy, cmd_compile_plugin, cmd_copy_deploy, cmd_record_deploy):
        if step(args) != 0:
            return 1
    return 0


def cmd_deploy(args):
    """`make deploy` after its gates: preflight, compile, copy and record, holding the game folder's Werkstatt lock."""
    with werkstatt_lock(game_dir()) as held:
        if not held:
            print("Another Werkstatt step is working on the game folder (a rebuild after a launch?). Try again in a minute.")
            return 1
        return deploy_steps(args)


def cmd_update(args):
    """`make update`: after a game update, move the plugin aside and rebuild it once BepInEx has prepared the game.
    When this checkout isn't what was deployed, it deploys it in full instead, with the gates."""
    game = game_dir()
    folder = deploy_dir_arg(args)
    if not game or not folder:
        print("Over the Hill not found. Install it in Steam, or set GAME_DIR.")
        return 1
    if game_running():
        print("The game is running. Quit it, then run `make update`.")
        return 1
    with werkstatt_lock(game) as held:
        if not held:
            print("Another Werkstatt step is working on the game folder (a rebuild after a launch?). Try again in a minute.")
            return 1
        settle(game, folder)
        if not os.path.isdir(aside_dir(folder)):
            rec = deploy_record(folder)
            if not rec:
                print("Nothing deployed yet. Run `make all`.")
                return 0
            recorded = rec.get("game")
            live = game_record(game, known=recorded) if recorded else None
            if launch_decision(True, recorded, live, False, game_prepared(game)) == "plain":
                print(f"The deployed plugin fits this game (Steam build {steam_build(game) or '?'}); nothing to do."
                      if recorded else "The deploy predates Werkstatt's record of the game's version, and BepInEx has "
                      "started the game since it last changed; nothing to do. `make deploy` records the version.")
                return 0
            if not move_aside(game, folder, "The game has changed since the last deploy"):
                return 1
        result = rebuild_from_aside(game, folder, automatic=False)
        if result != "redeploy":
            return 0 if result in ("rebuilt", "waiting", "nothing") else 1
        print(f"This checkout isn't what was deployed ({rebuild_refusal(deploy_record(aside_dir(folder)) or {}) or 'no record'}); "
              "deploying it in full, with the gates.")
        if cmd_gates([]) != 0:
            return 1
        return deploy_steps(args)


def cmd_launch_before(_args):
    """run_werkstatt.sh, before the game starts. Exit 0: start it as it is. Exit 3: the plugin is aside for this
    launch; call launch-after once the game has exited. Any other exit also starts the game as it is."""
    game = game_dir()
    folder = default_deploy_dir(game)
    # With the plugin aside a stock launch is safe, and the rebuild checks for a running game before its rename,
    # so a launch during a rebuild doesn't wait for it (Steam would show the game running with no window).
    waiting_aside = os.path.isdir(aside_dir(folder)) and not os.path.isdir(folder)
    test_save = test_save_status()
    if test_save:
        stamp(f"Launch: {test_save}")      # on every launch path, like the lock's own notes
    with werkstatt_lock(game, wait=0 if waiting_aside else 5) as held:
        if not held:
            if waiting_aside:
                stamp("Launch: the plugin is aside and a rebuild is running; starting without it, trying again after the game exits")
                return 3
            stamp("Launch: another Werkstatt step still holds the game folder; starting normally")
            return 0
        settle(game, folder)
        rec = deploy_record(folder) if os.path.isdir(folder) else None
        recorded = (rec or {}).get("game")
        # Hashing only when there is a record to compare with; unchanged files keep their recorded hashes.
        live = game_record(game, known=recorded) if recorded else {"steamBuild": steam_build(game)}
        prepared = True if recorded or rec is None else game_prepared(game)
        decision = launch_decision(rec is not None, recorded, live, os.path.isdir(aside_dir(folder)), prepared)
        build = live["steamBuild"] or "?"
        if decision == "plain":
            if recorded and files_touched(recorded, live):
                write_json(os.path.join(folder, "deployed.json"), {**rec, "game": {**recorded, "files": live["files"]}})
            why = ("nothing deployed" if rec is None else
                   "no game version recorded (make deploy records it)" if not recorded else "the plugin fits this game")
            stamp(f"Launch: {why} (Steam build {build}); starting normally")
            return 0
        if decision == "pending":
            stamp("Launch: the plugin is still aside after a game update; starting without it, rebuilding after the game exits")
            return 3
        old = (recorded or {}).get("steamBuild") or "?"
        why = (f"Launch: the game updated (Steam build {old} → {build}) since the last deploy" if recorded else
               "Launch: the game's code files changed since BepInEx last started it, and the deploy has no record to compare")
        return 3 if move_aside(game, folder, why) else 0


def cmd_launch_after(_args):
    """run_werkstatt.sh, after the game exits: rebuild and reinstall the plugin moved aside before the launch."""
    game = game_dir()
    with werkstatt_lock(game) as held:
        if not held:
            stamp("After the launch: another Werkstatt step holds the game folder; the plugin stays aside for now")
            return 1
        result = rebuild_from_aside(game, default_deploy_dir(game), automatic=True)
    stamp(f"After the launch: {result}")
    return 0 if result != "failed" else 1


def log_to(path):
    """Send stdout and stderr, the subprocesses' too, to the end of `path`, first trimming it to its last LOG_CAP bytes."""
    try:
        if os.path.getsize(path) > LOG_CAP:
            with open(path, "rb") as f:
                f.seek(-LOG_CAP, os.SEEK_END)
                tail = f.read()
            write_atomic(path, tail[tail.find(b"\n") + 1:].decode(errors="replace"))
    except OSError:
        pass
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    sys.stdout.flush()
    sys.stderr.flush()
    os.dup2(fd, 1)
    os.dup2(fd, 2)
    os.close(fd)


def cmd_status(args):
    game = game_dir()
    repo = checkout()
    if repo:
        print(f"Checkout:     {repo[1]} @ {repo[0][:7]}{' (uncommitted changes)' if repo[2] else ''}")
    else:
        print("Checkout:     not a git checkout")
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
        if os.path.isfile(rec_path):
            rec = json.load(open(rec_path))
            commit = rec.get("repoCommit")
            if commit and repo:
                same = commit == repo[0] and not repo[2]
                print(f"  installed:  {rec.get('branch') or '?'} @ {commit[:7]}{'+dirty' if '+dirty' in commit else ''}"
                      f" ({rec.get('deployedAt', '?')}); "
                      + ("matches this checkout" if same and state == "current" else "differs from this checkout"))
            else:
                print(f"  installed:  {rec.get('deployedAt', '?')}")
        if game:
            print(f"Game version: {update_report(game, folder)[1]}")
    if game and not WINDOWS:
        target = launch_script_target(game)
        print(f"Launch script: {'not installed (make bepinex)' if target is None else 'installed, pointing nowhere (make bepinex)' if not target else target}"
              + (" (this checkout)" if target and os.path.realpath(target) == os.path.realpath(ROOT) else
                 " (another checkout: after a game update it rebuilds from there)" if target else ""))
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
    test_save = test_save_status()
    if test_save:
        print(f"Test save:    {test_save}")
    for v in vehicles():
        body = os.path.join(v, "build", "body_LOD0.obj")
        built = os.path.isfile(body)
        fresh = built and os.path.getmtime(body) >= os.path.getmtime(os.path.join(v, "vehicle.json"))
        print(f"Vehicle {os.path.basename(v):12s} {'built' if fresh else ('out of date' if built else 'not built')}")
    return 0


def cmd_save_add(args):
    # The parts list (slow on its first run: it reads the game's bundles) comes before the check for a running game.
    cars = parts_catalogue()
    if game_running():
        print("The game is running. Quit it first: the game overwrites the save when it quits.")
        return 1
    if save_add_blocked():
        return 1
    # The Makefile exports PROFILE even when it is unset, so an empty value means the default.
    profile = os.environ.get("PROFILE") or "Player1"
    saves = os.path.join(my_games(), "Saves")
    save = os.path.join(saves, profile + ".json")
    if not os.path.isfile(save):
        others = sorted(os.path.basename(p)[:-5] for p in glob.glob(os.path.join(saves, "*.json")))
        print(f"No save at {save}." + (f" Profiles found: {', '.join(others)}; pick one with PROFILE=<name>."
                                       if others else
                                       " Start the game once and play past the start, then quit and try again."))
        return 1
    print(f"Adding the trucks to {save} (backed up first if anything changes).", flush=True)
    ids = [a for a in args if a.isdigit()] or [str(i) for i in ITEM_IDS.values()]
    cmd = [sys.executable, os.path.join(ROOT, "tools", "add_vehicle_to_save.py"), save] + ids
    if cars:
        # Each truck also gets a state on every cosmetic its donor owns: cosmetics unlocked before it was registered
        # miss it (the game writes one state per car in the catalogue when a reward unlocks a cosmetic).
        cmd += ["--parts", os.path.join(ROOT, "extracted", "parts.json")]
        for m in map(manifest, vehicles()):
            if m.get("itemId") and m.get("donor") in cars:
                cmd += ["--truck", f"{m['itemId']}:{m['donor']}:{m.get('codename', m['itemId'])}"]
    else:
        print("Couldn't read the game's parts list (extracted/parts.json), so the trucks get their cars but not their "
              "donor's cosmetics. Run `make setup` and `make extract`, then `make save-add` again.")
    r = subprocess.run(cmd)
    return r.returncode


def save_profile():
    """(profile name, Saves folder, its save file); the Makefile exports PROFILE even when unset."""
    profile = os.environ.get("PROFILE") or "Player1"
    saves = os.path.join(my_games(), "Saves")
    return profile, saves, os.path.join(saves, profile + ".json")


def test_save_paths():
    """`make save-test` swaps the whole Saves/ folder (save, its .bak, FogOfWar/, Animals/) by renames on one
    filesystem: the real folder is parked beside it, never copied over or deleted."""
    base = os.path.join(my_games(), "DieKollektion")
    folder = os.path.join(base, "test-save")
    return {"saves": os.path.join(my_games(), "Saves"), "folder": folder,
            "parked": os.path.join(folder, "Saves"), "building": os.path.join(folder, "Saves.building"),
            "note": os.path.join(folder, "test-save.json"), "backups": os.path.join(base, "backups", "test-save")}


def parts_catalogue():
    """extracted/parts.json, written from the player's own bundles (tools/export_parts.py) when missing."""
    path = os.path.join(ROOT, "extracted", "parts.json")
    if not os.path.isfile(path):
        game = game_dir()
        aa = os.path.join(game or "", f"{GAME_FOLDER}_Data", "StreamingAssets", "aa", "StandaloneWindows64" if WINDOWS else "StandaloneLinux64")
        bundles = [b for pattern in ("scriptableobjects_assets_all_*.bundle", "cars_assets_all_*.bundle", "*_monoscripts_*.bundle")
                   for b in glob.glob(os.path.join(aa, pattern))]
        py = VENV_PY if os.path.isfile(VENV_PY) else None
        if len(bundles) != 3 or not py:
            return None
        if subprocess.run([py, "-I", os.path.join(ROOT, "tools", "export_parts.py"), path] + bundles).returncode:
            return None
    return json.load(open(path))["cars"]


# A save whose stock cars lack under this share of their upgrades is taken for a test save (save_unlock.upgrade_gap):
# against the parked real save at save-real, against all of them at save-test.
TEST_SAVE_SHARE = 0.1
STEAM_WAIT = "After quitting the game, wait until Steam has finished syncing before `make save-test` or `make save-real`."
STEAM_CLOUD_BEFORE = ("Steam Cloud: launch the game once on this machine before `make save-test`, so your local save "
                      "is current. While the test save is in place, don't play on another machine (Steam would "
                      "download the test save there), and if Steam reports a conflict, keep the local files. "
                      + STEAM_WAIT)
STEAM_CLOUD_AFTER = ("Steam Cloud uploads your own save on the next launch; if Steam reports a conflict, keep the "
                     "local files.")


def fsync_tree(path):
    """Flush a folder's files and the folder itself to disk."""
    for top, _dirs, files in os.walk(path):
        for name in files + ["."]:
            fsync_file(os.path.join(top, name))


def fsync_file(path):
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def write_note(paths, note):
    """The test save's note, on disk before the step it describes."""
    os.makedirs(paths["folder"], exist_ok=True)
    write_json(paths["note"], note)
    fsync_file(paths["note"])
    fsync_file(paths["folder"])


def read_note(paths):
    try:
        with open(paths["note"]) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def test_save_state(paths):
    """Where a test save stands, from the folders themselves (the note may be missing or behind):
    "none", "in place" (real folder parked, a Saves/ in use), "half" (real folder parked, no Saves/: a swap was
    cut off). A note left by a run that never parked anything is cleared along with its staging copy."""
    parked, live = os.path.isdir(paths["parked"]), os.path.isdir(paths["saves"])
    if not parked:
        if os.path.isdir(paths["building"]) and live:
            shutil.rmtree(paths["building"])     # a copy of the live folder, never the only one
        if os.path.isfile(paths["note"]) and live:
            os.remove(paths["note"])
        return "none"
    return "in place" if live else "half"


def rename_or_explain(src, dst, first=True):
    """os.rename, or a plain reason (another filesystem, a permission) and False; the folder is never half moved.
    `first`: no earlier step of this command moved anything, so nothing changed."""
    try:
        os.rename(src, dst)
        return True
    except OSError as error:
        why = "they are on different filesystems" if error.errno == errno.EXDEV else error.strerror
        print(f"Couldn't move {src} to {dst}: {why}." + (" Nothing changed." if first else ""))
        return False


def unique_folder(folder, stem):
    """folder/stem, or folder/stem-2, -3...: a name nothing holds yet."""
    path, n = os.path.join(folder, stem), 1
    while os.path.exists(path):
        n += 1
        path = os.path.join(folder, f"{stem}-{n}")
    return path


def looks_like_test_save(save, cars, names, reference=None):
    """True when the save's stock cars own nearly all their upgrades: under TEST_SAVE_SHARE of what `reference`
    (the parked real save) lacks, or of all of them without one."""
    import save_unlock
    missing, total = save_unlock.upgrade_gap(save, cars, names)
    if reference is not None:
        ref_missing = save_unlock.upgrade_gap(reference, cars, names)[0]
        if ref_missing:
            return missing < TEST_SAVE_SHARE * ref_missing
    return total > 0 and missing < TEST_SAVE_SHARE * total


def load_save(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def cmd_save_test(_args):
    """`make save-test`: park the real Saves/ folder and put a copy in its place in which every car owns every part
    it offers. A swap cut off earlier (real folder parked, no Saves/) is finished."""
    import save_unlock
    paths = test_save_paths()
    profile, saves, save = save_profile()
    cars = parts_catalogue()     # the slow part, before any check that a swap relies on
    if not cars:
        print("Couldn't read the game's parts list (extracted/parts.json). Run `make setup` and `make extract`, then try again.")
        return 1
    derived = {m["itemId"]: m["donor"] for m in map(manifest, vehicles()) if m.get("itemId") and m.get("donor") in cars}
    if game_running():
        print("The game is running. Quit it first: the game overwrites the save when it quits.")
        return 1
    if test_save_state(paths) != "none":
        return _finish_or_refuse(paths, profile)
    source = os.path.join(saves, profile + ".json")
    if not os.path.isfile(source):
        print(f"No save at {source}. Start the game once and play past the start, then quit and try again.")
        return 1
    data = load_save(source)
    names = save_unlock.stock_names(cars)
    if looks_like_test_save(data, cars, names):
        print(f"{source} already looks like a test save (every car owns every part), so it isn't parked as your own. "
              f"If a test save is in place, `make save-real` puts yours back.")
        return 1
    report = save_unlock.unlock(data, cars, derived)
    text = save_unlock.dumps(data)
    building = paths["building"]
    if os.path.isdir(building):
        shutil.rmtree(building)
    os.makedirs(paths["folder"], exist_ok=True)
    shutil.copytree(saves, building)
    write_atomic(os.path.join(building, profile + ".json"), text)
    if hashlib.sha256(text.encode("utf-8")).hexdigest() != sha256(os.path.join(building, profile + ".json")):
        print("The test save didn't read back as written; nothing changed.")
        shutil.rmtree(building)
        return 1
    fsync_tree(building)
    note = {"state": "parking", "profile": profile, "createdAt": datetime.datetime.now().isoformat(timespec="seconds"),
            "realSha256": sha256(source), "testSha256": sha256(os.path.join(building, profile + ".json")),
            "cars": names, "trucks": {str(k): v for k, v in derived.items()}}
    write_note(paths, note)
    running = game_running()
    if running or not rename_or_explain(saves, paths["parked"]):
        if running:
            print("The game started; nothing changed.")
        shutil.rmtree(building)
        os.remove(paths["note"])
        return 1
    if sha256(os.path.join(paths["parked"], profile + ".json")) != note["realSha256"]:
        print(f"Warning: your parked save at {paths['parked']} doesn't match what was read; it is kept as it is.")
    write_note(paths, {**note, "state": "parked"})
    result = _land_test_save(paths, profile)
    if result == 0:
        print(f"Test save in place: every car owns every part it offers ({report['states']} part ownerships added on "
              f"{len(save_unlock.offers(cars, derived))} vehicles, {report['parts']} parts new to the save, "
              f"{report['liveries']} liveries; {report['dlc']} parts need a DLC and stay only if you own it).")
        if report["cars"]:
            print(f"Cars added to your garage for comparison: {len(report['cars'])}.")
        print(f"Your own Saves folder (save, fog of war, animal photos) is parked, untouched, in {paths['parked']}.\n"
              f"{STEAM_CLOUD_BEFORE}\n"
              "In the game: the mechanic, pick a truck, Cosmetics; each part previews on the truck before you fit it.\n"
              "Done testing? Quit the game and run `make save-real`.")
    return result


def _land_test_save(paths, profile):
    """Rename the built test folder into Saves/; the real folder is already parked."""
    if game_running():
        print(f"The game started before the test save was in place. Your own Saves folder is parked in {paths['parked']}; "
              "quit the game, then `make save-real` puts it back (or `make save-test` finishes the swap).")
        return 1
    if not rename_or_explain(paths["building"], paths["saves"], first=False):
        print(f"Your own Saves folder is parked in {paths['parked']}; `make save-real` puts it back.")
        return 1
    note = read_note(paths) or {"profile": profile}
    write_note(paths, {**note, "state": "built"})
    return 0


def _finish_or_refuse(paths, profile):
    """A swap cut off with the real folder parked and no Saves/: finish it when the built copy is there."""
    if test_save_state(paths) == "in place":
        note = read_note(paths) or {}
        print(f"A test save is already in place{' (since ' + note['createdAt'] + ')' if note.get('createdAt') else ''}. "
              "`make save-real` puts your own save back.")
        return 1
    if os.path.isdir(paths["building"]) and os.path.isfile(os.path.join(paths["building"], profile + ".json")):
        print("Finishing a test-save swap that was cut off.")
        return _land_test_save(paths, profile)
    note = read_note(paths) or {}
    if note.get("state") == "filed":
        print(f"`make save-real` was cut off after filing the test save. Your own Saves folder is parked in "
              f"{paths['parked']}; `make save-real` finishes putting it back.")
    else:
        print(f"A test-save swap was cut off before the test save was built. Your own Saves folder is parked in "
              f"{paths['parked']}; `make save-real` puts it back.")
    return 1


def save_add_blocked():
    """True (and says so) while a test save is in place or half swapped: edits would land in the test save."""
    paths = test_save_paths()
    state = test_save_state(paths)
    if state == "none":
        return False
    print(f"A test save is {'in place' if state == 'in place' else 'half swapped in'}; your own save is parked in "
          f"{paths['parked']}. `make save-real` puts it back first.")
    return True


def cmd_save_real(_args):
    """`make save-real`: copy the parked real save aside, file the Saves/ folder in place under backups/test-save/
    and rename the parked real one back. Refuses when the save in place doesn't look like the test save (FORCE=1
    restores anyway, filing it as a replaced save)."""
    paths = test_save_paths()
    state = test_save_state(paths)
    if state == "none":
        print("No test save in place; your save is your own.")
        return 0
    note = read_note(paths) or {}
    profile = note.get("profile") or save_profile()[0]
    live_save = os.path.join(paths["saves"], profile + ".json")
    parked_save = os.path.join(paths["parked"], profile + ".json")
    force = os.environ.get("FORCE") == "1"
    is_test = True
    if state == "in place":
        is_test = os.path.isfile(live_save) and sha256(live_save) == note.get("testSha256")
        if not is_test and os.path.isfile(live_save):
            cars = parts_catalogue()
            if cars:
                names = [n for n in note.get("cars") or [] if n in cars] or [n for n in cars if "[CatalogExcluded]" not in n]
                reference = load_save(parked_save) if os.path.isfile(parked_save) else None
                is_test = looks_like_test_save(load_save(live_save), cars, names, reference)
        if not is_test and not force:
            print(f"The save in place ({live_save}) doesn't look like the test save: Steam Cloud, a manual restore "
                  f"or a launch without the plugin may have changed it. Nothing changed. Your own Saves folder is "
                  f"parked in {paths['parked']}; FORCE=1 files the one in place under {paths['backups']} as replaced "
                  f"and restores yours anyway.")
            return 1
    if game_running():
        print("The game is running. Quit it first: the game overwrites the save when it quits.")
        return 1
    stamp_now = time.strftime('%Y%m%d-%H%M%S')
    os.makedirs(paths["backups"], exist_ok=True)
    # A copy of the real save outside Saves/ (which Steam Cloud syncs), made before anything moves.
    real_copy = unique_folder(paths["backups"], f"{profile}-real-{stamp_now}")
    os.makedirs(real_copy)
    for name in (profile + ".json", profile + ".json.bak"):
        if os.path.isfile(os.path.join(paths["parked"], name)):
            shutil.copy2(os.path.join(paths["parked"], name), os.path.join(real_copy, name))
    fsync_tree(real_copy)
    filed = None
    if state == "in place":
        filed = unique_folder(paths["backups"], f"{profile}-{'test-save' if is_test else 'replaced'}-{stamp_now}")
        if not rename_or_explain(paths["saves"], filed):
            return 1
        write_note(paths, {**note, "state": "filed", "filed": filed})
    if not rename_or_explain(paths["parked"], paths["saves"], first=not filed):
        print(f"Your own Saves folder is still parked in {paths['parked']} (and copied to {real_copy}); "
              "run `make save-real` again.")
        return 1
    real = os.path.join(paths["saves"], profile + ".json")
    if os.path.isfile(real):
        os.utime(real)       # newer than any test save in the cloud, so Steam keeps it; the content is unchanged
    if os.path.isfile(paths["note"]):
        if filed:
            os.replace(paths["note"], os.path.join(filed, "test-save.json"))
        else:
            os.remove(paths["note"])
    if os.path.isdir(paths["building"]):
        shutil.rmtree(paths["building"])     # an unused copy from a swap that was cut off
    exact = note.get("realSha256") is None or (os.path.isfile(real) and sha256(real) == note["realSha256"])
    print("Your own Saves folder is back, as it was" + ("" if exact else " (its save differs from the one parked; it is the folder that was parked)") + ".")
    print(f"A copy of your save is also kept in {real_copy}.")
    if filed:
        print(f"The test save as you left it: {filed}" if is_test else
              f"The save that was in place instead of the test save: {filed}")
    print(STEAM_CLOUD_AFTER)
    return 0


def test_save_status():
    """None, or a line for status, start and the launch log while a test save is in place."""
    paths = test_save_paths()
    if not os.path.isdir(paths["parked"]):
        return None
    note = read_note(paths) or {}
    profile = note.get("profile") or save_profile()[0]
    live = os.path.join(paths["saves"], profile + ".json")
    played = ("untouched" if os.path.isfile(live) and sha256(live) == note.get("testSha256") else
              "half swapped in" if not os.path.isdir(paths["saves"]) else "played")
    return f"a test save is in place since {note.get('createdAt', '?')} ({played}); `make save-real` puts your own save back"


def compared_with():
    """The commit a vehicle's change is summarised against, and how to describe it: on a branch, where it
    left main; on main, the last commit. None outside a git checkout."""
    repo = checkout()
    if not repo:
        return None, None
    if repo[1] == "main":
        return "HEAD", "the last commit"
    run(["git", "fetch", "--quiet", "origin", "main"], cwd=ROOT)
    base = git("merge-base", "HEAD", "origin/main") or git("merge-base", "HEAD", "main")
    return (base, "where this branch left main") if base else ("HEAD", "the last commit")


def cmd_loop(args):
    names = [os.path.basename(v) for v in vehicles()]
    if not args or args[0] not in names:
        print(f"Name a vehicle: make loop V=<{'|'.join(names)}>")
        return 2
    name = args[0]
    vdir = os.path.join(ROOT, "vehicles", name)
    # A vehicle's generator: tools/make_<name>.py (writes the whole manifest), and/or a part generator the
    # manifest names (e.g. tools/golf_bag.py), which rewrites its own meshes from the manifest it is given.
    make = os.path.join(ROOT, "tools", f"make_{name}.py")
    parts = manifest(vdir).get("generator")
    steps = ([[VENV_PY, make]] if os.path.isfile(make) else []) + (
        [[VENV_PY, os.path.join(ROOT, parts), os.path.join(vdir, "vehicle.json")]] if parts else []) + [
        [VENV_PY, os.path.join(ROOT, "tools", "build_vehicle.py"), os.path.join(vdir, "vehicle.json")],
        [sys.executable, os.path.abspath(__file__), "gates", name],
        [VENV_PY, os.path.join(ROOT, "tools", "composite_atlas.py"), manifest(vdir).get("base", {}).get("car", "Mammoth")],
        [VENV_PY, os.path.join(ROOT, "tools", "contact_sheet.py"), vdir],
    ]
    for cmd in steps:
        print("→ " + " ".join(os.path.relpath(c, ROOT) if c.startswith(ROOT) else c for c in cmd), flush=True)
        if subprocess.run(cmd, cwd=ROOT).returncode:
            print(f"Stopped here. Fix what it reports, then run `make loop V={name}` again.")
            return 1
    base, how = compared_with()
    old = git("show", f"{base}:vehicles/{name}/contact/contact.json") if base else None
    with tempfile.TemporaryDirectory() as tmp:
        old_path = "-"
        if old:
            old_path = os.path.join(tmp, "old.json")
            open(old_path, "w").write(old)
        r = run([VENV_PY, os.path.join(ROOT, "tools", "contact_sheet.py"), "--changes", old_path,
                 os.path.join(vdir, "contact", "contact.json")], cwd=ROOT)
    if r.returncode:
        print("contact_sheet.py --changes failed:\n" + r.stderr.strip())
        return 1
    note = (f"Compared with {base[:7]} ({how})." if old else
            "Nothing to compare with: " + ("no committed contact sheet for this vehicle." if base else "this copy isn't a git checkout."))
    open(os.path.join(vdir, "contact", "CHANGES.md"), "w").write(f"<!-- {note} -->\n" + r.stdout)
    print("\n" + note + "\n" + r.stdout)
    say("Next step:", f"Look at vehicles/{name}/README.md (the renders, the rig view and the gates). "
        f"vehicles/{name}/contact/CHANGES.md is the summary to share with the change.")
    return 0


COMMANDS = {
    "start": cmd_start, "require": cmd_require, "doctor": cmd_doctor, "game-dir": cmd_game_dir, "bepinex": cmd_bepinex,
    "gates": cmd_gates, "preflight-deploy": cmd_preflight_deploy, "record-deploy": cmd_record_deploy,
    "undeploy": cmd_undeploy, "status": cmd_status,
    "compile-plugin": cmd_compile_plugin, "copy-deploy": cmd_copy_deploy, "save-add": cmd_save_add, "loop": cmd_loop,
    "save-test": cmd_save_test, "save-real": cmd_save_real,
    "update": cmd_update, "launch-before": cmd_launch_before, "launch-after": cmd_launch_after, "deploy": cmd_deploy,
}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(__doc__)
        sys.exit(2)
    args = sys.argv[2:]
    # `timeout` and systemd stop with SIGTERM: exit through the finally/except blocks, so write_atomic removes
    # its temp file and the lock is released.
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
    if "--log" in args:
        i = args.index("--log")
        log_to(args[i + 1])
        del args[i:i + 2]
    sys.exit(COMMANDS[sys.argv[1]](args))
