"""DL369 (R5.65): no devices mapping in compose.kvm.yaml; the supervisor makes /dev/kvm itself from /proc/misc."""
import os
import stat
import sys
import unittest

from _helpers import make_root  # noqa: F401  (puts the scripts folder on sys.path)

TEMPLATES = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'templates', 'runner-pool')
sys.path.insert(0, TEMPLATES)
import pool_supervisor as S  # noqa: E402

MISC = '  1 psaux\n232 kvm\n237 loop-control\n'


class Compose(unittest.TestCase):
    def test_rule_not_mapping(self):
        with open(os.path.join(TEMPLATES, 'compose.kvm.yaml'), encoding='utf-8') as f:
            text = f.read()
        self.assertIn("'c 10:232 rwm'", text)
        self.assertNotRegex(text, r'(?m)^\s*devices:')
        self.assertNotIn('/dev/kvm:/dev/kvm', text)


class ProcMisc(unittest.TestCase):
    def test_present(self):
        self.assertTrue(S.host_has_kvm(read=lambda: MISC))

    def test_absent(self):
        self.assertFalse(S.host_has_kvm(read=lambda: '  1 psaux\n'))

    def test_unreadable(self):
        def boom():
            raise OSError('no /proc/misc')
        self.assertFalse(S.host_has_kvm(read=boom))


class Node(unittest.TestCase):
    def run_it(self, host, exists_now):
        calls = []
        ok = S.ensure_kvm_node(host_has=lambda: host, exists=lambda p: exists_now,
                               mknod=lambda *a: calls.append(('mknod',) + a),
                               chown=lambda *a: calls.append(('chown',) + a), makedev=lambda a, b: (a << 8) | b,
                               group_gid=lambda: 108, log=lambda m: None)
        return ok, calls

    def test_makes_node_when_host_has_it(self):
        ok, calls = self.run_it(True, False)
        self.assertTrue(ok)
        self.assertEqual(calls[0], ('mknod', '/dev/kvm', stat.S_IFCHR | 0o660, (10 << 8) | 232))
        self.assertEqual(calls[1], ('chown', '/dev/kvm', 0, 108))

    def test_nothing_when_host_lacks_it(self):
        self.assertEqual(self.run_it(False, False), (False, []))

    def test_nothing_when_node_exists(self):
        self.assertEqual(self.run_it(True, True), (True, []))

    def test_mknod_failure_is_logged_not_raised(self):
        logs = []

        def boom(*a):
            raise PermissionError('denied')
        ok = S.ensure_kvm_node(host_has=lambda: True, exists=lambda p: False, mknod=boom, log=logs.append)
        self.assertFalse(ok)
        self.assertEqual(len(logs), 1)


class Wait(unittest.TestCase):
    def setUp(self):
        del S._KVM_WAITED[:]

    def test_node_made_on_a_later_poll_ends_the_wait(self):
        state = {'gid': None, 'polls': 0}
        now = [0]

        def make():
            state['polls'] += 1
            if state['polls'] == 3:
                state['gid'] = 108
        gid = S.wait_for_kvm(lambda: state['gid'], sleep=lambda n: now.__setitem__(0, now[0] + n),
                             clock=lambda: now[0], log=lambda m: None, make_node=make)
        self.assertEqual(gid, 108)
        self.assertLess(now[0], 120)

    def test_still_bounded_at_120(self):
        now, logs = [0], []
        gid = S.wait_for_kvm(lambda: None, sleep=lambda n: now.__setitem__(0, now[0] + n), clock=lambda: now[0],
                             log=logs.append, make_node=lambda: None)
        self.assertIsNone(gid)
        self.assertEqual(logs, ['pool: /dev/kvm missing after 120 s; starting without KVM'])


if __name__ == '__main__':
    unittest.main()
