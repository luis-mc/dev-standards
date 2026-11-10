"""DL103 (B14): a rerun of the pool setup keeps the owner's cap from the pool .env, never lowers .wslconfig, and
`pool-refresh` rewrites only RUNNER_SHA256, POOL_BROWSERS and PLAYWRIGHT_VERSION. Temp folders and fakes; no Docker."""
import argparse
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest import mock

from _helpers import make_root  # noqa: F401  (sets sys.path to the scripts folder)
import delivery_ci_setup as S
import delivery_runner_pool as P
from test_runner_pool import FILES, FakeProbe

MEASURED = {'mem_gib': 4.0, 'cpus': 2.0, 'ok': True, 'message': '', 'wsl': {'memory': 6, 'processors': 3}}
OWNER = {'POOL_MEM': '8.5g', 'POOL_CPUS': '4'}


class KeepCapTests(unittest.TestCase):
    def test_owner_cap_is_kept_over_a_lower_measured_one(self):
        cap = P.keep_owner_cap(dict(MEASURED), OWNER, host_cpus=8)
        self.assertEqual((cap['mem_gib'], cap['cpus'], cap['source']), (8.5, 4.0, 'kept'))
        self.assertEqual(cap['measured_cap'], {'mem_gib': 4.0, 'cpus': 2.0})
        self.assertEqual(cap['wsl'], {'memory': 11, 'processors': 5})

    def test_kept_cap_rescues_a_refused_measurement(self):
        refused = dict(MEASURED, ok=False, message='below the floor')
        self.assertTrue(P.keep_owner_cap(refused, OWNER)['ok'])

    def test_resize_uses_the_measured_cap_and_says_why(self):
        cap = P.keep_owner_cap(dict(MEASURED), OWNER, resize=True, shrink=True)  # DL176: lowering needs shrink
        self.assertEqual((cap['mem_gib'], cap['source']), (4.0, 'measured'))
        self.assertIn('--resize', cap['reason'])

    def test_a_cap_under_the_floor_is_replaced_with_a_reason(self):
        cap = P.keep_owner_cap(dict(MEASURED), {'POOL_MEM': '0.5g', 'POOL_CPUS': '1'})
        self.assertEqual(cap['mem_gib'], 4.0)
        self.assertIn('under the floor', cap['reason'])

    def test_no_env_keeps_the_measured_cap(self):
        cap = P.keep_owner_cap(dict(MEASURED), {})
        self.assertEqual((cap['mem_gib'], cap['source']), (4.0, 'measured'))
        self.assertNotIn('reason', cap)

    def test_processors_never_exceed_the_host(self):
        self.assertEqual(P.keep_owner_cap(dict(MEASURED), OWNER, host_cpus=4)['wsl']['processors'], 4)


class WslNeverLowerTests(unittest.TestCase):
    def test_existing_values_are_never_lowered(self):
        w, enough = P._wsl_values({'wsl': {'memory': 10.0, 'processors': 3}}, {'wsl': {'memory': 6, 'processors': 5}})
        self.assertEqual(w, {'memory': 10, 'processors': 5})
        self.assertFalse(enough)

    def test_a_higher_need_is_written(self):
        w, _ = P._wsl_values({'wsl': {'memory': 6.0, 'processors': 2}}, {'wsl': {'memory': 11, 'processors': 5}})
        self.assertEqual(w, {'memory': 11, 'processors': 5})


