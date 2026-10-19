"""Game-update handling (tools/werkstatt.py, run_werkstatt.sh's helper) over a fake game folder: no game needed.

Run: python3 -m unittest discover -s tests (part of `make check` and `python3 tools/release.py ci`).
"""
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
import werkstatt as ws  # noqa: E402


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
        self.assertEqual(ws.launch_decision(True, None, files(), False), "plain")      # deployed before records
        self.assertEqual(ws.launch_decision(True, files(), files(), False), "plain")
        self.assertEqual(ws.launch_decision(True, files(), files(assembly="b"), False), "move-aside")
        self.assertEqual(ws.launch_decision(False, None, files(), True), "pending")
        self.assertEqual(ws.launch_decision(True, files(), files(), True), "pending")

    def test_rebuild_ready(self):
        note = {"interopHash": "old", "movedAt": 100.0}
        self.assertTrue(ws.rebuild_ready(note, "new", None, ""))
        self.assertFalse(ws.rebuild_ready(note, "old", None, ""))
        self.assertFalse(ws.rebuild_ready(note, "old", 90.0, "Chainloader initialized"))     # the log predates the move
        self.assertFalse(ws.rebuild_ready(note, "old", 110.0, "Preloader started"))          # stopped before interop
        self.assertTrue(ws.rebuild_ready(note, "old", 110.0, "[Message:   BepInEx] Chainloader initialized"))
        self.assertFalse(ws.rebuild_ready(note, None, None, ""))


