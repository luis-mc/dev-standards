"""DL165/DL166: pool-refresh fixes a wrong runner hash and reports the build result truthfully.
Temp pool dir, fake probe, fake docker; no Docker."""
import io
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from _helpers import make_root  # noqa: F401  (sets sys.path to the scripts folder)
import delivery_ci_setup as CI
import delivery_doctor as D  # noqa: F401
import delivery_runner_pool as P
from test_runner_pool import FakeProbe

PLACEHOLDER = 'a' * 64
RELEASED = 'd' * 63 + '1'


class Probe(FakeProbe):
    """Fake docker. `ids` is a list of (container id, running image, tagged image), one per read, the last repeats."""
    def __init__(self, ids=None, release=None):
        super().__init__()
        self.ids = list(ids or [('c1', 'sha256:aaa', 'sha256:aaa')])
        self.release = release
        self.phase = 0  # 0 before the build, 1 after it

    def sh(self, argv, input=None, timeout=60):
        i = min(self.phase, len(self.ids) - 1)
        if argv[:2] == ['docker', 'inspect']:
            return 0, self.ids[i][0 if '{{.Id}}' in argv else 1] + '\n'
        if argv[:3] == ['docker', 'image', 'inspect']:
            return 0, self.ids[i][2] + '\n'
        return super().sh(argv, input, timeout)

    def gh_json(self, args):
        if any(a.startswith('repos/actions/runner/releases') for a in args):
            return ({'assets': [{'name': 'actions-runner-linux-x64-%s.tar.gz' % self.version, 'digest': 'sha256:' + self.release}]}
                    if self.release else None), None
        return super().gh_json(args)

    version = '2.300.0'


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.pool = os.path.join(self.tmp.name, 'pools', 'main')
        os.makedirs(self.pool)
        mock.patch.object(P, 'pool_dir', lambda pool: self.pool).start()
        self.addCleanup(mock.patch.stopall)
        self.addCleanup(self.tmp.cleanup)
        P.copy_pool_templates(self.pool)
        Path(self.pool, 'agents.json').write_text('{"agents": []}')
        self.repo = os.path.join(self.tmp.name, 'app')
        os.makedirs(os.path.join(self.repo, '.delivery'))
        self.env(PLACEHOLDER, P.RUNNER_VERSION)

    def env(self, sha, version):
        Path(self.pool, '.env').write_text('POOL_MEM=8g\nPOOL_CPUS=4\nPOOL_BROWSERS=none\nRUNNER_VERSION=%s\nRUNNER_SHA256=%s\nPLAYWRIGHT_VERSION=%s\n'
                                           % (version, sha, P.PLAYWRIGHT_VERSION))

    def plan(self, probe=None):
        return P.refresh_plan(probe or Probe(), 'main', [self.repo])

    def refresh(self, probe, run_rc=0, busy=False):
        ex = P.Executor(probe)
        calls = []
        def run(argv, **k):
            calls.append(argv)
            if argv[:3] == ['docker', 'compose', 'build']:
                probe.phase = 1
            return type('R', (), {'returncode': run_rc, 'stderr': 'boom'})()
        with mock.patch.object(ex, 'runners_busy', lambda: busy), mock.patch.object(P.subprocess, 'run', run), \
                mock.patch.object(P.Executor, 'drain', lambda s, pool, t: (True, '')):
            ok, text = ex.refresh(self.plan(probe))
        return ok, text, calls


class HashTests(Base):
    def test_placeholder_is_replaced_by_the_pinned_hash(self):
        rp = self.plan()
        self.assertEqual(rp['changes']['RUNNER_SHA256'], (PLACEHOLDER, P.RUNNER_SHA256))
        self.assertIn('did not match the pinned hash for %s' % P.RUNNER_VERSION, rp['sha_reason'])
        self.refresh(Probe())
        self.assertIn('RUNNER_SHA256=' + P.RUNNER_SHA256, Path(self.pool, '.env').read_text())

    def test_plan_line_is_short(self):
        out = io.StringIO()
        args = CI.argparse.Namespace(pool='main', yes=False)
        with redirect_stdout(out):
            CI.cmd_pool_refresh(args, self.repo, P, Probe())
        self.assertIn('RUNNER_SHA256: aaaaaaaa -> %s (did not match the pinned hash for %s)' % (P.RUNNER_SHA256[:8], P.RUNNER_VERSION), out.getvalue())

    def test_correct_hash_is_kept(self):
        self.env(P.RUNNER_SHA256, P.RUNNER_VERSION)
        self.assertNotIn('RUNNER_SHA256', self.plan()['changes'])

    def test_malformed_or_repeated_values_are_wrong(self):
        for bad in ('abc', 'z' * 64, '0' * 64, 'f' * 64):
            self.env(bad, P.RUNNER_VERSION)
            self.assertEqual(self.plan()['changes']['RUNNER_SHA256'][1], P.RUNNER_SHA256, bad)

    def test_other_version_uses_the_released_hash(self):
        self.env(PLACEHOLDER, '2.300.0')
        rp = self.plan(Probe(release=RELEASED))
        self.assertEqual(rp['changes']['RUNNER_SHA256'], (PLACEHOLDER, RELEASED))

    def test_other_version_unreadable_release_keeps_value_and_says_so(self):
        good = 'ab12' * 16
        self.env(good, '2.300.0')
        rp = self.plan(Probe(release=None))
        self.assertNotIn('RUNNER_SHA256', rp['changes'])
        self.assertTrue(any('could not be read' in n for n in rp['notes']), rp['notes'])
        self.assertNotIn('error', rp)

    def test_doctor_warns_on_a_wrong_hash(self):
        c = {x['id']: x for x in P.doctor_checks(self.tmp.name, FakeProbe())}
        self.assertEqual(c['pool.main.runner-sha']['status'], 'warn')
        self.assertIn('pool-refresh --yes', c['pool.main.runner-sha']['detail'])

    def test_doctor_ok_on_the_pinned_hash(self):
        self.env(P.RUNNER_SHA256, P.RUNNER_VERSION)
        Path(self.pool, 'compose.yaml').write_text('x')
        c = {x['id']: x for x in P.doctor_checks(self.tmp.name, FakeProbe())}
        self.assertEqual(c['pool.main.runner-sha']['status'], 'ok')


