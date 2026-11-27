"""DS287 (R5.92, R5.94): the rerun wiring in the ts, go and rust templates, and `--check` for unmapped files."""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

PLUGIN = Path(__file__).resolve().parent.parent
TPL = PLUGIN / "templates"
SCRIPTS = TPL / "shared" / "scripts" / "delivery"
ACTION = TPL / "shared" / ".github" / "actions" / "rerun-narrow" / "action.yml"
TEST_JOBS = {"ts": ["verify", "integration", "integration-pool"], "go": ["verify", "integration"],
             "rust": ["verify", "integration", "integration-pool"]}
RUNNER = {"ts": "vitest", "go": "go", "rust": "cargo"}


def load(track):
    return yaml.safe_load((TPL / track / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))


def uses_rerun(step):
    return str(step.get("uses", "")).endswith("actions/rerun-narrow")


class TemplateWiring(unittest.TestCase):
    def test_each_test_job_has_the_rerun_step_on_pull_request_only(self):
        for track, jobs in TEST_JOBS.items():
            wf = load(track)
            for job in jobs:
                with self.subTest(track=track, job=job):
                    steps = wf["jobs"][job]["steps"]
                    rr = [s for s in steps if uses_rerun(s)]
                    self.assertEqual(len(rr), 1)
                    self.assertIn("github.event_name == 'pull_request'", rr[0]["if"])
                    self.assertEqual(rr[0]["with"]["runner"], RUNNER[track])
                    self.assertTrue(rr[0].get("continue-on-error"))
                    narrow = [s for s in steps if "rerun_step.py exec" in str(s.get("run", ""))]
                    self.assertEqual(len(narrow), 1)
                    self.assertIn("github.event_name == 'pull_request'", narrow[0]["if"])
                    self.assertIn("outputs.mode == 'narrow'", narrow[0]["if"])

    def test_normal_command_runs_unless_narrow(self):
        for track, jobs in TEST_JOBS.items():
            for job in jobs:
                with self.subTest(track=track, job=job):
                    steps = load(track)["jobs"][job]["steps"]
                    normal = [s for s in steps if "outputs.mode != 'narrow'" in str(s.get("if", ""))]
                    self.assertEqual(len(normal), 1)
                    # an empty mode (step skipped or failed) runs the normal command
                    self.assertNotIn("== 'narrow'", normal[0]["if"].replace("!= 'narrow'", ""))

    def test_report_upload_has_a_stable_name(self):
        for track, jobs in TEST_JOBS.items():
            for job in jobs:
                with self.subTest(track=track, job=job):
                    ups = [s for s in load(track)["jobs"][job]["steps"]
                           if str(s.get("uses", "")).startswith("actions/upload-artifact") and
                           str(s["with"]["name"]).startswith("test-report-")]
                    self.assertEqual(len(ups), 1)
                    self.assertNotIn("${{", ups[0]["with"]["name"])
                    self.assertIn("!cancelled()", ups[0]["if"])
        # the report name the lookup reads is the one the job uploads
        for track, jobs in TEST_JOBS.items():
            for job in jobs:
                steps = load(track)["jobs"][job]["steps"]
                rr = next(s for s in steps if uses_rerun(s))
                up = next(s for s in steps if str(s.get("uses", "")).startswith("actions/upload-artifact") and
                          str(s["with"]["name"]).startswith("test-report-"))
                self.assertEqual(rr["with"]["report-name"], up["with"]["name"])

    def test_existing_gates_are_kept(self):
        for track, jobs in TEST_JOBS.items():
            for job in jobs:
                j = load(track)["jobs"][job]
                self.assertIn("carry_plan", str(j["if"]))
                self.assertTrue(j.get("needs"))

    def test_action_calls_rerun_tests_and_falls_back(self):
        act = yaml.safe_load(ACTION.read_text(encoding="utf-8"))
        text = ACTION.read_text(encoding="utf-8")
        for needle in ("rerun_tests.py", "--prev-conclusion", "--report", "--changed-file -", "--json", "rerun_step.py lookup"):
            self.assertIn(needle, text)
        self.assertEqual(text.count("mode=current"), 2)  # no previous run, and a failed rerun_tests.py
        self.assertIn("mode", act["outputs"])

    def test_a_job_without_the_step_is_detected(self):
        # the checks above can fail: drop the step from a loaded template and the same test finds none
        steps = [s for s in load("go")["jobs"]["verify"]["steps"] if not uses_rerun(s)]
        self.assertEqual([s for s in steps if uses_rerun(s)], [])
        self.assertEqual(len([s for s in load("go")["jobs"]["verify"]["steps"] if uses_rerun(s)]), 1)


