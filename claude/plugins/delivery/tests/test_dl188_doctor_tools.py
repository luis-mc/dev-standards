"""DL188: the doctor finds cached tools, reads both tools.json shapes, names real commands, checks scripts, shows wait_min."""
import json
import os
import re
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from _helpers import make_root
import delivery_doctor as D

HERE = Path(__file__).resolve().parent
TEMPLATES = HERE.parent / "templates" / "shared" / "scripts" / "delivery"
SHA = "b" * 64


def project(pins, track="rust", toolchain='[toolchain]\nchannel = "1.90.0"\ntargets = []\n'):
    root = make_root({})
    d = Path(root, "scripts", "delivery")
    d.mkdir(parents=True)
    (d / "gate.json").write_text(json.dumps({"track": track}))
    (d / "tools.json").write_text(json.dumps(pins))
    Path(root, "rust-toolchain.toml").write_text(toolchain)
    return root


def plat_pin(plats, **extra):
    return {"version": "1.0", "platforms": {p: dict({"url": "https://x.example/t", "sha256": SHA}, **extra) for p in plats}}


class Base(unittest.TestCase):
    def setUp(self):
        self.cache = tempfile.mkdtemp(prefix="cache-")
        p = mock.patch.dict(os.environ, {"CI_TOOLS_DIR": self.cache, "PATH": ""})
        p.start()
        self.addCleanup(p.stop)
        self.addCleanup(shutil.rmtree, self.cache, True)


class CacheLayout(Base):
    def test_linux_shape_found(self):
        root = project({"zig": plat_pin(["linux_x64"], bin_dir="zig-linux-x86_64-0.14.0")})
        with mock.patch.object(D, "_ci_tool_module") as m:
            ct = m.return_value
            ct.current_platform.return_value = "linux_x64"
            ct.cached_tool.side_effect = lambda *a, **k: None
            self.assertFalse(D._cached("zig", root))
        exe = Path(self.cache, "zig", "1.0", "unpacked-linux_x64", "zig-linux-x86_64-0.14.0", "zig")
        exe.parent.mkdir(parents=True)
        exe.write_text("x")
        with mock.patch("sys.platform", "linux"), mock.patch("platform.machine", return_value="x86_64"):
            self.assertTrue(D._cached("zig", root))

    def test_windows_shape_found_two_levels_deep(self):
        root = project({"llvm": plat_pin(["windows_x64"], bin_dir="LLVM-18.1.8-win64/bin")})
        exe = Path(self.cache, "llvm", "1.0", "unpacked-windows_x64", "LLVM-18.1.8-win64", "bin", "clang-cl.exe")
        exe.parent.mkdir(parents=True)
        exe.write_text("x")
        with mock.patch("sys.platform", "win32"), mock.patch("platform.machine", return_value="AMD64"):
            self.assertTrue(D._cached("clang-cl", root))
            self.assertFalse(D._cached("lld-link", root))

    def test_file_kind(self):
        root = project({"zig": dict(plat_pin(["linux_x64"], kind="file", bin="zig"))})
        exe = Path(self.cache, "zig", "1.0", "linux_x64-zig")
        exe.parent.mkdir(parents=True)
        exe.write_text("x")
        with mock.patch("sys.platform", "linux"), mock.patch("platform.machine", return_value="x86_64"):
            self.assertTrue(D._cached("zig", root))


class Pins(Base):
    NEEDED = ("rustup-init", "llvm", "zig", "cargo-deny")

    def run_pins(self, pins, targets):
        tc = '[toolchain]\nchannel = "1.90.0"\ntargets = [%s]\n' % ", ".join('"%s"' % t for t in targets)
        root = project(pins, toolchain=tc)
        with mock.patch("sys.platform", "linux"), mock.patch("platform.machine", return_value="x86_64"):
            return {i["id"]: i for i in D.rust_items(root)}["rust.pins"]

    def test_flat_and_platforms_pass(self):
        flat = {n: {"version": "1", "sha256": SHA} for n in self.NEEDED}
        self.assertEqual(self.run_pins(flat, [])["status"], "ok")
        both = {n: plat_pin(["linux_x64", "windows_x64"]) for n in self.NEEDED}
        self.assertEqual(self.run_pins(both, ["x86_64-pc-windows-msvc"])["status"], "ok")

    def test_missing_platform_is_named(self):
        pins = {n: plat_pin(["linux_x64"]) for n in self.NEEDED}
        item = self.run_pins(pins, ["x86_64-pc-windows-msvc"])
        self.assertEqual(item["status"], "fail")
        self.assertIn("zig (platform windows_x64)", item["detail"])

    def test_no_pin_at_all(self):
        pins = {n: plat_pin(["linux_x64"]) for n in self.NEEDED[:3]}
        self.assertIn("cargo-deny (no entry)", self.run_pins(pins, [])["detail"])


