"""DS235d: OS step scripts parse, and the shared step logic works with mocked service tools."""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

OS = Path(__file__).resolve().parent.parent / "templates" / "lifecycle" / "os"
SH = sorted(OS.glob("*.sh"))
PS1 = sorted(OS.glob("*.ps1"))


def run_bash(script, cwd=None):
    return subprocess.run(["bash", "-c", script], capture_output=True, text=True, timeout=60, cwd=cwd)


class Parse(unittest.TestCase):
    def test_files_present(self):
        names = {p.name for p in OS.iterdir()}
        for n in ("windows.ps1", "linux-deb.sh", "linux-rpm.sh", "macos.sh", "leftovers.ps1",
                  "leftovers-linux.sh", "leftovers-macos.sh", "lifecycle-lanes.yml"):
            self.assertIn(n, names)

    def test_bash_syntax(self):
        for f in SH:
            r = subprocess.run(["bash", "-n", str(f)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, "%s: %s" % (f.name, r.stderr))

    @unittest.skipUnless(shutil.which("shellcheck"), "shellcheck is not installed")
    def test_shellcheck(self):
        for f in SH:
            r = subprocess.run(["shellcheck", "-x", "-S", "warning", str(f)], capture_output=True, text=True,
                               cwd=str(OS))
            self.assertEqual(r.returncode, 0, "%s: %s" % (f.name, r.stdout))

    @unittest.skipUnless(shutil.which("pwsh"), "pwsh is not installed")
    def test_powershell_parse(self):
        for f in PS1:
            cmd = "$e=$null;[void][System.Management.Automation.Language.Parser]::ParseFile('%s',[ref]$null,[ref]$e);if($e){$e;exit 1}" % f
            r = subprocess.run(["pwsh", "-NoProfile", "-Command", cmd], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, "%s: %s" % (f.name, r.stdout))

    def test_no_runner_named_in_template(self):
        text = (OS / "lifecycle-lanes.yml").read_text()
        for lane in ("windows", "ubuntu-lts", "fedora", "debian", "macos"):
            self.assertIn("\n  %s:" % lane, text)
        self.assertNotIn("ubuntu-latest", text)
        self.assertNotIn("windows-latest", text)
        self.assertNotIn("macos-latest", text)
        self.assertNotIn("self-hosted", text)


class Logic(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp(prefix="ds235d-"))
        self.addCleanup(shutil.rmtree, self.d, True)
        self.cfg, self.data, self.logs = self.d / "etc", self.d / "var", self.d / "log"
        for p in (self.cfg, self.data, self.logs):
            p.mkdir()
            (p / "f.txt").write_text("x")
        self.lc = self.d / "lifecycle.json"
        self.lc.write_text(json.dumps({
            "product": "demo", "keep_on_remove": [str(self.data)],
            "paths": {"config": str(self.cfg), "data": str(self.data), "logs": str(self.logs),
                      "service": "demo", "console_port": 1, "data_roots": [str(self.d / "roots")],
                      "legacy_data": [str(self.d / "old")]},
            "test_interface": {"selftest": "true", "pair": "true"}}))

    def run_steps(self, hooks, check):
        script = ("export LIFECYCLE_JSON=%s; . %s/os-common.sh; %s\nlc_run %s" % (self.lc, OS, hooks, check))
        return run_bash(script)

    def test_lc9_pass_and_fail(self):
        hooks = ("export LC_PKG=a.pkg; os_install(){ return 0; }; os_reboot_pending(){ return 1; }; "
                 "os_service_active(){ return 0; }; lc_console_up(){ return 0; }")
        r = self.run_steps(hooks, "lc9")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("LC-9 PASS", r.stdout)
        r = self.run_steps(hooks.replace("os_install(){ return 0; }", "os_install(){ return 3; }"), "lc9")
        self.assertEqual(r.returncode, 1)
        self.assertIn("exit 3", r.stdout)
        r = self.run_steps(hooks.replace("os_reboot_pending(){ return 1; }", "os_reboot_pending(){ return 0; }"), "lc9")
        self.assertIn("reboot", r.stdout)
        self.assertEqual(r.returncode, 1)

    def test_lc14_keeps_exactly_keep_on_remove(self):
        good = "os_remove(){ rm -rf %s %s; }" % (self.cfg, self.logs)
        r = self.run_steps(good, "lc14")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("LC-14 PASS", r.stdout)
        # A remove that deletes the kept folder fails.
        (self.cfg).mkdir(exist_ok=True)
        r = self.run_steps("os_remove(){ rm -rf %s; }" % self.data, "lc14")
        self.assertEqual(r.returncode, 1)
        # A remove that keeps config (not in keep_on_remove) fails.
        self.data.mkdir(exist_ok=True)
        r = self.run_steps("os_remove(){ rm -rf %s; }" % self.logs, "lc14")
        self.assertEqual(r.returncode, 1)

    def test_lc13_downgrade_refused(self):
        base = "export LC_OLDER_PKG=old; os_installed_version(){ cat %s/v; }; " % self.d
        (self.d / "v").write_text("2.0")
        r = self.run_steps(base + "os_install(){ return 1; }", "lc13")
        self.assertIn("LC-13 PASS", r.stdout)
        r = self.run_steps(base + "os_install(){ echo 1.0 > %s/v; }" % self.d, "lc13")
        self.assertIn("LC-13 FAIL", r.stdout)

    def test_lc10_reinstall_changes_nothing(self):
        base = "export LC_PKG=p; os_installed_version(){ echo 1.0; }; "
        r = self.run_steps(base + "os_install(){ return 0; }", "lc10")
        self.assertIn("LC-10 PASS", r.stdout)
        r = self.run_steps(base + "os_install(){ echo y > %s/f.txt; }" % self.cfg, "lc10")
        self.assertIn("LC-10 FAIL", r.stdout)

    def test_lc15_uses_leftovers(self):
        base = "os_purge(){ return 0; }; "
        r = self.run_steps(base + "os_leftovers(){ return 0; }", "lc15")
        self.assertIn("LC-15 PASS", r.stdout)
        r = self.run_steps(base + "os_leftovers(){ echo 'file: /x'; return 1; }", "lc15")
        self.assertIn("LC-15 FAIL", r.stdout)
        self.assertIn("file: /x", r.stdout)

    def test_lc33_one_data_folder(self):
        base = "true; "
        r = self.run_steps(base, "lc33")
        self.assertIn("LC-33 PASS", r.stdout)
        (self.d / "old").mkdir()
        r = self.run_steps(base, "lc33")
        self.assertIn("LC-33 FAIL", r.stdout)

    def test_missing_input_fails(self):
        r = self.run_steps("unset LC_PREV_PKG", "lc11")
        self.assertEqual(r.returncode, 1)
        self.assertIn("missing input", r.stdout)

    def test_unknown_check(self):
        self.assertEqual(self.run_steps("true", "lc999").returncode, 2)

    def test_lc21_unsigned_by_decision(self):
        script = ("export LIFECYCLE_JSON=%s LC_UNSIGNED_DECISION=D42; . %s/os-common.sh; "
                  "sed -n '/^os_lint()/,/^}/p' %s/macos.sh > %s/lint.sh; . %s/lint.sh; os_lint"
                  % (self.lc, OS, OS, self.d, self.d))
        r = run_bash(script)
        self.assertIn("LC-21 PASS unsigned by decision D42", r.stdout)


class Leftovers(unittest.TestCase):
    def test_linux_scanner(self):
        d = Path(tempfile.mkdtemp(prefix="ds235d-"))
        self.addCleanup(shutil.rmtree, d, True)
        lc = d / "lifecycle.json"
        gone = d / "nothing"
        lc.write_text(json.dumps({"product": "zz-demo", "paths": {"data": str(gone), "service": "zz-demo"}}))
        r = subprocess.run(["bash", str(OS / "leftovers-linux.sh")], capture_output=True, text=True,
                           env={"LIFECYCLE_JSON": str(lc), "PATH": "/usr/bin:/bin"})
        self.assertEqual(r.returncode, 0, r.stdout)
        gone.mkdir()
        r = subprocess.run(["bash", str(OS / "leftovers-linux.sh")], capture_output=True, text=True,
                           env={"LIFECYCLE_JSON": str(lc), "PATH": "/usr/bin:/bin"})
        self.assertEqual(r.returncode, 1)
        self.assertIn("file: " + str(gone), r.stdout)


if __name__ == "__main__":
    unittest.main()
