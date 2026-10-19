"""Game-update handling (tools/werkstatt.py, tools/run_werkstatt.sh) over a fake game folder: no game needed.

Run: python3 -m unittest discover -s tests (part of `make check` and `python3 tools/release.py ci`).
"""
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
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

    def test_launch_decision(self):
        self.assertEqual(ws.launch_decision(False, None, files(), False), "plain")
        self.assertEqual(ws.launch_decision(True, files(), files(), False), "plain")
        self.assertEqual(ws.launch_decision(True, files(), files(assembly="b"), False), "move-aside")
        self.assertEqual(ws.launch_decision(False, None, files(), True), "pending")
        self.assertEqual(ws.launch_decision(True, files(), files(), True), "pending")
        # A deploy that predates the record: BepInEx's last start decides.
        self.assertEqual(ws.launch_decision(True, None, files(), False, prepared=True), "plain")
        self.assertEqual(ws.launch_decision(True, None, files(), False, prepared=False), "move-aside")

    def test_rebuild_ready(self):
        note = {"interopHash": "old", "movedAt": 100.0}
        self.assertTrue(ws.rebuild_ready(note, "new", None, ""))
        self.assertFalse(ws.rebuild_ready(note, "old", None, ""))
        self.assertFalse(ws.rebuild_ready(note, "old", 90.0, "Chainloader initialized"))     # the log predates the move
        self.assertFalse(ws.rebuild_ready(note, "old", 110.0, "Preloader started"))          # stopped before interop
        self.assertTrue(ws.rebuild_ready(note, "old", 110.0, "[Message:   BepInEx] Chainloader initialized"))
        self.assertFalse(ws.rebuild_ready(note, None, None, ""))
        # Without a known interop hash, any hash on disk proves nothing.
        self.assertFalse(ws.rebuild_ready({"movedAt": 100.0}, "new", None, ""))


