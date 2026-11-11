"""DL183: the `rerun-first/held` commit status closes the green-without-run-2 gap. Fakes only; no network."""
import importlib.util
import io
import re
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
SHARED = HERE.parent / "templates" / "shared" / "scripts" / "delivery"
CI = HERE.parent / "templates" / "ts" / ".github" / "workflows" / "ci.yml"
sys.path.insert(0, str(SHARED))
import ci_watch as cw  # noqa: E402

spec = importlib.util.spec_from_file_location("ci_rerun_first", SHARED / "ci_rerun_first.py")
R = importlib.util.module_from_spec(spec)
spec.loader.exec_module(R)

SHA = "c" * 40
TEXT = CI.read_text(encoding="utf-8")


def step():
    """The e2e job's closing step."""
    m = re.search(r"- name: Close the rerun-first/held status\n(.*?)(?=\n      #|\Z)", block("e2e"), re.S)
    assert m
    return m.group(1)


def block(name):
    """The text of one top-level job."""
    m = re.search(r"^  %s:\n(.*?)(?=^  [a-z][a-z0-9-]*:\n|\Z)" % re.escape(name), TEXT, re.M | re.S)
    assert m, name
    return m.group(1)


class WorkflowText(unittest.TestCase):
    def test_pending_is_set_in_plan_before_held_jobs(self):
        plan = block("plan")
        self.assertIn("--hold-status", plan)
        self.assertIn("statuses: write", plan)
        # the status is set by the plan step, which every held job (needs: plan) waits for
        for name in ("integration", "e2e-shard"):
            self.assertRegex(block(name), r"needs:.*plan")

    def test_only_the_status_jobs_get_statuses_write(self):
        holders = [n for n in re.findall(r"^  ([a-z][a-z0-9-]*):\n", TEXT, re.M) if "statuses: write" in block(n)]
        self.assertEqual(sorted(holders), ["e2e", "plan"])
        self.assertNotIn("statuses", TEXT.split("jobs:")[0])  # top-level permissions unchanged

    def test_second_run_closes_the_status(self):
        job = step()
        self.assertIn("always()", job)
        self.assertIn("JOB_STATUS", job)
        self.assertIn("workflow_dispatch", job)
        for state in ("success", "failure", "error"):
            self.assertIn(state, job)
        self.assertIn("cancelled) [ \"$state\" = failure ] || state=error", job)
        self.assertIn("--set-status", job)

    def test_first_set_failed_sets_failure(self):
        job = step()
        self.assertIn("first set failed; held jobs not run", job)
        self.assertIn("plan.outputs.rerun == 'true'", job)

    def test_job_graph_has_no_new_job(self):
        jobs = set(re.findall(r"^  ([a-z][a-z0-9-]*):\n", TEXT.split("\njobs:\n")[1], re.M))
        self.assertEqual(jobs, {"decide", "plan", "verify", "integration", "e2e-shard", "e2e"})

    def test_status_step_runs_only_for_rerun_first(self):
        cond = re.search(r"if: (.*)", step()).group(1)
        self.assertIn("inputs.only != ''", cond)
        self.assertIn("rerun == 'true'", cond)

    def test_one_constant_names_the_context(self):
        self.assertEqual(R.STATUS_CONTEXT, "rerun-first/held")
        self.assertEqual(cw.HELD_CONTEXT, R.STATUS_CONTEXT)


class ScriptStatus(unittest.TestCase):
    def test_set_status_posts_the_context(self):
        with mock.patch.object(R, "run") as run:
            R.post_status("acme/widget", SHA, "success", "held jobs passed", "http://x/1")
        cmd = run.call_args[0][0]
        self.assertIn(f"repos/acme/widget/statuses/{SHA}", cmd)
        self.assertIn("context=rerun-first/held", cmd)
        self.assertIn("state=success", cmd)

    def test_bad_state_is_refused(self):
        with self.assertRaises(R.Undecided):
            R.post_status("acme/widget", SHA, "green", "x")

    def test_hold_status_failure_holds_nothing(self):
        decided = (True, ["verify"], ["integration"], "r")
        with mock.patch.object(R, "decide", return_value=decided), \
                mock.patch.object(R, "post_status", side_effect=R.Undecided("denied")), \
                redirect_stdout(io.StringIO()) as out:
            R.main(["--repo", "acme/widget", "--sha", SHA, "--hold-status", "--json"])
        self.assertIn('"rerun": false', out.getvalue())

    def test_hold_status_posts_pending_when_holding(self):
        decided = (True, ["verify"], ["integration"], "r")
        with mock.patch.object(R, "decide", return_value=decided), \
                mock.patch.object(R, "post_status") as post, redirect_stdout(io.StringIO()) as out:
            R.main(["--repo", "acme/widget", "--sha", SHA, "--hold-status", "--json"])
        self.assertEqual(post.call_args[0][2], "pending")
        self.assertIn('"rerun": true', out.getvalue())

    def test_no_status_without_a_hold(self):
        with mock.patch.object(R, "decide", return_value=(False, [], [], "r")), \
                mock.patch.object(R, "post_status") as post, redirect_stdout(io.StringIO()):
            R.main(["--repo", "acme/widget", "--sha", SHA, "--hold-status", "--json"])
        post.assert_not_called()