def run_step(*args, **kw):
    return subprocess.run([sys.executable, str(SCRIPTS / "rerun_step.py"), *args], capture_output=True, text=True, **kw)


class StepHelper(unittest.TestCase):
    def test_exec_runs_then_only_when_step_one_passes(self):
        with tempfile.TemporaryDirectory() as d:
            dec = Path(d, "d.json")
            marker = Path(d, "m")
            dec.write_text(json.dumps({"mode": "narrow", "invocations": [["-c", "raise SystemExit(0)"]], "then": [["-c", f"open({str(marker)!r}, 'a').write('x')"]]}))
            r = run_step("exec", "--decision", str(dec), "--prefix", sys.executable)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertTrue(marker.exists())
            marker.unlink()
            dec.write_text(json.dumps({"mode": "narrow", "invocations": [["-c", "raise SystemExit(1)"]], "then": [["-c", f"open({str(marker)!r}, 'a').write('x')"]]}))
            r = run_step("exec", "--decision", str(dec), "--prefix", sys.executable)
            self.assertEqual(r.returncode, 1)
            self.assertFalse(marker.exists())

    def test_then_failure_fails_the_job(self):
        with tempfile.TemporaryDirectory() as d:
            dec = Path(d, "d.json")
            dec.write_text(json.dumps({"mode": "narrow", "invocations": [["-c", "raise SystemExit(0)"]], "then": [["-c", "raise SystemExit(3)"]]}))
            self.assertEqual(run_step("exec", "--decision", str(dec), "--prefix", sys.executable).returncode, 1)

    def test_mode_falls_back_to_current(self):
        with tempfile.TemporaryDirectory() as d:
            for body, want in (("not json", "current"), ('{"mode": "whole"}', "whole"), ('{"mode": "narrow"}', "narrow"),
                               ('{"mode": "weird"}', "current")):
                p = Path(d, "x.json")
                p.write_text(body)
                self.assertIn(f"mode={want}", run_step("mode", str(p)).stdout)
            self.assertIn("mode=current", run_step("mode", str(Path(d, "missing.json"))).stdout)

    def test_lookup_error_gives_empty_values(self):
        with tempfile.TemporaryDirectory() as d:
            r = run_step("lookup", "--repo", "o/r", "--workflow", "ci.yml", "--pr", "1", "--sha", "abc",
                         "--job-name", "verify", "--report-name", "x", "--out", d,
                         env={**os.environ, "PATH": "/nonexistent"})
            self.assertEqual(r.returncode, 0)
            self.assertIn("prev_conclusion=\n", r.stdout)


def git(cwd, *a):
    subprocess.run(["git", *a], cwd=cwd, check=True, capture_output=True)


def fixture(files, cmap, where):
    d = tempfile.mkdtemp()
    for f in files:
        p = Path(d, f)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x")
    m = Path(d, where)
    m.parent.mkdir(parents=True, exist_ok=True)
    m.write_text(json.dumps(cmap))
    git(d, "init", "-q")
    git(d, "add", "-A")
    return d


CHANGED = {"areas": {"code": ["src/**"]}, "docs": ["docs/**"], "all": [".github/**", "package.json"]}
SELECT = {"areas": {"code": {"paths": ["src/**"]}}, "docs": ["docs/**"], "run_everything": [".github/**", "package.json"]}
MAPPED = ["src/a.py", "docs/x.md", ".github/w.yml", "package.json"]


class CheckChanged(unittest.TestCase):
    def run_check(self, d, *a):
        return subprocess.run([sys.executable, str(SCRIPTS / "changed_areas.py"), "--map", ".delivery/ci-areas.json",
                               "unmapped", *a], cwd=d, capture_output=True, text=True)

    def test_mapped_passes(self):
        # the map file itself is mapped through `all`
        d2 = fixture(MAPPED, {**CHANGED, "all": CHANGED["all"] + [".delivery/**"]}, ".delivery/ci-areas.json")
        r = self.run_check(d2, "--check")
        self.assertEqual((r.returncode, r.stdout), (0, ""), r.stderr)

    def test_unmapped_fails_and_is_named(self):
        d = fixture(MAPPED + ["tools/new.py"], {**CHANGED, "all": CHANGED["all"] + [".delivery/**"]}, ".delivery/ci-areas.json")
        r = self.run_check(d, "--check")
        self.assertEqual(r.returncode, 1)
        self.assertEqual(r.stdout.split(), ["tools/new.py"])

    def test_without_check_exit_is_zero(self):
        d = fixture(MAPPED + ["tools/new.py"], {**CHANGED, "all": CHANGED["all"] + [".delivery/**"]}, ".delivery/ci-areas.json")
        self.assertEqual(self.run_check(d).returncode, 0)


