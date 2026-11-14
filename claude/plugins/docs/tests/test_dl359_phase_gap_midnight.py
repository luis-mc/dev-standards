"""DL359: a phase that starts before the previous one ends rolls to the next day, even after a gap."""
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _helpers  # noqa: F401,E402  (puts scripts on the path)
import project_artifacts as P  # noqa: E402

NOW = datetime(2026, 11, 14, 20, 40, tzinfo=timezone.utc)


class PhaseGapMidnight(unittest.TestCase):
    def test_phase_after_a_gap_past_midnight_is_next_day(self):
        out = P.parse_phases(["join=20:42-20:55", "ci=01:00-03:00", "merge=03:00-03:20"], NOW)
        ends = {p['name']: p['end'] for p in out}
        self.assertTrue(ends['ci'].startswith('2026-11-15T03:00'))
        self.assertTrue(ends['merge'].startswith('2026-11-15T03:20'))

    def test_same_day_phases_unchanged(self):
        out = P.parse_phases(["join=20:42-20:55", "ci=20:55-21:05"], NOW)
        self.assertTrue(out[-1]['end'].startswith('2026-11-14T21:05'))

    def test_contiguous_wrap_still_works(self):
        out = P.parse_phases(["ci=23:30-00:10", "merge=00:10-00:20"], NOW)
        self.assertTrue(out[-1]['end'].startswith('2026-11-15T00:20'))


if __name__ == '__main__':
    unittest.main()
