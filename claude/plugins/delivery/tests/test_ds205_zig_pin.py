"""DS205: the zig pin comes from a PyPI wheel; ci_tool.py has a `wheel` kind."""
import contextlib
import hashlib
import io
import json
import os
import re
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

DELIVERY = Path(__file__).resolve().parent.parent / "templates" / "shared" / "scripts" / "delivery"
sys.path.insert(0, str(DELIVERY))
import ci_tool  # noqa: E402


class ZigPin(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.old = dict(os.environ)
        os.environ["CI_TOOLS_DIR"] = str(self.tmp / "cache")
        os.environ["CI_TOOL_RETRY_DELAY"] = "0"
        os.environ["CI_TOOLS_JSON"] = str(self.tmp / "pins.json")

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.old)

    def run_cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = ci_tool.main(list(args))
        return code, out.getvalue().strip(), err.getvalue().strip()

    def fake_wheel(self, name="zig"):
        whl = self.tmp / "ziglang-9.9.9-py3-none-any.whl"
        with zipfile.ZipFile(whl, "w") as z:
            info = zipfile.ZipInfo("ziglang/" + name)
            info.external_attr = (0o100755 << 16)
            z.writestr(info, "#!/bin/sh\necho zig\n")
            z.writestr("ziglang/lib/std.zig", "// std\n")
        return whl

    def pin(self, whl, plat="linux_x64", sha=None):
        sha = sha or hashlib.sha256(whl.read_bytes()).hexdigest()
        (self.tmp / "pins.json").write_text(json.dumps({"zig": {"version": "9.9.9", "platforms": {
            plat: {"kind": "wheel", "url": whl.as_uri(), "sha256": sha, "file": "ziglang.whl",
                   "bin_dir": "ziglang", "bin": "zig"}}}}))

    def test_wheel_unpacks_and_keeps_exec_bit(self):
        whl = self.fake_wheel()
        self.pin(whl)
        code, out, err = self.run_cli("tool", "zig", "--platform", "linux_x64")
        self.assertEqual(code, 0, err)
        p = Path(out)
        self.assertEqual(p.name, "zig")
        self.assertTrue(p.is_file())
        if os.name != "nt":
            self.assertTrue(os.access(p, os.X_OK))
        self.assertTrue((p.parent / "lib" / "std.zig").is_file())

    def test_windows_adds_exe(self):
        whl = self.fake_wheel("zig.exe")
        self.pin(whl, "windows_x64")
        code, out, err = self.run_cli("tool", "zig", "--platform", "windows_x64")
        self.assertEqual(code, 0, err)
        self.assertEqual(Path(out).name, "zig.exe")

    def test_bad_sha_fails(self):
        whl = self.fake_wheel()
        self.pin(whl, sha="0" * 64)
        code, _, err = self.run_cli("tool", "zig", "--platform", "linux_x64")
        self.assertEqual(code, 1)
        self.assertIn("zig", err.lower())

    def test_shipped_pin_shape(self):
        data = json.loads((DELIVERY / "tools.json").read_text())
        z = data["zig"]
        self.assertEqual(z["version"], "0.17.1")
        for plat in ("linux_x64", "linux_arm64", "windows_x64", "darwin_x64", "darwin_arm64"):
            e = z["platforms"][plat]
            self.assertEqual(e["kind"], "wheel")
            self.assertTrue(e["url"].startswith("https://files.pythonhosted.org/"))
            self.assertTrue(e["url"].endswith(".whl"))
            self.assertRegex(e["sha256"], r"^[0-9a-f]{64}$")


if __name__ == "__main__":
    unittest.main()
