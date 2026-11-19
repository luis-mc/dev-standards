"""AR74: an HH:MM-only phase list takes the occurrence nearest now (R5.40a); a far phase warns; two error hints."""
import contextlib
import io
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _helpers  # noqa: F401,E402  (puts scripts on the path)
import project_artifacts as P  # noqa: E402


def now(d, h, m):
    return datetime(2026, 11, d, h, m, tzinfo=timezone.utc)


def parse(specs, at):
    return {p['name']: (p['start'][:16], p['end'][:16]) for p in P.parse_phases(specs, at)}


LIST = ["join=21:59-22:07", "ci=07:00-07:50", "merge=07:50-08:10"]


class PhaseDates(unittest.TestCase):
    def test_next_morning_keeps_the_evening_before(self):
        out = parse(LIST, now(19, 5, 15))
        self.assertEqual(out['join'], ('2026-11-18T21:59', '2026-11-18T22:07'))
        self.assertEqual(out['ci'], ('2026-11-19T07:00', '2026-11-19T07:50'))
        self.assertEqual(out['merge'], ('2026-11-19T07:50', '2026-11-19T08:10'))

    def test_evening_chains_to_next_day(self):
        out = parse(LIST, now(18, 21, 0))
        self.assertEqual(out['join'], ('2026-11-18T21:59', '2026-11-18T22:07'))
        self.assertEqual(out['ci'], ('2026-11-19T07:00', '2026-11-19T07:50'))
        self.assertEqual(out['merge'][0], '2026-11-19T07:50')

    def test_same_day_stays_today(self):
        out = parse(["agents=14:10-14:50", "join=14:50-14:55"], now(19, 14, 0))
        self.assertEqual(out['agents'][0], '2026-11-19T14:10')
        self.assertEqual(out['join'], ('2026-11-19T14:50', '2026-11-19T14:55'))

    def test_dated_phases_keep_their_date(self):
        out = parse(["join=17 Nov 21:59-17 Nov 22:07", "ci=18 Nov 07:00-18 Nov 07:50"], now(19, 5, 15))
        self.assertEqual(out['join'][0], '2026-11-17T21:59')
        self.assertEqual(out['ci'][0], '2026-11-18T07:00')

    def test_far_phase_warns_and_succeeds(self):
        err = io.StringIO()
        P._WARNED.clear()
        with contextlib.redirect_stderr(err):
            out = P.parse_phases(["agents=18 Nov 10:00-18 Nov 10:30", "ci=09:00-09:30"], now(18, 14, 0))
        self.assertEqual(len(out), 2)
        text = err.getvalue()
        self.assertIn('--phase ci', text)
        self.assertIn('19 Nov 09:00', text)
        self.assertIn('DD Mon HH:MM', text)

    def test_no_warning_for_a_normal_list(self):
        err = io.StringIO()
        P._WARNED.clear()
        with contextlib.redirect_stderr(err):
            P.parse_phases(LIST, now(19, 5, 15))
        self.assertEqual(err.getvalue(), '')

    def test_clear_with_others_hint(self):
        with self.assertRaises(P.Fail) as cm:
            P.parse_phases(["", "ci=07:00-07:50"], now(19, 5, 15))
        self.assertIn('clear first with --phase "" alone, then give the new phases in a second call', str(cm.exception))

    def test_waiting_expected_with_old_phases_hint(self):
        task = {'id': 'X1', 'status': 'Waiting', 'release': 1, 'expected': '30 Nov ~10:00',
                'phases': [{'name': 'ci', 'start': '2026-11-19T07:00+00:00', 'end': '2026-11-19T07:50+00:00'}]}
        args = type('A', (), {'phase': None, 'risk': None, 'rides': None, 'release': None, 'no_release': None})()
        with self.assertRaises(P.Fail) as cm:
            P.apply_release_fields(task, {'X1': task}, args, now(19, 5, 15))
        self.assertIn('--phase ""', str(cm.exception))


if __name__ == '__main__':
    unittest.main()
