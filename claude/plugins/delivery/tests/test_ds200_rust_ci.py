"""DS200: rust_ci.py with fake tools and a fake cargo. No real toolchain."""
import contextlib
import io
import json
import os
import stat
import sys
import tempfile
import time
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent / "templates"
sys.path.insert(0, str(BASE / "shared" / "scripts" / "delivery"))
sys.path.insert(0, str(BASE / "rust" / "scripts" / "delivery"))
import rust_ci  # noqa: E402


def script(path, body):
    Path(path).write_text("#!/bin/sh\n" + body, encoding="utf-8")
    os.chmod(path, 0o755)


@unittest.skipIf(os.name == "nt", "fake tools are shell scripts")
class RustCi(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.root = self.tmp / "app1"
        (self.root / "scripts" / "delivery").mkdir(parents=True)
        self.old = dict(os.environ)
        os.environ["CI_TOOLS_DIR"] = str(self.tmp / "cache")
        os.environ["CI_TOOLS_JSON"] = str(self.tmp / "pins.json")
        os.environ["RUST_CI_ROOT"] = str(self.root)
        (self.tmp / "pins.json").write_text("{}")
        self.log = self.tmp / "calls.log"
        self.cargo = self.tmp / "cargo"
        script(self.cargo, 'echo "$@" >> %s\n[ -n "$FAKE_FETCH_FAIL" ] && [ "$3" = fetch ] && exit 1\n'
                           '[ -n "$FAKE_FETCH_FAIL" ] && [ "$4" = fetch ] && exit 1\nexit 0\n' % self.log)
        os.environ["RUST_CI_CARGO"] = str(self.cargo)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.old)

    def run_main(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = rust_ci.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def toolchain(self, text):
        (self.root / "rust-toolchain.toml").write_text(text)

    def fake_cc(self):
        d = self.tmp / "bin"
        d.mkdir(exist_ok=True)
        script(d / "cc", "exit 0\n")
        return d

    # toolchain
    def test_toolchain_reads_exact_channel(self):
        self.toolchain('[toolchain]\nchannel = "1.90.0"\ntargets = ["x86_64-pc-windows-msvc"]\n')
        self.assertEqual(rust_ci.read_toolchain(self.root), ("1.90.0", ["x86_64-pc-windows-msvc"]))

    def test_toolchain_rejects_stable(self):
        self.toolchain('[toolchain]\nchannel = "stable"\n')
        code, _, err = self.run_main("toolchain")
        self.assertEqual(code, 1)
        self.assertIn("exact version", err)

    def test_toolchain_uses_pinned_rustup_init(self):
        self.toolchain('[toolchain]\nchannel = "1.90.0"\n')
        init = self.tmp / "rustup-init"
        script(init, 'echo "$@" > %s\n' % (self.tmp / "init.args"))
        orig = rust_ci.tool_path
        rust_ci.tool_path = lambda name, exe=None: init
        try:
            code, _, _ = self.run_main("toolchain")
        finally:
            rust_ci.tool_path = orig
        self.assertEqual(code, 0)
        self.assertIn("--default-toolchain 1.90.0", (self.tmp / "init.args").read_text())

    # linker env
    def test_env_without_cc_or_zig_fails_with_fix(self):
        self.toolchain('[toolchain]\nchannel = "1.90.0"\n')
        os.environ["PATH"] = str(self.tmp / "empty")
        code, _, err = self.run_main("env")
        self.assertEqual(code, 1)
        self.assertIn("linker cc not found", err)
        self.assertIn("Fix:", err)

    @unittest.skipUnless(sys.platform.startswith("linux"), "linux host triple")
    def test_env_uses_system_cc_when_zig_not_pinned(self):
        self.toolchain('[toolchain]\nchannel = "1.90.0"\n')
        os.environ["PATH"] = str(self.fake_cc())
        code, out, err = self.run_main("env")
        self.assertEqual(code, 0)
        self.assertIn("zig is not pinned", err)
        self.assertIn(str(self.tmp / "bin" / "cc"), json.loads(out)["CARGO_TARGET_%s_LINKER" % rust_ci.host_triple().upper().replace("-", "_")])

    # strip PATH
    def test_strip_path_removes_compiler_dirs_keeps_cargo_dir(self):
        cc = self.fake_cc()
        rs = self.tmp / "rs"
        rs.mkdir()
        script(rs / "cargo", "exit 0\n")
        script(rs / "gcc", "exit 0\n")
        other = self.tmp / "other"
        other.mkdir()
        got = rust_ci.strip_path(os.pathsep.join([str(cc), str(rs), str(other)])).split(os.pathsep)
        self.assertNotIn(str(cc), got)
        self.assertIn(str(rs), got)
        self.assertIn(str(other), got)

    def test_isolated_default_true_and_off(self):
        self.assertTrue(rust_ci.isolated(self.root))
        (self.root / "scripts" / "delivery" / "gate.json").write_text('{"toolchain-isolated": false}')
        self.assertFalse(rust_ci.isolated(self.root))

    @unittest.skipUnless(sys.platform.startswith("linux"), "linux host triple")
    def test_run_removes_cc_from_path(self):
        self.toolchain('[toolchain]\nchannel = "1.90.0"\n')
        cc = self.fake_cc()
        os.environ["PATH"] = "%s%s/usr/bin%s/bin" % (cc, os.pathsep, os.pathsep)
        probe = self.tmp / "probe.sh"
        script(probe, 'echo "$PATH" > %s\n' % (self.tmp / "path.out"))
        code, _, _ = self.run_main("run", "--", str(probe))
        self.assertEqual(code, 0)
        seen = (self.tmp / "path.out").read_text().strip().split(os.pathsep)
        self.assertNotIn(str(cc), seen)

    # deny
    def deny_setup(self, age_days=None):
        (self.root / "Cargo.toml").write_text("[package]\n")
        (self.root / "deny.toml").write_text("[advisories]\nyanked = \"deny\"\n")
        db = rust_ci.advisory_dir()
        if age_days is not None:
            db.mkdir(parents=True)
            stamp = db / ".rust_ci_fetched"
            stamp.write_text("x")
            t = time.time() - age_days * 86400
            os.utime(stamp, (t, t))

    def test_deny_ok_uses_generated_copy_and_leaves_committed_file(self):
        self.deny_setup()
        before = (self.root / "deny.toml").read_text()
        code, _, _ = self.run_main("deny")
        self.assertEqual(code, 0)
        self.assertEqual((self.root / "deny.toml").read_text(), before)
        gen = (Path(os.environ["CI_TOOLS_DIR"]) / "deny.generated.toml").read_text()
        self.assertIn("db-path", gen)
        self.assertIn("yanked", gen)
        calls = self.log.read_text()
        self.assertIn("fetch", calls)
        self.assertIn("check --disable-fetch", calls)

    def test_deny_fetch_fails_fresh_cache_warns_to_summary(self):
        self.deny_setup(age_days=2)
        os.environ["FAKE_FETCH_FAIL"] = "1"
        summ = self.tmp / "summary.md"
        os.environ["GITHUB_STEP_SUMMARY"] = str(summ)
        code, _, err = self.run_main("deny")
        self.assertEqual(code, 0)
        self.assertIn("warning", err)
        self.assertIn("using the cache", summ.read_text())

    def test_deny_fetch_fails_old_cache_fails(self):
        self.deny_setup(age_days=9)
        os.environ["FAKE_FETCH_FAIL"] = "1"
        code, _, err = self.run_main("deny")
        self.assertEqual(code, 1)
        self.assertIn("9 days old", err)

    def test_deny_fetch_fails_no_cache_fails(self):
        self.deny_setup()
        os.environ["FAKE_FETCH_FAIL"] = "1"
        code, _, err = self.run_main("deny")
        self.assertEqual(code, 1)
        self.assertIn("no cached copy", err)

    # smoke
    @unittest.skipUnless(sys.platform.startswith("linux"), "linux host triple")
    def test_smoke_builds_and_runs_version(self):
        self.toolchain('[toolchain]\nchannel = "1.90.0"\n')
        os.environ["PATH"] = str(self.fake_cc()) + os.pathsep + os.environ["PATH"]
        target = self.tmp / "target"
        (target / "debug").mkdir(parents=True)
        script(target / "debug" / "tool1", 'echo "tool1 1.2.3"\n')
        os.environ["CARGO_TARGET_DIR"] = str(target)
        (self.root / "scripts" / "delivery" / "smoke.json").write_text(json.dumps({"smoke": {"binaries": ["tool1"]}}))
        code, out, _ = self.run_main("smoke")
        self.assertEqual(code, 0, out)
        self.assertIn("tool1 1.2.3", out)
        self.assertIn("build --locked --bin tool1", self.log.read_text())

    def test_smoke_no_binaries_is_noop(self):
        (self.root / "scripts" / "delivery" / "smoke.json").write_text('{"smoke": {}}')
        self.assertEqual(self.run_main("smoke")[0], 0)

    # gate.json
    def test_gate_json_has_new_steps_and_flag(self):
        g = json.loads((BASE / "rust" / "scripts" / "delivery" / "gate.json").read_text())
        names = [s["name"] for s in g["steps"]]
        self.assertIn("deny", names)
        self.assertIn("xwin", names)
        self.assertIs(g["toolchain-isolated"], True)
        self.assertIn("Cargo.lock", g["widen_on"])
        sys.path.insert(0, str(BASE / "shared" / "scripts" / "delivery"))
        import delivery_common as dc
        p = Path(tempfile.mkdtemp()) / "gate.json"
        p.write_text(json.dumps(g))
        self.assertTrue(hasattr(dc, "SCOPES"))
        for s in g["steps"]:
            self.assertIn(s["scope"], dc.SCOPES)


if __name__ == "__main__":
    unittest.main()
