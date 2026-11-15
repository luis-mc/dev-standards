"""DL367: a drain does not wait 45 minutes on a pool container that is not running. Fake probe; no Docker."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from _helpers import make_root  # noqa: F401  (sets sys.path to the scripts folder)
import delivery_runner_pool as P
from test_runner_pool import FakeProbe

INSPECT = ['docker', 'inspect', '--format', '{{.State.Running}}', 'pool-main-pool-1']


class Probe(FakeProbe):
    def __init__(self, running):
        super().__init__()
        self.running = running  # 'true', 'false', or None for a missing container
        self.slept_total = 0
        self.inspects = 0

    def sh(self, argv, input=None, timeout=60):
        if argv == INSPECT:
            self.inspects += 1
            if self.running is None:
                return 1, 'Error: No such object: pool-main-pool-1'
            return 0, self.running + '\n'
        return super().sh(argv, input, timeout)

    def sleep(self, sec):
        self.slept_total += sec


class DrainStoppedPool(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.pool = os.path.join(self.tmp.name, 'main')
        os.makedirs(self.pool)
        mock.patch.object(P, 'pool_dir', lambda pool: self.pool).start()
        self.addCleanup(mock.patch.stopall)

    def drain(self, probe, timeout=2700):
        return P.Executor(probe).drain('main', timeout)

    def test_exited_container_returns_at_once(self):
        probe = Probe('false')
        self.assertEqual(self.drain(probe), (True, ''))
        self.assertEqual(probe.slept_total, 0)

    def test_missing_container_returns_at_once(self):
        probe = Probe(None)
        self.assertEqual(self.drain(probe), (True, ''))
        self.assertEqual(probe.slept_total, 0)

    def test_running_container_still_waits_and_times_out(self):
        probe = Probe('true')
        ok, text = self.drain(probe, timeout=30)
        self.assertFalse(ok)
        self.assertIn('drain timed out', text)
        self.assertGreaterEqual(probe.slept_total, 30)
        self.assertFalse(os.path.exists(os.path.join(self.pool, 'drain')))

    def test_container_stops_during_the_wait(self):
        probe = Probe('true')
        probe.sleep = lambda sec: setattr(probe, 'running', 'false')
        self.assertEqual(self.drain(probe), (True, ''))

    def test_drained_file_still_wins_when_running(self):
        probe = Probe('true')
        probe.sleep = lambda sec: Path(self.pool, 'drained').write_text('x')
        self.assertEqual(self.drain(probe), (True, ''))


if __name__ == '__main__':
    unittest.main()