class PlanTests(unittest.TestCase):
    def run_plan(self, env, *extra):
        probe = FakeProbe(dict(FILES))
        probe.memory_gib = lambda: (16.0, 8.0)  # little free memory now: the measured cap alone is refused
        probe.cpu_count = lambda: 8
        args = argparse.Namespace(action='pool-plan', repos=None, windows_repos=None, pool='main', total_gib=None,
                                  used_gib=None, cpus=None, docker_gib=None, largest_shard_gib=None, yes=False,
                                  yes_delete=None, resize=False)
        for k, v in zip(extra[::2], extra[1::2]):
            setattr(args, k, v)
        out = StringIO()
        with mock.patch.object(P, 'Probe', lambda: probe), mock.patch.object(P, 'read_pool_env', lambda pr, pool: dict(env)), \
                redirect_stdout(out):
            rc = S.cmd_pool(args, '.')
        return rc, out.getvalue()

    def test_plan_reads_the_env_and_keeps_the_cap(self):
        rc, text = self.run_plan(OWNER)
        self.assertEqual(rc, 0, text)
        line = [x for x in text.splitlines() if x.startswith('Pool cap:')][0]
        self.assertIn('8.5 GiB memory, 4.0 CPUs', line)
        self.assertIn("kept from the pool's .env", line)
        files = [x for x in text.splitlines() if 'Write the pool files' in x]
        if files:  # only when the fixtures give a Linux repository
            self.assertIn('POOL_MEM 8.5g -> 8.5g (kept)', files[0])
            self.assertNotIn('unset', files[0].split('POOL_CPUSET')[0])


class EnvFileTests(unittest.TestCase):
    def test_set_env_values_replaces_and_adds_and_keeps_the_rest(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, '.env')
            with open(path, 'w') as f:
                f.write('POOL_MEM=8.5g\nPOOL_BROWSERS=none\nPOOL_CPUS=4\n')
            P.set_env_values(path, {'POOL_BROWSERS': 'chromium', 'RUNNER_SHA256': 'b' * 64})
            with open(path, 'rb') as f:
                data = f.read()
        self.assertNotIn(b'\r', data)
        self.assertEqual(data.decode().splitlines(),
                         ['POOL_MEM=8.5g', 'POOL_BROWSERS=chromium', 'POOL_CPUS=4', 'RUNNER_SHA256=' + 'b' * 64])

    def test_apply_cap_compares_numbers(self):
        with mock.patch.object(P.subprocess, 'run') as run:
            self.assertEqual(P.Executor(FakeProbe()).apply_cap('main', {'POOL_MEM': '8.5g', 'POOL_CPUS': '4'},
                                                               {'POOL_MEM': '8.5g', 'POOL_CPUS': '4.0'}), '')
        run.assert_not_called()


class OfflineProbe(P.Probe):
    platform = 'linux'

    def gh_json(self, args):
        return None, 'offline'


class RefreshTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.pool = os.path.join(self.tmp.name, 'pools', 'main')
        os.makedirs(self.pool)
        self.repo = os.path.join(self.tmp.name, 'app')
        os.makedirs(self.repo)
        with open(os.path.join(self.repo, 'package.json'), 'w') as f:
            json.dump({'devDependencies': {'@playwright/test': '^1.50.0'}}, f)
        self.patch = mock.patch.object(P, 'pool_dir', lambda pool: self.pool)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def env(self, text=None):
        path = os.path.join(self.pool, '.env')
        if text is not None:
            with open(path, 'w') as f:
                f.write(text)
        with open(path) as f:
            return f.read()

    def test_no_env_is_refused(self):
        self.assertIn('pool-run first', P.refresh_plan(OfflineProbe(), 'main', [self.repo])['error'])

    def test_refresh_writes_sha_and_browsers_and_keeps_the_cap(self):
        self.env('POOL_MEM=8.5g\nPOOL_CPUS=4\nRUNNER_VERSION=%s\nPOOL_BROWSERS=none\n' % P.RUNNER_VERSION)
        rp = P.refresh_plan(OfflineProbe(), 'main', [self.repo])
        self.assertNotIn('error', rp)
        self.assertEqual(rp['changes']['RUNNER_SHA256'], (None, P.RUNNER_SHA256))
        self.assertEqual(rp['changes']['POOL_BROWSERS'], ('none', 'chromium'))
        ex = P.Executor(OfflineProbe())
        with mock.patch.object(ex, 'runners_busy', lambda: True):
            ok, text = ex.refresh(rp)
        self.assertTrue(ok)
        self.assertIn('By hand', text)
        env = self.env()
        for line in ('POOL_MEM=8.5g', 'POOL_CPUS=4', 'POOL_BROWSERS=chromium', 'RUNNER_SHA256=' + P.RUNNER_SHA256):
            self.assertIn(line, env.splitlines())

    def test_chromium_is_kept_without_an_explicit_choice(self):
        os.remove(os.path.join(self.repo, 'package.json'))
        self.env('POOL_MEM=8g\nPOOL_CPUS=4\nPOOL_BROWSERS=chromium\nRUNNER_SHA256=%s\n' % ('c' * 64))
        rp = P.refresh_plan(OfflineProbe(), 'main', [self.repo])
        self.assertNotIn('POOL_BROWSERS', rp['changes'])
        self.assertIn('POOL_BROWSERS', P.refresh_plan(OfflineProbe(), 'main', [self.repo], 'none')['changes'])

    def test_idle_refresh_rebuilds(self):
        self.env('POOL_MEM=8g\nPOOL_CPUS=4\nRUNNER_VERSION=%s\n' % P.RUNNER_VERSION)
        ex = P.Executor(OfflineProbe())
        calls = []
        with mock.patch.object(ex, 'runners_busy', lambda: False), \
                mock.patch.object(P.subprocess, 'run', lambda argv, **k: calls.append(argv) or
                                  type('R', (), {'returncode': 0, 'stderr': '', 'stdout': ''})()):
            ok, text = ex.refresh(P.refresh_plan(OfflineProbe(), 'main', [self.repo]))
        self.assertTrue(ok, text)
        self.assertEqual([c for c in calls if c[:2] == ['docker', 'compose']], [['docker', 'compose', 'up', '-d', '--build']])
        self.assertIn('could not compare the image ids', text)

    def test_refresh_with_no_change_still_rebuilds(self):
        self.env('POOL_MEM=8g\nPOOL_CPUS=4\nPOOL_BROWSERS=chromium\nRUNNER_SHA256=%s\nPLAYWRIGHT_VERSION=%s\n'
                 % (P.RUNNER_SHA256, P.PLAYWRIGHT_VERSION))  # DL165: a repeated-character hash is wrong, so the pinned one is used
        rp = P.refresh_plan(OfflineProbe(), 'main', [], 'chromium', P.PLAYWRIGHT_VERSION)
        self.assertEqual(rp['changes'], {})
        P.copy_pool_templates(self.pool)  # DL162: the pool files match, so only the .env is judged
        rp = P.refresh_plan(OfflineProbe(), 'main', [], 'chromium', P.PLAYWRIGHT_VERSION)
        ex = P.Executor(OfflineProbe())
        calls = []
        with mock.patch.object(ex, 'runners_busy', lambda: False), \
                mock.patch.object(P.subprocess, 'run', lambda argv, **k: calls.append(argv) or
                                  type('R', (), {'returncode': 0, 'stderr': '', 'stdout': ''})()):
            ok, text = ex.refresh(rp)
        self.assertTrue(ok, text)
        self.assertEqual(len([c for c in calls if c[:2] == ['docker', 'compose']]), 1)
        self.assertIn('nothing to change', text)

    def test_pool_up_writes_a_missing_sha_to_the_env(self):
        self.env('POOL_MEM=8g\nPOOL_CPUS=4\nRUNNER_VERSION=%s\n' % P.RUNNER_VERSION)
        with mock.patch.object(P.subprocess, 'run', lambda argv, **k: type('R', (), {'returncode': 0, 'stderr': ''})()):
            ok, _ = P.Executor(OfflineProbe()).do_pool_up({'pool': 'main'})
        self.assertTrue(ok)
        self.assertIn('RUNNER_SHA256=' + P.RUNNER_SHA256, self.env().splitlines())


if __name__ == '__main__':
    unittest.main()
