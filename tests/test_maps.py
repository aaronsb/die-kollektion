"""The captured memory layouts under tests/maps/ are public: a BepInEx/dobby-maps.txt copied in unscrubbed would
publish the player's home folder (plugins/VehicleMods/CLAUDE.md asks for /game/... paths instead)."""
import glob
import os
import re
import shutil
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
USER_PATH = re.compile(r"/home/|/var/home/|/Users/|/root/|/run/user/|[A-Za-z]:\\Users\\", re.I)


def user_paths(folder):
    """(files examined, [(file, line number, line)] holding a user path) for every .maps file in folder."""
    files = sorted(glob.glob(os.path.join(folder, "*.maps")))
    found = []
    for path in files:
        with open(path, encoding="utf-8", errors="replace") as f:
            for n, line in enumerate(f, 1):
                if USER_PATH.search(line):
                    found.append((os.path.basename(path), n, line.strip()))
    return len(files), found


class Maps(unittest.TestCase):
    def test_the_captured_layouts_hold_no_user_paths(self):
        count, found = user_paths(os.path.join(ROOT, "tests", "maps"))
        self.assertGreater(count, 0, "no tests/maps/*.maps to check")
        self.assertEqual(found, [], "scrub these paths to /game/... before committing")

    def test_a_home_folder_is_caught(self):
        tmp = tempfile.mkdtemp(prefix="werkstatt-maps-")
        self.addCleanup(shutil.rmtree, tmp)
        with open(os.path.join(tmp, "scrubbed.maps"), "w") as f:
            f.write("7f0050000000-7f0050100000 r--p 00000000 00:00 0 /game/GameAssembly.so\n")
        with open(os.path.join(tmp, "raw.maps"), "w") as f:
            f.write("7f0050000000-7f0050100000 r--p 00000000 00:00 0 /home/someone/Steam/GameAssembly.so\n")
        count, found = user_paths(tmp)
        self.assertEqual(count, 2)
        self.assertEqual([(name, n) for name, n, _ in found], [("raw.maps", 1)])


if __name__ == "__main__":
    unittest.main()
