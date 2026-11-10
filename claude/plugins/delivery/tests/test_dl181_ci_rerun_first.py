"""DL181: a repeat CI run starts with the jobs that have not passed yet."""
import importlib.util
import json
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

TEMPLATES = Path(__file__).resolve().parents[1] / "templates"
CI = TEMPLATES / "ts" / ".github" / "workflows" / "ci.yml"
spec = importlib.util.spec_from_file_location("ci_rerun_first", TEMPLATES / "shared/scripts/delivery/ci_rerun_first.py")
R = importlib.util.module_from_spec(spec)
spec.loader.exec_module(R)

NEW, OLD = "b" * 40, "a" * 40


def job(name, conclusion):
    return {"name": name, "conclusion": conclusion}


GREEN = [job("lint, types, boundaries, unit + contract tests", "success"),
         job("integration tests (ephemeral Postgres)", "success"),
         job("web E2E shard 1", "success"), job("web E2E shard 2", "success")]


class FakeGh:
    def __init__(self, runs=None, jobs=None, error=None):
        self.runs = runs if runs is not None else [{"id": 7, "head_sha": OLD, "created_at": "2026-11-10T10:00:00Z"}]
        self.jobs, self.error, self.calls = jobs or GREEN, error, []

    def __call__(self, path, **query):
        self.calls.append((path, query))
        if self.error:
            raise R.Undecided(self.error)
        if path.endswith("/runs"):
            return {"workflow_runs": self.runs}
        return {"jobs": self.jobs}


def decide(gh, on=True, selected=None, only=""):
    with tempfile.TemporaryDirectory() as d:
        cfg = Path(d) / "ci-areas.json"
        cfg.write_text(json.dumps({"rerun_first": on}))
        args = R.argparse.Namespace(repo="o/r", workflow="ci.yml", branch="br", sha=NEW, event="pull_request",
                                    only=only, selected=selected, config=str(cfg))
        with mock.patch.object(R, "gh_api", gh):
            return R.decide(args)


