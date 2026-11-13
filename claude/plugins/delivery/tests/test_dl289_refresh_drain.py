"""DL289: pool-refresh builds first, drains the pool, then recreates. Fakes for docker, gh, the clock and files; no Docker."""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from _helpers import make_root  # noqa: F401  (sets sys.path to the scripts folder)
import delivery_runner_pool as P
from test_runner_pool import FakeProbe

HOOKS = Path(__file__).resolve().parent.parent / 'templates' / 'runner-pool' / 'hooks'
sys.path.insert(0, str(HOOKS.parent))
import pool_supervisor as SUP  # noqa: E402

BUILD = ['docker', 'compose', 'build']
STOP = ['docker', 'compose', 'stop', 'pool']
UP = ['docker', 'compose', 'up', '-d', '--no-build', '--force-recreate', 'pool']
SHA = 'd' * 63 + '1'


class Probe(FakeProbe):
    """Fake docker ids, a fake clock (sleep advances it) and an `on_sleep` hook that plays the supervisor."""
    def __init__(self):
        super().__init__()
        self.tag = 'sha256:aaa'
        self.log = []
        self.on_sleep = None
        self.slept_total = 0

    def sh(self, argv, input=None, timeout=60):
        if argv[:2] == ['docker', 'inspect']:
            return 0, ('c1\n' if '{{.Id}}' in argv else 'sha256:old\n')
        if argv[:3] == ['docker', 'image', 'inspect']:
            return 0, self.tag + '\n'
        return super().sh(argv, input, timeout)

    def sleep(self, sec):
        self.slept_total += sec
        if self.on_sleep:
            self.on_sleep(self.slept_total)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.pool = os.path.join(self.tmp.name, 'pools', 'main')
        os.makedirs(self.pool)
        mock.patch.object(P, 'pool_dir', lambda pool: self.pool).start()
        self.addCleanup(mock.patch.stopall)
        P.copy_pool_templates(self.pool)
        Path(self.pool, 'agents.json').write_text('{"agents": []}')
        Path(self.pool, '.env').write_text('POOL_MEM=8g\nPOOL_CPUS=4\nPOOL_BROWSERS=none\nRUNNER_VERSION=%s\nRUNNER_SHA256=%s\nPLAYWRIGHT_VERSION=%s\n'
                                           % (P.RUNNER_VERSION, P.RUNNER_SHA256, P.PLAYWRIGHT_VERSION))
        Path(self.pool, 'Dockerfile').write_text('FROM old\n')  # a stale file: the refresh has work to do
        self.events = []
        self.busy_now = []  # names GitHub reports busy at the second check

    def path(self, name):
        return os.path.join(self.pool, name)

    def refresh(self, probe=None, force=False, timeout=600):
        probe = probe or Probe()
        ex = P.Executor(probe)

        def run(argv, **k):
            self.events.append(('run', list(argv), os.path.exists(self.path('drain')), os.path.exists(self.path('drained'))))
            if argv == BUILD and getattr(self, 'during_build', None):
                self.during_build()
            return SimpleNamespace(returncode=0, stderr='', stdout='')
        rp = dict(P.refresh_plan(probe, 'main', []), repos=['owner/example-app'])
        gh = lambda pr, repos, pool: (list(self.busy_now), None)  # noqa: E731
        with mock.patch.object(P.subprocess, 'run', run), mock.patch.object(P, 'busy_pool_runners', gh):
            return ex.refresh(rp, force=force, drain_timeout=timeout) + (probe,)

    def cmds(self):
        return [e[1] for e in self.events]


