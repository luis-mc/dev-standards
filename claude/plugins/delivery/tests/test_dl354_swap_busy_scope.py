"""DL354 (R5.59): a container recreate counts only the runners in the container. Mocked gh and probe; no Docker."""
import json
import unittest
from unittest import mock

from _helpers import make_root  # noqa: F401  (sets sys.path to the scripts folder)
import delivery_runner_pool as P
from test_runner_pool import FakeProbe

REPO = 'owner/example-app'
REG = {'agents': [
    {'slug': 'app1', 'repo': REPO},
    {'name': 'host1-app1', 'os': 'windows', 'kind': 'service', 'repo': REPO},
]}


def runner(name, busy, os_name='Linux', pool_label=True):
    labels = [{'name': 'self-hosted'}] + ([{'name': 'pool-main'}] if pool_label else [])
    return {'id': 1, 'name': name, 'os': os_name, 'busy': busy, 'status': 'online', 'labels': labels}


class Probe(FakeProbe):
    def __init__(self, runners, registry=REG):
        super().__init__()
        self.runners = runners
        self.registry = registry

    def gh_json(self, args):
        if self.runners is None:
            return None, 'gh refused'
        return {'runners': self.runners}, None

    def read_text(self, path):
        if path.endswith('agents.json'):
            return None if self.registry is None else json.dumps(self.registry)
        return None


WIN_BUSY = runner('host1-app1', True, 'Windows')
LIN_BUSY = runner('main-app1', True)
LIN_IDLE = runner('main-app1', False)


class ScopeTests(unittest.TestCase):
    def scan(self, runners, registry=REG):
        return P.scan_pool_runners(Probe(runners, registry), [REPO], 'main')

    def test_busy_windows_service_is_outside(self):
        busy, outside, err, note = self.scan([LIN_IDLE, WIN_BUSY])
        self.assertEqual((busy, err, note), ([], None, ''))
        self.assertEqual(outside, ['host1-app1 (%s)' % REPO])
        self.assertEqual(P.busy_pool_runners(Probe([LIN_IDLE, WIN_BUSY]), [REPO], 'main'), ([], None))
        self.assertEqual(P.scope_text(Probe([LIN_IDLE, WIN_BUSY]), [REPO], 'main'), 'not affected: host1-app1 busy')

    def test_busy_container_runner_still_counts(self):
        busy, outside, _e, _n = self.scan([LIN_BUSY, WIN_BUSY])
        self.assertEqual(busy, ['main-app1 (%s)' % REPO])
        self.assertEqual(outside, ['host1-app1 (%s)' % REPO])

    def test_unreadable_list_is_an_error(self):
        _b, _o, err, _n = self.scan(None)
        self.assertIn('could not read the runners', err)
        ok, msg = P.rebuild_gate(Probe(None), [REPO], 'main')
        self.assertFalse(ok)
        self.assertIn('refused', msg)

    def test_no_registry_falls_back_to_container_names_and_says_so(self):
        busy, outside, _e, note = self.scan([LIN_BUSY, WIN_BUSY], registry=None)
        self.assertEqual(busy, ['main-app1 (%s)' % REPO])
        self.assertEqual(outside, ['host1-app1 (%s)' % REPO])
        self.assertIn('registry is missing', note)
        self.assertIn('registry is missing', P.scope_text(Probe([WIN_BUSY], None), [REPO], 'main'))

    def test_gate_ignores_a_busy_windows_service(self):
        self.assertEqual(P.rebuild_gate(Probe([LIN_IDLE, WIN_BUSY]), [REPO], 'main'), (True, ''))
        ok, msg = P.rebuild_gate(Probe([LIN_BUSY, WIN_BUSY]), [REPO], 'main')
        self.assertFalse(ok)
        self.assertIn('main-app1', msg)
        self.assertNotIn('host1-app1', msg)

    def test_runners_busy_scopes_to_the_container(self):
        def found(runners):
            return {'repos': [{'repo': REPO, 'runners': runners, 'error': None}], 'error': None}
        ex = P.Executor(Probe([]))
        ex.busy_pool = 'main'
        with mock.patch.object(P, 'detect_github', lambda pr: found([
                {'name': 'host1-app1', 'os': 'Windows', 'busy': True}, {'name': 'main-app1', 'os': 'Linux', 'busy': False}])):
            self.assertFalse(ex.runners_busy())
        with mock.patch.object(P, 'detect_github', lambda pr: found([{'name': 'main-app1', 'os': 'Linux', 'busy': True}])):
            self.assertTrue(ex.runners_busy())
        with mock.patch.object(P, 'detect_github', lambda pr: {'repos': [], 'error': 'gh cannot run'}):
            self.assertTrue(ex.runners_busy())


class RecreateTests(unittest.TestCase):
    def recreate(self, runners, force):
        probe = Probe(runners)
        ex = P.Executor(probe)
        rp = {'pool': 'main', 'repos': [REPO]}
        ran = []
        run = lambda argv, **k: ran.append(list(argv)) or mock.Mock(returncode=0, stderr='', stdout='')  # noqa: E731
        with mock.patch.object(P.subprocess, 'run', run), mock.patch.object(P, 'clear_drain', lambda pool: None), \
                mock.patch.object(P.Executor, 'drain', lambda s, pool, t: (True, '')), \
                mock.patch.object(P.Executor, 'kvm_gate', lambda s, pool, env=None: (True, '')):
            ok, text = ex.drain_and_recreate(rp, force, 60)
        return ok, text, ran

    def test_busy_windows_service_does_not_block_and_is_reported(self):
        ok, text, ran = self.recreate([LIN_IDLE, WIN_BUSY], False)
        self.assertTrue(ok, text)
        self.assertIn('not affected: host1-app1 busy', text)
        self.assertTrue(any('--force-recreate' in a for a in ran))

    def test_busy_container_runner_refuses(self):
        ok, text, ran = self.recreate([LIN_BUSY, WIN_BUSY], False)
        self.assertFalse(ok)
        self.assertIn('refused: pool runner busy: main-app1', text)
        self.assertFalse(any('--force-recreate' in a for a in ran))

    def test_force_warning_names_only_container_runners(self):
        ok, text, _ran = self.recreate([LIN_BUSY, WIN_BUSY], True)
        self.assertTrue(ok, text)
        warning = text
        self.assertIn('--force recreates while main-app1 (%s) is busy' % REPO, warning)
        self.assertNotIn('busy; its job may fail. host1', warning)
        self.assertNotIn('while host1-app1', warning)
        self.assertNotIn(', host1-app1', warning.split('may fail')[0])

    def test_unreadable_list_refuses(self):
        ok, text, ran = self.recreate(None, False)
        self.assertFalse(ok)
        self.assertIn('refused', text)
        self.assertFalse(any('--force-recreate' in a for a in ran))


if __name__ == '__main__':
    unittest.main()