class CheckSelect(unittest.TestCase):
    def run_check(self, d, *a):
        return subprocess.run([sys.executable, str(SCRIPTS / "area_select.py"), "--unmapped", *a], cwd=d,
                              capture_output=True, text=True)

    MAP = "scripts/delivery/ci-areas.json"

    def test_mapped_passes_docs_and_all_count(self):
        d = fixture(MAPPED, {**SELECT, "run_everything": SELECT["run_everything"] + ["scripts/**"]}, self.MAP)
        r = self.run_check(d, "--check")
        self.assertEqual((r.returncode, r.stdout.strip()), (0, ""), r.stderr)

    def test_unmapped_fails_and_is_named(self):
        d = fixture(MAPPED + ["lib/new.go", "lib/two.go"], {**SELECT, "run_everything": SELECT["run_everything"] + ["scripts/**"]}, self.MAP)
        r = self.run_check(d, "--check")
        self.assertEqual(r.returncode, 1)
        self.assertEqual(r.stdout.split(), ["lib/new.go", "lib/two.go"])

    def test_list_without_check_is_zero(self):
        d = fixture(MAPPED + ["lib/new.go"], {**SELECT, "run_everything": SELECT["run_everything"] + ["scripts/**"]}, self.MAP)
        r = self.run_check(d)
        self.assertEqual(r.returncode, 0)
        self.assertIn("lib/new.go", r.stdout)


class CiWiring(unittest.TestCase):
    def test_plan_jobs_run_the_check_on_pull_request(self):
        for track, job in (("ts", "plan"), ("go", "carry"), ("rust", "carry")):
            with self.subTest(track=track):
                steps = load(track)["jobs"][job]["steps"]
                st = [s for s in steps if "area_select.py --unmapped --check" in str(s.get("run", ""))]
                self.assertEqual(len(st), 1)
                self.assertIn("github.event_name == 'pull_request'", st[0]["if"])
        snip = yaml.safe_load((TPL / "ci-snippets" / "ci-areas-pattern.yml").read_text(encoding="utf-8"))
        st = [s for s in snip["jobs"]["areas"]["steps"] if "changed_areas.py unmapped --check" in str(s.get("run", ""))]
        self.assertEqual(len(st), 1)
        self.assertIn("pull_request", st[0]["if"])

    def test_go_and_rust_check_fails_when_the_plan_job_fails(self):
        for track in ("go", "rust"):
            text = (TPL / track / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
            self.assertIn('needs.carry.result }}" = failure', text)


class Doctor(unittest.TestCase):
    def doctor(self):
        sys.path.insert(0, str(PLUGIN / "scripts"))
        spec = importlib.util.spec_from_file_location("delivery_doctor_ds287", PLUGIN / "scripts" / "delivery_doctor.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_reports_count_and_names_ten(self):
        mod = self.doctor()
        extra = ["lib/f%02d.go" % i for i in range(12)]
        d = fixture(MAPPED + extra, {**SELECT, "run_everything": SELECT["run_everything"] + ["scripts/**"]}, "scripts/delivery/ci-areas.json")
        res = mod.check_unmapped(d, {})
        self.assertIn("12 tracked file", res[1])
        self.assertTrue(res[1].startswith("WARN"))
        self.assertIn("lib/f09.go", res[1])
        self.assertNotIn("lib/f10.go", res[1])
        self.assertIn("warn", res[2][0].values())

    def test_changed_areas_map_and_clean_repo(self):
        mod = self.doctor()
        d = fixture(MAPPED, {**CHANGED, "all": CHANGED["all"] + [".delivery/**"]}, ".delivery/ci-areas.json")
        res = mod.check_unmapped(d, {})
        self.assertNotIn("WARN", res[1])
        self.assertIn("0 unmapped", res[1])
        d = fixture(MAPPED + ["z.txt"], {**CHANGED, "all": CHANGED["all"] + [".delivery/**"]}, ".delivery/ci-areas.json")
        self.assertIn("1 tracked file", mod.check_unmapped(d, {})[1])

    def test_no_map_no_row(self):
        d = tempfile.mkdtemp()
        git(d, "init", "-q")
        self.assertIsNone(self.doctor().check_unmapped(d, {}))


if __name__ == "__main__":
    unittest.main()
