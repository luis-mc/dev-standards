"""DS199: ci_tool.py `tool` fetches any pin from tools.json (file, archive, crate)."""
import contextlib
import hashlib
import io
import json
import os
import stat
import sys
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path

DELIVERY = Path(__file__).resolve().parent.parent / "templates" / "shared" / "scripts" / "delivery"
sys.path.insert(0, str(DELIVERY))
import ci_tool  # noqa: E402
import tools_pin  # noqa: E402


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class ToolFetch(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.cache = self.tmp / "cache"
        self.src = self.tmp / "src"
        self.src.mkdir()
        self.old = dict(os.environ)
        os.environ["CI_TOOLS_DIR"] = str(self.cache)
        os.environ["CI_TOOL_RETRY_DELAY"] = "0"
        os.environ["CI_TOOLS_JSON"] = str(self.tmp / "pins.json")

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.old)

    def pins(self, data):
        (self.tmp / "pins.json").write_text(json.dumps(data))

    def run_cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = ci_tool.main(list(args))
        return code, out.getvalue().strip(), err.getvalue().strip()

    def make_tar(self):
        d = self.src / "llvm-1.0" / "bin"
        d.mkdir(parents=True)
        (d / "lld-link").write_text("#!/bin/sh\necho lld\n")
        (d / "clang-cl").write_text("#!/bin/sh\necho clang\n")
        arc = self.src / "llvm.tar.gz"
        with tarfile.open(arc, "w:gz") as t:
            t.add(self.src / "llvm-1.0", arcname="llvm-1.0")
        return arc

    def test_file_kind(self):
        f = self.src / "rustup-init"
        f.write_bytes(b"binary")
        self.pins({"rustup-init": {"version": "1.0.0", "platforms": {"linux_x64": {
            "kind": "file", "url": f.as_uri(), "sha256": sha(f), "bin": "rustup-init"}}}})
        code, out, _ = self.run_cli("tool", "rustup-init", "--platform", "linux_x64")
        self.assertEqual(code, 0)
        self.assertEqual(Path(out).read_bytes(), b"binary")
        self.assertTrue(Path(out).is_relative_to(self.cache.resolve()))
        self.assertTrue(os.stat(out).st_mode & stat.S_IXUSR)

    def test_archive_kind_and_exe(self):
        arc = self.make_tar()
        self.pins({"llvm": {"version": "1.0", "platforms": {"linux_x64": {
            "kind": "archive", "url": arc.as_uri(), "sha256": sha(arc),
            "bin_dir": "llvm-1.0/bin", "bin": "lld-link"}}}})
        code, out, _ = self.run_cli("tool", "llvm", "--platform", "linux_x64")
        self.assertEqual((code, Path(out).name), (0, "lld-link"))
        code, out, _ = self.run_cli("tool", "llvm", "--platform", "linux_x64", "--exe", "clang-cl")
        self.assertEqual((code, Path(out).name), (0, "clang-cl"))
        code, out, _ = self.run_cli("tool", "llvm", "--platform", "linux_x64", "--dir")
        self.assertEqual((code, Path(out).name), (0, "bin"))
        code, _, err = self.run_cli("tool", "llvm", "--platform", "linux_x64", "--exe", "nope")
        self.assertEqual(code, 1)
        self.assertIn("nope", err)

    def test_zip_archive(self):
        arc = self.src / "z.zip"
        with zipfile.ZipFile(arc, "w") as z:
            z.writestr("zig-1/zig.exe", "x")
        self.pins({"zig": {"version": "1", "platforms": {"windows_x64": {
            "kind": "archive", "url": arc.as_uri(), "sha256": sha(arc), "bin_dir": "zig-1", "bin": "zig"}}}})
        code, out, _ = self.run_cli("tool", "zig", "--platform", "windows_x64")
        self.assertEqual((code, Path(out).name), (0, "zig.exe"))

    def test_checksum_mismatch_fails(self):
        arc = self.make_tar()
        self.pins({"llvm": {"version": "1.0", "platforms": {"linux_x64": {
            "url": arc.as_uri(), "sha256": "0" * 64, "bin_dir": "llvm-1.0/bin"}}}})
        os.environ["CI_TOOL_RETRY_DELAY"] = "0"
        code, _, err = self.run_cli("tool", "llvm", "--platform", "linux_x64")
        self.assertEqual(code, 1)
        self.assertIn("checksum mismatch", err)
        self.assertFalse(list(self.cache.rglob("*.partial")))

    def test_unsafe_archive_path_rejected(self):
        arc = self.src / "bad.tar.gz"
        evil = self.src / "evil.txt"
        evil.write_text("x")
        with tarfile.open(arc, "w:gz") as t:
            t.add(evil, arcname="../escape.txt")
        self.pins({"llvm": {"version": "1.0", "platforms": {"linux_x64": {
            "url": arc.as_uri(), "sha256": sha(arc)}}}})
        code, _, err = self.run_cli("tool", "llvm", "--platform", "linux_x64")
        self.assertEqual(code, 1)
        self.assertIn("unsafe", err)
        self.assertFalse((self.cache / "llvm" / "escape.txt").exists())

    def test_unpacks_once(self):
        arc = self.make_tar()
        self.pins({"llvm": {"version": "1.0", "platforms": {"linux_x64": {
            "url": arc.as_uri(), "sha256": sha(arc), "bin_dir": "llvm-1.0/bin", "bin": "lld-link"}}}})
        first = self.run_cli("tool", "llvm", "--platform", "linux_x64")[1]
        marker = Path(first).parent / "marker"
        marker.write_text("kept")
        arc.unlink()  # the second call must not need the network
        second = self.run_cli("tool", "llvm", "--platform", "linux_x64")[1]
        self.assertEqual(first, second)
        self.assertTrue(marker.exists())

    def test_crate_kind_builds_once_with_cargo_install(self):
        crate_dir = self.src / "demo-1.0.0"
        crate_dir.mkdir()
        (crate_dir / "Cargo.toml").write_text("[package]\nname='demo'\n")
        arc = self.src / "demo-1.0.0.crate"
        with tarfile.open(arc, "w:gz") as t:
            t.add(crate_dir, arcname="demo-1.0.0")
        fake = self.tmp / "fakecargo.py"
        log = self.tmp / "calls.txt"
        fake.write_text(
            "import sys, pathlib\n"
            "a = sys.argv[1:]\n"
            f"open({str(log)!r}, 'a').write(' '.join(a) + '\\n')\n"
            "root = pathlib.Path(a[a.index('--root') + 1]) / 'bin'\n"
            "root.mkdir(parents=True)\n"
            "(root / 'demo').write_text('x')\n")
        wrapper = self.tmp / "cargo"
        wrapper.write_text(f"#!/bin/sh\nexec {sys.executable} {fake} \"$@\"\n")
        wrapper.chmod(0o755)
        os.environ["CI_TOOL_CARGO"] = str(wrapper)
        self.pins({"demo": {"version": "1.0.0", "platforms": {"linux_x64": {
            "kind": "crate", "url": arc.as_uri(), "sha256": sha(arc), "bin": "demo"}}}})
        code, out, err = self.run_cli("tool", "demo", "--platform", "linux_x64")
        self.assertEqual((code, Path(out).name), (0, "demo"), err)
        self.assertEqual(Path(out).parent.name, "bin")
        self.run_cli("tool", "demo", "--platform", "linux_x64")
        calls = log.read_text().splitlines()
        self.assertEqual(len(calls), 1)
        self.assertIn("install --locked --path", calls[0])

    def test_failed_cargo_leaves_nothing(self):
        crate_dir = self.src / "demo-1.0.0"
        crate_dir.mkdir()
        (crate_dir / "Cargo.toml").write_text("x")
        arc = self.src / "demo.crate"
        with tarfile.open(arc, "w:gz") as t:
            t.add(crate_dir, arcname="demo-1.0.0")
        os.environ["CI_TOOL_CARGO"] = str(self.tmp / "no-such-cargo")
        self.pins({"demo": {"version": "1.0.0", "platforms": {"linux_x64": {
            "kind": "crate", "url": arc.as_uri(), "sha256": sha(arc)}}}})
        code, _, err = self.run_cli("tool", "demo", "--platform", "linux_x64")
        self.assertEqual(code, 1)
        self.assertIn("cargo", err)
        self.assertFalse(list(self.cache.rglob("root-linux_x64")))
        self.assertFalse(list(self.cache.rglob("*.partial")))

    def test_missing_pin_and_platform(self):
        self.pins({"llvm": {"version": "1", "platforms": {}}})
        self.assertEqual(self.run_cli("tool", "zig")[0], 1)
        code, _, err = self.run_cli("tool", "llvm", "--platform", "linux_x64")
        self.assertEqual(code, 1)
        self.assertIn("llvm", err)

    def test_gitleaks_command_unchanged(self):
        # The shipped tools.json keeps its gitleaks shape.
        data = json.loads((DELIVERY / "tools.json").read_text())
        g = data["gitleaks"]
        self.assertEqual(set(g), {"version", "sha256"})
        self.assertEqual(set(g["sha256"]), set(ci_tool.PLATFORMS))


