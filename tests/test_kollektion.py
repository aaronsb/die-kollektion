"""`kollektion` on each target: the same checks run the linux-x64 build natively, the win-x64 build under Wine
(when wine is installed) and natively on Windows (the windows-latest CI job). Each finds the game through a fake
Steam install (libraryfolders.vdf naming a second library) and reads BepInEx, the interop hash and the Steam build
from the fake game folder, so the per-OS paths in Kollektion.Core are checked without a game.

They publish both builds (the .NET 10 SDK, and the network for its runtime packs), so they run only when asked:
KOLLEKTION_TESTS=1, which `python3 tools/release.py ci` and the CI matrix job set. The deploy's gates never run
them; a player's older SDK or offline machine would fail them there."""
import json
import os
import platform
import re
import shutil
import stat
import subprocess
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WINDOWS = platform.system() == "Windows"
HOST_RID = "win-x64" if WINDOWS else "linux-x64"
APP_ID = "2929250"
BEPINEX = "6.0.0-be.789+6cea286d204eb3754d3b8363a5a1fd6640164a49"
HASH = "0123456789abcdef0123456789abcdef"
BUILD = "26062472"
TIMEOUT = 120    # a run that takes longer is hung (a Wine dialog, say), not slow


def setUpModule():
    if os.environ.get("KOLLEKTION_TESTS") != "1":
        raise unittest.SkipTest("the kollektion tests run with KOLLEKTION_TESTS=1 (release.py ci, CI)")


def newest_source():
    newest = 0
    for d, dirs, files in os.walk(os.path.join(ROOT, "src")):
        dirs[:] = [x for x in dirs if x not in ("bin", "obj")]
        newest = max([newest] + [os.path.getmtime(os.path.join(d, f)) for f in files if f.endswith((".cs", ".csproj"))])
    return newest


def sdk_major():
    out = subprocess.run(["dotnet", "--list-sdks"], capture_output=True, text=True).stdout if shutil.which("dotnet") else ""
    return max((int(m.group(1)) for m in re.finditer(r"^(\d+)\.", out, re.M)), default=0)


def exe(rid):
    """build/kollektion/<rid>/kollektion[.exe], published there (as `make kollektion` does) when it is missing or
    older than its sources."""
    path = os.path.join(ROOT, "build", "kollektion", rid, "kollektion.exe" if rid == "win-x64" else "kollektion")
    if not os.path.isfile(path) or os.path.getmtime(path) < newest_source():
        # The tests were asked for (KOLLEKTION_TESTS=1): a missing SDK is a failure, not a skip.
        if sdk_major() < 10:
            raise RuntimeError("the kollektion tests need the .NET 10 SDK to build kollektion")
        subprocess.run(["dotnet", "publish", "src/kollektion", "-c", "Release", "-r", rid, "-nologo", "-v", "quiet",
                        "-o", os.path.dirname(path)], cwd=ROOT, check=True, timeout=600)
    return path


def fake_steam(tmp, os_path):
    """A Steam root whose libraryfolders.vdf names a second library holding the game, with BepInEx and our
    loader installed. os_path turns a host path into the path the program under test sees."""
    root, library = os.path.join(tmp, "Steam"), os.path.join(tmp, "Library2")
    game = os.path.join(library, "steamapps", "common", "over the hill")
    for d in (os.path.join(root, "steamapps"), os.path.join(game, "BepInEx", "core"),
              os.path.join(game, "BepInEx", "interop"), os.path.join(game, "BepInEx", "plugins")):
        os.makedirs(d)
    lib = os_path(library).replace("\\", "\\\\")
    with open(os.path.join(root, "steamapps", "libraryfolders.vdf"), "w") as f:
        f.write('"libraryfolders"\n{\n\t"0"\n\t{\n\t\t"path"\t\t"' + lib + '"\n\t}\n}\n')
    with open(os.path.join(library, "steamapps", f"appmanifest_{APP_ID}.acf"), "w") as f:
        f.write(f'"AppState"\n{{\n\t"appid"\t\t"{APP_ID}"\n\t"buildid"\t\t"{BUILD}"\n}}\n')
    for name in ("over the hill.x86_64", "over the hill.exe"):
        open(os.path.join(game, name), "w").close()
    with open(os.path.join(game, "BepInEx", "core", "BepInEx.Core.dll"), "wb") as f:
        f.write(b"MZ\0\0" + BEPINEX.encode() + b"\0")
    with open(os.path.join(game, "BepInEx", "interop", "assembly-hash.txt"), "w") as f:
        f.write(HASH + "\n")
    open(os.path.join(game, "BepInEx", "plugins", "DieKollektion.Loader.dll"), "w").close()
    return root, game


