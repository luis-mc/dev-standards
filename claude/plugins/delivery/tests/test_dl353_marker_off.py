"""DL353 (D301): the ci-wait marker is written only when the project has the Option 4 fallback on."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'scripts'))
import runner_load_gate as G  # noqa: E402

ON = {'ci': {'fallback': {'after_min': 5, 'options': {'linux': 'cloud'}}}}


def _root(cfg):
    d = tempfile.mkdtemp()
    os.makedirs(os.path.join(d, '.git'))
    if cfg is not None:
        os.makedirs(os.path.join(d, '.delivery'))
        with open(os.path.join(d, '.delivery', 'config.json'), 'w') as f:
            f.write(cfg if isinstance(cfg, str) else json.dumps(cfg))
    return d


def _marker(root, lines):
    env = {'GITHUB_SHA': 'abc', 'GITHUB_JOB': 'unit', 'DELIVERY_MARKER_ROOT': root}
    with mock.patch.dict(os.environ, env, clear=False):
        return G.Marker(env=env, log=lines.append)


def _boom(*a, **k):
    raise AssertionError('git must not run: %r' % (a,))


class MarkerOff(unittest.TestCase):
    def _off(self, cfg):
        lines = []
        with mock.patch.object(subprocess, 'run', _boom), mock.patch.object(subprocess, 'Popen', _boom):
            m = _marker(_root(cfg), lines)
            m.start()
            m.stop()
            self.assertFalse(m.claim_lost())
        self.assertIsNone(m.mod)
        self.assertIn('fallback off', m.skipped)
        self.assertEqual(lines, ['runner gate: no ci-wait marker written: ' + m.skipped])

    def test_config_without_fallback(self):
        self._off({'ci': {}})

    def test_missing_config(self):
        self._off(None)

    def test_unreadable_config(self):
        self._off('{not json')

    def test_fallback_without_after_min(self):
        self._off({'ci': {'fallback': {'options': {'linux': 'cloud'}}}})

    def test_fallback_on_runs_marker_path(self):
        lines = []
        m = _marker(_root(ON), lines)
        self.assertIsNotNone(m.mod)
        self.assertEqual(m.skipped, '')
        with mock.patch.object(m.mod, 'mark_wait', return_value=True) as mw:
            m.start()
        mw.assert_called_once()
        self.assertTrue(m.on)


if __name__ == '__main__':
    unittest.main()