class FixText(unittest.TestCase):
    def test_every_ci_tool_subcommand_is_real(self):
        real = set(re.findall(r'sub\.add_parser\("([\w-]+)"', (TEMPLATES / "ci_tool.py").read_text(encoding="utf-8")))
        self.assertTrue({"fetch", "tool", "gitleaks"} <= real)
        text = Path(D.__file__).read_text(encoding="utf-8")
        used = re.findall(r"ci_tool\.py (\w+)", text)
        self.assertTrue(used)
        for sub in used:
            self.assertIn(sub, real, "doctor text names ci_tool.py %s" % sub)


class ScriptsCurrent(Base):
    def setUp(self):
        super().setUp()
        self.root = make_root({})
        self.d = Path(self.root, "scripts", "delivery")
        self.d.mkdir(parents=True)
        shutil.copyfile(TEMPLATES / "ci_tool.py", self.d / "ci_tool.py")
        self.tpl = [n for n in os.listdir(TEMPLATES) if n != "CONTRACT.md" and (TEMPLATES / n).is_file()]

    def status(self):
        # only ci_tool.py is installed: filter the rest out by marking them kept
        (self.d / "ci-install.json").write_text(json.dumps({"keep": [
            "scripts/delivery/%s" % n for n in self.tpl if n != "ci_tool.py"] + self.extra_keep}))
        return {i["id"]: i for i in D.scripts_items(self.root)}["ci.scripts-current"]

    extra_keep = []

    def test_matching_is_ok(self):
        self.assertEqual(self.status()["status"], "warn")  # the other templates are missing: written
        for n in self.tpl:
            shutil.copyfile(TEMPLATES / n, self.d / n)
        self.assertEqual(self.status()["status"], "ok")

    def test_stale_warns_with_file_and_command(self):
        for n in self.tpl:
            shutil.copyfile(TEMPLATES / n, self.d / n)
        (self.d / "ci_tool.py").write_text("# old\n")
        item = self.status()
        self.assertEqual(item["status"], "warn")
        self.assertIn("scripts/delivery/ci_tool.py", item["detail"])
        self.assertIn("delivery_ci_install.py update", item["detail"])
        self.assertIn("ci-install.json", item["detail"])

    def test_edited_file_kept_on_purpose_is_ok(self):
        for n in self.tpl:
            shutil.copyfile(TEMPLATES / n, self.d / n)
        (self.d / "ci_tool.py").write_text("# mine\n")
        self.extra_keep = ["scripts/delivery/ci_tool.py"]
        try:
            item = self.status()
        finally:
            self.extra_keep = []
        self.assertEqual(item["status"], "ok")
        self.assertIn("kept on purpose", item["detail"])

    def test_row_never_fails(self):
        (self.d / "ci_tool.py").write_text("# old\n")
        ok, detail, items = D.check_scripts(self.root, {})
        self.assertTrue(ok)
        self.assertIn("ci.scripts-current", detail)


class WaitMin(unittest.TestCase):
    def cfg(self, wait):
        ci = {"options": {"linux": "self-hosted"}}
        if wait is not None:
            ci["wait_min"] = wait
        return {"ci": ci, "runners": [{"name": "r1", "os": "linux", "labels": ["self-hosted", "linux"]}]}

    def test_configured_value_shown(self):
        self.assertEqual(D._wait_min(self.cfg(30)), 30)
        self.assertIn("waits more than 30 min", D._second_machine_note(self.cfg(30), "linux"))

    def test_default_is_ten(self):
        self.assertEqual(D._wait_min(self.cfg(None)), 10)
        self.assertEqual(D._wait_min(self.cfg("x")), 10)
        self.assertIn("waits more than 10 min", D._second_machine_note(self.cfg(None), "linux"))


if __name__ == "__main__":
    unittest.main()
