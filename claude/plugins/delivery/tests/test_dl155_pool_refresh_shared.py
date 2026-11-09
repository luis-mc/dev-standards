"""DL155: one pool serves several repos. pool-refresh keeps the layers and Playwright version other repos set.
Fake probe, temp pool .env; no Docker."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from _helpers import make_root  # noqa: F401  (sets sys.path to the scripts folder)
import delivery_runner_pool as P
from test_runner_pool import FakeProbe


def lock(version):
    return json.dumps({'packages': {'node_modules/@playwright/test': {'version': version}}})


class SharedRefreshTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.pool = os.path.join(self.tmp.name, 'pools', 'main')
        os.makedirs(self.pool)
        self.patch = mock.patch.object(P, 'pool_dir', lambda pool: self.pool)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def repo(self, layers=None, pw='1.62.1'):
        d = tempfile.mkdtemp(dir=self.tmp.name)
        os.makedirs(os.path.join(d, '.delivery'))
        if layers is not None:
            Path(d, '.delivery', 'config.json').write_text(json.dumps({'pool': {'layers': layers}}))
        if pw:
            Path(d, 'package-lock.json').write_text(lock(pw))
        return d

    def env(self, text):
        Path(self.pool, '.env').write_text(text)

    def base(self, extra=''):
        return 'POOL_MEM=8g\nPOOL_CPUS=4\nPOOL_BROWSERS=chromium\nRUNNER_SHA256=%s\n' % ('c' * 64) + extra

    def plan(self, repo, **kw):
        source = kw.pop('source', 'owner/app2')
        return P.refresh_plan(FakeProbe(), 'main', [repo], source=source, **kw)

    def test_keeps_the_other_repos_layer(self):
        self.env(self.base('POOL_LAYERS=windows-packaging\nPOOL_LAYER_SOURCES=windows-packaging:owner/app1\n'))
        rp = self.plan(self.repo([]))
        self.assertNotIn('error', rp)
        self.assertNotIn('POOL_LAYERS', rp['changes'])
        self.assertIn('--drop-layer windows-packaging', ' '.join(rp['notes']))

    def test_adds_its_own_layer_and_records_the_source(self):
        self.env(self.base('POOL_LAYERS=\n'))
        rp = self.plan(self.repo(['windows-packaging']))
        self.assertEqual(rp['changes']['POOL_LAYERS'][1], 'windows-packaging')
        self.assertEqual(rp['changes']['POOL_LAYER_SOURCES'][1], 'windows-packaging:owner/app2')

    def test_keeps_old_source_when_both_ask(self):
        self.env(self.base('POOL_LAYERS=windows-packaging\nPOOL_LAYER_SOURCES=windows-packaging:owner/app1\n'))
        rp = self.plan(self.repo(['windows-packaging']))
        self.assertNotIn('POOL_LAYER_SOURCES', rp['changes'])
        self.assertEqual(rp['layers'], [('windows-packaging', 'owner/app1')])

    def test_apt_names_are_merged(self):
        self.env(self.base('POOL_APT=libfoo-dev\n'))
        d = self.repo([])
        Path(d, '.delivery', 'pool.apt').write_text('libbar-dev\n')
        self.assertEqual(self.plan(d)['changes']['POOL_APT'][1], 'libfoo-dev libbar-dev')

    def test_drop_layer_and_drop_apt(self):
        self.env(self.base('POOL_LAYERS=windows-packaging\nPOOL_APT=libfoo-dev libbar-dev\n'
                           'POOL_LAYER_SOURCES=windows-packaging:owner/app1\n'))
        rp = self.plan(self.repo([]), drop_layers=['windows-packaging'], drop_apt=['libfoo-dev'])
        self.assertEqual(rp['changes']['POOL_LAYERS'][1], '')
        self.assertEqual(rp['changes']['POOL_LAYER_SOURCES'][1], '')
        self.assertEqual(rp['changes']['POOL_APT'][1], 'libbar-dev')

    def test_keeps_a_higher_playwright(self):
        self.env(self.base('PLAYWRIGHT_VERSION=1.63.0\n'))
        rp = self.plan(self.repo(pw='1.62.1'))
        self.assertNotIn('PLAYWRIGHT_VERSION', rp['changes'])
        self.assertIn('kept Playwright 1.63.0', ' '.join(rp['notes']))

    def test_raises_playwright(self):
        self.env(self.base('PLAYWRIGHT_VERSION=1.62.1\n'))
        rp = self.plan(self.repo(pw='1.64.0'))
        self.assertEqual(rp['changes']['PLAYWRIGHT_VERSION'], ('1.62.1', '1.64.0'))

    def test_flag_may_lower_playwright(self):
        self.env(self.base('PLAYWRIGHT_VERSION=1.63.0\n'))
        rp = self.plan(self.repo(pw='1.64.0'), playwright_version='1.60.0')
        self.assertEqual(rp['changes']['PLAYWRIGHT_VERSION'], ('1.63.0', '1.60.0'))

    def test_plan_text_names_the_source(self):
        import argparse
        from contextlib import redirect_stdout
        from io import StringIO
        import delivery_ci_setup as S
        self.env(self.base('POOL_LAYERS=windows-packaging\nPOOL_LAYER_SOURCES=windows-packaging:owner/app1\n'))
        d = self.repo([])
        args = argparse.Namespace(pool='main', browsers=None, playwright=None, repos='owner/app2', drop_layer=None,
                                  drop_apt=None, yes=False, force=False)
        out = StringIO()
        with redirect_stdout(out):
            S.cmd_pool_refresh(args, d, P, FakeProbe())
        self.assertIn('windows-packaging (asked by owner/app1)', out.getvalue())
        self.assertIn('--drop-layer', out.getvalue())


if __name__ == '__main__':
    unittest.main()
