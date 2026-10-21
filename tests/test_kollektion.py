"""`kollektion` on each target: the same checks run the linux-x64 build natively, the win-x64 build under Wine
(when wine is installed) and natively on Windows (the windows-latest CI job). Each finds the game through a fake
Steam install (libraryfolders.vdf naming a second library) and reads BepInEx, the interop hash and the Steam build
from the fake game folder, so the per-OS paths in Kollektion.Core are checked without a game."""
import json
import os
import platform
import shutil
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


def newest_source():
    return max(os.path.getmtime(os.path.join(d, f)) for d, _, files in os.walk(os.path.join(ROOT, "src"))
               for f in files if f.endswith((".cs", ".csproj")))


def exe(rid):
    """build/kollektion/<rid>/kollektion[.exe], published there (as `make kollektion` does) when it is missing or
    older than its sources."""
    path = os.path.join(ROOT, "build", "kollektion", rid, "kollektion.exe" if rid == "win-x64" else "kollektion")
    if not os.path.isfile(path) or os.path.getmtime(path) < newest_source():
        if not shutil.which("dotnet"):
            raise unittest.SkipTest("no .NET SDK to build kollektion")
        subprocess.run(["dotnet", "publish", "src/kollektion", "-c", "Release", "-r", rid, "-nologo", "-v", "quiet",
                        "-o", os.path.dirname(path)], cwd=ROOT, check=True)
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


class Target:
    """The checks; a subclass names the target and how to run it."""
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

    def status(self, **env):
        r = self.run_exe(["status", "--json"], dict(self.env, **env))
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def same_path(self, got, want):
        norm = lambda p: os.path.normcase(p.replace("\\", "/").rstrip("/"))
        self.assertEqual(norm(got), norm(self.os_path(want)))

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
        env = {k: v for k, v in self.env.items() if k != "XDG_CONFIG_HOME"}
        r = self.run_exe(["status", "--json"], env)
        s = json.loads(r.stdout)
        if self.rid == "win-x64":
            self.assertTrue(s["saves"].endswith(r"\Documents\My Games\over the hill\Saves"), s["saves"])
            self.assertTrue(s["playerLog"].endswith(r"\AppData\LocalLow\Funselektor\over the hill\Player.log"),
                            s["playerLog"])
        else:
            self.assertEqual(s["saves"], os.path.expanduser("~/My Games/over the hill/Saves"))
            self.assertEqual(s["playerLog"],
                             os.path.expanduser("~/.config/unity3d/Funselektor/over the hill/Player.log"))

    def test_no_steam(self):
        s = self.status(KOLLEKTION_STEAM_ROOT=self.os_path(os.path.join(self.tmp, "nothing")))
        self.assertIsNone(s["gameDir"])
        self.assertIsNone(s["loader"])

    def test_unknown_command(self):
        r = self.run_exe(["frobnicate"], self.env)
        self.assertEqual(r.returncode, 2)
        self.assertIn("Usage: kollektion", r.stderr)


class Native(Target, unittest.TestCase):
    """This machine's own build: linux-x64 on Linux, win-x64 on Windows."""
    rid = HOST_RID

    def run_exe(self, args, env):
        return subprocess.run([self.exe] + args, env=env, capture_output=True, text=True, encoding="utf-8")


@unittest.skipIf(WINDOWS or not shutil.which("wine"), "the Wine run needs Linux with wine installed")
class UnderWine(Target, unittest.TestCase):
    """The win-x64 build under Wine, in a prefix of its own (build/wineprefix), never the user's ~/.wine."""
    rid = "win-x64"

    def setUp(self):
        self.prefix = os.path.join(ROOT, "build", "wineprefix")
        super().setUp()
        self.env.update(WINEPREFIX=self.prefix, WINEDEBUG="-all")

    def os_path(self, path):
        # Wine maps the host's / to Z:.
        return "Z:" + os.path.abspath(path).replace("/", "\\")

    def run_exe(self, args, env):
        return subprocess.run(["wine", self.exe] + args, env=env, capture_output=True, text=True, encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
