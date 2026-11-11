"""DL226: agent_ci reads docs/work/<TASK>/REPORT.md first, then the old path; ci_watch waits for every run and never
calls an in-progress run or job failed. Stubbed gh and git; no network."""
import contextlib
import io
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
SHARED = HERE.parent / "templates" / "shared" / "scripts" / "delivery"
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(SHARED))

import agent_ci as ac  # noqa: E402
import ci_watch as cw  # noqa: E402

SHA = "a" * 40
NEW = "docs/work/T9/REPORT.md"
OLD = "docs/work/reports/T9.md"


def git_show(files):
    def run(argv, **kw):
        path = argv[-1].split(":", 1)[1]
        if argv[:2] == ["git", "show"] and path in files:
            return subprocess.CompletedProcess(argv, 0, files[path], "")
        return subprocess.CompletedProcess(argv, 1, "", "missing")
    return run


class AgentCiReport(unittest.TestCase):
    cfg = dict(ac.DEFAULTS)

    def state(self, files):
        with mock.patch.object(ac.subprocess, "run", git_show(files)):
            return ac.report_state("claude/T9-x", self.cfg)

    def test_per_task_report_is_first(self):
        self.assertEqual(ac.report_paths(self.cfg, "T9")[:2], [NEW, OLD])

    def test_finds_per_task_report(self):
        self.assertEqual(self.state({NEW: "x\nCODE DONE\n"}), "done")

    def test_finds_old_report(self):
        self.assertEqual(self.state({OLD: "CODE DONE\n"}), "done")

    def test_open_and_missing(self):
        self.assertEqual(self.state({NEW: "working\n"}), "open")
        self.assertEqual(self.state({}), "missing")

    def test_skip_line_names_both_paths(self):
        out = io.StringIO()
        with mock.patch.object(ac, "git", return_value="abc123\n"), \
                mock.patch.object(ac, "branches", return_value=["claude/T9-x"]), \
                mock.patch.object(ac, "pick", return_value=["claude/T9-x"]), \
                mock.patch.object(ac, "report_state", return_value="missing"), \
                contextlib.redirect_stdout(out):
            ac.one_pass(dict(self.cfg), dry_run=True)
        self.assertIn(NEW, out.getvalue())
        self.assertIn(OLD, out.getvalue())


def run_watch(poll_runs, jobs_for):
    """Run ci_watch.main over a list of run lists (one per poll); returns (code, stdout, polls used)."""
    polls = iter(poll_runs)
    used = []

    def list_runs(*a, **k):
        used.append(1)
        return next(polls)

    def gh_json(args):
        return {"jobs": jobs_for}

    out = io.StringIO()
    with mock.patch.object(cw.shutil, "which", return_value="gh"), \
            mock.patch.object(cw, "resolve_repo", side_effect=lambda r: r or "acme/widget"), \
            mock.patch.object(cw, "resolve_sha", return_value=SHA), \
            mock.patch.object(cw, "list_runs", side_effect=list_runs), \
            mock.patch.object(cw, "add_other_workflows", side_effect=lambda runs, *a, **k: runs), \
            mock.patch.object(cw, "gh_json", side_effect=gh_json), \
            mock.patch.object(cw, "gh_text", return_value=""), \
            mock.patch.object(cw, "warn_queued_jobs"), \
            mock.patch.object(cw.fallback_launch, "check_and_launch"), \
            mock.patch.object(cw, "executed_jobs", return_value=True), \
            mock.patch.object(cw, "waiting_for_held_jobs", return_value=False), \
            mock.patch.object(cw, "print_slowest_job_summary"), \
            mock.patch.object(cw, "ledger_ci"), \
            mock.patch.object(cw, "finish", side_effect=lambda code, *a, **k: code), \
            mock.patch.object(cw.time, "sleep"), \
            contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        code = cw.main([SHA, "--no-fallback", "--interval", "0", "--timeout", "100"])
    return code, out.getvalue(), len(used)


def run(rid, name, status, conclusion):
    return {"databaseId": rid, "workflowName": name, "status": status, "conclusion": conclusion,
            "event": "push", "headSha": SHA}


class CiWatchWaits(unittest.TestCase):
    def test_waits_for_in_progress_run_then_reports_failure(self):
        first = [run(1, "ci", "completed", "failure"), run(2, "ci", "completed", "success"),
                 run(3, "Package", "in_progress", None)]
        last = [run(1, "ci", "completed", "failure"), run(2, "ci", "completed", "success"),
                run(3, "Package", "completed", "success")]
        code, out, polls = run_watch([first, first, last], [{"name": "build", "status": "completed",
                                                              "conclusion": "failure", "steps": []}])
        self.assertEqual(code, 1)
        self.assertEqual(polls, 3)
        self.assertIn("1 of 3 ci.yml run(s)", out)

    def test_in_progress_run_alone_is_never_failure(self):
        runs = [run(1, "Package", "in_progress", None)]
        done = [run(1, "Package", "completed", "success")]
        code, out, polls = run_watch([runs, done], [])
        self.assertEqual(code, 0)
        self.assertNotIn("did not succeed", out)

    def test_in_progress_job_not_labelled_failed(self):
        jobs = [{"name": "pkg", "status": "in_progress", "conclusion": None, "steps": []},
                {"name": "lint", "status": "completed", "conclusion": "failure", "steps": []}]
        out = io.StringIO()
        with mock.patch.object(cw, "gh_json", return_value={"jobs": jobs}), \
                mock.patch.object(cw, "gh_text", return_value=""), contextlib.redirect_stdout(out):
            cw.print_failed_jobs(run(1, "ci", "completed", "failure"), None)
        self.assertIn("FAILED job: lint", out.getvalue())
        self.assertNotIn("FAILED job: pkg", out.getvalue())


if __name__ == "__main__":
    unittest.main()