class ResultTests(Base):
    RECREATE = ['docker', 'compose', 'up', '-d', '--no-build', '--force-recreate', 'pool']

    def test_build_failure_exits_non_zero_and_keeps_the_old_container(self):
        ex = P.Executor(Probe())
        run = lambda argv, **k: type('R', (), {'returncode': 1, 'stderr': 'computed checksum did NOT match', 'stdout': ''})()  # noqa: E731
        args = CI.argparse.Namespace(pool='main', yes=True)
        out = io.StringIO()
        with mock.patch.object(P.Executor, 'runners_busy', lambda s: False), mock.patch.object(P.subprocess, 'run', run), \
                redirect_stdout(out), redirect_stderr(io.StringIO()):
            rc = CI.cmd_pool_refresh(args, self.repo, P, Probe())
        self.assertEqual(rc, 1)
        self.assertIn('the rebuild failed', out.getvalue())
        self.assertIn('old container keeps running', out.getvalue())
        del ex

    def test_failed_build_never_recreates(self):
        ok, text, calls = self.refresh(Probe(), run_rc=1)
        self.assertFalse(ok)
        self.assertNotIn(self.RECREATE, calls)

    def test_rebuilt_image_is_reported_as_rebuilt(self):
        p = Probe(ids=[('c1', 'sha256:aaa', 'sha256:aaa'), ('c1', 'sha256:aaa', 'sha256:bbb')])
        ok, text, calls = self.refresh(p)
        self.assertIn('image rebuilt', text)
        self.assertNotIn('cache hit', text)
        self.assertIn(self.RECREATE, calls)

    def test_unchanged_image_is_a_cache_hit(self):
        ok, text, calls = self.refresh(Probe())
        self.assertIn('image unchanged (cache hit)', text)
        self.assertNotIn('was rebuilt', text)


class GuardTests(Base):
    def test_refresh_with_machine_dir_unset_writes_only_in_temp(self):
        """The default machine folder is patched to a temp path; the real default is never opened for writing."""
        real = ['/etc/luismc-delivery', 'ProgramData']
        opened = []
        orig = open

        def spy(file, mode='r', *a, **k):
            if any(c in str(mode) for c in 'wax+') and any(r in str(file) for r in real):
                opened.append(str(file))
            return orig(file, mode, *a, **k)
        mock.patch.stopall()
        mock.patch.dict(os.environ, {}, clear=False).start()
        os.environ.pop('DELIVERY_MACHINE_DIR', None)
        base = os.path.join(self.tmp.name, 'machine')
        mock.patch.object(P.MS, 'machine_dir', lambda: base).start()
        pool = P.pool_dir('main')
        self.assertTrue(pool.startswith(self.tmp.name))
        os.makedirs(pool)
        Path(pool, '.env').write_text('POOL_MEM=8g\nPOOL_CPUS=4\nRUNNER_VERSION=%s\nRUNNER_SHA256=%s\n' % (P.RUNNER_VERSION, PLACEHOLDER))
        ex = P.Executor(Probe())
        run = lambda argv, **k: type('R', (), {'returncode': 0, 'stderr': ''})()  # noqa: E731
        with mock.patch('builtins.open', spy), mock.patch.object(ex, 'runners_busy', lambda: False), mock.patch.object(P.subprocess, 'run', run):
            ok, _ = ex.refresh(P.refresh_plan(Probe(), 'main', [self.repo]))
        self.assertEqual(opened, [])
        self.assertIn(P.RUNNER_SHA256, Path(pool, '.env').read_text())


if __name__ == '__main__':
    unittest.main()
