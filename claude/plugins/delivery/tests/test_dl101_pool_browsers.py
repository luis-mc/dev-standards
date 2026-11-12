"""DL101 (D117): the setup picks POOL_BROWSERS=chromium for Playwright repositories; the doctor fails when the image lacks them.
Fake repositories in temp folders and a fake docker runner. No Docker is used."""
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from _helpers import make_root  # noqa: F401  (sets sys.path to the scripts folder)
import delivery_runner_pool as P


class DockerProbe(P.Probe):
    """Real file reads; docker answers from the fields below."""
    platform = "linux"

    def __init__(self, ps="main pool-image:1\n", libs_rc=0, readable=True):
        self.ps, self.libs_rc, self.readable, self.calls = ps, libs_rc, readable, []

    def sh(self, argv, input=None, timeout=60):
        self.calls.append(argv)
        if argv[0] != "docker" or not self.readable:
            return None
        if argv[1] == "ps":
            return 0, self.ps
        if argv[1] == "run":
            return self.libs_rc, ""
        return 0, ""


def repo(d, name, files):
    root = Path(d, name)
    for rel, text in files.items():
        f = root / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text)
    root.mkdir(parents=True, exist_ok=True)
    return str(root)


PW_DEP = json.dumps({"devDependencies": {"@playwright/test": "^1.50.0"}})
PLAIN = json.dumps({"dependencies": {"left-pad": "1.0.0"}})


class PickTests(unittest.TestCase):
    def pick(self, files, browsers=None):
        with tempfile.TemporaryDirectory() as d:
            return P.pick_browsers(P.Probe(), browsers, [repo(d, "app1", files)])

    def test_config_file_gives_chromium(self):
        b, why = self.pick({"playwright.config.ts": "export default {}"})
        self.assertEqual(b, "chromium")
        self.assertIn("playwright.config.ts", why)

    def test_dev_dependency_gives_chromium(self):
        self.assertEqual(self.pick({"package.json": PW_DEP})[0], "chromium")

    def test_playwright_dependency_gives_chromium(self):
        self.assertEqual(self.pick({"package.json": json.dumps({"dependencies": {"playwright": "1"}})})[0], "chromium")

    def test_workspace_package_gives_chromium(self):
        self.assertEqual(self.pick({"package.json": PLAIN, "packages/web/package.json": PW_DEP})[0], "chromium")
        self.assertEqual(self.pick({"package.json": PLAIN, "apps/web/playwright.config.js": ""})[0], "chromium")

    def test_none_found_gives_none(self):
        b, why = self.pick({"package.json": PLAIN, "README.md": "x"})
        self.assertEqual((b, why), ("none", None))

    def test_broken_package_json_is_none(self):
        self.assertEqual(self.pick({"package.json": "{not json"})[0], "none")

    def test_owner_choice_wins(self):
        self.assertEqual(self.pick({"package.json": PW_DEP}, "none"), ("none", None))
        self.assertEqual(self.pick({"package.json": PLAIN}, "chromium"), ("chromium", None))

    def test_one_playwright_repo_among_many(self):
        with tempfile.TemporaryDirectory() as d:
            a = repo(d, "app1", {"package.json": PLAIN})
            b = repo(d, "app2", {"package.json": PW_DEP})
            self.assertEqual(P.pick_browsers(P.Probe(), None, [a, b])[0], "chromium")


class PlanTests(unittest.TestCase):
    def test_plan_prints_why_and_writes_chromium(self):
        from test_runner_pool import FakeProbe
        found = P.detect(FakeProbe())
        found["pool_env"] = {}
        cap = {"ok": True, "cpus": 2, "mem_gib": 6, "cpus_text": ""}
        with tempfile.TemporaryDirectory() as d:
            path = repo(d, "app1", {"playwright.config.ts": ""})
            out = io.StringIO()
            with redirect_stdout(out):
                pl = P.plan(found, ["owner/example-app"], [], "main", cap, repo_paths=[path], probe=P.Probe())
        step = next(s for s in pl["steps"] if s["action"] == "pool-files")
        self.assertEqual(step["browsers"], "chromium")
        self.assertIn("POOL_BROWSERS set to chromium", out.getvalue())

    def test_plan_without_playwright_stays_none(self):
        from test_runner_pool import FakeProbe
        found = P.detect(FakeProbe())
        found["pool_env"] = {}
        cap = {"ok": True, "cpus": 2, "mem_gib": 6, "cpus_text": ""}
        with tempfile.TemporaryDirectory() as d:
            path = repo(d, "app1", {"package.json": PLAIN})
            out = io.StringIO()
            with redirect_stdout(out):
                pl = P.plan(found, ["owner/example-app"], [], "main", cap, repo_paths=[path], probe=P.Probe())
        step = next(s for s in pl["steps"] if s["action"] == "pool-files")
        self.assertEqual(step["browsers"], "none")
        self.assertEqual(out.getvalue(), "")


class DoctorTests(unittest.TestCase):
    def run_doctor(self, files, env_browsers="chromium", **probe_kw):
        with tempfile.TemporaryDirectory() as d:
            pd = Path(d, "pools", "main")
            pd.mkdir(parents=True)
            (pd / "compose.yaml").write_text("services: {}\n")
            (pd / ".env").write_text("POOL_CPUS=2\nPOOL_MEM=8g\nPOOL_BROWSERS=%s\n" % env_browsers)
            (pd / "agents.json").write_text(json.dumps({"agents": [{"slug": "a", "user": "r-a", "repo": "owner/app1", "private": True}]}))
            path = repo(d, "app1", files)
            probe = DockerProbe(**probe_kw)
            res = P.doctor_checks(d, probe, repo_paths=[path])
        return {c["id"].split(".")[-1]: c for c in res}, probe

    def test_fails_on_none_with_playwright(self):
        by, _ = self.run_doctor({"playwright.config.ts": ""}, env_browsers="none")
        self.assertEqual(by["browsers"]["status"], "fail")
        self.assertIn("owner/app1", by["browsers"]["detail"])
        self.assertIn("POOL_BROWSERS=chromium", by["browsers"]["detail"])
        self.assertIn("rebuild the image", by["browsers"]["detail"])

    def test_fails_when_libs_missing(self):
        by, probe = self.run_doctor({"package.json": PW_DEP}, libs_rc=1)
        self.assertEqual(by["browser-libs"]["status"], "fail")
        self.assertIn("owner/app1", by["browser-libs"]["detail"])
        run = next(c for c in probe.calls if c[1] == "run")
        self.assertIn("pool-image:1", run)
        self.assertIn("ldconfig -p | grep -q libglib-2.0", run[-1])

    def test_ok_when_libs_present(self):
        by, _ = self.run_doctor({"package.json": PW_DEP})
        self.assertEqual(by["browser-libs"]["status"], "ok")

    def test_warns_when_docker_unreadable(self):
        by, _ = self.run_doctor({"package.json": PW_DEP}, readable=False)
        self.assertEqual(by["browser-libs"]["status"], "warn")
        self.assertNotIn("browsers", by)

    def test_warns_when_container_not_found(self):
        by, _ = self.run_doctor({"package.json": PW_DEP}, ps="")
        self.assertEqual(by["browser-libs"]["status"], "warn")

    def test_no_playwright_adds_no_browser_check(self):
        by, probe = self.run_doctor({"package.json": PLAIN}, env_browsers="none")
        self.assertNotIn("browsers", by)
        self.assertNotIn("browser-libs", by)
        self.assertFalse([c for c in probe.calls if c[1] == "run" and "--device" not in c])


if __name__ == "__main__":
    unittest.main()
