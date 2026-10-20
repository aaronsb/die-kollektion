"""The captured memory layouts under tests/maps/ are public: a BepInEx/dobby-maps.txt copied in unscrubbed would
publish the player's home folder (plugins/VehicleMods/CLAUDE.md asks for /game/... paths instead)."""
import glob
import os
import re
import shutil
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Steam libraries on other drives sit under /media/<user>/ or /mnt/<name>/.
USER_PATH = re.compile(r"/home/|/var/home/|/Users/|/root/|/run/user/|/media/[^/\s]+/|/mnt/[^/\s]+/|[A-Za-z]:\\Users\\", re.I)


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


def repeated_regions(folder):
    """[(file, line number, range)] for a region listed twice in one .maps file: two dobby-maps.txt sections
    (at Load, before the hooks) copied into one file."""
    found = []
    for path in sorted(glob.glob(os.path.join(folder, "*.maps"))):
        seen = set()
        with open(path, encoding="utf-8", errors="replace") as f:
            for n, line in enumerate(f, 1):
                if line.startswith("#") or not line.strip():
                    continue
                region = line.split()[0]
                if region in seen:
                    found.append((os.path.basename(path), n, region))
                seen.add(region)
    return found


class Maps(unittest.TestCase):
    def test_the_captured_layouts_hold_no_user_paths(self):
        count, found = user_paths(os.path.join(ROOT, "tests", "maps"))
        self.assertGreater(count, 0, "no tests/maps/*.maps to check")
        self.assertEqual(found, [], "scrub these paths to /game/... before committing")
        self.assertEqual(repeated_regions(os.path.join(ROOT, "tests", "maps")), [],
                         "one dobby-maps.txt section per .maps file")

    def test_a_home_folder_is_caught(self):
        tmp = tempfile.mkdtemp(prefix="werkstatt-maps-")
        self.addCleanup(shutil.rmtree, tmp)
        with open(os.path.join(tmp, "scrubbed.maps"), "w") as f:
            f.write("7f0050000000-7f0050100000 r--p 00000000 00:00 0 /game/GameAssembly.so\n")
        with open(os.path.join(tmp, "raw.maps"), "w") as f:
            f.write("7f0050000000-7f0050100000 r--p 00000000 00:00 0 /home/someone/Steam/GameAssembly.so\n")
        with open(os.path.join(tmp, "drive.maps"), "w") as f:
            f.write("7f0050000000-7f0050100000 r--p 00000000 00:00 0 /media/someone/Games/GameAssembly.so\n"
                    "7f0060000000-7f0060100000 r--p 00000000 00:00 0 /mnt/games/SteamLibrary/UnityPlayer.so\n")
        count, found = user_paths(tmp)
        self.assertEqual(count, 3)
        self.assertEqual([(name, n) for name, n, _ in found], [("drive.maps", 1), ("drive.maps", 2), ("raw.maps", 1)])

    def test_two_sections_in_one_file_are_caught(self):
        tmp = tempfile.mkdtemp(prefix="werkstatt-maps-")
        self.addCleanup(shutil.rmtree, tmp)
        region = "7f0050000000-7f0050100000 r--p 00000000 00:00 0 /game/GameAssembly.so\n"
        with open(os.path.join(tmp, "one.maps"), "w") as f:
            f.write("# at Load: no placement\n" + region)
        with open(os.path.join(tmp, "two.maps"), "w") as f:
            f.write("# at Load: no placement\n" + region + "# before the hooks: no placement\n" + region)
        self.assertEqual(repeated_regions(tmp), [("two.maps", 4, "7f0050000000-7f0050100000")])


if __name__ == "__main__":
    unittest.main()
