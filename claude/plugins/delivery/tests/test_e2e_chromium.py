"""DL89: the e2e gate step skips the browser download when E2E_CHROMIUM_PATH names a browser; agent setup finds one."""
import json
import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

PLUGIN = Path(__file__).resolve().parent.parent
GATE = PLUGIN / "templates" / "ts" / "scripts" / "delivery" / "gate.json"
SETUP = PLUGIN / "templates" / "shared" / "scripts" / "delivery" / "agent_setup.sh"
TEST_CMD = "pnpm exec playwright test"
INSTALL = "pnpm exec playwright install chromium"
SH = shutil.which("sh")
BASH = shutil.which("bash")


def e2e_step():
    steps = json.loads(GATE.read_text())["steps"]
    return next(s for s in steps if s["name"] == "e2e")


def make_exe(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


class GateTests(unittest.TestCase):
    def test_both_commands_hold_the_guard_and_end_with_the_test_run(self):
        step = e2e_step()
        for key, tail in (("run", TEST_CMD + " {e2e_specs}"), ("run_full", TEST_CMD)):
            cmd = step[key]
            self.assertIn('[ -x "$E2E_CHROMIUM_PATH" ]', cmd, key)
            self.assertIn("|| " + INSTALL, cmd, key)
            self.assertTrue(cmd.endswith("&& " + tail), key)

    @unittest.skipUnless(SH, "sh not available")
    def test_guard_skips_or_runs_the_install(self):
        tmp = Path(tempfile.mkdtemp(prefix="dl89-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        log = tmp / "calls.log"
        stub = make_exe(tmp / "bin" / "pnpm")
        stub.write_text('#!/bin/sh\necho "$*" >> "%s"\n' % log)
        browser = make_exe(tmp / "chrome")
        cases = {"set": (str(browser), False), "unset": (None, True), "missing": (str(tmp / "nope"), True)}
        for key in ("run", "run_full"):
            cmd = e2e_step()[key].replace("{e2e_specs}", "a.spec.ts")
            for name, (value, installs) in cases.items():
                with self.subTest(step=key, case=name):
                    log.write_text("")
                    env = {k: v for k, v in os.environ.items() if k != "E2E_CHROMIUM_PATH"}
                    env["PATH"] = str(tmp / "bin") + os.pathsep + env.get("PATH", "")
                    if value is not None:
                        env["E2E_CHROMIUM_PATH"] = value
                    r = subprocess.run([SH, "-c", cmd], env=env, capture_output=True, text=True)
                    self.assertEqual(r.returncode, 0, r.stderr)
                    calls = log.read_text().splitlines()
                    self.assertEqual("exec playwright install chromium" in calls, installs)
                    self.assertEqual(sum(c.startswith("exec playwright test") for c in calls), 1)


class SetupTests(unittest.TestCase):
    def test_script_holds_detection_and_env_file_write(self):
        text = SETUP.read_text()
        self.assertIn("/opt/pw-browsers", text)
        self.assertIn("PLAYWRIGHT_BROWSERS_PATH", text)
        for pat in ("*/chrome-linux/chrome", "*/chrome-linux64/chrome", "chromium*/chrome"):
            self.assertIn(pat, text)
        self.assertIn("CLAUDE_ENV_FILE", text)
        self.assertIn("export E2E_CHROMIUM_PATH=", text)

    def snippet(self, fake_root):
        text = SETUP.read_text()
        start = text.index("find_chromium() {")
        end = text.index("setup_cmds=$(")
        return text[start:end].replace("/opt/pw-browsers", fake_root)

    def run_snippet(self, env_extra):
        tmp = Path(tempfile.mkdtemp(prefix="dl89-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        script = "say() { printf 'agent_setup: %s\\n' \"$*\" >&2; }\n" + self.snippet(str(tmp / "opt"))
        env = {k: v for k, v in os.environ.items() if k not in ("E2E_CHROMIUM_PATH", "CLAUDE_ENV_FILE", "PLAYWRIGHT_BROWSERS_PATH")}
        env.update(env_extra(tmp))
        r = subprocess.run([BASH, "-c", script], env=env, capture_output=True, text=True)
        return tmp, r

    @unittest.skipUnless(BASH, "bash not available")
    def test_finds_browser_under_playwright_path_and_writes_env_file(self):
        def extra(tmp):
            make_exe(tmp / "pw" / "chromium-9" / "chrome-linux64" / "chrome")
            return {"PLAYWRIGHT_BROWSERS_PATH": str(tmp / "pw"), "CLAUDE_ENV_FILE": str(tmp / "env.sh")}
        tmp, r = self.run_snippet(extra)
        self.assertEqual(r.returncode, 0, r.stderr)
        path = str(tmp / "pw" / "chromium-9" / "chrome-linux64" / "chrome")
        self.assertIn(path, r.stderr)
        self.assertEqual((tmp / "env.sh").read_text(), "export E2E_CHROMIUM_PATH=%s\n" % path)

    @unittest.skipUnless(BASH, "bash not available")
    def test_nothing_found_does_not_fail(self):
        tmp, r = self.run_snippet(lambda t: {"PLAYWRIGHT_BROWSERS_PATH": str(t / "empty"), "CLAUDE_ENV_FILE": str(t / "env.sh")})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse((tmp / "env.sh").exists())

    @unittest.skipUnless(BASH, "bash not available")
    def test_finds_browser_under_the_default_root(self):
        def extra(tmp):
            make_exe(tmp / "opt" / "chromium-1" / "chrome-linux" / "chrome")
            return {"CLAUDE_ENV_FILE": str(tmp / "env.sh")}
        tmp, r = self.run_snippet(extra)
        self.assertIn("chromium-1/chrome-linux/chrome", (tmp / "env.sh").read_text())

    @unittest.skipUnless(BASH, "bash not available")
    def test_already_set_is_left_alone(self):
        def extra(tmp):
            make_exe(tmp / "pw" / "chromium-9" / "chrome-linux64" / "chrome")
            return {"PLAYWRIGHT_BROWSERS_PATH": str(tmp / "pw"), "CLAUDE_ENV_FILE": str(tmp / "env.sh"), "E2E_CHROMIUM_PATH": "/x/chrome"}
        tmp, r = self.run_snippet(extra)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse((tmp / "env.sh").exists())


if __name__ == "__main__":
    unittest.main()
