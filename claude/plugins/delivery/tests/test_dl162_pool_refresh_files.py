"""DL162: pool-refresh copies the plugin's current pool files and says what the build really did.
Temp pool dir, fake probe, fake docker; no Docker."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from _helpers import make_root  # noqa: F401  (sets sys.path to the scripts folder)
import delivery_runner_pool as P
from test_runner_pool import FakeProbe


class Probe(FakeProbe):
    """Fake docker: the running container uses image `run_id`; the tag points at `tag_id`."""
    run_id = 'sha256:aaa'
    tag_id = 'sha256:aaa'

    def sh(self, argv, input=None, timeout=60):
        if argv[:2] == ['docker', 'inspect']:
            return 0, self.run_id + '\n'
        if argv[:3] == ['docker', 'image', 'inspect']:
            return 0, self.tag_id + '\n'
        return super().sh(argv, input, timeout)


class FilesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.pool = os.path.join(self.tmp.name, 'pools', 'main')
        os.makedirs(self.pool)
        mock.patch.object(P, 'pool_dir', lambda pool: self.pool).start()
        self.addCleanup(mock.patch.stopall)
        self.addCleanup(self.tmp.cleanup)
        P.copy_pool_templates(self.pool)
        Path(self.pool, '.env').write_text('POOL_MEM=8g\nPOOL_CPUS=4\nPOOL_BROWSERS=none\nRUNNER_SHA256=%s\nPLAYWRIGHT_VERSION=%s\n'
                                           % ('c' * 64, P.PLAYWRIGHT_VERSION))
        Path(self.pool, 'agents.json').write_text('{"agents": []}')
        Path(self.pool, 'db-admin.pw').write_text('secret')
        self.stale()
        self.repo = os.path.join(self.tmp.name, 'app')
        os.makedirs(os.path.join(self.repo, '.delivery'))

    def stale(self):
        Path(self.pool, 'Dockerfile').write_text('FROM old\n')

    def plan(self, probe=None):
        return P.refresh_plan(probe or Probe(), 'main', [self.repo])

    def run_refresh(self, probe, busy=False):
        ex = P.Executor(probe)
        calls = []
        run = lambda argv, **k: calls.append(argv) or type('R', (), {'returncode': 0, 'stderr': ''})()  # noqa: E731
        with mock.patch.object(ex, 'runners_busy', lambda: busy), mock.patch.object(P.subprocess, 'run', run):
            ok, text = ex.refresh(self.plan(probe))
        return ok, text, calls

    def test_plan_lists_stale_dockerfile_only(self):
        self.assertEqual(self.plan()['files'], ['Dockerfile'])

    def test_crlf_is_not_a_difference(self):
        data = Path(P.TEMPLATES, 'Dockerfile').read_bytes().replace(b'\r\n', b'\n').replace(b'\n', b'\r\n')
        Path(self.pool, 'Dockerfile').write_bytes(data)
        self.assertEqual(self.plan()['files'], [])

    def test_yes_backs_up_copies_and_keeps_state_files(self):
        ok, text, _ = self.run_refresh(Probe())
        self.assertTrue(ok, text)
        self.assertEqual(Path(self.pool, 'Dockerfile').read_bytes(), Path(P.TEMPLATES, 'Dockerfile').read_bytes())
        baks = [d for d in os.listdir(self.pool) if d.startswith('bak-')]
        self.assertEqual(len(baks), 1)
        self.assertEqual(Path(self.pool, baks[0], 'Dockerfile').read_text(), 'FROM old\n')
        self.assertEqual(os.listdir(os.path.join(self.pool, baks[0])), ['Dockerfile'])
        self.assertEqual(Path(self.pool, 'agents.json').read_text(), '{"agents": []}')
        self.assertEqual(Path(self.pool, 'db-admin.pw').read_text(), 'secret')
        self.assertIn('POOL_MEM=8g', Path(self.pool, '.env').read_text())

    def test_unchanged_image_is_said_plainly(self):
        ok, text, calls = self.run_refresh(Probe())
        self.assertIn('image unchanged', text)
        self.assertNotIn('was rebuilt', text)
        self.assertEqual(calls, [['docker', 'compose', 'up', '-d', '--build']])

    def test_changed_image_recreates_the_container(self):
        p = Probe()
        p.tag_id = 'sha256:bbb'
        ok, text, calls = self.run_refresh(p)
        self.assertIn('container recreated', text)
        self.assertIn(['docker', 'compose', 'up', '-d', '--no-build', '--force-recreate', 'pool'], calls)

    def test_busy_runner_blocks_the_recreate(self):
        p = Probe()
        p.tag_id = 'sha256:bbb'
        ex = P.Executor(p)
        calls = []
        run = lambda argv, **k: calls.append(argv) or type('R', (), {'returncode': 0, 'stderr': ''})()  # noqa: E731
        rp = dict(self.plan(p), repos=['owner/example-app'])
        with mock.patch.object(P, 'rebuild_gate', lambda *a: (True, '')), \
                mock.patch.object(ex, 'runners_busy', lambda: True), mock.patch.object(P.subprocess, 'run', run):
            ok, text = ex.refresh(rp)
        self.assertTrue(ok, text)
        self.assertIn('not recreated', text)
        self.assertNotIn(['docker', 'compose', 'up', '-d', '--no-build', '--force-recreate', 'pool'], calls)

    def test_doctor_warns_on_stale_file(self):
        import delivery_doctor as D
        items = D._pool_files_items(P, os.path.dirname(os.path.dirname(self.pool)))
        self.assertEqual([(i['id'], i['status']) for i in items], [('pool.main.files-current', 'warn')])
        self.assertIn('pool-refresh --yes', items[0]['detail'])


if __name__ == '__main__':
    unittest.main()