class OrderTests(Base):
    def test_order_is_build_then_drain_then_wait_then_recreate(self):
        probe = Probe()
        probe.on_sleep = lambda t: Path(self.path('drained')).write_text('x')  # the supervisor drains on its first tick
        ok, text, _ = self.refresh(probe)
        self.assertTrue(ok, text)
        self.assertEqual(self.cmds(), [BUILD, STOP, UP])
        build, stop, up = self.events
        self.assertEqual(build[2:], (False, False))  # no drain file while it builds
        self.assertEqual(stop[2:], (True, True))     # stopped only after drained, drain file still there
        self.assertEqual(up[2:], (False, False))     # new container starts with no drain file
        self.assertIn('container recreated', text)

    def test_job_started_during_the_build_is_waited_for(self):
        probe = Probe()
        self.during_build = lambda: None  # a job starts here; the supervisor reports it busy until t=120
        def supervisor(t):
            if t < 120:
                Path(self.path('drain-busy')).write_text('app1\n')
            else:
                Path(self.path('drained')).write_text('x')
        probe.on_sleep = supervisor
        ok, text, probe = self.refresh(probe)
        self.assertTrue(ok, text)
        self.assertGreaterEqual(probe.slept_total, 120)
        self.assertEqual(self.cmds(), [BUILD, STOP, UP])

    def test_drain_timeout_restores_and_refuses_with_the_busy_agents(self):
        probe = Probe()
        probe.on_sleep = lambda t: Path(self.path('drain-busy')).write_text('app1\napp2\n')
        ok, text, _ = self.refresh(probe, timeout=30)
        self.assertFalse(ok)
        self.assertIn('refused: drain timed out, busy: app1, app2', text)
        self.assertEqual(self.cmds(), [BUILD])  # the container was never stopped or recreated
        for name in ('drain', 'drained', 'drain-busy'):
            self.assertFalse(os.path.exists(self.path(name)), name)

    def test_second_github_check_refuses_and_clears_the_drain(self):
        probe = Probe()
        probe.on_sleep = lambda t: Path(self.path('drained')).write_text('x')
        self.busy_now = ['main-app1 (owner/example-app)']
        ok, text, _ = self.refresh(probe)
        self.assertFalse(ok)
        self.assertIn('refused: pool runner busy: main-app1', text)
        self.assertEqual(self.cmds(), [BUILD])
        self.assertFalse(os.path.exists(self.path('drain')))

    def test_force_skips_the_drain_and_warns(self):
        self.busy_now = ['main-app1 (owner/example-app)']
        ok, text, probe = self.refresh(force=True)
        self.assertTrue(ok, text)
        self.assertEqual(self.cmds(), [BUILD, UP])
        self.assertEqual(probe.slept_total, 0)
        self.assertIn('warning: --force', text)

    def test_build_failure_never_drains(self):
        probe = Probe()
        ex = P.Executor(probe)
        rp = dict(P.refresh_plan(probe, 'main', []), repos=[])
        with mock.patch.object(P.subprocess, 'run', lambda argv, **k: self.events.append(argv) or SimpleNamespace(returncode=1, stderr='boom', stdout='')), \
                mock.patch.object(ex, 'runners_busy', lambda: False):
            ok, text = ex.refresh(rp)
        self.assertFalse(ok)
        self.assertIn('old container keeps running', text)
        self.assertFalse(os.path.exists(self.path('drain')))


class SupervisorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.drain = self.tmp.name
        Path(self.tmp.name, 'agents.json').write_text('{"agents": [{"slug": "a", "user": "r-a"}, {"slug": "b", "user": "r-b"}]}')
        self.now = 0.0
        self.busy = set()
        self.procs = []
        self.sup = SUP.Supervisor(os.path.join(self.tmp.name, 'agents.json'), self.tmp.name, spawn=self.spawn,
                                  clock=lambda: self.now, drain_dir=self.drain, busy=lambda s: s in self.busy)

    def spawn(self, agent):
        p = mock.Mock()
        p.alive = True
        p.poll = lambda: None if p.alive else 0
        p.terminate = lambda: setattr(p, 'alive', False)
        p.slug = agent['slug']
        self.procs.append(p)
        return p

    def has(self, name):
        return os.path.exists(os.path.join(self.drain, name))

    def test_idle_listeners_stop_at_drain_and_are_not_restarted(self):
        self.sup.tick()
        self.assertEqual(len(self.procs), 2)
        Path(self.drain, 'drain').write_text('x')
        self.sup.tick()
        self.assertTrue(all(not p.alive for p in self.procs))
        self.sup.tick()
        self.now += 1000
        self.sup.tick()
        self.assertEqual(len(self.procs), 2)  # none restarted
        self.assertTrue(self.has('drained'))

    def test_busy_listener_finishes_its_job_then_stops(self):
        self.sup.tick()
        self.busy = {'a'}
        Path(self.drain, 'drain').write_text('x')
        self.sup.tick()
        by = {p.slug: p for p in self.procs}
        self.assertTrue(by['a'].alive)
        self.assertFalse(by['b'].alive)
        self.assertFalse(self.has('drained'))
        self.assertEqual(Path(self.drain, 'drain-busy').read_text().split(), ['a'])
        self.busy = set()  # the completed hook removed the marker
        self.sup.tick()
        self.assertFalse(by['a'].alive)
        self.sup.tick()
        self.assertTrue(self.has('drained'))
        self.assertFalse(self.has('drain-busy'))

    def test_listeners_restart_when_the_drain_file_goes(self):
        self.sup.tick()
        Path(self.drain, 'drain').write_text('x')
        self.sup.tick()
        self.sup.tick()
        os.remove(os.path.join(self.drain, 'drain'))
        self.sup.tick()
        self.assertEqual(len(self.procs), 4)
        self.assertFalse(self.has('drained'))

    def test_stale_marker_is_ignored(self):
        os.makedirs(os.path.join(self.tmp.name, 'a'))
        marker = os.path.join(self.tmp.name, 'a', '.job-running')
        Path(marker).write_text('1')
        mtime = os.path.getmtime(marker)
        self.assertTrue(SUP.job_running(self.tmp.name, 'a', now=lambda: mtime + 5 * 3600))
        self.assertFalse(SUP.job_running(self.tmp.name, 'a', now=lambda: mtime + 7 * 3600))
        self.assertFalse(SUP.job_running(self.tmp.name, 'none', now=lambda: mtime))


@unittest.skipUnless(os.name == 'posix' and subprocess.run(['sh', '-c', 'true']).returncode == 0, 'needs a POSIX shell')
class HookTests(unittest.TestCase):
    def hook_part(self, name):
        """Run only the marker line of a hook, in a temp /agents-like folder."""
        text = (HOOKS / name).read_text()
        line = next(l for l in text.splitlines() if '.job-running' in l and l.startswith('d='))
        return line

    def run_line(self, line, tmpdir):
        return subprocess.run(['sh', '-c', line], env=dict(os.environ, TMPDIR=tmpdir), capture_output=True, text=True)

    def test_started_writes_and_completed_removes_the_marker(self):
        with tempfile.TemporaryDirectory() as root:
            folder = os.path.join(root, 'agents', 'app1')
            os.makedirs(os.path.join(folder, 'tmp'))
            started = self.hook_part('job-started.sh').replace('/agents/*', root + '/agents/*')
            done = self.hook_part('job-completed.sh').replace('/agents/*', root + '/agents/*')
            self.assertEqual(self.run_line(started, folder + '/tmp').returncode, 0)
            self.assertTrue(os.path.isfile(os.path.join(folder, '.job-running')))
            self.assertEqual(self.run_line(done, folder + '/tmp').returncode, 0)
            self.assertFalse(os.path.exists(os.path.join(folder, '.job-running')))

    def test_outside_agents_nothing_is_written(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertEqual(self.run_line(self.hook_part('job-started.sh'), os.path.join(root, 'tmp')).returncode, 0)
            self.assertFalse(os.path.exists(os.path.join(root, '.job-running')))

    def test_hooks_still_exec_their_python(self):
        for name, script in (('job-started.sh', 'runner_load_gate.py'), ('job-completed.sh', 'runner_job_done.py')):
            self.assertIn('exec /usr/bin/python3 /opt/delivery/' + script, (HOOKS / name).read_text())


if __name__ == '__main__':
    unittest.main()
