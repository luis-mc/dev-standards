"""DL194: a shared (world-writable) tool cache works for every agent user."""
import contextlib
import hashlib
import io
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

DELIVERY = Path(__file__).resolve().parent.parent / "templates" / "shared" / "scripts" / "delivery"
sys.path.insert(0, str(DELIVERY))
import ci_tool  # noqa: E402

POSIX = os.name != "nt"
DATA = b"tool-bytes"
SHA = hashlib.sha256(DATA).hexdigest()


def fake_download(url, partial):
    Path(partial).write_bytes(DATA)


@unittest.skipUnless(POSIX, "POSIX modes")
class SharedCache(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.cache = self.tmp / "ci-tools"
        self.cache.mkdir()
        os.chmod(self.cache, 0o1777)
        self.old = dict(os.environ)
        os.environ["CI_TOOLS_DIR"] = str(self.cache)
        os.environ["HOME"] = str(self.tmp / "home")
        os.environ["CI_TOOL_RETRY_DELAY"] = "0"
        ci_tool._FALLBACK = None
        self.old_umask = os.umask(0o077)

    def tearDown(self):
        os.umask(self.old_umask)
        ci_tool._FALLBACK = None
        os.environ.clear()
        os.environ.update(self.old)

    def test_new_folders_have_shared_mode(self):
        with mock.patch.object(ci_tool, "_download", fake_download):
            p = ci_tool.fetch("http://x/f", SHA, "tool/1.0/f")
        self.assertEqual(p.read_bytes(), DATA)
        for d in (self.cache / "tool", self.cache / "tool" / "1.0"):
            self.assertEqual(d.stat().st_mode & 0o777, 0o777, d)

    def test_unwritable_version_folder_falls_back(self):
        folder = self.cache / "tool" / "1.0"
        folder.mkdir(parents=True)
        real = os.access
        shared = folder.resolve()

        def fake_access(path, mode, *a, **k):
            if Path(path).resolve() == shared:
                return False
            return real(path, mode, *a, **k)

        err = io.StringIO()
        with mock.patch.object(ci_tool, "_download", fake_download), \
                mock.patch.object(os, "access", fake_access), contextlib.redirect_stderr(err):
            p = ci_tool.fetch("http://x/f", SHA, "tool/1.0/f")
        self.assertEqual(p.read_bytes(), DATA)
        self.assertIn(str(self.tmp / "home"), str(p))
        self.assertIn("per-user cache", err.getvalue())

    def test_existing_good_file_is_used_without_write(self):
        folder = self.cache / "tool" / "1.0"
        folder.mkdir(parents=True)
        (folder / "f").write_bytes(DATA)
        calls = []
        with mock.patch.object(ci_tool, "_download", lambda u, p: calls.append(u)):
            p = ci_tool.fetch("http://x/f", SHA, "tool/1.0/f")
        self.assertEqual(p, (folder / "f").resolve())
        self.assertEqual(calls, [])

    def test_racing_fetches_end_with_one_good_file(self):
        results = []

        def slow(url, partial):
            time.sleep(0.3)
            Path(partial).write_bytes(DATA)

        # Two threads share one pid, so give each its own partial via patched getpid.
        ids = iter([1001, 1002])
        lock = threading.Lock()

        def run():
            with lock:
                pid = next(ids)
            with mock.patch.object(os, "getpid", return_value=pid):
                results.append(ci_tool.fetch("http://x/f", SHA, "tool/1.0/f"))

        with mock.patch.object(ci_tool, "_download", slow):
            ts = [threading.Thread(target=run) for _ in range(2)]
            [t.start() for t in ts]
            [t.join(10) for t in ts]
        self.assertEqual(len(results), 2)
        files = sorted(x.name for x in (self.cache / "tool" / "1.0").iterdir())
        self.assertEqual(files, ["f"])
        self.assertEqual((self.cache / "tool" / "1.0" / "f").read_bytes(), DATA)

    def test_private_cache_keeps_default_modes(self):
        priv = self.tmp / "private"
        priv.mkdir()
        os.chmod(priv, 0o755)
        os.environ["CI_TOOLS_DIR"] = str(priv)
        with mock.patch.object(ci_tool, "_download", fake_download):
            ci_tool.fetch("http://x/f", SHA, "tool/1.0/f")
        self.assertNotEqual((priv / "tool").stat().st_mode & 0o777, 0o777)


if __name__ == "__main__":
    unittest.main()
