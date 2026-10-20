"""Deploying with the loader, and game-update reporting (tools/werkstatt.py, tools/run_werkstatt.sh), over a fake
game folder: no game needed.

Run: python3 -m unittest discover -s tests (part of `make check` and `python3 tools/release.py ci`).
"""
import contextlib
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

TESTS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TESTS)
sys.path.insert(0, os.path.join(ROOT, "tools"))
import werkstatt as ws  # noqa: E402

# The Makefile exports these; a test that inherited them would deploy into, or force changes on, a real folder.
LEAKY = ("DEPLOY_DIR", "FORCE", "GAME_DIR", "MY_GAMES")


def files(assembly="a", metadata="m"):
    return {"files": {"gameAssembly": {"sha256": assembly}, "globalMetadata": {"sha256": metadata}}}


class Decisions(unittest.TestCase):
    def test_game_changed_follows_the_code_files(self):
        self.assertFalse(ws.game_changed(files(), files()))
        self.assertTrue(ws.game_changed(files(), files(assembly="b")))
        self.assertTrue(ws.game_changed(files(), files(metadata="n")))
        # A new Steam build that leaves the code files alone needs no rebuild.
        self.assertFalse(ws.game_changed({**files(), "steamBuild": "1"}, {**files(), "steamBuild": "2"}))


