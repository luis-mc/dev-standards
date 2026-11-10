"""DL176: pool-plan / pool-run keep browsers, layers and apt from the pool .env, size from the median of several memory
samples, refuse a --resize that lowers the cap without --shrink, and take --pool-gib / --pool-cpus. Fake probe; no Docker."""
import argparse
import unittest
from contextlib import redirect_stdout, redirect_stderr
from io import StringIO
from unittest import mock

from _helpers import make_root  # noqa: F401  (sets sys.path to the scripts folder)
import delivery_ci_setup as S
import delivery_runner_pool as P
from test_runner_pool import FILES, FakeProbe

WSL = '[wsl2]\nmemory=11GB\nprocessors=5\n'
ENV = {'POOL_MEM': '8.5g', 'POOL_CPUS': '4.0', 'POOL_BROWSERS': 'chromium', 'POOL_LAYERS': 'windows-packaging',
       'POOL_APT': 'jq', 'PLAYWRIGHT_VERSION': '1.60.0'}


def probe_with(used_series, total=31.7, vm=11.0, cpus=20):
    """A probe whose memory reads follow `used_series` (PC-wide used GiB, VM included)."""
    files = dict(FILES, **{'C:/Users/u1/.wslconfig': WSL})
    probe = FakeProbe(files)
    seq = list(used_series)
    probe.memory_gib = lambda: (total, seq.pop(0) if len(seq) > 1 else seq[0])
    probe.wsl_vm_gib = lambda: vm
    probe.cpu_count = lambda: cpus
    return probe


def run(env, probe, **over):
    args = argparse.Namespace(action='pool-plan', repos='owner/example-app', windows_repos=None, pool='main', total_gib=None,
                              used_gib=None, cpus=None, docker_gib=None, largest_shard_gib=None, yes=False, yes_delete=None,
                              resize=False, shrink=False, pool_gib=None, pool_cpus=None, browsers=None, playwright=None,
                              drop_layer=None, drop_apt=None)
    for k, v in over.items():
        setattr(args, k, v)
    out, err = StringIO(), StringIO()
    with mock.patch.object(P, 'Probe', lambda: probe), mock.patch.object(P, 'read_pool_env', lambda pr, pool: dict(env)), \
            redirect_stdout(out), redirect_stderr(err):
        rc = S.cmd_pool(args, make_root().as_posix())
    return rc, out.getvalue(), err.getvalue()


def pool_files_line(text):
    return next(x for x in text.splitlines() if 'Write the pool files' in x)


STEADY = [19.0] * 5  # 8 GiB used outside WSL once the 11 GiB VM is left out


class KeepFromEnvTests(unittest.TestCase):
    def test_browsers_kept_from_env_without_a_flag(self):
        rc, out, _ = run(ENV, probe_with(STEADY))
        self.assertEqual(rc, 0, out)
        self.assertIn('POOL_BROWSERS chromium', pool_files_line(out))
        self.assertNotIn('no Chromium libraries', out)

    def test_browsers_kept_with_the_flag_too(self):
        rc, out, _ = run(ENV, probe_with(STEADY), browsers='chromium')
        self.assertIn('POOL_BROWSERS chromium', pool_files_line(out))

    def test_flag_none_lowers_it(self):
        rc, out, _ = run(ENV, probe_with(STEADY), browsers='none')
        self.assertIn('POOL_BROWSERS none', pool_files_line(out))

    def test_pick_browsers_detection_only_raises(self):
        probe = FakeProbe({})
        probe.read_text = lambda path: '{"devDependencies": {"@playwright/test": "1.50.0"}}' if path.endswith('package.json') else None
        self.assertEqual(P.pick_browsers(probe, None, ['/r'], 'chromium')[0], 'chromium')
        self.assertEqual(P.pick_browsers(probe, None, ['/r'], 'none')[0], 'chromium')
        self.assertEqual(P.pick_browsers(FakeProbe({}), None, ['/r'], 'none')[0], 'none')
        self.assertEqual(P.pick_browsers(FakeProbe({}), None, [], 'chromium')[0], 'chromium')

    def test_layers_apt_and_playwright_are_kept(self):
        rc, out, _ = run(ENV, probe_with(STEADY))
        line = pool_files_line(out)
        self.assertIn('windows-packaging', line)
        self.assertIn('Apt packages kept: jq', line)
        self.assertIn('Playwright 1.60.0 (kept from the pool .env)', line)

    def test_drop_flags_still_work(self):
        rc, out, _ = run(ENV, probe_with(STEADY), drop_layer=['windows-packaging'], drop_apt=['jq'])
        line = pool_files_line(out)
        self.assertNotIn('Layers kept', line)
        self.assertNotIn('Apt packages kept', line)

    def test_the_written_env_keeps_the_extra_lines(self):
        import os
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            P.write_pool_files('main', {'cpus': 8, 'mem_gib': 12}, dest=d, browsers='chromium',
                               keep_env=dict(ENV, POOL_LAYER_SOURCES='windows-packaging:o/a'))
            with open(os.path.join(d, '.env'), encoding='utf-8') as f:
                text = f.read()
        for want in ('POOL_LAYERS=windows-packaging', 'POOL_APT=jq', 'POOL_LAYER_SOURCES=windows-packaging:o/a', 'POOL_MEM=12g'):
            self.assertIn(want, text)
        self.assertEqual(text.count('POOL_MEM='), 1)


