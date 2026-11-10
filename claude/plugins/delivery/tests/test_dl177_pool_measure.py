"""DL177: pool sizing measures the WSL VM (working set vs private bytes vs container use), reads Docker through the
Windows CLI first, judges 'fits' against the host-load sample too, and names sizes that pass. Fake probe and shell."""
import argparse
import unittest
from contextlib import redirect_stdout, redirect_stderr
from io import StringIO
from unittest import mock

from _helpers import make_root  # noqa: F401  (sets sys.path to the scripts folder)
import delivery_ci_setup as S
import delivery_runner_pool as P
from test_runner_pool import FILES, FakeProbe

GIB = 2 ** 30
PS = '\n'


class WinShell(P.Probe):
    """A Windows probe whose shell is a table: argv prefix -> (rc, text) or None (cannot run)."""
    platform = 'win32'

    def __init__(self, table):
        self.table, self.calls = table, []

    def sh(self, argv, input=None, timeout=60):
        self.calls.append(list(argv))
        for prefix, result in self.table:
            if list(argv[:len(prefix)]) == list(prefix):
                return result
        return None


PS_CALL = ['powershell']
DOCKER_PS = 'pool-main-runner\tyes\t\npool-main-db\t\tpool-main\nother-box\t\t\n'
STATS = 'pool-main-runner\t2GiB / 12GiB\npool-main-db\t512MiB / 12GiB\nother-box\t1.5GiB / 12GiB\n'


class VmReadTests(unittest.TestCase):
    def test_private_bytes_beat_a_trimmed_working_set(self):
        pr = WinShell([(PS_CALL, (0, '%d\n%d\n' % (5.7 * GIB, 9.8 * GIB)))])
        self.assertEqual(pr.wsl_vm_parts(), (5.7, 9.8))
        self.assertEqual(pr.wsl_vm_gib(), 9.8)

    def test_working_set_wins_when_larger(self):
        pr = WinShell([(PS_CALL, (0, '%d\n%d\n' % (11.9 * GIB, 9.4 * GIB)))])
        self.assertEqual(pr.wsl_vm_gib(), 11.9)

    def test_no_vm_reads_zero(self):
        self.assertEqual(WinShell([(PS_CALL, (0, ''))]).wsl_vm_gib(), 0.0)
        self.assertEqual(WinShell([]).wsl_vm_gib(), 0.0)

    def test_linux_has_no_vm(self):
        self.assertEqual(FakeProbe({}).wsl_vm_gib(), 0.0)


class DockerReadTests(unittest.TestCase):
    def test_container_use_through_the_windows_cli(self):
        pr = WinShell([(['docker', 'ps'], (0, DOCKER_PS)), (['docker', 'stats'], (0, STATS))])
        got = pr.container_gib()
        self.assertEqual((got['pool'], got['other'], got['others']), (2.5, 1.5, ['other-box']))
        self.assertFalse(any(c[0] == 'wsl' for c in pr.calls))

    def test_container_use_falls_back_to_wsl(self):
        pr = WinShell([(['docker', 'ps'], None), (['docker', 'stats'], None),
                       (['wsl', 'docker', 'ps'], (0, DOCKER_PS)), (['wsl', 'docker', 'stats'], (0, STATS))])
        got = pr.container_gib()
        self.assertEqual((got['pool'], got['other']), (2.5, 1.5))

    def test_docker_cpus_cli_then_wsl_then_none(self):
        self.assertEqual(WinShell([(['docker', 'info'], (0, '20\n'))]).docker_cpus(), 20)
        self.assertEqual(WinShell([(['docker', 'info'], None), (['wsl', 'docker', 'info'], (0, '12\n'))]).docker_cpus(), 12)
        self.assertEqual(WinShell([(['docker', 'info'], None), (['wsl', 'docker', 'info'],
                                   (1, 'The command docker could not be found in this WSL 2 distro'))]).docker_cpus(), None)

    def test_docker_missing_on_both_reads_zero(self):
        pr = WinShell([])
        self.assertEqual(pr.container_gib(), {'pool': 0.0, 'other': 0.0, 'others': []})
        self.assertIsNone(pr.docker_cpus())

    def test_linux_never_calls_wsl(self):
        pr = FakeProbe({})
        pr.container_gib()
        pr.docker_cpus()
        self.assertFalse(any(c[0][0] == 'wsl' for c in pr.calls))


