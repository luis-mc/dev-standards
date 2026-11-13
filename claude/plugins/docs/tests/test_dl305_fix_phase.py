"""DL305: `fix` is a fifth release phase; ci and fix may repeat; Expected is the end of the last phase."""
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _helpers  # noqa: F401,E402  (puts scripts on the path)
import project_artifacts as P  # noqa: E402
import render_artifacts as R  # noqa: E402

NOW = datetime(2026, 11, 13, 9, 0, tzinfo=timezone.utc)
SPECS = ["agents=09:00-09:10", "join=09:10-09:15", "ci=09:15-09:30", "fix=09:30-09:45",
         "ci=09:45-10:00", "merge=10:00-10:06"]


class FixPhase(unittest.TestCase):
    def test_six_phases_with_fix_are_accepted(self):
        phases = P.parse_phases(SPECS, NOW)
        self.assertEqual([p["name"] for p in phases], ["agents", "join", "ci", "fix", "ci", "merge"])

    def test_unknown_name_lists_the_names(self):
        with self.assertRaises(P.Fail) as cm:
            P.parse_phases(["repair=09:00-09:10"], NOW)
        self.assertIn("agents, join, ci, fix, merge", str(cm.exception))

    def test_other_names_still_may_not_repeat(self):
        with self.assertRaises(P.Fail):
            P.parse_phases(["agents=09:00-09:10", "agents=09:10-09:20"], NOW)

    def test_expected_must_equal_last_phase_end(self):
        phases = P.parse_phases(SPECS, NOW)
        task = {"id": "DL1", "release": 1, "status": "Running", "expected": "13 Nov ~10:06", "phases": phases}
        self.assertEqual([m for r, m in P.release_problems(task, {"DL1": task}) if r == "R5.41"], [])
        task["expected"] = "13 Nov ~09:45"
        self.assertTrue([m for r, m in P.release_problems(task, {"DL1": task}) if r == "R5.41"])

    def test_timeline_renders_the_fix_bar(self):
        ref = datetime(2026, 11, 13, 9, 20, tzinfo=timezone.utc)
        task = {"id": "DL1", "item": "RELEASE-1", "release": 1, "status": "Running", "expected": "13 Nov ~10:06",
                "phases": P.parse_phases(SPECS, NOW)}
        html = R.release_timeline([task], ref, "t")
        self.assertIn("rt-bar fix", html)
        self.assertIn("fix round", html)

    def test_fix_has_a_label_and_a_phase_list_entry(self):
        self.assertEqual(R.PHASE_LABELS["fix"], "fix round")
        self.assertIn("fix", R.RELEASE_PHASES)


if __name__ == "__main__":
    unittest.main()