class MedianTests(unittest.TestCase):
    def test_a_spike_does_not_cut_the_cap(self):
        # PC-wide used: 19, 19, 29 (a spike), 19, 19 -> outside WSL: 8, 8, 18, 8, 8 -> median 8
        host = P.detect_host(probe_with([19.0, 19.0, 29.0, 19.0, 19.0]))
        self.assertEqual(host['used_gib'], 8.0)
        self.assertEqual(len(host['used_samples']), 5)

    def test_sampling_sleeps_between_reads_through_the_probe(self):
        probe = probe_with(STEADY)
        P.detect_host(probe)
        self.assertEqual(probe.slept, 4)

    def test_even_count_uses_the_middle_pair(self):
        self.assertEqual(P.median([1.0, 9.0, 3.0, 5.0]), 4.0)

    def test_three_resize_plans_with_different_spikes_agree(self):
        caps = []
        for series in ([19.0] * 5, [19.0, 29.0, 19.0, 19.0, 19.0], [19.0, 19.0, 28.0, 30.0, 19.0]):
            found = P.detect(probe_with(series))
            found['pool_env'] = {}
            caps.append(P.measured_sizing(found)['mem_gib'])
        self.assertEqual(len(set(caps)), 1, caps)

    def test_plan_prints_its_inputs(self):
        rc, out, _ = run(ENV, probe_with(STEADY), pool_gib=12, pool_cpus=8)
        line = next(x for x in out.splitlines() if 'Sizing inputs' in x)
        for want in ('total 31.7 GiB', 'used outside WSL 8.0 GiB', 'median of 5 samples', '85% budget 26.9 GiB', 'room 18.9 GiB',
                     'Docker ceiling 11'):
            self.assertIn(want, line)


class ShrinkTests(unittest.TestCase):
    def test_resize_that_lowers_refuses(self):
        # 20 GiB used outside WSL leaves room for a 4.5 GiB cap, below the 8.5 in .env
        rc, out, err = run(ENV, probe_with([31.0] * 5), resize=True)
        self.assertEqual(rc, 1)
        self.assertIn('--shrink', err)
        self.assertIn('would lower', err)
        self.assertNotIn('Pool cap', out)

    def test_resize_that_lowers_goes_through_with_shrink(self):
        rc, out, err = run(ENV, probe_with([31.0] * 5), resize=True, shrink=True)
        self.assertEqual(rc, 0, err)
        self.assertIn('--resize: the measured cap replaces', out)

    def test_resize_that_raises_needs_no_shrink(self):
        rc, out, err = run(ENV, probe_with(STEADY), resize=True)
        self.assertEqual(rc, 0, err)

    def test_a_resize_that_lowers_only_cpus_refuses_too(self):
        cap = {'mem_gib': 12.0, 'cpus': 2.0, 'ok': True, 'message': ''}
        self.assertFalse(P.keep_owner_cap(cap, ENV, resize=True)['ok'])


class TargetTests(unittest.TestCase):
    def test_the_owner_case(self):
        rc, out, err = run(ENV, probe_with(STEADY), pool_gib=12, pool_cpus=8)
        self.assertEqual(rc, 0, err + out)
        line = pool_files_line(out)
        self.assertIn('POOL_MEM 8.5g -> 12g', line)
        self.assertIn('POOL_CPUS 4.0 -> 8,', line)
        self.assertIn('POOL_BROWSERS chromium', line)
        self.assertIn('windows-packaging', line)
        self.assertIn('memory 11GB -> 14GB', out)
        self.assertIn('processors 5 -> 9', out)

    def test_within_budget_is_used_as_given(self):
        rc, out, _ = run(ENV, probe_with(STEADY), pool_gib=10, pool_cpus=6)
        self.assertEqual(rc, 0)
        self.assertIn('POOL_MEM 8.5g -> 10g', pool_files_line(out))

    def test_over_the_memory_budget_refuses_and_names_it(self):
        rc, out, err = run(ENV, probe_with(STEADY), pool_gib=20, pool_cpus=8)
        self.assertEqual(rc, 1)
        self.assertIn('Memory budget short', err)
        self.assertNotIn('CPU budget short', err)

    def test_over_the_cpu_budget_refuses_and_names_it(self):
        rc, out, err = run(ENV, probe_with(STEADY), pool_gib=24 - 12, pool_cpus=14)
        self.assertEqual(rc, 1)
        self.assertIn('CPU budget short', err)
        self.assertNotIn('Memory budget short', err)

    def test_under_the_floor_refuses(self):
        rc, _, err = run(ENV, probe_with(STEADY), pool_gib=3, pool_cpus=2)
        self.assertEqual(rc, 1)
        self.assertIn('Floor', err)

    def test_too_little_memory_per_cpu_refuses(self):
        rc, _, err = run(ENV, probe_with(STEADY), pool_gib=6, pool_cpus=8)
        self.assertEqual(rc, 1)
        self.assertIn('per CPU', err)

    def test_one_number_leaves_the_other_as_in_env(self):
        rc, out, _ = run(ENV, probe_with(STEADY), pool_gib=12)
        self.assertEqual(rc, 0)
        self.assertIn('POOL_CPUS 4.0 -> 4.0', pool_files_line(out))


if __name__ == '__main__':
    unittest.main()
