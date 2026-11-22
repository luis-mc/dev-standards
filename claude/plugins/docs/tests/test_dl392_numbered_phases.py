"""DL392: a numbered repeat of any phase name (ci2, fix2) is accepted and shown in order."""
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _helpers  # noqa: F401,E402
import project_artifacts as P  # noqa: E402
import render_artifacts as R  # noqa: E402

NOW = datetime(2026, 11, 13, 9, 0, tzinfo=timezone.utc)
SPECS = ["agents=09:00-09:10", "ci=09:10-09:30", "fix=09:30-09:40", "ci2=09:40-10:00", "fix2=10:00-10:10",
         "merge=10:10-10:16"]


class Numbered(unittest.TestCase):
    def test_numbered_names_accepted_in_order(self):
        phases = P.parse_phases(SPECS, NOW)
        self.assertEqual([p["name"] for p in phases], ["agents", "ci", "fix", "ci2", "fix2", "merge"])

    def test_bad_numbered_names_refused(self):
        for bad in ("ci1", "xx2", "ci0"):
            with self.assertRaises(P.Fail):
                P.parse_phases([bad + "=09:00-09:10"], NOW)

    def test_stored_phases_validate_and_render(self):
        phases = P.parse_phases(SPECS, NOW)
        task = {"id": "DL1", "item": "RELEASE-1", "release": 1, "status": "Running", "expected": "13 Nov ~10:16",
                "phases": phases}
        self.assertEqual([m for r, m in P.release_problems(task, {"DL1": task}) if r == "R5.40"], [])
        html = R.release_timeline([task], datetime(2026, 11, 13, 9, 20, tzinfo=timezone.utc), "t")
        self.assertIn("rt-bar ci", html)
        self.assertIn("PR CI 2 09:40", html)


if __name__ == "__main__":
    unittest.main()
