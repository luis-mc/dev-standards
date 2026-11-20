"""DL375: rerun narrowing for every test job. Recorded log and report fixtures; no network."""
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIX = HERE / "fixtures" / "dl375"
sys.path.insert(0, str(HERE.parent / "templates" / "shared" / "scripts" / "delivery"))
import rerun_tests as R  # noqa: E402


def fx(name):
    return (FIX / name).read_text(encoding="utf-8")


def names(found):
    return [f["name"] for f in found]


AREAS = {"docs": ["docs/**"], "areas": {
    "api": {"paths": ["api/**"], "tests": ["api/**"]},
    "bare": {"paths": ["bare/**"]},
}}
FILES = ["api/test_x.py", "api/x.py", "api/x.test.ts", "bare/test_y.py"]
FAILED = {"conclusion": "failure"}


def prev(runner, **kw):
    return {"conclusion": "failure", **kw}


class Parsers(unittest.TestCase):
    def test_pytest_junit_and_log(self):
        want = ["tests/test_a.py::test_bad", "tests/test_b.py::TestKlass::test_param[1]"]
        self.assertEqual(names(R.parse_failures("pytest", fx("pytest_junit.xml"))), want)
        self.assertEqual(names(R.parse_failures("pytest", fx("pytest.log"))), want)

    def test_unittest_log(self):
        got = R.parse_failures("pytest", "FAIL: test_x (pkg.test_mod.Case.test_x)\n")
        self.assertEqual(names(got), ["pkg/test_mod.py::Case::test_x"])

    def test_vitest_log(self):
        self.assertEqual(names(R.parse_failures("vitest", fx("vitest.log"))), ["math adds numbers", "renders"])

    def test_vitest_junit(self):
        xml = '<testsuites><testsuite><testcase classname="src/a.test.ts" name="math &gt; adds"><failure/></testcase></testsuite></testsuites>'
        got = R.parse_failures("vitest", xml)
        self.assertEqual((got[0]["file"], got[0]["name"]), ("src/a.test.ts", "math adds"))

    def test_playwright_json(self):
        got = R.parse_failures("playwright", fx("playwright.json"))
        self.assertEqual([(f["file"], f["line"]) for f in got], [("e2e/login.spec.ts", 12), ("e2e/login.spec.ts", 30)])

    def test_go_log(self):
        got = R.parse_failures("go", fx("go.log"))
        self.assertEqual([(f["package"], f["name"]) for f in got], [("example.test/calc", "TestAdd"), ("example.test/calc", "TestSub")])

    def test_cargo_log(self):
        got = R.parse_failures("cargo", fx("cargo.log"))
        self.assertEqual(names(got), ["tests::bad", "api::broken"])

    def test_cargo_failures_block_only(self):
        text = "     Running unittests src/lib.rs (target/debug/deps/c-0123456789abcdef)\nfailures:\n    a::b\n\ntest result: FAILED\n"
        self.assertEqual(names(R.parse_failures("cargo", text)), ["a::b"])

    def test_nextest_log_dedupes(self):
        got = R.parse_failures("nextest", fx("nextest.log"))
        self.assertEqual([(f["binary"], f["name"]) for f in got], [("mycrate", "tests::bad"), ("mycrate::bin/tool", "cli::broken")])

    def test_unreadable(self):
        for runner, text in (("pytest", ""), ("go", "FAIL\tpkg\t0.1s\n"), ("go", "FAIL\tpkg [build failed]\n"),
                             ("playwright", "not json"), ("vitest", "all fine"), ("nextest", "PASS x y"),
                             ("cargo", "test a ... ok"), ("pytest", "<broken")):
            with self.assertRaises(R.Unreadable, msg=runner):
                R.parse_failures(runner, text)

    def test_report_first_then_log(self):
        got = R.read_failures("pytest", report="<bad", log=fx("pytest.log"))
        self.assertEqual(len(got), 2)
        with self.assertRaises(R.Unreadable):
            R.read_failures("pytest")


class Arguments(unittest.TestCase):
    def inv(self, runner, name, extra=()):
        return R.build_invocations(runner, R.parse_failures(runner, fx(name)), extra)

    def test_pytest_node_ids(self):
        self.assertEqual(self.inv("pytest", "pytest.log"), [["tests/test_a.py::test_bad", "tests/test_b.py::TestKlass::test_param[1]"]])

    def test_pytest_changed_file_replaces_its_node_ids(self):
        self.assertEqual(self.inv("pytest", "pytest.log", ["tests/test_a.py"]),
                         [["tests/test_b.py::TestKlass::test_param[1]", "tests/test_a.py"]])

    def test_vitest_file_and_t(self):
        self.assertEqual(self.inv("vitest", "vitest.log"),
                         [["src/a.test.ts", "-t", "^(?:math\\ adds\\ numbers)$"], ["src/b.test.ts", "-t", "^(?:renders)$"]])

    def test_playwright_file_line(self):
        self.assertEqual(self.inv("playwright", "playwright.json"), [["e2e/login.spec.ts:12", "e2e/login.spec.ts:30"]])

    def test_playwright_grep_without_line(self):
        f = [{"name": "a b", "file": "x.spec.ts", "package": "", "binary": "", "line": 0}]
        self.assertEqual(R.build_invocations("playwright", f), [["x.spec.ts", "--grep", "^(?:a\\ b)$"]])

    def test_go_run_regex_per_package(self):
        self.assertEqual(self.inv("go", "go.log"), [["example.test/calc", "-run", "^(TestAdd|TestSub)$"]])

    def test_cargo_exact_per_binary(self):
        self.assertEqual(self.inv("cargo", "cargo.log"),
                         [["--lib", "--", "--exact", "tests::bad"], ["--test", "it", "--", "--exact", "api::broken"]])

    def test_nextest_filterset(self):
        self.assertEqual(self.inv("nextest", "nextest.log"),
                         [["-E", "(binary_id(=mycrate) & test(=tests::bad)) | (binary_id(=mycrate::bin/tool) & test(=cli::broken))"]])


