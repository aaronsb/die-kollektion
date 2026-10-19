"""The Nexus workflow's helpers in tools/release.py: the changelog it posts and whether it uploads."""
import os
import sys
import tempfile
import unittest

TESTS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(TESTS), "tools"))

import release  # noqa: E402

NEXUS = """0.6.0 (2026-10-19): halogen headlights, a status line.
- Halogen headlights.
- A status line.

0.5.1 (2026-10-18): a fix with no bullets.

0.5.0 (2026-10-18): first public release.
- The make flow.
"""

CHANGELOG = """# Changelog

## [Unreleased]

## [0.7.0] - 2026-11-01

### Added
- Something only CHANGELOG.md knows.

## [0.6.0] - 2026-10-19

### Added
- Halogen headlights (CHANGELOG.md wording).
"""


class NexusChangelog(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.nexus = os.path.join(self.tmp.name, "changelog.txt")
        self.changelog = os.path.join(self.tmp.name, "CHANGELOG.md")
        open(self.nexus, "w").write(NEXUS)
        open(self.changelog, "w").write(CHANGELOG)

    def text(self, version):
        return release.nexus_changelog(version, self.nexus, self.changelog)

    def test_the_bullets_without_the_version_line(self):
        self.assertEqual(self.text("0.6.0"), "- Halogen headlights.\n- A status line.")

    def test_an_entry_without_bullets_gives_its_headline(self):
        self.assertEqual(self.text("0.5.1"), "a fix with no bullets.")

    def test_falls_back_to_the_changelog_section(self):
        self.assertEqual(self.text("0.7.0"), "### Added\n- Something only CHANGELOG.md knows.")

    def test_a_missing_nexus_file_falls_back_too(self):
        self.assertIn("CHANGELOG.md wording", release.nexus_changelog("0.6.0", os.path.join(self.tmp.name, "none"),
                                                                     self.changelog))

    def test_unknown_version(self):
        self.assertIsNone(self.text("9.9.9"))


class NexusPlan(unittest.TestCase):
    def test_uploads_a_newer_version_and_ignores_non_semver(self):
        plan, why = release.nexus_plan("0.6.0", ["1"])
        self.assertEqual(plan, "upload")
        self.assertIn("ignored: 1", why)

    def test_skips_a_version_nexus_has(self):
        self.assertEqual(release.nexus_plan("0.6.0", ["1", "0.6.0"])[0], "skip")

    def test_refuses_an_older_version(self):
        self.assertEqual(release.nexus_plan("0.5.1", ["0.6.0"]), ("refuse", "Nexus has 0.6.0, newer than 0.5.1"))

    def test_compares_numerically(self):
        self.assertEqual(release.nexus_plan("0.10.0", ["0.9.0"])[0], "upload")
        self.assertEqual(release.nexus_plan("0.9.0", ["0.10.0"])[0], "refuse")


if __name__ == "__main__":
    unittest.main()
