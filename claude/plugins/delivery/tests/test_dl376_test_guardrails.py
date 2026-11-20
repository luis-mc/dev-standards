"""DL376 (DL-99): the test guardrails guard scans fixture repos, reports per guardrail, warns or blocks."""
import contextlib
import io
import json
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "templates" / "shared" / "scripts" / "delivery"))
import fast_guards as F  # noqa: E402
import test_guardrails as tg  # noqa: E402

WF_OK = """name: ci
on:
  pull_request:
  push:
    branches: [main]
jobs:
  test:
    runs-on: ubuntu-latest
    timeout-minutes: 20
    steps:
      - run: make test
      - uses: actions/upload-artifact@v4
        with:
          name: ci-run-times
          path: ci-run-times.json
"""

GOOD = {
    "ts": {
        "vitest.config.ts": "export default { test: { testTimeout: 5000 } }\n",
        "playwright.config.ts": "export default { timeout: 60_000, retries: 0 }\n",
        "src/a.test.ts": "it('a', () => { expect(1).toBe(1) })\n",
        "e2e/a.spec.ts": "test('a', async () => {})\n",
        ".github/workflows/ci.yml": WF_OK,
    },
    "py": {
        "pytest.ini": "[pytest]\ntimeout = 5\n",
        "tests/test_a.py": "def test_a():\n    assert 1\n",
        ".github/workflows/ci.yml": WF_OK,
    },
    "go": {
        "a_test.go": "package a\nfunc TestA(t *testing.T) {}\n",
        "Makefile": "test:\n\tgo test -timeout 10s ./...\n",
        ".github/workflows/ci.yml": WF_OK,
    },
    "rust-nextest": {
        "tests/a.rs": "#[test]\nfn a() {}\n",
        ".config/nextest.toml": '[profile.default]\nslow-timeout = { period = "5s", terminate-after = 2 }\n',
        ".github/workflows/ci.yml": WF_OK,
    },
}

# stack, file to add or replace, text, guardrail it breaks
BREAKS = [
    ("ts", "vitest.config.ts", "export default { test: {} }\n", "G1"),
    ("ts", "playwright.config.ts", "export default { timeout: 600000 }\n", "G1"),
    ("ts", "playwright.config.ts", "export default { timeout: 60000,\n  retries: process.env.CI ? 2 : 0 }\n", "G3"),
    ("py", "pytest.ini", "[pytest]\n", "G1"),
    ("py", "tests/test_a.py", "import time\ndef test_a():\n    time.sleep(1)\n", "G4"),
    ("py", "tests/test_a.py", "import pytest\n@pytest.mark.parametrize('x', [%s])\ndef test_a(x):\n    pass\n"
     % ",".join(str(i) for i in range(25)), "G5"),
    ("py", "pytest.ini", "[pytest]\ntimeout = 5\naddopts = --reruns 2\n", "G3"),
    ("go", "Makefile", "test:\n\tgo test ./...\n", "G1"),
    ("go", "a_test.go", "package a\nfunc TestA(t *testing.T) {\n\ttime.Sleep(time.Second)\n}\n", "G4"),
    ("go", "a_test.go", "package a\nfunc TestA(t *testing.T) {\n\ttests := []struct{n int}{\n%s\t}\n}\n"
     % "".join("\t\t{%d},\n" % i for i in range(30)), "G5"),
    ("rust-nextest", ".config/nextest.toml", '[profile.default]\nslow-timeout = { period = "5s" }\n', "G1"),
    ("rust-nextest", ".config/nextest.toml", '[profile.default]\nslow-timeout = { period = "5s", terminate-after = 2 }\nretries = 2\n', "G3"),
    ("rust-nextest", "tests/a.rs", "#[test]\nfn a() { std::thread::sleep(d); }\n", "G4"),
    ("rust-nextest", "tests/a.rs", "#[rstest]\n%sfn a() {}\n" % "".join("#[case(%d)]\n" % i for i in range(22)), "G5"),
    ("ts", ".github/workflows/ci.yml", WF_OK.replace("    timeout-minutes: 20\n", ""), "G2"),
    ("ts", ".github/workflows/ci.yml", WF_OK.replace("timeout-minutes: 20", "timeout-minutes: 60"), "G2"),
    ("ts", ".github/workflows/ci.yml", WF_OK.replace("      - uses: actions/upload-artifact@v4\n        with:\n"
     "          name: ci-run-times\n          path: ci-run-times.json\n", ""), "G7"),
    ("ts", ".github/workflows/ci.yml", WF_OK + "      - run: npx stryker run\n", "G6"),
]