def run1(**kw):
    return {"databaseId": 1, "workflowName": "CI", "status": "completed", "conclusion": "success",
            "event": "pull_request", "headSha": SHA, **kw}


def run2(**kw):
    return run1(databaseId=2, event="workflow_dispatch", **kw)


class WatchHeld(unittest.TestCase):
    def watch(self, run_lists, statuses, opted_in=True):
        """Poll results in order (the last repeats); `statuses` is the held context state or None."""
        seq = list(run_lists)

        def list_runs(*_a, **_k):
            return seq.pop(0) if len(seq) > 1 else seq[0]

        got = {} if statuses is None else {cw.HELD_CONTEXT: statuses}
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(cw.shutil, "which", return_value="gh"), \
                mock.patch.object(cw, "resolve_sha", return_value=SHA), \
                mock.patch.object(cw, "list_runs", side_effect=list_runs), \
                mock.patch.object(cw, "list_statuses", return_value=got) as ls, \
                mock.patch.object(cw, "rerun_first_on", return_value=opted_in), \
                mock.patch.object(cw, "add_other_workflows", side_effect=lambda r, *a, **k: r), \
                mock.patch.object(cw, "executed_jobs", return_value=True), \
                mock.patch.object(cw, "has_open_pr", return_value=True), \
                mock.patch.object(cw, "print_slowest_job_summary"), \
                mock.patch.object(cw, "ledger_ci"), mock.patch.object(cw, "finish", side_effect=lambda c, *a: c), \
                mock.patch.object(cw.time, "sleep"), \
                redirect_stdout(out), mock.patch.object(sys, "stderr", err):
            code = cw.main([SHA, "--interval", "0", "--timeout", "60"])
        self.status_calls = ls.call_count
        return code, out.getvalue()

    def test_waits_for_run_2_then_returns(self):
        code, out = self.watch([[run1()], [run1()], [run1(), run2(status="in_progress", conclusion=None)],
                                [run1(), run2()]], "pending")
        self.assertEqual(code, 0)
        self.assertIn("waiting for held jobs (run 2)", out)
        self.assertIn("2 ci.yml run(s)", out)

    def test_failing_run_2_fails_the_watch(self):
        code, _ = self.watch([[run1()], [run1(), run2(conclusion="failure")]], "pending")
        self.assertEqual(code, 1)

    def test_no_status_is_unchanged(self):
        code, out = self.watch([[run1()]], None)
        self.assertEqual(code, 0)
        self.assertNotIn("held jobs", out)

    def test_not_opted_in_makes_no_status_call(self):
        code, out = self.watch([[run1()]], "pending", opted_in=False)
        self.assertEqual(code, 0)
        self.assertEqual(self.status_calls, 0)
        self.assertNotIn("held jobs", out)

    def test_opt_in_reads_the_config(self):
        import json, tempfile
        with tempfile.TemporaryDirectory() as d:
            cfg = Path(d) / "scripts" / "delivery"
            cfg.mkdir(parents=True)
            (cfg / "ci-areas.json").write_text(json.dumps({"rerun_first": True}))
            with mock.patch.object(cw, "config_root", return_value=Path(d)):
                self.assertTrue(cw.rerun_first_on())
                (cfg / "ci-areas.json").write_text("{}")
                self.assertFalse(cw.rerun_first_on())

    def test_settled_status_does_not_wait(self):
        code, out = self.watch([[run1()]], "success")
        self.assertEqual(code, 0)
        self.assertNotIn("held jobs", out)


if __name__ == "__main__":
    unittest.main()