class Decision(unittest.TestCase):
    def run_decide(self, runner="pytest", log="pytest.log", p=None, changed=(), cfg=None, **kw):
        p = p if p is not None else {"conclusion": "failure", "log": fx(log)}
        return R.decide(runner, "unit", p, list(changed), kw.get("scope", {}), kw.get("areas", AREAS), FILES, cfg)

    def test_failed_only(self):
        r = self.run_decide()
        self.assertEqual((r["mode"], r["failed"], len(r["invocations"])), ("narrow", 2, 1))

    def test_failed_plus_changed_tests(self):
        r = self.run_decide(changed=["api/x.py"])
        self.assertEqual(r["mode"], "narrow")
        self.assertEqual(r["changed_tests"], ["api/test_x.py"])
        self.assertIn("api/test_x.py", r["invocations"][0])

    def test_docs_change_adds_nothing(self):
        r = self.run_decide(changed=["docs/a.md"])
        self.assertEqual((r["mode"], r["changed_tests"]), ("narrow", []))

    def test_unmapped_changed_file_is_whole(self):
        self.assertEqual(self.run_decide(changed=["other/z.py"])["mode"], "whole")
        self.assertEqual(self.run_decide(changed=["bare/q.py"])["mode"], "whole")

    def test_valves_are_whole(self):
        for f in ("pnpm-lock.yaml", "web/package-lock.json", "rust-toolchain.toml", ".github/workflows/ci.yml",
                  "scripts/delivery/rerun_tests.py", "scripts/ci/x.sh", "Cargo.lock"):
            r = self.run_decide(changed=[f])
            self.assertEqual(r["mode"], "whole", f)
            self.assertIn("valve", r["reason"])

    def test_scope_full_files_are_whole(self):
        r = self.run_decide(changed=["tsconfig.base.json"], scope={"full_files": ["tsconfig.base.json"]})
        self.assertEqual(r["mode"], "whole")

    def test_cancelled_and_timed_out_are_whole(self):
        for c in ("cancelled", "timed_out", "startup_failure", None):
            r = self.run_decide(p={"conclusion": c, "log": fx("pytest.log")})
            self.assertEqual(r["mode"], "whole", c)

    def test_unreadable_is_whole(self):
        self.assertEqual(self.run_decide(p={"conclusion": "failure", "log": "Segmentation fault"})["mode"], "whole")
        self.assertEqual(self.run_decide(p={"conclusion": "failure"})["mode"], "whole")
        self.assertEqual(self.run_decide(runner="go", p={"conclusion": "failure", "log": "FAIL\tp\t1s\n"})["mode"], "whole")

    def test_config_whole(self):
        cfg = {"unit": {"rerun": "whole"}}
        self.assertEqual(self.run_decide(cfg=cfg)["mode"], "whole")
        self.assertEqual(self.run_decide(cfg={"unit": {"rerun": "failed+changed"}})["mode"], "narrow")
        self.assertEqual(self.run_decide(cfg={"other": {"rerun": "whole"}})["mode"], "narrow")

    def test_green_or_no_previous_keeps_current(self):
        self.assertEqual(self.run_decide(p={"conclusion": "success"})["mode"], "current")
        self.assertEqual(R.decide("pytest", "unit", None)["mode"], "current")

    def test_report_artifact_beats_log(self):
        r = self.run_decide(p={"conclusion": "failure", "report": fx("pytest_junit.xml"), "log": "noise"})
        self.assertEqual((r["mode"], r["failed"]), ("narrow", 2))

    def test_every_runner_narrows(self):
        for runner, name in (("vitest", "vitest.log"), ("playwright", "playwright.json"), ("go", "go.log"),
                             ("cargo", "cargo.log"), ("nextest", "nextest.log")):
            key = "report" if name.endswith(".json") else "log"
            r = R.decide(runner, "j", {"conclusion": "failure", key: fx(name)}, [], {}, AREAS, FILES, None)
            self.assertEqual(r["mode"], "narrow", runner)

    def test_cargo_changed_code_is_whole(self):
        r = R.decide("cargo", "j", {"conclusion": "failure", "log": fx("cargo.log")}, ["api/x.rs"], {}, AREAS, FILES, None)
        self.assertEqual(r["mode"], "whole")

    def test_cli(self):
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            R.main(["--runner", "go", "--prev-conclusion", "success", "--json", "--test-files", str(FIX / "go.log")])
        self.assertIn('"mode": "current"', buf.getvalue())


if __name__ == "__main__":
    unittest.main()