def build(files):
    root = Path(tempfile.mkdtemp(prefix="dl376-"))
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return root


def run(root, *args):
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        code = tg.main(["--root", str(root), *args])
    return code, out.getvalue()


class Fixtures(unittest.TestCase):
    def make(self, files):
        root = build(files)
        self.addCleanup(shutil.rmtree, root, True)
        return root

    def test_good_fixtures_pass(self):
        for stack, files in GOOD.items():
            with self.subTest(stack=stack):
                report = tg.scan(self.make(files), {})
                bad = {g: r["breaks"] for g, r in report["results"].items() if r["state"] != "pass"}
                self.assertEqual(bad, {})

    def test_each_break_is_found(self):
        for stack, rel, text, g in BREAKS:
            with self.subTest(stack=stack, file=rel, guardrail=g):
                files = dict(GOOD[stack])
                files[rel] = text
                report = tg.scan(self.make(files), {})
                self.assertEqual(report["results"][g]["state"], "break", report["results"][g])
                others = [k for k, r in report["results"].items() if k != g and r["state"] == "break"]
                self.assertEqual(others, [])

    def test_plain_cargo_test_breaks_and_property_runs_on_pull_request(self):
        files = {"tests/a.rs": "#[test]\nfn a() {}\n", ".github/workflows/ci.yml": WF_OK.replace("make test", "cargo test")}
        report = tg.scan(self.make(files), {})
        self.assertEqual(report["results"]["G1"]["state"], "break")
        files = dict(GOOD["ts"])
        files["src/p.test.ts"] = "fc.assert(p, { numRuns: 1000 })\n"
        self.assertEqual(tg.scan(self.make(files), {})["results"]["G6"]["state"], "break")
        files = dict(GOOD["ts"], **{".github/workflows/ci.yml": WF_OK.replace("on:\n  pull_request:\n  push:\n    branches: [main]",
                                                                             "on:\n  schedule:\n    - cron: '0 3 * * *'") + "      - run: npx stryker run\n"})
        self.assertEqual(tg.scan(self.make(files), {})["results"]["G6"]["state"], "pass")

    def test_offenders_are_capped_at_ten(self):
        files = dict(GOOD["py"])
        for i in range(14):
            files["tests/test_s%d.py" % i] = "import time\ndef test_a():\n    time.sleep(1)\n"
        root = self.make(files)
        code, out = run(root)
        self.assertEqual(code, 0)
        self.assertIn("G4 14 breaks", out)
        self.assertIn("and 4 more", out)
        self.assertEqual(sum(1 for ln in out.splitlines() if ".py:3" in ln), 10)


