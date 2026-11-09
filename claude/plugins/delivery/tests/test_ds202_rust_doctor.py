import json
import os
import shutil
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from _helpers import make_root
import delivery_doctor as D

SHA = "a" * 64
PINS = {n: {"version": "1", "sha256": {"linux_x64": SHA}} for n in D.RUST_TOOLS}


def rust_root(track="rust", toolchain='[toolchain]\nchannel = "1.90.0"\ntargets = ["x86_64-pc-windows-msvc"]\n',
              pins=PINS):
    root = make_root({})
    d = Path(root, "scripts", "delivery")
    d.mkdir(parents=True)
    (d / "gate.json").write_text(json.dumps({"track": track}))
    if toolchain is not None:
        Path(root, "rust-toolchain.toml").write_text(toolchain)
    if pins is not None:
        (d / "tools.json").write_text(json.dumps(pins))
    return root


def items(root):
    return {i["id"]: i for i in D.rust_items(root)}


class RustDoctor(unittest.TestCase):
    def setUp(self):
        self.tools = tempfile.mkdtemp(prefix="tools-")
        p = mock.patch.dict(os.environ, {"CI_TOOLS_DIR": self.tools})
        p.start()
        self.addCleanup(p.stop)
        self.addCleanup(shutil.rmtree, self.tools, True)

    def test_other_track_prints_nothing_new(self):
        root = rust_root(track="ts")
        self.assertIsNone(D.check_rust(root, {}))
        self.assertNotIn("rust", [r["check"] for r in D.run_checks(root)])

    def test_rust_track_adds_row(self):
        self.assertIn("rust", [r["check"] for r in D.run_checks(rust_root())])

    def test_rust_ci_file_counts(self):
        root = rust_root(track="ts")
        Path(root, "scripts", "delivery", "rust_ci.py").write_text("")
        self.assertIsNotNone(D.check_rust(root, {}))

    def test_linker_missing_message_and_fix(self):
        with mock.patch.object(D, "_have", lambda n: False):
            it = items(rust_root())["rust.linker"]
        self.assertEqual(it["status"], "fail")
        self.assertIn("linker cc not found", it["detail"])
        self.assertIn("Fix:", it["detail"])

    def test_windows_target_needs_llvm(self):
        with mock.patch.object(D, "_have", lambda n: n == "cc"):
            it = items(rust_root())["rust.windows"]
        self.assertEqual(it["status"], "fail")
        self.assertIn("clang-cl and lld-link", it["detail"])

    def test_no_windows_target_no_llvm_check(self):
        root = rust_root(toolchain='[toolchain]\nchannel = "1.90.0"\n')
        self.assertNotIn("rust.windows", items(root))

    def test_stable_fails_exact_passes(self):
        self.assertEqual(items(rust_root(toolchain='[toolchain]\nchannel = "stable"\n'))["rust.toolchain"]["status"], "fail")
        self.assertEqual(items(rust_root())["rust.toolchain"]["status"], "ok")

    def test_toolchain_missing(self):
        self.assertEqual(items(rust_root(toolchain=None))["rust.toolchain"]["status"], "fail")

    def test_pins_complete_and_missing_keys_do_not_crash(self):
        self.assertEqual(items(rust_root())["rust.pins"]["status"], "ok")
        for pins in (None, {}, {"zig": "x", "llvm": None, "rustup-init": {"sha256": {"a": "short"}}}):
            it = items(rust_root(pins=pins))["rust.pins"]
            self.assertEqual(it["status"], "fail")
            self.assertIn("cargo-deny", it["detail"])

    def test_bad_tools_json_is_a_finding(self):
        root = rust_root()
        Path(root, "scripts", "delivery", "tools.json").write_text("{not json")
        self.assertEqual(items(root)["rust.pins"]["status"], "fail")

    def test_advisory_age_is_warning_only(self):
        self.assertEqual(items(rust_root())["rust.advisory"]["status"], "warn")
        db = Path(self.tools, "advisory-db")
        db.mkdir()
        self.assertEqual(items(rust_root())["rust.advisory"]["status"], "ok")
        old = time.time() - 8 * 86400
        os.utime(db, (old, old))
        self.assertEqual(items(rust_root())["rust.advisory"]["status"], "warn")

    def test_low_disk_is_warning(self):
        fake = shutil._ntuple_diskusage(100 * 10**9, 99 * 10**9, 10**9)
        with mock.patch("shutil.disk_usage", lambda p: fake):
            self.assertEqual(items(rust_root())["rust.disk"]["status"], "warn")

    def test_warnings_do_not_fail_check(self):
        with mock.patch.object(D, "_have", lambda n: True):
            ok, detail, its = D.check_rust(rust_root(), {})
        self.assertTrue(ok)
        self.assertIn("warn rust.advisory", detail)

    def test_changes_nothing(self):
        root = rust_root()
        before = sorted(str(p) for p in Path(root).rglob("*"))
        D.check_rust(root, {})
        self.assertEqual(before, sorted(str(p) for p in Path(root).rglob("*")))


if __name__ == "__main__":
    unittest.main()
