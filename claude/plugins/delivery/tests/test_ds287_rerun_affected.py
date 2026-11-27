"""DS287 R5.92: rerun_tests.py plans failed tests, then affected packages."""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "templates" / "shared" / "scripts" / "delivery"))
import rerun_tests as R  # noqa: E402

MOD = "module example.com/app\n\ngo 1.22\n"
DEPS = "\n".join([
    "example.com/app/leaf fmt",
    "example.com/app/mid fmt example.com/app/leaf",
    "example.com/app/top fmt example.com/app/leaf example.com/app/mid",
    "example.com/app/other fmt strings",
])
GO_LOG = json.dumps({"Action": "fail", "Package": "example.com/app/other", "Test": "TestX"})
AREAS = {"docs": ["docs/**"], "areas": {"all": {"paths": ["**"], "tests": ["**"]}}}
FILES = ["leaf/a_test.go", "src/a.test.ts", "tests/test_a.py", "src/a.py", "main_test.go"]


def go_decide(changed, deps=DEPS, mod=MOD):
    prev = {"conclusion": "failure", "log": GO_LOG, "report": None}
    return R.decide("go", "t", prev, changed, None, AREAS, FILES, None, deps, mod)


class Go(unittest.TestCase):
    def test_leaf_selects_dependents(self):
        r = go_decide(["leaf/a.go"])
        self.assertEqual(r["mode"], "narrow")
        self.assertEqual(r["then"], [["example.com/app/leaf", "example.com/app/mid", "example.com/app/top"]])

    def test_unrelated_not_selected(self):
        pk = r = go_decide(["leaf/a.go"])["then"][0]
        self.assertNotIn("example.com/app/other", pk)
        self.assertEqual(go_decide(["top/t.go"])["then"], [["example.com/app/top"]])

    def test_root_package(self):
        deps = "example.com/app/cmd example.com/app\nexample.com/app fmt"
        self.assertEqual(go_decide(["main.go"], deps)["then"], [["example.com/app", "example.com/app/cmd"]])

    def test_no_deps_or_module_is_today(self):
        self.assertEqual(go_decide(["leaf/a.go"], None)["then"], [])
        self.assertEqual(go_decide(["leaf/a.go"], DEPS, "")["then"], [])

    def test_callable_sources(self):
        r = go_decide(["leaf/a.go"], lambda: DEPS, lambda: MOD)
        self.assertEqual(len(r["then"][0]), 3)


class Js(unittest.TestCase):
    LOG = "FAIL src/a.test.ts > adds\n"

    def run_js(self, runner, changed):
        prev = {"conclusion": "failure", "log": self.LOG, "report": None}
        return R.decide(runner, "t", prev, changed, None, AREAS, FILES, None)

    def test_vitest_related(self):
        r = self.run_js("vitest", ["src/a.ts", "src/b.tsx", "README.md"])
        self.assertEqual(r["then"], [["related", "src/a.ts", "src/b.tsx", "--run"]])

    def test_jest_find_related(self):
        r = self.run_js("jest", ["src/a.ts"])
        self.assertEqual(r["mode"], "narrow")
        self.assertEqual(r["then"], [["--findRelatedTests", "src/a.ts"]])

    def test_no_js_files_no_then(self):
        self.assertEqual(self.run_js("vitest", ["docs/x.md"])["then"], [])


class Unchanged(unittest.TestCase):
    def test_pytest_no_then(self):
        log = "FAILED tests/test_a.py::test_x - boom\n"
        r = R.decide("pytest", "t", {"conclusion": "failure", "log": log, "report": None}, ["src/a.py"], None, AREAS, FILES, None)
        self.assertEqual(r["then"], [])
        self.assertEqual(r["invocations"], [["tests/test_a.py"]])  # as before: changed code maps to the whole test file

    def test_existing_keys_and_step_one(self):
        r = go_decide(["leaf/a.go"])
        for k in ("mode", "reason", "invocations", "failed", "changed_tests"):
            self.assertIn(k, r)
        self.assertEqual(r["invocations"][0], ["example.com/app/other", "-run", "^(TestX)$"])
        self.assertEqual(r["failed"], 1)

    def test_valves_stay_whole(self):
        for changed in (["go.mod"], [".github/workflows/ci.yml", "leaf/a.go"]):
            r = go_decide(changed)
            self.assertEqual(r["mode"], "whole")
            self.assertEqual(r["then"], [])
            self.assertEqual(r["invocations"], [])

    def test_green_and_whole_config(self):
        self.assertEqual(R.decide("go", "t", {"conclusion": "success"}, ["leaf/a.go"], None, AREAS, FILES, None, DEPS, MOD)["then"], [])
        cfg = {"t": {"rerun": "whole"}}
        r = R.decide("go", "t", {"conclusion": "failure", "log": GO_LOG}, ["leaf/a.go"], None, AREAS, FILES, cfg, DEPS, MOD)
        self.assertEqual((r["mode"], r["then"]), ("whole", []))


class Cli(unittest.TestCase):
    def test_cli_go_deps_file(self):
        import io
        import tempfile
        from contextlib import redirect_stdout
        d = Path(tempfile.mkdtemp())
        (d / "deps.txt").write_text(DEPS)
        (d / "go.mod").write_text(MOD)
        (d / "log.txt").write_text(GO_LOG)
        (d / "changed.txt").write_text("leaf/a.go\n")
        (d / "files.txt").write_text("\n".join(FILES))
        (d / "areas.json").write_text(json.dumps(AREAS))
        buf = io.StringIO()
        with redirect_stdout(buf):
            R.main(["--runner", "go", "--prev-conclusion", "failure", "--log", str(d / "log.txt"),
                    "--changed-file", str(d / "changed.txt"), "--go-deps", str(d / "deps.txt"),
                    "--go-mod", str(d / "go.mod"), "--test-files", str(d / "files.txt"),
                    "--job-config", str(d / "none"), "--scope-config", str(d / "none"),
                    "--areas", str(d / "areas.json"), "--json"])
        out = json.loads(buf.getvalue())
        self.assertEqual(len(out["then"][0]), 3)


if __name__ == "__main__":
    unittest.main()