class Modes(unittest.TestCase):
    def setUp(self):
        files = dict(GOOD["py"], **{"tests/test_a.py": "import time\ndef test_a():\n    time.sleep(1)\n"})
        self.root = build(files)
        self.addCleanup(shutil.rmtree, self.root, True)

    def config(self, tg_cfg=None, jobs=None):
        ci = {}
        if tg_cfg is not None:
            ci["test_guardrails"] = tg_cfg
        if jobs is not None:
            ci["jobs"] = jobs
        (self.root / ".delivery").mkdir(exist_ok=True)
        (self.root / ".delivery" / "config.json").write_text(json.dumps({"ci": ci}), encoding="utf-8")

    def test_warn_is_the_default_and_exits_zero(self):
        code, out = run(self.root)
        self.assertEqual(code, 0)
        self.assertIn("mode warn", out)
        self.assertIn("G4 1 break", out)
        self.assertIn("G1 PASS", out)

    def test_block_exits_nonzero(self):
        self.config({"mode": "block"})
        self.assertEqual(run(self.root)[0], 1)

    def test_block_with_the_guardrail_off_and_a_reason_passes(self):
        self.config({"mode": "block", "off": ["G4"], "reasons": {"G4": "a driver needs a pause"}})
        code, out = run(self.root)
        self.assertEqual(code, 0)
        self.assertIn("G4 OFF", out)

    def test_off_without_a_reason_is_reported_and_still_scanned(self):
        self.config({"mode": "block", "off": ["G4"]})
        code, out = run(self.root)
        self.assertEqual(code, 1)
        self.assertIn("G4 is turned off without a reason", out)
        self.assertIn("G4 1 break", out)

    def test_bad_mode_is_a_usage_error(self):
        self.config({"mode": "loud"})
        self.assertEqual(run(self.root)[0], 2)

    def test_json_output(self):
        code, out = run(self.root, "--json")
        data = json.loads(out)
        self.assertEqual(code, 0)
        self.assertEqual(data["results"]["G4"]["count"], 1)
        self.assertEqual(data["results"]["G4"]["breaks"][0]["file"], "tests/test_a.py")

    def test_lower_job_test_timeout_is_accepted_a_higher_one_refused(self):
        files = dict(GOOD["ts"], **{"vitest.config.ts": "export default { test: { testTimeout: 8000 } }\n"})
        root = build(files)
        self.addCleanup(shutil.rmtree, root, True)

        def put(jobs):
            (root / ".delivery").mkdir(exist_ok=True)
            (root / ".delivery" / "config.json").write_text(json.dumps({"ci": {"jobs": jobs}}), encoding="utf-8")

        put({"test": {"test_timeout_s": {"unit": 9}}})  # lower than 10 and the config's 8 s is within it
        self.assertEqual(tg.scan(root, tg.load_config(root))["results"]["G1"]["state"], "pass")
        put({"test": {"test_timeout_s": {"unit": 5}}})  # the project lowered it to 5: 8 s is now over
        self.assertEqual(tg.scan(root, tg.load_config(root))["results"]["G1"]["state"], "break")
        put({"test": {"test_timeout_s": {"unit": 30}}})  # raising is refused
        g1 = tg.scan(root, tg.load_config(root))["results"]["G1"]
        self.assertEqual(g1["state"], "break")
        self.assertIn("may only lower", g1["breaks"][0]["message"])

    def test_job_timeout_minutes_from_config(self):
        files = dict(GOOD["ts"], **{".github/workflows/ci.yml": WF_OK.replace("    timeout-minutes: 20\n", "")})
        root = build(files)
        self.addCleanup(shutil.rmtree, root, True)
        self.assertEqual(tg.scan(root, {"ci": {"jobs": {"test": {"timeout_minutes": 15}}}})["results"]["G2"]["state"], "pass")
        self.assertEqual(tg.scan(root, {"ci": {"jobs": {"test": {"timeout_minutes": 45}}}})["results"]["G2"]["state"], "break")


class Wiring(unittest.TestCase):
    def test_fast_guards_warns_or_blocks(self):
        root = build(dict(GOOD["py"], **{"tests/test_a.py": "import time\ndef test_a():\n    time.sleep(1)\n"}))
        self.addCleanup(shutil.rmtree, root, True)
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertTrue(F.run_test_guardrails(root))
        self.assertIn("G4 1 break", out.getvalue())
        (root / ".delivery").mkdir()
        (root / ".delivery" / "config.json").write_text('{"ci": {"test_guardrails": {"mode": "block"}}}', encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertFalse(F.run_test_guardrails(root))
        self.assertIn("FAIL always-on guard test-guardrails", out.getvalue())


class Speed(unittest.TestCase):
    def test_scan_of_all_fixtures_under_two_seconds(self):
        roots = [build(f) for f in GOOD.values()]
        self.addCleanup(lambda: [shutil.rmtree(r, True) for r in roots])
        t = time.time()
        for r in roots:
            tg.scan(r, {})
        self.assertLess(time.time() - t, 2)


if __name__ == "__main__":
    unittest.main()