class Fixture:
    """A fake Steam install and how to ask the program under test about it; a subclass names the target and how
    to run it."""
    rid = None

    def run_exe(self, args, env):
        raise NotImplementedError

    def os_path(self, path):
        return path

    def setUp(self):
        self.exe = exe(self.rid)
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.root, self.game = fake_steam(self.tmp, self.os_path)
        self.env = {k: v for k, v in os.environ.items() if k not in ("GAME_DIR", "MY_GAMES")}
        self.env["KOLLEKTION_STEAM_ROOT"] = self.os_path(self.root)

    def status(self, env=None, **extra):
        r = self.run_exe(["status", "--json"], dict(env or self.env, **extra))
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def same_path(self, got, want, ignore_case=False):
        norm = lambda p: os.path.normcase(p.replace("\\", "/").rstrip("/"))
        got, want = norm(got), norm(self.os_path(want))
        self.assertEqual(got.lower() if ignore_case else got, want.lower() if ignore_case else want)


class Target(Fixture):
    """The checks every target runs."""

    def test_finds_the_game_through_a_second_library(self):
        s = self.status()
        self.assertEqual(s["os"], "windows" if self.rid == "win-x64" else "linux")
        self.same_path(s["gameDir"], self.game)
        self.assertEqual((s["steamBuild"], s["bepinex"], s["interopHash"], s["loader"]),
                         (BUILD, BEPINEX, HASH, "installed"))

    def test_game_dir_and_my_games_override(self):
        s = self.status(GAME_DIR=self.os_path(self.tmp), MY_GAMES=self.os_path(os.path.join(self.tmp, "mg")))
        self.same_path(s["gameDir"], self.tmp)
        self.assertEqual((s["bepinex"], s["interopHash"], s["loader"]), (None, None, "not installed"))
        self.same_path(s["saves"], os.path.join(self.tmp, "mg", "Saves"))

    def test_default_saves_and_player_log(self):
        # The two paths #45 found wrong in the loader and plugin on Windows.
        s = self.status({k: v for k, v in self.env.items() if k != "XDG_CONFIG_HOME"})
        if self.rid == "win-x64":
            self.assertTrue(s["saves"].endswith(r"\Documents\My Games\over the hill\Saves"), s["saves"])
            self.assertTrue(s["playerLog"].endswith(r"\AppData\LocalLow\Funselektor\over the hill\Player.log"),
                            s["playerLog"])
        else:
            self.assertEqual(s["saves"], os.path.expanduser("~/My Games/over the hill/Saves"))
            self.assertEqual(s["playerLog"],
                             os.path.expanduser("~/.config/unity3d/Funselektor/over the hill/Player.log"))

    @unittest.skipIf(WINDOWS, "a mode-000 file is a POSIX permission")
    def test_unreadable_files_are_reported_not_fatal(self):
        unreadable = [os.path.join(self.game, "BepInEx", "core", "BepInEx.Core.dll"),
                      os.path.join(self.game, "BepInEx", "interop", "assembly-hash.txt"),
                      os.path.join(self.game, "..", "..", f"appmanifest_{APP_ID}.acf")]
        for p in unreadable:
            os.chmod(p, 0)
            self.addCleanup(os.chmod, p, stat.S_IRUSR | stat.S_IWUSR)
        if os.access(unreadable[0], os.R_OK):
            self.skipTest("running as root: mode 000 doesn't stop reads")
        s = self.status()
        self.same_path(s["gameDir"], self.game)
        self.assertEqual((s["steamBuild"], s["bepinex"], s["interopHash"]), (None, "unknown", None))
        # An unreadable libraryfolders.vdf: the second library isn't found, and status still answers.
        vdf = os.path.join(self.root, "steamapps", "libraryfolders.vdf")
        os.chmod(vdf, 0)
        self.addCleanup(os.chmod, vdf, stat.S_IRUSR | stat.S_IWUSR)
        self.assertIsNone(self.status()["gameDir"])

    def test_no_steam(self):
        s = self.status(KOLLEKTION_STEAM_ROOT=self.os_path(os.path.join(self.tmp, "nothing")))
        self.assertIsNone(s["gameDir"])
        self.assertIsNone(s["loader"])

    def test_unknown_command(self):
        r = self.run_exe(["frobnicate"], self.env)
        self.assertEqual(r.returncode, 2)
        self.assertIn("Usage: kollektion", r.stderr)