class Sources(unittest.TestCase):
    def test_the_sources_hash_matches_the_loaders(self):
        """The loader rebuilds only while LoaderCore.SourcesHash equals what deploy recorded (plugin_sources_hash)."""
        if ws.dotnet_sdk_major() < 6:
            self.skipTest("tools/loader-plan needs a .NET SDK")
        project = os.path.join(ROOT, "plugins", "VehicleMods")
        r = subprocess.run(["dotnet", "run", "--project", "tools/loader-plan", "-v", "quiet", "--", "sources", project, ROOT],
                           cwd=ROOT, capture_output=True, text=True, timeout=300)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), ws.plugin_sources_hash(project, ROOT))

    def test_the_hashes_agree_over_msbuild_inputs_above_the_project(self):
        """The real tree has no Directory.Build.* or global.json, so both hashes are compared over a tree that has them,
        with names whose ordinal and cultural orders differ."""
        if ws.dotnet_sdk_major() < 6:
            self.skipTest("tools/loader-plan needs a .NET SDK")
        tmp = tempfile.mkdtemp(prefix="werkstatt-sources-")
        self.addCleanup(shutil.rmtree, tmp)
        project = os.path.join(tmp, "plugins", "VehicleMods")
        for rel, text in (("Directory.Build.props", "<Project/>"), ("global.json", "{}"), ("plugins/Directory.Build.targets", "<Project/>"),
                          ("plugins/VehicleMods/Plugin.cs", "class P {}"), ("plugins/VehicleMods/b.cs", "class B {}"),
                          ("plugins/VehicleMods/_Z.cs", "class Z {}"), ("plugins/VehicleMods/VehicleMods.csproj", "<Project/>"),
                          ("plugins/VehicleMods/bin/x.cs", "built")):
            path = os.path.join(tmp, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            open(path, "w").write(text)

        def loader_hash():
            r = subprocess.run(["dotnet", "run", "--project", "tools/loader-plan", "-v", "quiet", "--", "sources", project, tmp],
                               cwd=ROOT, capture_output=True, text=True, timeout=300)
            self.assertEqual(r.returncode, 0, r.stderr)
            return r.stdout.strip()

        with_inputs = ws.plugin_sources_hash(project, tmp)
        self.assertEqual(loader_hash(), with_inputs)
        os.remove(os.path.join(tmp, "Directory.Build.props"))
        self.assertNotEqual(ws.plugin_sources_hash(project, tmp), with_inputs)
        self.assertEqual(loader_hash(), ws.plugin_sources_hash(project, tmp))

    def test_the_hash_follows_sources_only(self):
        tmp = tempfile.mkdtemp(prefix="werkstatt-sources-")
        self.addCleanup(shutil.rmtree, tmp)
        for rel, text in (("Plugin.cs", "class P {}"), ("VehicleMods.csproj", "<Project/>"), ("bin/x.cs", "built"), ("notes.md", "n")):
            os.makedirs(os.path.dirname(os.path.join(tmp, rel)) or tmp, exist_ok=True)
            open(os.path.join(tmp, rel), "w").write(text)
        before = ws.plugin_sources_hash(tmp)
        open(os.path.join(tmp, "notes.md"), "w").write("changed")
        open(os.path.join(tmp, "bin", "x.cs"), "w").write("rebuilt")
        self.assertEqual(ws.plugin_sources_hash(tmp), before)
        open(os.path.join(tmp, "HalfDone.cs"), "w").write("class H {")
        self.assertNotEqual(ws.plugin_sources_hash(tmp), before)
        # MSBuild reads Directory.Build.* and global.json from the project's parents too.
        project = os.path.join(tmp, "plugins", "VehicleMods")
        os.makedirs(project)
        open(os.path.join(project, "Plugin.cs"), "w").write("class P {}")
        alone = ws.plugin_sources_hash(project, tmp)
        open(os.path.join(tmp, "Directory.Build.props"), "w").write("<Project/>")
        self.assertNotEqual(ws.plugin_sources_hash(project, tmp), alone)


class FakeGame(unittest.TestCase):
    """A game folder with the files Werkstatt fingerprints, a deployed plugin and loader, and Steam's app manifest."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="werkstatt-test-")
        self.addCleanup(shutil.rmtree, self.tmp)
        self.game = os.path.join(self.tmp, "steamapps", "common", "over the hill")
        self.write("GameAssembly.so", "code v1")
        self.write("over the hill_Data/il2cpp_data/Metadata/global-metadata.dat", "metadata v1")
        self.write("BepInEx/interop/assembly-hash.txt", "hash-v1")
        self.write("BepInEx/interop/Assembly-CSharp.dll", "interop")
        self.manifest("100", "1760000000")
        self.dll = os.path.join(self.tmp, "VehicleMods.dll")
        self.vehicle = os.path.join(self.tmp, "glyptodon.json")
        self.loader = os.path.join(self.tmp, ws.LOADER_NAME)
        open(self.dll, "w").write("plugin built for v1")
        open(self.vehicle, "w").write("vehicle as gated")
        open(self.loader, "w").write("loader")
        self.folder = ws.default_deploy_dir(self.game)
        env = mock.patch.dict(os.environ, {"GAME_DIR": self.game})
        env.start()
        self.addCleanup(env.stop)
        for name in LEAKY[:2]:
            os.environ.pop(name, None)
        for p in (mock.patch.object(ws, "game_running", return_value=False),
                  mock.patch.object(ws, "expected_sources",
                                    side_effect=lambda: {"VehicleMods.dll": self.dll, "vehicles/glyptodon.json": self.vehicle}),
                  mock.patch.object(ws, "plugin_dll", side_effect=lambda game=None: self.dll),
                  mock.patch.object(ws, "loader_dll", side_effect=lambda: self.loader),
                  mock.patch.object(ws, "compile_plugin", return_value=0),
                  # No test may run the real gates: they run these tests again.
                  mock.patch.object(ws, "cmd_gates", side_effect=AssertionError("a test reached the real gates"))):
            p.start()
            self.addCleanup(p.stop)

    def write(self, rel, text):
        path = os.path.join(self.game, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(text)

    def manifest(self, build, updated):
        path = os.path.join(self.tmp, "steamapps", f"appmanifest_{ws.APP_ID}.acf")
        with open(path, "w") as f:
            f.write(f'"AppState"\n{{\n\t"appid"\t\t"{ws.APP_ID}"\n\t"LastUpdated"\t\t"{updated}"\n\t"buildid"\t\t"{build}"\n}}\n')

    def update_game(self):
        self.write("GameAssembly.so", "code v2")
        self.manifest("200", "1760100000")

    def quiet(self, fn, *args, **kw):
        with mock.patch("sys.stdout"):
            return fn(*args, **kw)

    def deploy(self):
        self.assertEqual(self.quiet(ws.cmd_deploy, []), 0)

    def plugins(self, *rel):
        return os.path.join(self.game, "BepInEx", "plugins", *rel)

    # -- deploy

    def test_deploy_puts_the_plugin_outside_plugins_and_the_loader_inside(self):
        self.deploy()
        self.assertEqual(self.folder, os.path.join(self.game, "BepInEx", "VehicleMods"))
        self.assertTrue(os.path.isfile(os.path.join(self.folder, "VehicleMods.dll")))
        self.assertEqual(os.listdir(self.plugins()), [ws.LOADER_NAME])
        rec = ws.deploy_record(self.folder)
        self.assertEqual(rec["game"]["interopHash"], "hash-v1")
        self.assertEqual(rec["werkstatt"], ws.ROOT)
        self.assertEqual(rec["pluginSources"]["sha256"], ws.plugin_sources_hash())
        self.assertEqual(rec["loader"], {"path": "plugins/" + ws.LOADER_NAME, "sha256": ws.sha256(self.loader)})
        self.assertEqual(ws.deploy_state(self.folder), "current")
        self.assertEqual(ws.launch_script_target(self.game), ws.ROOT)

    def test_a_missing_or_changed_loader_shows_in_the_deploy_state(self):
        self.deploy()
        os.remove(self.plugins(ws.LOADER_NAME))
        self.assertEqual(ws.deploy_state(self.folder), "stale")
        self.deploy()
        open(self.plugins(ws.LOADER_NAME), "w").write("edited")
        self.assertEqual(ws.deploy_state(self.folder), "modified")
        open(self.loader, "w").write("a newer loader")
        self.assertIn(ws.deploy_state(self.folder), ("modified", "stale"))

    def test_an_install_from_before_the_loader_moves_out_of_plugins(self):
        legacy = ws.legacy_deploy_dir(self.game)
        os.makedirs(legacy)
        open(os.path.join(legacy, "VehicleMods.dll"), "w").write("old plugin")
        ws.write_json(os.path.join(legacy, "deployed.json"), {"files": [
            {"path": "VehicleMods.dll", "sha256": ws.sha256(os.path.join(legacy, "VehicleMods.dll"))}]})
        self.deploy()
        self.assertFalse(os.path.exists(legacy))
        self.assertEqual(os.listdir(self.plugins()), [ws.LOADER_NAME])
        self.assertEqual(open(os.path.join(self.folder, "VehicleMods.dll")).read(), "plugin built for v1")

    def deploy_with_placements(self):
        """Deploys a placements.json, then deletes its source; returns the sources a deploy now expects."""
        placements = os.path.join(self.tmp, "placements.json")
        open(placements, "w").write("{}")
        sources = {"VehicleMods.dll": self.dll, "vehicles/glyptodon.json": self.vehicle}
        with mock.patch.object(ws, "expected_sources",
                               side_effect=lambda: dict(sources, **{"vehicles/glyptodon/placements.json": placements})):
            self.assertEqual(self.quiet(ws.cmd_deploy, []), 0)
        os.remove(placements)
        return sources

    def test_a_deleted_placements_file_leaves_the_game_with_make_deploy(self):
        self.deploy_with_placements()
        self.assertEqual(self.quiet(ws.cmd_deploy, []), 0)
        self.assertEqual(sorted(ws.listing(self.folder)), ["VehicleMods.dll", "vehicles/glyptodon.json"])

    def test_copy_deploy_removes_a_retired_file_unless_it_changed(self):
        self.deploy_with_placements()
        deployed = os.path.join(self.folder, "vehicles", "glyptodon", "placements.json")
        self.assertEqual(self.quiet(ws.cmd_copy_deploy, []), 0)
        self.assertFalse(os.path.exists(deployed))
        self.assertFalse(os.path.exists(os.path.dirname(deployed)))
        self.deploy_with_placements()
        open(deployed, "w").write('{"edited": "by hand"}')
        self.assertEqual(self.quiet(ws.cmd_copy_deploy, []), 0)
        self.assertTrue(os.path.isfile(deployed))

    def test_a_folder_left_aside_by_the_old_update_handling_is_retired(self):
        aside = ws.aside_dir(self.folder)
        os.makedirs(aside)
        open(os.path.join(aside, "VehicleMods.dll"), "w").write("old plugin")
        ws.write_json(os.path.join(aside, "deployed.json"), {"files": [
            {"path": "VehicleMods.dll", "sha256": ws.sha256(os.path.join(aside, "VehicleMods.dll"))}]})
        self.deploy()
        self.assertFalse(os.path.exists(aside))

    def test_deploy_after_a_game_update_is_not_refused(self):
        """The loader rebuilds a plugin built for the old interop at the next start, so deploy needn't wait."""
        self.deploy()
        self.update_game()
        self.deploy()
        self.assertEqual(ws.deploy_state(self.folder), "current")

    def test_a_failed_compile_leaves_the_install_as_it_was(self):
        self.deploy()
        before = sorted(ws.listing(self.folder))
        with mock.patch.object(ws, "compile_plugin", return_value=1):
            self.assertEqual(self.quiet(ws.cmd_deploy, []), 1)
        self.assertEqual(sorted(ws.listing(self.folder)), before)
        self.assertEqual(ws.deploy_state(self.folder), "current")

    def test_undeploy_removes_the_loader_too(self):
        self.deploy()
        self.assertEqual(self.quiet(ws.cmd_undeploy, []), 0)
        self.assertFalse(os.path.exists(self.plugins(ws.LOADER_NAME)))
        self.assertFalse(os.path.exists(self.folder))

    def test_undeploy_keeps_a_loader_changed_by_hand(self):
        self.deploy()
        open(self.plugins(ws.LOADER_NAME), "w").write("edited")
        self.assertEqual(self.quiet(ws.cmd_undeploy, []), 0)
        self.assertTrue(os.path.exists(self.plugins(ws.LOADER_NAME)))

    # -- reporting

    def test_update_report_states(self):
        self.deploy()
        self.assertEqual(ws.update_report(self.game, self.folder)[0], "current")
        self.update_game()
        state, text = ws.update_report(self.game, self.folder)
        self.assertEqual(state, "pending")
        self.assertIn("the loader rebuilds the plugin at the next start", text)
        # What the loader writes once it has rebuilt the plugin for the regenerated interop.
        self.write("BepInEx/interop/assembly-hash.txt", "hash-v2")
        rec = ws.deploy_record(self.folder)
        rec["game"]["interopHash"] = "hash-v2"
        rec["afterUpdate"] = {"by": "loader", "how": "compiled", "steamBuild": "200", "rebuiltAt": "now"}
        ws.write_json(os.path.join(self.folder, "deployed.json"), rec)
        state, text = ws.update_report(self.game, self.folder)
        self.assertEqual(state, "rebuilt")
        self.assertIn("Steam build 200", text)
        os.remove(self.plugins(ws.LOADER_NAME))
        rec.pop("afterUpdate")
        ws.write_json(os.path.join(self.folder, "deployed.json"), rec)
        self.assertEqual(ws.update_report(self.game, self.folder)[0], "needed")

    def test_make_update_deploys_with_the_gates(self):
        self.deploy()
        self.update_game()
        with mock.patch.object(ws, "cmd_gates", return_value=0) as gates:
            self.assertEqual(self.quiet(ws.cmd_update, []), 0)
        gates.assert_called_once()

    # -- launches

    def test_with_the_loader_a_launch_changes_nothing(self):
        self.deploy()
        self.update_game()
        self.assertEqual(self.quiet(ws.cmd_launch_before, []), 0)
        self.assertTrue(os.path.isfile(os.path.join(self.folder, "VehicleMods.dll")))
        self.assertFalse(os.path.exists(ws.aside_dir(self.folder)))
        self.assertEqual(self.quiet(ws.cmd_launch_after, []), 0)

    def test_without_the_loader_a_game_update_moves_the_old_plugin_aside(self):
        legacy = ws.legacy_deploy_dir(self.game)
        os.makedirs(legacy)
        open(os.path.join(legacy, "VehicleMods.dll"), "w").write("old plugin")
        ws.write_json(os.path.join(legacy, "deployed.json"), {"game": ws.game_record(self.game), "files": []})
        self.assertEqual(self.quiet(ws.cmd_launch_before, []), 0)
        self.assertTrue(os.path.isdir(legacy))                                     # unchanged game: stays
        self.update_game()
        self.assertEqual(self.quiet(ws.cmd_launch_before, []), 0)
        self.assertFalse(os.path.exists(legacy))
        self.assertTrue(os.path.isfile(os.path.join(ws.aside_dir(legacy), "VehicleMods.dll")))
        # The next deploy installs the loader and retires the aside folder.
        self.deploy()
        self.assertFalse(os.path.exists(ws.aside_dir(self.folder)))
        self.assertTrue(os.path.isfile(self.plugins(ws.LOADER_NAME)))

    def test_sigterm_leaves_no_temp_file(self):
        self.deploy()
        code = ("import os, signal, sys, time; sys.path.insert(0, sys.argv[1]); import werkstatt as ws\n"
                "signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))\n"
                "real = os.replace\n"
                "def slow(a, b): os.kill(os.getpid(), signal.SIGTERM); time.sleep(5); real(a, b)\n"
                "os.replace = slow\n"
                "ws.write_json(os.path.join(sys.argv[2], 'deployed.json'), {})\n")
        r = subprocess.run([sys.executable, "-c", code, os.path.join(ROOT, "tools"), self.folder], capture_output=True)
        self.assertEqual(r.returncode, 143)
        self.assertEqual([n for n in os.listdir(self.folder) if n.startswith(".deployed.json.")], [])

    def test_one_step_at_a_time(self):
        with ws.werkstatt_lock(self.game) as held:
            self.assertTrue(held)
            self.assertEqual(self.quiet(ws.cmd_deploy, []), 1)


class GatesInsideTests(unittest.TestCase):
    """The gates run these tests; a test that reaches the real gates must get a refusal, never a nested run."""

    def test_gates_refuse_inside_their_own_tests(self):
        with mock.patch.dict(os.environ, {ws.IN_TESTS: "1"}), \
             mock.patch.object(ws, "vehicles", side_effect=AssertionError("the gates ran")):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(ws.cmd_gates([]), 1)


class Isolation(unittest.TestCase):
    def test_the_makefiles_deploy_dir_is_left_alone(self):
        """The Makefile exports DEPLOY_DIR and FORCE; the tests above must not deploy into that folder."""
        sentinel = tempfile.mkdtemp(prefix="werkstatt-sentinel-")
        self.addCleanup(shutil.rmtree, sentinel)
        with open(os.path.join(sentinel, "user-file.txt"), "w") as f:
            f.write("keep me")
        env = {**os.environ, "DEPLOY_DIR": sentinel, "FORCE": "1"}
        r = subprocess.run([sys.executable, "-W", "ignore", "-m", "unittest", "test_launch.FakeGame"],
                           cwd=TESTS, env=env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr[-2000:])
        self.assertEqual(os.listdir(sentinel), ["user-file.txt"])
        with open(os.path.join(sentinel, "user-file.txt")) as f:
            self.assertEqual(f.read(), "keep me")


class Log(unittest.TestCase):
    def test_the_launch_log_keeps_its_last_256_kb(self):
        tmp = tempfile.mkdtemp(prefix="werkstatt-log-")
        self.addCleanup(shutil.rmtree, tmp)
        log = os.path.join(tmp, "werkstatt-launch.log")
        with open(log, "w") as f:
            f.write("".join(f"old line {i:06d}\n" for i in range(40000)))       # about 640 KB
        code = "import sys; sys.path.insert(0, sys.argv[1]); import werkstatt; werkstatt.log_to(sys.argv[2]); print('new line')"
        subprocess.run([sys.executable, "-c", code, os.path.join(ROOT, "tools"), log], check=True)
        with open(log) as f:
            text = f.read()
        self.assertLessEqual(len(text), ws.LOG_CAP + 100)
        self.assertTrue(text.startswith("old line "))                            # cut at a line boundary
        self.assertTrue(text.endswith("old line 039999\nnew line\n"))


class LaunchScript(unittest.TestCase):
    """tools/run_werkstatt.sh with a stub run_bepinex.sh and a stub Werkstatt helper."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="werkstatt-sh-")
        self.addCleanup(shutil.rmtree, self.tmp)
        self.game = os.path.join(self.tmp, "over the hill")
        self.werkstatt = os.path.join(self.tmp, "werk statt's")
        os.makedirs(os.path.join(self.game, "BepInEx", "plugins", "VehicleMods"))
        os.makedirs(os.path.join(self.werkstatt, "tools"))
        with open(os.path.join(self.game, "run_bepinex.sh"), "w") as f:
            f.write('#!/bin/sh\nfor a in "$@"; do printf "[%s]" "$a"; done > args.txt\nexit 7\n')
        os.chmod(os.path.join(self.game, "run_bepinex.sh"), 0o755)
        with open(os.path.join(self.werkstatt, "tools", "werkstatt.py"), "w") as f:
            f.write("import os, sys\n"
                    "game = os.environ['GAME_DIR']\n"
                    "open(os.path.join(game, 'calls.txt'), 'a').write(sys.argv[1] + '\\n')\n"
                    "sys.exit(int(open(os.path.join(game, 'before-exit.txt')).read().strip()))\n")
        with open(os.path.join(ROOT, "tools", ws.LAUNCH_SCRIPT)) as f:
            text = f.read()
        self.script = os.path.join(self.game, ws.LAUNCH_SCRIPT)
        with open(self.script, "w") as f:
            f.write(text.replace('WERKSTATT_DIR=""', f"WERKSTATT_DIR={ws.shell_quote(self.werkstatt)}", 1))
        os.chmod(self.script, 0o755)

    def launch(self, before_exit=0):
        with open(os.path.join(self.game, "before-exit.txt"), "w") as f:
            f.write(str(before_exit))
        env = {k: v for k, v in os.environ.items() if k not in LEAKY}
        r = subprocess.run(["./" + ws.LAUNCH_SCRIPT, "/x/reaper", "SteamLaunch", "AppId=1", "--", "a game/with spaces"],
                           cwd=self.game, env=env, capture_output=True, text=True, timeout=60)
        with open(os.path.join(self.game, "args.txt")) as f:
            self.assertEqual(f.read(), "[/x/reaper][SteamLaunch][AppId=1][--][a game/with spaces]")
        return r.returncode

    def calls(self):
        path = os.path.join(self.game, "calls.txt")
        return open(path).read().split() if os.path.exists(path) else []

    def test_with_the_loader_the_script_only_passes_through(self):
        open(os.path.join(self.game, "BepInEx", "plugins", ws.LOADER_NAME), "w").write("loader")
        self.assertEqual(self.launch(), 7)                      # run_bepinex.sh's own exit code
        self.assertEqual(self.calls(), [])

    def test_an_install_without_the_loader_is_checked_first(self):
        self.assertEqual(self.launch(), 7)
        self.assertEqual(self.calls(), ["launch-before"])

    def test_a_failing_helper_starts_the_game_normally(self):
        self.assertEqual(self.launch(1), 7)
        self.assertEqual(self.calls(), ["launch-before"])

    def test_no_werkstatt_folder_falls_through(self):
        shutil.rmtree(self.werkstatt)
        self.assertEqual(self.launch(), 7)
        self.assertEqual(self.calls(), [])


if __name__ == "__main__":
    unittest.main()