class FakeGame(unittest.TestCase):
    """A game folder with the files Werkstatt fingerprints, a deployed plugin, and Steam's app manifest."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="werkstatt-test-")
        self.addCleanup(shutil.rmtree, self.tmp)
        self.game = os.path.join(self.tmp, "steamapps", "common", "over the hill")
        self.write("GameAssembly.so", "code v1")
        self.write("over the hill_Data/il2cpp_data/Metadata/global-metadata.dat", "metadata v1")
        self.write("BepInEx/interop/assembly-hash.txt", "hash-v1")
        self.write("BepInEx/interop/Assembly-CSharp.dll", "interop")
        # Installed a while ago; every later date (BepInEx's start, an update) is set relative to that.
        past = time.time() - 1000
        for path in ws.game_file_paths(self.game).values():
            os.utime(path, (past, past))
        self.bepinex_started(after=True)
        self.manifest("100", "1760000000")
        self.dll = os.path.join(self.tmp, "VehicleMods.dll")
        self.vehicle = os.path.join(self.tmp, "glyptodon.json")
        open(self.dll, "w").write("plugin built for v1")
        open(self.vehicle, "w").write("vehicle as gated")
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
                  mock.patch.object(ws, "compile_plugin", return_value=0),
                  # The real checkout's state (a dirty plugins/VehicleMods) must not steer these tests, and no test
                  # may run the real gates: they run these tests again.
                  mock.patch.object(ws, "rebuild_refusal", return_value=None),
                  mock.patch.object(ws, "cmd_gates", side_effect=AssertionError("a test reached the real gates"))):
            p.start()
            self.addCleanup(p.stop)
        self.assertEqual(self.quiet(ws.cmd_deploy, []), 0)

    def write(self, rel, text, append=False):
        path = os.path.join(self.game, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a" if append else "w") as f:
            f.write(text)

    def bepinex_started(self, after=True, chainloader=True):
        """BepInEx's log of a start, dated after (or before) the game's code files last changed."""
        self.write("BepInEx/LogOutput.log", "[Message:   BepInEx] Chainloader initialized\n" if chainloader else "Preloader\n")
        newest = max(os.path.getmtime(p) for p in ws.game_file_paths(self.game).values())
        when = newest + 10 if after else newest - 10
        os.utime(os.path.join(self.game, "BepInEx", "LogOutput.log"), (when, when))

    def manifest(self, build, updated):
        path = os.path.join(self.tmp, "steamapps", f"appmanifest_{ws.APP_ID}.acf")
        with open(path, "w") as f:
            f.write(f'"AppState"\n{{\n\t"appid"\t\t"{ws.APP_ID}"\n\t"LastUpdated"\t\t"{updated}"\n\t"buildid"\t\t"{build}"\n}}\n')

    def update_game(self):
        self.update_game_files_only()
        self.manifest("200", "1760100000")

    def bepinex_regenerated(self):
        self.write("BepInEx/interop/assembly-hash.txt", "hash-v2")

    def quiet(self, fn, *args, **kw):
        with mock.patch("sys.stdout"):
            return fn(*args, **kw)

    def read(self, *rel):
        with open(os.path.join(*rel)) as f:
            return f.read()

    # -- deploy and launch

    def test_deploy_records_the_game_and_installs_the_launch_script(self):
        rec = ws.deploy_record(self.folder)
        self.assertEqual(rec["game"]["steamBuild"], "100")
        self.assertEqual(rec["game"]["interopHash"], "hash-v1")
        self.assertEqual(rec["game"]["files"]["gameAssembly"]["sha256"], ws.sha256(os.path.join(self.game, "GameAssembly.so")))
        self.assertEqual(ws.launch_script_target(self.game), ws.ROOT)
        self.assertEqual(ws.update_report(self.game, self.folder)[0], "current")

    def test_launch_script_quotes_the_werkstatt_folder(self):
        odd = os.path.join(self.tmp, "it's a \"folder\" $HOME `x`")
        with mock.patch.object(ws, "ROOT", odd):
            ws.install_launch_script(self.game)
        self.assertEqual(ws.launch_script_target(self.game), odd)
        script = os.path.join(self.game, ws.LAUNCH_SCRIPT)
        out = subprocess.run(["sh", "-c", 'eval "$(grep ^WERKSTATT_DIR= "$1")"; printf %s "$WERKSTATT_DIR"', "sh", script],
                             capture_output=True, text=True).stdout
        self.assertEqual(out, odd)

    def test_unchanged_files_are_not_hashed_again_and_touched_ones_are_saved(self):
        known = ws.deploy_record(self.folder)["game"]
        known["files"]["gameAssembly"]["sha256"] = "remembered"
        self.assertEqual(ws.game_record(self.game, known)["files"]["gameAssembly"]["sha256"], "remembered")
        # Same content, new time (a Steam verify): the launch saves the new time, so the next one skips hashing.
        path = os.path.join(self.game, "GameAssembly.so")
        os.utime(path, (os.path.getmtime(path) + 5, os.path.getmtime(path) + 5))
        self.assertEqual(self.quiet(ws.cmd_launch_before, []), 0)
        self.assertEqual(ws.deploy_record(self.folder)["game"]["files"]["gameAssembly"]["mtime"], os.stat(path).st_mtime_ns)

    def test_unchanged_game_launches_normally(self):
        self.assertEqual(self.quiet(ws.cmd_launch_before, []), 0)
        self.assertTrue(os.path.isdir(self.folder))

    def test_update_moves_aside_then_rebuilds_the_dll_only(self):
        self.update_game()
        self.assertEqual(ws.update_report(self.game, self.folder)[0], "needed")
        self.assertEqual(self.quiet(ws.cmd_launch_before, []), 3)
        aside = ws.aside_dir(self.folder)
        self.assertFalse(os.path.exists(self.folder))
        self.assertEqual(aside, os.path.join(os.path.realpath(self.game), "BepInEx", "VehicleMods.aside"))
        self.assertEqual(json.loads(self.read(aside, ws.ASIDE_NOTE))["interopHash"], "hash-v1")
        # The game exited before BepInEx regenerated its interop: the plugin waits.
        self.assertEqual(self.quiet(ws.rebuild_from_aside, self.game, self.folder, automatic=True), "waiting")
        self.assertEqual(self.quiet(ws.cmd_launch_before, []), 3)                     # still pending next launch
        # BepInEx regenerated it: rebuild the DLL, keep the gated vehicle files, remember the update.
        self.bepinex_regenerated()
        open(self.dll, "w").write("plugin built for v2")
        open(self.vehicle, "w").write("vehicle edited in the working tree, not gated")
        self.assertEqual(self.quiet(ws.cmd_launch_after, []), 0)
        self.assertFalse(os.path.exists(aside))
        self.assertFalse(os.path.exists(aside[:-len(".aside")] + ".staging"))
        self.assertEqual(self.read(self.folder, "VehicleMods.dll"), "plugin built for v2")
        self.assertEqual(self.read(self.folder, "vehicles", "glyptodon.json"), "vehicle as gated")
        rec = ws.deploy_record(self.folder)
        self.assertEqual(rec["game"]["steamBuild"], "200")
        self.assertEqual(rec["game"]["interopHash"], "hash-v2")
        self.assertEqual(rec["afterUpdate"]["fromBuild"], "100")
        self.assertEqual({f["path"]: f["sha256"] for f in rec["files"]}["VehicleMods.dll"], ws.sha256(self.dll))
        state, text = ws.update_report(self.game, self.folder)
        self.assertEqual(state, "rebuilt")
        self.assertIn("rebuilt", text)
        self.assertEqual(self.quiet(ws.cmd_launch_before, []), 0)

    def test_rebuild_without_a_steam_manifest(self):
        os.remove(os.path.join(self.tmp, "steamapps", f"appmanifest_{ws.APP_ID}.acf"))
        self.update_game_files_only()
        self.assertEqual(self.quiet(ws.cmd_launch_before, []), 3)
        self.bepinex_regenerated()
        self.assertEqual(self.quiet(ws.cmd_launch_after, []), 0)
        self.assertEqual(ws.update_report(self.game, self.folder)[0], "rebuilt")

    def update_game_files_only(self):
        """Steam replaces GameAssembly.so: new content, dated after BepInEx's last start."""
        self.write("GameAssembly.so", "+", append=True)
        log = os.path.join(self.game, "BepInEx", "LogOutput.log")
        later = (os.path.getmtime(log) if os.path.exists(log) else time.time() - 500) + 20
        os.utime(os.path.join(self.game, "GameAssembly.so"), (later, later))

    def test_failed_build_leaves_the_plugin_aside(self):
        self.update_game()
        self.quiet(ws.cmd_launch_before, [])
        self.bepinex_regenerated()
        with mock.patch.object(ws, "compile_plugin", return_value=1):
            self.assertEqual(self.quiet(ws.cmd_launch_after, []), 1)
        self.assertFalse(os.path.exists(self.folder))
        self.assertTrue(os.path.isdir(ws.aside_dir(self.folder)))

    def test_bepinex_log_counts_when_the_hash_stays(self):
        self.update_game()
        self.quiet(ws.cmd_launch_before, [])
        note = json.loads(self.read(ws.aside_dir(self.folder), ws.ASIDE_NOTE))
        self.write("BepInEx/LogOutput.log", "[Message:   BepInEx] Chainloader initialized\n")
        os.utime(os.path.join(self.game, "BepInEx", "LogOutput.log"), (note["movedAt"] + 1, note["movedAt"] + 1))
        self.assertEqual(self.quiet(ws.rebuild_from_aside, self.game, self.folder, automatic=True), "rebuilt")

    def test_a_truncated_note_does_not_count_as_prepared(self):
        self.update_game()
        self.quiet(ws.cmd_launch_before, [])
        aside = ws.aside_dir(self.folder)
        with open(os.path.join(aside, ws.ASIDE_NOTE), "w") as f:
            f.write('{"movedAt": ')
        self.assertFalse(ws.aside_prepared(self.game, aside))
        self.assertEqual(ws.aside_note(aside)["interopHash"], "hash-v1")                 # recovered from deployed.json

    def test_hand_changes_survive_the_rebuild(self):
        self.write("BepInEx/plugins/VehicleMods/notes.txt", "mine")
        self.update_game()
        self.quiet(ws.cmd_launch_before, [])
        self.bepinex_regenerated()
        self.assertEqual(self.quiet(ws.cmd_launch_after, []), 0)
        self.assertEqual(self.read(self.folder, "notes.txt"), "mine")

    def test_automatic_rebuild_refuses_another_checkout(self):
        self.update_game()
        self.quiet(ws.cmd_launch_before, [])
        self.bepinex_regenerated()
        with mock.patch.object(ws, "rebuild_refusal", return_value="the plugin was deployed from fffffff"):
            self.assertEqual(self.quiet(ws.cmd_launch_after, []), 1)
            self.assertTrue(os.path.isdir(ws.aside_dir(self.folder)))
            # `make update` deploys that checkout in full instead, after the gates.
            with mock.patch.object(ws, "cmd_gates", return_value=0) as gates:
                self.assertEqual(self.quiet(ws.cmd_update, []), 0)
                gates.assert_called_once()
        self.assertFalse(os.path.exists(ws.aside_dir(self.folder)))
        self.assertEqual(ws.update_report(self.game, self.folder)[0], "current")

    # -- interrupted installs

    def test_cut_off_after_the_rename_finishes_on_the_next_launch(self):
        self.update_game()
        self.quiet(ws.cmd_launch_before, [])
        aside = ws.aside_dir(self.folder)
        kept = shutil.copytree(aside, os.path.join(self.tmp, "aside-copy"))
        self.bepinex_regenerated()
        self.quiet(ws.cmd_launch_after, [])
        os.rename(kept, aside)                                                         # killed before retire_aside
        self.assertEqual(ws.update_report(self.game, self.folder)[0], "rebuilt")
        self.assertEqual(self.quiet(ws.cmd_launch_before, []), 0)
        self.assertFalse(os.path.exists(aside))
        self.assertTrue(os.path.isdir(self.folder))

    def test_a_stale_plugin_next_to_the_aside_one_leaves_plugins(self):
        self.update_game()
        self.quiet(ws.cmd_launch_before, [])
        shutil.copytree(ws.aside_dir(self.folder), self.folder,
                        ignore=lambda d, names: [ws.ASIDE_NOTE] if ws.ASIDE_NOTE in names else [])
        self.assertEqual(self.quiet(ws.cmd_launch_before, []), 3)
        self.assertFalse(os.path.exists(self.folder))
        self.assertTrue(os.path.isdir(ws.aside_dir(self.folder)))
        replaced = [d for d in os.listdir(os.path.join(self.game, "BepInEx")) if d.startswith("VehicleMods.replaced-")]
        self.assertEqual(len(replaced), 1)

    # -- by hand

    def test_make_update_by_hand(self):
        self.assertEqual(self.quiet(ws.cmd_update, []), 0)                           # nothing to do
        self.assertTrue(os.path.isdir(self.folder))
        self.update_game()
        self.assertEqual(self.quiet(ws.cmd_update, []), 0)                           # moved aside, waiting
        self.assertTrue(os.path.isdir(ws.aside_dir(self.folder)))
        self.bepinex_regenerated()
        self.assertEqual(self.quiet(ws.cmd_update, []), 0)
        self.assertEqual(ws.update_report(self.game, self.folder)[0], "rebuilt")

    def test_deploy_refuses_until_bepinex_has_prepared_the_updated_game(self):
        self.update_game()
        self.assertEqual(self.quiet(ws.cmd_deploy, []), 1)
        self.assertTrue(os.path.isdir(ws.aside_dir(self.folder)))
        self.bepinex_regenerated()
        self.assertEqual(self.quiet(ws.cmd_deploy, []), 0)
        self.assertFalse(os.path.exists(ws.aside_dir(self.folder)))

    def test_deploys_before_the_record_are_judged_by_bepinex_log(self):
        rec = ws.deploy_record(self.folder)
        del rec["game"]
        ws.write_json(os.path.join(self.folder, "deployed.json"), rec)
        self.assertEqual(self.quiet(ws.cmd_launch_before, []), 0)                    # BepInEx ran since: fine
        self.update_game()                                                            # code files newer than the log
        self.assertEqual(self.quiet(ws.cmd_deploy, []), 1)
        self.assertTrue(os.path.isdir(ws.aside_dir(self.folder)))
        self.bepinex_started(after=True, chainloader=False)                           # started, stopped before interop
        self.assertEqual(self.quiet(ws.cmd_deploy, []), 1)
        self.bepinex_started(after=True)
        self.assertEqual(self.quiet(ws.cmd_deploy, []), 0)

    def test_a_launch_during_a_rebuild_does_not_wait_for_it(self):
        self.update_game()
        self.quiet(ws.cmd_launch_before, [])                                          # plugin aside
        waits = []
        real_lock = ws.werkstatt_lock
        with real_lock(self.game) as held, mock.patch.object(
                ws, "werkstatt_lock", side_effect=lambda game, wait=0.0: waits.append(wait) or real_lock(game, wait)):
            self.assertTrue(held)                                                     # the rebuild holds the lock
            started = time.monotonic()
            self.assertEqual(self.quiet(ws.cmd_launch_before, []), 3)                 # stock now, retry after
            self.assertLess(time.monotonic() - started, 1)
        self.assertEqual(waits, [0])
        self.assertFalse(os.path.exists(self.folder))

    def test_a_launch_waits_briefly_when_the_plugin_is_in_place(self):
        waits = []
        real_lock = ws.werkstatt_lock
        with mock.patch.object(ws, "werkstatt_lock", side_effect=lambda game, wait=0.0: waits.append(wait) or real_lock(game, wait)):
            self.assertEqual(self.quiet(ws.cmd_launch_before, []), 0)
        self.assertEqual(waits, [5])

    def test_a_symlinked_plugins_folder_keeps_the_aside_folder_beside_its_target(self):
        """plugins/ on another disk: the aside folder goes next to the real one, so moving there is a rename."""
        elsewhere = os.path.join(self.tmp, "other disk", "BepInEx-plugins")
        plugins = os.path.join(self.game, "BepInEx", "plugins")
        os.makedirs(os.path.dirname(elsewhere))
        os.rename(plugins, elsewhere)
        os.symlink(elsewhere, plugins)
        self.assertEqual(ws.aside_dir(self.folder), os.path.join(os.path.realpath(os.path.dirname(elsewhere)), "VehicleMods.aside"))
        self.update_game()
        self.assertEqual(self.quiet(ws.cmd_launch_before, []), 3)
        self.assertFalse(os.path.exists(self.folder))
        self.assertTrue(os.path.isdir(ws.aside_dir(self.folder)))
        self.bepinex_regenerated()
        self.assertEqual(self.quiet(ws.cmd_launch_after, []), 0)
        self.assertTrue(os.path.isfile(os.path.join(elsewhere, "VehicleMods", "VehicleMods.dll")))
        self.assertFalse(os.path.exists(ws.aside_dir(self.folder)))

    def test_a_move_across_filesystems_is_refused(self):
        self.update_game()
        exdev = OSError(ws.errno.EXDEV, "Invalid cross-device link")
        with mock.patch.object(ws.os, "rename", side_effect=exdev):
            self.assertEqual(self.quiet(ws.cmd_launch_before, []), 0)
        self.assertTrue(os.path.isdir(self.folder))

    def test_deploy_needs_no_bepinex_log_when_the_plugin_fits(self):
        os.remove(os.path.join(self.game, "BepInEx", "LogOutput.log"))               # disk logging switched off
        self.assertEqual(self.quiet(ws.cmd_deploy, []), 0)
        self.update_game()
        self.assertEqual(self.quiet(ws.cmd_deploy, []), 1)                            # after an update it still waits

    def test_sigterm_leaves_no_temp_file(self):
        """`timeout` stops launch-before with SIGTERM; the entry point exits through write_atomic's cleanup."""
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
            self.assertEqual(self.quiet(ws.cmd_update, []), 1)
            self.assertEqual(self.quiet(ws.cmd_deploy, []), 1)