def host_probe(used=19.0, vm=9.0, containers=(0.0, 0.0), load=(None, None), total=31.7):
    pr = FakeProbe(dict(FILES, **{'C:/Users/u1/.wslconfig': '[wsl2]\nmemory=12GB\nprocessors=6\n'}))
    pr.memory_gib = lambda: (total, used)
    pr.wsl_vm_gib = lambda: vm
    pr.container_gib = lambda: {'pool': containers[0], 'other': containers[1], 'others': ['x'] if containers[1] else []}
    pr.host_load = lambda: load
    pr.cpu_count = lambda: 20
    return pr


class HostTests(unittest.TestCase):
    def test_vm_is_never_less_than_container_use(self):
        h = P.detect_host(host_probe(used=19.0, vm=5.7, containers=(6.0, 3.0)), samples=3, gap=0)
        self.assertEqual(h['wsl_vm_gib'], 9.0)
        self.assertEqual(h['used_gib'], 10.0)  # 19 - 9

    def test_trimmed_and_steady_vm_give_the_same_room(self):
        a = P.detect_host(host_probe(used=19.0, vm=9.8), samples=3, gap=0)
        b = P.detect_host(host_probe(used=19.0, vm=9.8), samples=3, gap=0)
        self.assertEqual(a['used_gib'], b['used_gib'])

    def test_fresh_host_load_larger_than_median_decides(self):
        h = P.detect_host(host_probe(load=({'mem': 80.0, 'cpu': 10.0}, 5.0)), samples=3, gap=0)
        self.assertEqual(h['used_decided_by'], 'host-load file')
        self.assertEqual(h['load_file'], 'fresh')
        self.assertEqual(h['used_gib'], round(31.7 * 0.8 - 9.0, 1))

    def test_fresh_host_load_smaller_leaves_the_median(self):
        h = P.detect_host(host_probe(load=({'mem': 40.0, 'cpu': 10.0}, 5.0)), samples=3, gap=0)
        self.assertEqual(h['used_decided_by'], 'median')
        self.assertEqual(h['used_gib'], 10.0)

    def test_stale_host_load_is_ignored(self):
        h = P.detect_host(host_probe(load=({'mem': 95.0, 'cpu': 10.0}, 600.0)), samples=3, gap=0)
        self.assertEqual((h['load_file'], h['used_decided_by'], h['used_gib']), ('stale', 'median', 10.0))

    def test_missing_host_load_uses_samples_alone(self):
        h = P.detect_host(host_probe(), samples=3, gap=0)
        self.assertEqual((h['load_file'], h['used_decided_by'], h['used_gib']), ('missing', 'median', 10.0))


class MessageTests(unittest.TestCase):
    def test_memory_per_cpu_names_the_nearest_sizes(self):
        found = {'host': {'total_gib': 31.7, 'cpus': 20}, 'wsl': {'memory': 14}}
        cap = P.measured_sizing(found, used_gib=8.0)
        got = P.owner_target(cap, found, pool_gib=10, pool_cpus=7)
        self.assertFalse(got['ok'])
        self.assertIn('10 GiB fits 6 CPUs; 7 CPUs needs 10.5 GiB', got['message'])

    def test_sizing_line_shows_the_figures_and_who_decided(self):
        pr = host_probe(load=({'mem': 80.0, 'cpu': 1.0}, 5.0))
        args = argparse.Namespace(action='pool-plan', repos='owner/example-app', windows_repos=None, pool='main', total_gib=None,
                                  used_gib=None, cpus=None, docker_gib=None, largest_shard_gib=None, yes=False,
                                  yes_delete=None, resize=False, shrink=False, pool_gib=None, pool_cpus=None, browsers=None,
                                  playwright=None, drop_layer=None, drop_apt=None)
        out = StringIO()
        with mock.patch.object(P, 'Probe', lambda: pr), mock.patch.object(P, 'read_pool_env', lambda p, n: {}), \
                redirect_stdout(out), redirect_stderr(StringIO()):
            S.cmd_pool(args, make_root().as_posix())
        text = out.getvalue()
        self.assertIn('WSL VM 9.0 GiB', text)
        self.assertIn('host-load file fresh', text)
        self.assertIn('decided by: host-load file', text)


if __name__ == '__main__':
    unittest.main()
