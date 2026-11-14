"""DL329: rust_ci.py links <repo>/target to the target cache folder."""
import contextlib
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

BASE = Path(__file__).resolve().parent.parent / "templates"
sys.path.insert(0, str(BASE / "shared" / "scripts" / "delivery"))
sys.path.insert(0, str(BASE / "rust" / "scripts" / "delivery"))
import rust_ci  # noqa: E402


class TargetLink(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        t = Path(self.tmp.name)
        self.root, self.cache = t / "repo", t / "cache"
        (self.root / ".git" / "info").mkdir(parents=True)
        (self.root / "rust-toolchain.toml").write_text('[toolchain]\nchannel = "1.90.0"\n')
        env = {"RUNNER_NAME": "r1", "CARGO_TARGET_DIR": "", "DELIVERY_NO_TARGET_CACHE": ""}
        p = mock.patch.dict(os.environ, env)
        p.start()
        self.addCleanup(p.stop)
        c = mock.patch.object(rust_ci, "cache_dir", lambda: self.cache)
        c.start()
        self.addCleanup(c.stop)

    def run_env(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            out = rust_ci.target_cache_env(self.root)
        return out, err.getvalue()

    def test_link_created_when_absent(self):
        out, _ = self.run_env()
        link = self.root / "target"
        self.assertTrue(rust_ci._is_link(link))  # a junction on Windows, a symlink elsewhere
        self.assertEqual(link.resolve(), Path(out["CARGO_TARGET_DIR"]).resolve())

    def test_exports_delivery_rust_target(self):
        out, _ = self.run_env()
        self.assertEqual(out["DELIVERY_RUST_TARGET"], out["CARGO_TARGET_DIR"])

    def test_stale_link_replaced(self):
        old = Path(self.tmp.name) / "old"
        old.mkdir()
        rust_ci._make_link(self.root / "target", old)  # junction on Windows: no symlink privilege needed
        out, _ = self.run_env()
        self.assertEqual((self.root / "target").resolve(), Path(out["CARGO_TARGET_DIR"]).resolve())
        self.assertTrue(old.is_dir())

    def test_real_dir_untouched_with_warning(self):
        real = self.root / "target"
        (real / "debug").mkdir(parents=True)
        (real / "debug" / "keep").write_text("x")
        out, err = self.run_env()
        self.assertFalse(rust_ci._is_link(real))
        self.assertTrue((real / "debug" / "keep").exists())
        self.assertIn("is a real folder; bins live in", err)
        self.assertIn("CARGO_TARGET_DIR", out)

    def test_opt_outs_make_no_link(self):
        for k, v in (("DELIVERY_NO_TARGET_CACHE", "1"), ("CARGO_TARGET_DIR", "/somewhere")):
            with mock.patch.dict(os.environ, {k: v}):
                out, _ = self.run_env()
            self.assertEqual(out, {})
            self.assertFalse(os.path.lexists(self.root / "target"))

    def test_link_failure_is_warning(self):
        with mock.patch.object(rust_ci, "_make_link", side_effect=OSError("denied")):
            out, err = self.run_env()
        self.assertIn("could not link", err)
        self.assertIn("CARGO_TARGET_DIR", out)

    def test_windows_uses_junction(self):
        calls = []
        with mock.patch.object(rust_ci.os, "name", "nt"), \
                mock.patch.object(rust_ci.subprocess, "run") as run, \
                mock.patch.dict(sys.modules, {"_winapi": None}):
            run.side_effect = lambda a, **k: calls.append(a) or mock.Mock(returncode=0)
            rust_ci._make_link(self.root / "target", self.cache)
        self.assertEqual(calls[0][:4], ["cmd", "/c", "mklink", "/J"])

    def test_git_exclude_has_target(self):
        self.run_env()
        self.assertIn("/target", (self.root / ".git" / "info" / "exclude").read_text())


if __name__ == "__main__":
    unittest.main()
