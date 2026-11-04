"""The watcher refreshes .delivery/ci-runs.json: once a minute at most, and a failure never fails the tick."""
import os
import unittest
from datetime import datetime, timezone
from pathlib import Path

from _helpers import make_root

import ci_runs as CR
import delivery_watch as W
from test_ci_runs import FakeShell, REPO

NOW = datetime(2026, 11, 4, 14, 33, tzinfo=timezone.utc)


def watcher(root, sh):
    return W.Watcher(root, sh=sh, now=lambda: NOW, out=lambda *_: None, repo=REPO)


class WatchCiRuns(unittest.TestCase):
    def setUp(self):
        os.environ["DELIVERY_MACHINE_DIR"] = str(Path(__file__).parent / "fixtures" / "ci_runs")

    def tearDown(self):
        os.environ.pop("DELIVERY_MACHINE_DIR", None)

    def test_writes_the_file(self):
        root = make_root({})
        watcher(root, FakeShell()).pass_ci_runs()
        self.assertTrue((Path(root) / CR.OUT_REL).is_file())

    def test_at_most_once_a_minute(self):
        root = make_root({})
        sh = FakeShell()
        w = watcher(root, sh)
        w.pass_ci_runs()
        n = len(sh.calls)
        w.pass_ci_runs()
        self.assertEqual(len(sh.calls), n)
        old = os.path.getmtime(Path(root) / CR.OUT_REL) - 120
        os.utime(Path(root) / CR.OUT_REL, (old, old))
        w.pass_ci_runs()
        self.assertGreater(len(sh.calls), n)

    def test_dry_run_writes_nothing(self):
        root = make_root({})
        w = W.Watcher(root, sh=FakeShell(), dry_run=True, now=lambda: NOW, out=lambda *_: None, repo=REPO)
        w.pass_ci_runs()
        self.assertFalse((Path(root) / CR.OUT_REL).exists())

    def test_gh_failure_never_fails_the_tick(self):
        root = make_root({})
        w = watcher(root, FakeShell(fail=True))
        w.run_once()
        self.assertFalse((Path(root) / CR.OUT_REL).exists())

    def test_a_raise_in_the_pass_is_contained(self):
        root = make_root({})
        w = watcher(root, FakeShell())
        w.pass_ci_runs = lambda: 1 / 0
        w.run_once()


if __name__ == "__main__":
    unittest.main()