class WindowsSteam:
    """Finding Steam itself on Windows, without KOLLEKTION_STEAM_ROOT: the default folder under Program Files
    (x86), and the SteamPath Steam writes to the registry, lower-cased with forward slashes."""

    def program_files(self):
        """(host folder standing in for Program Files (x86), the env that points the program at it)."""
        pf = os.path.join(self.tmp, "PF86")
        os.makedirs(pf, exist_ok=True)
        return pf, {"ProgramFiles(x86)": self.os_path(pf)}

    def windows_env(self, **extra):
        env = {k: v for k, v in self.env.items() if k != "KOLLEKTION_STEAM_ROOT"}
        env.update(extra)
        return env

    def test_default_steam_under_program_files(self):
        pf, env = self.program_files()
        steam = os.path.join(pf, "Steam")
        shutil.rmtree(steam, True)    # left by an interrupted run, it would hold a stale library
        shutil.move(self.root, steam)
        self.addCleanup(shutil.rmtree, steam, True)
        self.same_path(self.status(self.windows_env(**env))["gameDir"], self.game)

    def test_steam_path_from_the_registry(self):
        key = r"HKCU\Software\Valve\Steam"
        steam_path = self.os_path(self.root).replace("\\", "/").lower()
        self.reg(["add", key, "/v", "SteamPath", "/t", "REG_SZ", "/d", steam_path, "/f"])
        self.addCleanup(self.reg, ["delete", key, "/v", "SteamPath", "/f"])
        s = self.status(self.windows_env(**{"ProgramFiles(x86)": self.os_path(os.path.join(self.tmp, "none"))}))
        self.same_path(s["gameDir"], self.game, ignore_case=True)


class NativeRun:
    """This machine's own build: linux-x64 on Linux, win-x64 on Windows."""
    rid = HOST_RID

    def run_exe(self, args, env):
        return subprocess.run([self.exe] + args, env=env, capture_output=True, text=True, encoding="utf-8",
                              timeout=TIMEOUT)


class Native(NativeRun, Target, unittest.TestCase):
    pass


# The registry test writes HKCU, so natively it runs only on CI's throwaway Windows runner.
@unittest.skipUnless(WINDOWS and os.environ.get("GITHUB_ACTIONS") == "true",
                     "Windows' own Steam lookup runs natively on CI's Windows runner only")
class NativeWindowsSteam(WindowsSteam, NativeRun, Fixture, unittest.TestCase):
    def reg(self, args):
        subprocess.run(["reg"] + args, check=True, capture_output=True, timeout=TIMEOUT)


@unittest.skipIf(WINDOWS or not shutil.which("wine"), "the Wine run needs Linux with wine installed")
class UnderWine(Target, WindowsSteam, unittest.TestCase):
    """The win-x64 build under Wine, in a prefix of its own (build/wineprefix), never the user's ~/.wine."""
    rid = "win-x64"

    def setUp(self):
        self.prefix = os.path.join(ROOT, "build", "wineprefix")
        super().setUp()
        # No Mono or Gecko install prompt in a fresh prefix: the exe is self-contained and needs neither.
        self.env.update(WINEPREFIX=self.prefix, WINEDEBUG="-all", WINEDLLOVERRIDES="mscoree=;mshtml=")

    def program_files(self):
        # Wine sets ProgramFiles(x86) from the prefix, whatever the environment says: use the prefix's own folder.
        return os.path.join(self.prefix, "drive_c", "Program Files (x86)"), {}

    def os_path(self, path):
        # Wine maps the host's / to Z:.
        return "Z:" + os.path.abspath(path).replace("/", "\\")

    def run_exe(self, args, env):
        return subprocess.run(["wine", self.exe] + args, env=env, capture_output=True, text=True, encoding="utf-8",
                              timeout=TIMEOUT)

    def reg(self, args):
        subprocess.run(["wine", "reg"] + args, env=self.env, check=True, capture_output=True, timeout=TIMEOUT)


if __name__ == "__main__":
    unittest.main()