class FakeGame(unittest.TestCase):
    """A game folder with the files Werkstatt fingerprints, a deployed plugin, and Steam's app manifest."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="werkstatt-test-")
        self.game = os.path.join(self.tmp, "steamapps", "common", "over the hill")
        self.write("GameAssembly.so", "code v1")
        self.write("over the hill_Data/il2cpp_data/Metadata/global-metadata.dat", "metadata v1")
        self.write("BepInEx/interop/assembly-hash.txt", "hash-v1")
        self.write("BepInEx/interop/Assembly-CSharp.dll", "interop")
        self.manifest("100", "1760000000")
        self.dll = os.path.join(self.tmp, "VehicleMods.dll")
        open(self.dll, "w").write("plugin built for v1")
        self.folder = ws.default_deploy_dir(self.game)
        patches = [mock.patch.dict(os.environ, {"GAME_DIR": self.game}),
                   mock.patch.object(ws, "game_running", return_value=False),
                   mock.patch.object(ws, "expected_sources", side_effect=lambda: {"VehicleMods.dll": self.dll}),
                   mock.patch.object(ws, "cmd_compile_plugin", return_value=0)]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(shutil.rmtree, self.tmp)
        with mock.patch("sys.stdout"):
            self.assertEqual(ws.cmd_copy_deploy([]), 0)
            self.assertEqual(ws.cmd_record_deploy([]), 0)

    def write(self, rel, text, append=False):
        path = os.path.join(self.game, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        open(path, "a" if append else "w").write(text)

    def manifest(self, build, updated):
        path = os.path.join(self.tmp, "steamapps", f"appmanifest_{ws.APP_ID}.acf")
        open(path, "w").write(f'"AppState"\n{{\n\t"appid"\t\t"{ws.APP_ID}"\n\t"LastUpdated"\t\t"{updated}"\n'
                              f'\t"buildid"\t\t"{build}"\n}}\n')

    def update_game(self):
        self.write("GameAssembly.so", "+", append=True)
        self.manifest("200", "1760100000")

    def quiet(self, fn, *args):
        with mock.patch("sys.stdout"):
            return fn(*args)

    def test_deploy_records_the_game_and_installs_the_launch_script(self):
        rec = ws.deploy_record(self.folder)
        self.assertEqual(rec["game"]["steamBuild"], "100")
        self.assertEqual(rec["game"]["interopHash"], "hash-v1")
        self.assertEqual(rec["game"]["files"]["gameAssembly"]["sha256"], ws.sha256(os.path.join(self.game, "GameAssembly.so")))
        self.assertTrue(ws.launch_script_ready(self.game))
        self.assertEqual(ws.update_report(self.game, self.folder)[0], "current")

    def test_unchanged_files_are_not_hashed_again(self):
        known = ws.deploy_record(self.folder)["game"]
        known["files"]["gameAssembly"]["sha256"] = "remembered"
        self.assertEqual(ws.game_record(self.game, known)["files"]["gameAssembly"]["sha256"], "remembered")
        self.write("GameAssembly.so", "+", append=True)
        self.assertNotEqual(ws.game_record(self.game, known)["files"]["gameAssembly"]["sha256"], "remembered")

    def test_unchanged_game_launches_normally(self):
        self.assertEqual(self.quiet(ws.cmd_launch_before, []), 0)
        self.assertTrue(os.path.isdir(self.folder))

    def test_update_moves_aside_then_rebuilds_once_bepinex_has_prepared_the_game(self):
        self.update_game()
        self.assertEqual(ws.update_report(self.game, self.folder)[0], "needed")
        self.assertEqual(self.quiet(ws.cmd_launch_before, []), 3)
        aside = ws.aside_dir(self.folder)
        self.assertFalse(os.path.exists(self.folder))
        self.assertEqual(aside, os.path.join(self.game, "BepInEx", "VehicleMods.aside"))
        self.assertEqual(json.load(open(os.path.join(aside, ws.ASIDE_NOTE)))["interopHash"], "hash-v1")
        # The game exited before BepInEx regenerated its interop: the plugin waits.
        self.assertEqual(self.quiet(ws.rebuild_from_aside, self.game, self.folder), "waiting")
        self.assertEqual(self.quiet(ws.cmd_launch_before, []), 3)                     # still pending next launch
        # BepInEx regenerated it: rebuild, install, and remember the update.
        self.write("BepInEx/interop/assembly-hash.txt", "hash-v2")
        open(self.dll, "w").write("plugin built for v2")
        self.assertEqual(self.quiet(ws.cmd_launch_after, []), 0)
        self.assertFalse(os.path.exists(aside))
        self.assertFalse(os.path.exists(aside[:-len(".aside")] + ".staging"))
        rec = ws.deploy_record(self.folder)
        self.assertEqual(rec["game"]["steamBuild"], "200")
        self.assertEqual(rec["game"]["interopHash"], "hash-v2")
        self.assertEqual(rec["afterUpdate"]["fromBuild"], "100")
        self.assertEqual(open(os.path.join(self.folder, "VehicleMods.dll")).read(), "plugin built for v2")
        state, text = ws.update_report(self.game, self.folder)
        self.assertEqual(state, "rebuilt")
        self.assertIn("rebuilt", text)
        self.assertEqual(self.quiet(ws.cmd_launch_before, []), 0)

    def test_failed_build_leaves_the_plugin_aside(self):
        self.update_game()
        self.quiet(ws.cmd_launch_before, [])
        self.write("BepInEx/interop/assembly-hash.txt", "hash-v2")
        with mock.patch.object(ws, "cmd_compile_plugin", return_value=1):
            self.assertEqual(self.quiet(ws.cmd_launch_after, []), 1)
        self.assertFalse(os.path.exists(self.folder))
        self.assertTrue(os.path.isdir(ws.aside_dir(self.folder)))

    def test_bepinex_log_counts_when_the_hash_stays(self):
        self.update_game()
        self.quiet(ws.cmd_launch_before, [])
        time.sleep(0.01)
        self.write("BepInEx/LogOutput.log", "[Message:   BepInEx] Chainloader initialized\n")
        self.assertEqual(self.quiet(ws.rebuild_from_aside, self.game, self.folder), "rebuilt")

    def test_hand_changes_survive_the_rebuild(self):
        self.write("BepInEx/plugins/VehicleMods/notes.txt", "mine")
        self.update_game()
        self.quiet(ws.cmd_launch_before, [])
        self.write("BepInEx/interop/assembly-hash.txt", "hash-v2")
        self.assertEqual(self.quiet(ws.cmd_launch_after, []), 0)
        kept = [d for d in os.listdir(os.path.join(self.game, "BepInEx")) if d.startswith("VehicleMods.replaced-")]
        self.assertEqual(len(kept), 1)
        self.assertTrue(os.path.isfile(os.path.join(self.game, "BepInEx", kept[0], "notes.txt")))

    def test_make_update_by_hand(self):
        self.assertEqual(self.quiet(ws.cmd_update, []), 0)                           # nothing to do
        self.assertTrue(os.path.isdir(self.folder))
        self.update_game()
        self.assertEqual(self.quiet(ws.cmd_update, []), 0)                           # moved aside, waiting
        self.assertTrue(os.path.isdir(ws.aside_dir(self.folder)))
        self.write("BepInEx/interop/assembly-hash.txt", "hash-v2")
        self.assertEqual(self.quiet(ws.cmd_update, []), 0)
        self.assertEqual(ws.update_report(self.game, self.folder)[0], "rebuilt")

    def test_deploy_refuses_until_bepinex_has_prepared_the_updated_game(self):
        self.update_game()
        self.assertEqual(self.quiet(ws.cmd_preflight_deploy, []), 1)
        self.assertTrue(os.path.isdir(ws.aside_dir(self.folder)))
        self.write("BepInEx/interop/assembly-hash.txt", "hash-v2")
        self.assertEqual(self.quiet(ws.cmd_preflight_deploy, []), 0)
        self.assertFalse(os.path.exists(ws.aside_dir(self.folder)))


if __name__ == "__main__":
    unittest.main()
