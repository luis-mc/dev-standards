"""DL362 (R5.62): the kvm-loader compose service, the supervisor's /dev/kvm wait and fallback, and the doctor line."""
import os
import sys
import unittest

from _helpers import make_root  # noqa: F401  (puts the scripts folder on sys.path)

import delivery_runner_pool as pool

TEMPLATES = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'templates', 'runner-pool')
sys.path.insert(0, TEMPLATES)
import pool_supervisor as S  # noqa: E402


def kvm_compose():
    with open(os.path.join(TEMPLATES, 'compose.kvm.yaml'), encoding='utf-8') as f:
        return f.read()


class ComposeText(unittest.TestCase):
    def test_loader_service(self):
        text = kvm_compose()
        loader = text[text.index('  kvm-loader:'):text.index('  pool:')]
        for want in ('image: alpine', 'privileged: true', 'pid: host', 'restart: unless-stopped',
                     'nsenter -t 1 -m -- modprobe kvm_intel', 'nsenter -t 1 -m -- modprobe kvm_amd', 'sleep infinity'):
            self.assertIn(want, loader)

    def test_pool_depends_and_is_not_privileged(self):
        text = kvm_compose()
        pool_part = text[text.index('  pool:'):]
        self.assertIn('kvm-loader:', pool_part)
        self.assertIn('depends_on', pool_part)
        self.assertNotIn('privileged', pool_part)
        self.assertIn('device_cgroup_rules', pool_part)
        self.assertNotIn('devices:', pool_part)


class SupervisorWait(unittest.TestCase):
    def setUp(self):
        del S._KVM_WAITED[:]

    def test_waits_then_finds(self):
        gids, now, logs = iter([None, None, 108]), [0], []
        gid = S.wait_for_kvm(lambda: next(gids), sleep=lambda n: now.__setitem__(0, now[0] + n), clock=lambda: now[0], log=logs.append)
        self.assertEqual(gid, 108)
        self.assertEqual(logs, [])

    def test_gives_up_after_120_seconds_with_one_line(self):
        now, logs = [0], []
        gid = S.wait_for_kvm(lambda: None, sleep=lambda n: now.__setitem__(0, now[0] + n), clock=lambda: now[0], log=logs.append)
        self.assertIsNone(gid)
        self.assertGreaterEqual(now[0], 120)
        self.assertEqual(logs, ['pool: /dev/kvm missing after 120 s; starting without KVM'])

    def test_prepare_kvm_still_starts_the_runner(self):
        now = [0]
        orig = S.wait_for_kvm
        S.wait_for_kvm = lambda gid_of, log=None, **kw: orig(gid_of, sleep=lambda n: now.__setitem__(0, now[0] + n), clock=lambda: now[0], log=lambda m: None)
        try:
            self.assertTrue(S.prepare_kvm({'user': 'r-a'}, {'POOL_KVM': '1'}, run=lambda a: None, gid_of=lambda: None))
        finally:
            S.wait_for_kvm = orig

    def test_waits_once_per_start(self):
        calls = []
        now = [0]
        S.wait_for_kvm(lambda: None, sleep=lambda n: now.__setitem__(0, now[0] + n), clock=lambda: now[0], log=lambda m: None)
        before = now[0]
        S.wait_for_kvm(lambda: calls.append(1), sleep=lambda n: now.__setitem__(0, now[0] + 1000), clock=lambda: now[0], log=lambda m: None)
        self.assertEqual(now[0], before)


class DoctorLine(unittest.TestCase):
    def run_check(self, kvm_text):
        class P(pool.Probe):
            platform = 'win32'

            def read_text(self, path):
                return kvm_text if path.endswith('compose.kvm.yaml') else None

            def isfile(self, path):
                return True

            def sh(self, argv, input=None, timeout=60):
                return (0, '')
        out = []
        pool._kvm_checks(lambda n, s, d: out.append((n, s, d)), P(), 'main',
                         {'POOL_KVM': '1', 'COMPOSE_FILE': pool.KVM_COMPOSE}, 'dir', [])
        return {n: (s, d) for n, s, d in out}

    def test_warns_without_loader(self):
        got = self.run_check('services:\n  pool:\n    devices: []\n')
        self.assertEqual(got['kvm-loader'][0], 'warn')

    def test_ok_with_loader(self):
        self.assertEqual(self.run_check(kvm_compose())['kvm-loader'][0], 'ok')


if __name__ == '__main__':
    unittest.main()