class ScriptTests(unittest.TestCase):
    def test_no_previous_run_is_undecided(self):
        with self.assertRaises(R.Undecided):
            decide(FakeGh(runs=[]))

    def test_main_fails_open_on_no_previous_run(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = Path(d) / "c.json"
            cfg.write_text('{"rerun_first": true}')
            out = Path(d) / "out"
            with mock.patch.object(R, "gh_api", FakeGh(runs=[])), mock.patch.dict(os.environ, {"GITHUB_OUTPUT": str(out)}):
                self.assertEqual(R.main(["--repo", "o/r", "--workflow", "ci.yml", "--branch", "b", "--sha", NEW,
                                         "--config", str(cfg)]), 0)
            self.assertIn("rerun=false", out.read_text())
            self.assertIn("first=[]", out.read_text())

    def test_same_head_is_not_a_previous_run(self):
        gh = FakeGh(runs=[{"id": 9, "head_sha": NEW, "created_at": "2026-11-10T11:00:00Z"}])
        with self.assertRaises(R.Undecided):
            decide(gh)

    def test_all_green_means_false_and_empty_first(self):
        rerun, first, held, reason = decide(FakeGh())
        self.assertEqual((rerun, first, held), (False, [], []))
        self.assertIn("nothing to put first", reason)

    def test_failed_cancelled_and_skipped_while_selected(self):
        jobs = [job("lint, types, boundaries, unit + contract tests", "success"),
                job("integration tests (ephemeral Postgres)", "failure"),
                job("web E2E shard 1", "cancelled"), job("web E2E shard 2", "skipped")]
        rerun, first, held, _ = decide(FakeGh(jobs=jobs))
        self.assertEqual(first, ["e2e-shard", "integration"])
        self.assertFalse(rerun)  # both holdable jobs are first: nothing to hold
        self.assertEqual(held, [])

    def test_failed_verify_holds_the_passed_jobs(self):
        jobs = [job("lint, types, boundaries, unit + contract tests", "failure")] + GREEN[1:]
        rerun, first, held, _ = decide(FakeGh(jobs=jobs))
        self.assertEqual((rerun, first, sorted(held)), (True, ["verify"], ["e2e-shard", "integration"]))

    def test_skipped_while_selected_is_first_but_not_selected_is_not(self):
        jobs = [GREEN[0], job("integration tests (ephemeral Postgres)", "success"), job("web E2E shard 1", "skipped"),
                job("web E2E shard 2", "skipped")]
        rerun, first, held, _ = decide(FakeGh(jobs=jobs), selected="integration,e2e-shard")
        self.assertEqual((rerun, first, held), (True, ["e2e-shard"], ["integration"]))
        rerun, first, held, _ = decide(FakeGh(jobs=jobs), selected="integration")
        self.assertEqual((rerun, first), (False, []))

    def test_matrix_shards_collapse(self):
        self.assertEqual(R.job_key("web E2E shard 2"), "e2e-shard")
        self.assertEqual(R.job_key("build (3)"), "build")
        self.assertEqual(R.job_key("integration tests (ephemeral Postgres)"), "integration")

    def test_newest_previous_head_is_used(self):
        runs = [{"id": 1, "head_sha": "c" * 40, "created_at": "2026-11-10T08:00:00Z"},
                {"id": 2, "head_sha": OLD, "created_at": "2026-11-10T10:00:00Z"}]
        gh = FakeGh(runs=runs)
        decide(gh)
        self.assertIn("runs/2/jobs", gh.calls[-1][0])

    def test_gh_error_is_false_through_main(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = Path(d) / "c.json"
            cfg.write_text('{"rerun_first": true}')
            with mock.patch.object(R, "gh_api", FakeGh(error="boom")), mock.patch("builtins.print") as pr:
                self.assertEqual(R.main(["--repo", "o/r", "--workflow", "ci.yml", "--branch", "b", "--sha", NEW,
                                         "--config", str(cfg), "--json"]), 0)
            data = json.loads(pr.call_args[0][0])
            self.assertFalse(data["rerun"])
            self.assertIn("boom", data["reason"])

    def test_key_off_or_missing_makes_no_api_call(self):
        gh = FakeGh()
        self.assertFalse(decide(gh, on=False)[0])
        self.assertEqual(gh.calls, [])

    def test_only_holds_the_others_and_never_reruns(self):
        gh = FakeGh()
        rerun, first, held, _ = decide(gh, on=False, only="integration")
        self.assertEqual((rerun, first, held), (False, ["integration"], ["e2e-shard"]))
        self.assertEqual(gh.calls, [])


class WorkflowTextTests(unittest.TestCase):
    text = CI.read_text(encoding="utf-8")

    def test_key_and_script_are_wired(self):
        self.assertIn("ci_rerun_first.py", self.text)
        self.assertIn("rerun_first", self.text)
        self.assertIn("only:", self.text)
        self.assertIn("rerun: ${{ steps.rerun.outputs.rerun }}", self.text)
        self.assertIn("held: ${{ steps.rerun.outputs.held }}", self.text)

    def test_job_graph_unchanged(self):
        import test_dl147_workflow_needs as N
        jobs = N.read_jobs(self.text)
        self.assertEqual(set(jobs), {"decide", "plan", "verify", "integration", "e2e-shard", "e2e"})
        self.assertEqual(jobs["verify"]["needs"], ["decide"])
        self.assertEqual(jobs["integration"]["needs"], ["decide", "plan"])
        self.assertEqual(jobs["e2e-shard"]["needs"], ["decide", "plan"])
        self.assertEqual(jobs["e2e"]["needs"], ["decide", "plan", "verify", "integration", "e2e-shard"])

    def test_key_off_leaves_every_job_running(self):
        # A hold is a planned skip: the plan outputs turn 'false'. With the key off `held` is empty, so the
        # outputs equal the area_select outputs and the job conditions (untouched) run the jobs.
        for name, out in (("integration", "integration"), ("e2e-shard", "e2e")):
            m = re.search(r"%s: \$\{\{ contains\(format\(',\{0\},', steps\.rerun\.outputs\.held\), ',%s,'\) "
                          r"&& 'false' \|\| steps\.areas\.outputs\.%s \}\}" % (out, name, out), self.text)
            self.assertTrue(m, name)
        self.assertNotIn("',verify,'", self.text)  # verify is never held
        self.assertNotIn("held", "".join(l for l in self.text.splitlines() if l.startswith("    if:")))

    def test_second_run_is_the_last_step_family_of_e2e(self):
        i = self.text.index("Dispatch the second run")
        self.assertGreater(i, self.text.index("  e2e:\n    name: web E2E"))
        self.assertIn("needs.plan.outputs.rerun == 'true'", self.text)
        self.assertIn("gh workflow run ci.yml", self.text)


if __name__ == "__main__":
    unittest.main()