class ShippedPins(unittest.TestCase):
    def test_every_pin_has_url_and_sha(self):
        data = json.loads((DELIVERY / "tools.json").read_text())
        for name, pin in data.items():
            if name == "gitleaks":
                continue
            self.assertIn("version", pin, name)
            self.assertTrue(pin["platforms"], name)
            for plat, e in pin["platforms"].items():
                self.assertIn(plat, ci_tool.PLATFORMS, name)
                self.assertTrue(e["url"].startswith("https://"), (name, plat))
                self.assertRegex(e["sha256"], r"^[0-9a-f]{64}$", (name, plat))

    def test_required_tools_are_pinned_when_present(self):
        data = json.loads((DELIVERY / "tools.json").read_text())
        for name in ("rustup-init", "llvm", "cargo-deny", "cargo-xwin"):
            self.assertIn(name, data)


class PinHelper(unittest.TestCase):
    def test_pin_crate_and_manual_entry(self):
        tmp = Path(tempfile.mkdtemp())
        pins = tmp / "t.json"
        pins.write_text(json.dumps({"gitleaks": {"version": "1.2.3", "sha256": {}}}))
        index = tmp / "index.jsonl"
        index.write_text(json.dumps({"name": "demo", "vers": "0.9.0", "cksum": "a" * 64}) + "\n")
        self.assertEqual(tools_pin.main(
            ["crate", "demo", "0.9.0", "--index-file", str(index), "--tools-json", str(pins)]), 0)
        self.assertEqual(tools_pin.main(
            ["entry", "llvm", "20.1.8", "--platform", "linux_x64", "--kind", "archive",
             "--url", "https://example.invalid/l.tar.xz", "--sha256", "b" * 64,
             "--bin-dir", "llvm/bin", "--bin", "lld-link", "--tools-json", str(pins)]), 0)
        data = json.loads(pins.read_text())
        self.assertEqual(data["gitleaks"], {"version": "1.2.3", "sha256": {}})
        e = data["demo"]["platforms"]["linux_x64"]
        self.assertEqual(e["sha256"], "a" * 64)
        self.assertEqual(e["kind"], "crate")
        self.assertIn("static.crates.io/crates/demo/demo-0.9.0.crate", e["url"])
        self.assertEqual(data["llvm"]["platforms"]["linux_x64"]["bin_dir"], "llvm/bin")
        # a platform is merged, not replaced
        tools_pin.main(["entry", "llvm", "20.1.8", "--platform", "windows_x64", "--kind", "archive",
                        "--url", "https://example.invalid/w.tar.xz", "--sha256", "c" * 64,
                        "--tools-json", str(pins)])
        self.assertEqual(set(json.loads(pins.read_text())["llvm"]["platforms"]), {"linux_x64", "windows_x64"})


if __name__ == "__main__":
    unittest.main()
