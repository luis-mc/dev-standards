"""DL189: a kind 'file' tool keeps its exact name in a per-platform folder."""
import contextlib
import hashlib
import io
import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path

DELIVERY = Path(__file__).resolve().parent.parent / "templates" / "shared" / "scripts" / "delivery"
sys.path.insert(0, str(DELIVERY))
import ci_tool  # noqa: E402


class FileName(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.cache = self.tmp / "cache"
        self.old = dict(os.environ)
        os.environ["CI_TOOLS_DIR"] = str(self.cache)
        os.environ["CI_TOOL_RETRY_DELAY"] = "0"
        os.environ["CI_TOOLS_JSON"] = str(self.tmp / "pins.json")
        self.src = self.tmp / "fake-tool-init"
        self.src.write_bytes(b"binary")
        self.sha = hashlib.sha256(b"binary").hexdigest()

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.old)

    def pins(self, plat, kind="file"):
        (self.tmp / "pins.json").write_text(json.dumps({"fake-tool-init": {"version": "1.0.0", "platforms": {
            plat: {"kind": kind, "url": self.src.as_uri(), "sha256": self.sha, "bin": "fake-tool-init"}}}}))

    def run_cli(self, plat):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = ci_tool.main(["tool", "fake-tool-init", "--platform", plat])
        return code, Path(out.getvalue().strip())

    def test_exact_name_in_platform_folder(self):
        self.pins("linux_x64")
        code, path = self.run_cli("linux_x64")
        self.assertEqual(code, 0)
        self.assertEqual(path.name, "fake-tool-init")
        self.assertEqual(path.parent.name, "linux_x64")
        self.assertTrue(os.stat(path).st_mode & stat.S_IXUSR)
        self.assertEqual(path.read_bytes(), b"binary")

    def test_windows_gets_exe(self):
        self.pins("windows_x64")
        _, path = self.run_cli("windows_x64")
        self.assertEqual((path.parent.name, path.name), ("windows_x64", "fake-tool-init.exe"))

    def test_second_call_reuses(self):
        self.pins("linux_x64")
        _, first = self.run_cli("linux_x64")
        mtime = first.stat().st_mtime_ns
        _, second = self.run_cli("linux_x64")
        self.assertEqual((first, mtime), (second, second.stat().st_mtime_ns))
        self.assertFalse(list(self.cache.rglob("*.partial")))

    def test_old_cache_file_ignored(self):
        self.pins("linux_x64")
        _, path = self.run_cli("linux_x64")
        old = path.parent.parent / "linux_x64-fake-tool-init"
        old.write_bytes(b"stale")
        path.unlink()
        _, again = self.run_cli("linux_x64")
        self.assertEqual(again, path)
        self.assertEqual(again.read_bytes(), b"binary")
        self.assertEqual(old.read_bytes(), b"stale")

    def test_dir_flag_points_at_platform_folder(self):
        self.pins("linux_x64")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            ci_tool.main(["tool", "fake-tool-init", "--platform", "linux_x64", "--dir"])
        self.assertEqual(Path(out.getvalue().strip()).name, "linux_x64")


if __name__ == "__main__":
    unittest.main()