class GatesInsideTests(unittest.TestCase):
    """The gates run these tests; a test that reaches the real gates must get a refusal, never a nested run."""

    def test_gates_refuse_inside_their_own_tests(self):
        with mock.patch.dict(os.environ, {ws.IN_TESTS: "1"}), \
             mock.patch.object(ws, "vehicles", side_effect=AssertionError("the gates ran")):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(ws.cmd_gates([]), 1)


class Refusal(unittest.TestCase):
    """rebuild_refusal over a scratch git repository standing in for the Werkstatt checkout."""

    def setUp(self):
        self.repo = tempfile.mkdtemp(prefix="werkstatt-git-")
        self.addCleanup(shutil.rmtree, self.repo)
        os.makedirs(os.path.join(self.repo, "plugins", "VehicleMods"))
        self.write("plugins/VehicleMods/Plugin.cs", "class Plugin {}\n")
        self.write(".gitignore", "plugins/*/bin/\n")
        for cmd in (["init", "-q"], ["add", "-A"], ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "x"]):
            subprocess.run(["git", *cmd], cwd=self.repo, check=True, capture_output=True)
        patch = mock.patch.object(ws, "ROOT", self.repo)
        patch.start()
        self.addCleanup(patch.stop)
        self.record = {"repoCommit": ws.checkout()[0]}

    def write(self, rel, text):
        path = os.path.join(self.repo, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(text)

    def test_a_clean_checkout_at_the_deployed_commit_rebuilds(self):
        self.write("plugins/VehicleMods/bin/Release/VehicleMods.dll", "build output")    # ignored
        self.assertIsNone(ws.rebuild_refusal(self.record))

    def test_an_untracked_source_file_refuses(self):
        self.write("plugins/VehicleMods/HalfDone.cs", "class HalfDone {")              # the csproj compiles every .cs
        self.assertIn("uncommitted changes", ws.rebuild_refusal(self.record))

    def test_another_commit_refuses(self):
        self.assertIn("deployed from", ws.rebuild_refusal({"repoCommit": "0" * 40}))


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
        os.makedirs(os.path.join(self.game, "BepInEx"))
        os.makedirs(os.path.join(self.werkstatt, "tools"))
        with open(os.path.join(self.game, "run_bepinex.sh"), "w") as f:
            f.write('#!/bin/sh\nfor a in "$@"; do printf "[%s]" "$a"; done > args.txt\nexit 7\n')
        os.chmod(os.path.join(self.game, "run_bepinex.sh"), 0o755)
        # The helper's exit code before a launch comes from a file; each call is recorded.
        with open(os.path.join(self.werkstatt, "tools", "werkstatt.py"), "w") as f:
            f.write("import os, sys\n"
                    "game = os.environ['GAME_DIR']\n"
                    "open(os.path.join(game, 'calls.txt'), 'a').write(sys.argv[1] + '\\n')\n"
                    "code = open(os.path.join(game, 'before-exit.txt')).read().strip()\n"
                    "sys.exit(int(code) if sys.argv[1] == 'launch-before' else 0)\n")
        with open(os.path.join(ROOT, "tools", ws.LAUNCH_SCRIPT)) as f:
            text = f.read()
        self.script = os.path.join(self.game, ws.LAUNCH_SCRIPT)
        with open(self.script, "w") as f:
            f.write(text.replace('WERKSTATT_DIR=""', f"WERKSTATT_DIR={ws.shell_quote(self.werkstatt)}", 1))
        os.chmod(self.script, 0o755)

    def launch(self, before_exit):
        with open(os.path.join(self.game, "before-exit.txt"), "w") as f:
            f.write(str(before_exit))
        env = {k: v for k, v in os.environ.items() if k not in LEAKY}
        r = subprocess.run(["./" + ws.LAUNCH_SCRIPT, "/x/reaper", "SteamLaunch", "AppId=1", "--", "a game/with spaces"],
                           cwd=self.game, env=env, capture_output=True, text=True, timeout=60)
        with open(os.path.join(self.game, "args.txt")) as f:
            self.assertEqual(f.read(), "[/x/reaper][SteamLaunch][AppId=1][--][a game/with spaces]")
        return r.returncode

    def calls(self, wait_for=None):
        path = os.path.join(self.game, "calls.txt")
        deadline = time.monotonic() + 20
        while True:
            calls = open(path).read().split() if os.path.exists(path) else []
            if wait_for is None or wait_for in calls or time.monotonic() > deadline:
                return calls
            time.sleep(0.2)

    def test_plain_launch_passes_through(self):
        self.assertEqual(self.launch(0), 7)                     # run_bepinex.sh's own exit code
        self.assertEqual(self.calls(), ["launch-before"])

    def test_plugin_aside_runs_the_rebuild_after_the_game(self):
        self.assertEqual(self.launch(3), 7)
        self.assertEqual(self.calls(wait_for="launch-after"), ["launch-before", "launch-after"])

    def test_a_failing_helper_starts_the_game_normally(self):
        self.assertEqual(self.launch(1), 7)
        self.assertEqual(self.calls(), ["launch-before"])

    def test_no_werkstatt_folder_falls_through(self):
        shutil.rmtree(self.werkstatt)
        self.assertEqual(self.launch(0), 7)
        self.assertFalse(os.path.exists(os.path.join(self.game, "calls.txt")))


if __name__ == "__main__":
    unittest.main()
