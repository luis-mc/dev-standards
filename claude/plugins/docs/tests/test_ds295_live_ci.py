"""DS295: live CI runs in Full Progress (R5.39 to R5.41). No network: the fetch takes a fake runner."""
import json
import os
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS.parents[3] / "tools"))
import ci_live as CL  # noqa: E402
import render_artifacts as R  # noqa: E402
import test_render_artifacts as TR  # noqa: E402

NOW = "2026-10-10T12:39:00+00:00"
PR_LINKS = {"provider": "github", "repo": "o/r"}
RUNS = [
    {"name": "ci", "status": "completed", "conclusion": "success", "url": "https://github.com/o/r/actions/runs/1",
     "createdAt": "2026-10-10T12:00:00Z", "updatedAt": "2026-10-10T12:04:30Z", "headBranch": "DS9-x", "event": "pull_request"},
    {"name": "lint", "status": "in_progress", "conclusion": "", "url": "https://github.com/o/r/actions/runs/2",
     "createdAt": "2026-10-10T12:30:00Z", "updatedAt": "2026-10-10T12:31:00Z", "headBranch": "DS9-x", "event": "pull_request"},
    {"name": "deploy", "status": "completed", "conclusion": "failure", "url": "https://github.com/o/r/actions/runs/3",
     "createdAt": "2026-10-10T12:10:00Z", "updatedAt": "2026-10-10T12:10:09Z", "headBranch": "DS9-x", "event": "pull_request"},
]
TAG_RUN = {"name": "publish", "status": "queued", "conclusion": "", "url": "https://github.com/o/r/actions/runs/4",
           "createdAt": "2026-10-10T12:20:00Z", "updatedAt": "2026-10-10T12:20:00Z", "headBranch": "v1.2.0", "event": "push"}


def fake(calls=None, fail=False):
    def run(args):
        if calls is not None:
            calls.append(list(args))
        if fail:
            return 1, ""
        if args[:2] == ["pr", "view"]:
            return 0, json.dumps({"headRefOid": "abc", "mergeCommit": None})
        if "--commit" in args:
            return 0, json.dumps(RUNS)
        return 0, json.dumps([TAG_RUN])
    return run


def release():
    row = TR.release("DS9", "Release DS9", "10 Oct ~18:00", None)
    row.update(release=1, pr=7, tag="v1.2.0")
    return row


def task():
    return {"id": "DS8", "owner": "x", "status": "Running", "item": "A task", "detail": "d", "expected": "10 Oct ~15:00", "pr": 8}


class LiveCi(unittest.TestCase):
    def setUp(self):
        os.environ.pop("CLAUDE_ARTIFACTS_NO_GH", None)
        self.addCleanup(os.environ.pop, "CLAUDE_ARTIFACTS_NO_GH", None)

    def test_fetch_parses_gh_json_and_stores_ci_runs(self):
        calls, t = [], release()
        self.assertEqual(CL.refresh([t], fake(calls), NOW), 1)
        self.assertIn(["pr", "view", "7", "--json", "headRefOid,mergeCommit"], calls)
        self.assertTrue(any(c[:4] == ["run", "list", "--commit", "abc"] for c in calls))
        stored = t["ci_runs"]
        self.assertEqual(stored["fetched_at"], NOW)
        states = {r["name"]: r["state"] for r in stored["runs"]}
        self.assertEqual(states, {"ci": "passed", "lint": "running", "deploy": "failed", "publish": "queued"})
        self.assertEqual([r["kind"] for r in stored["runs"] if r["name"] == "publish"], ["tag"])

    def test_states(self):
        self.assertEqual(CL.state_of("completed", "cancelled"), "cancelled")
        self.assertEqual(CL.state_of("queued", ""), "queued")
        self.assertEqual(CL.state_of("completed", "timed_out"), "failed")

    def test_release_row_shows_name_status_link_and_time(self):
        t = release()
        CL.refresh([t], fake(), NOW)
        html = R.release_timeline([t], R._parse_iso("2026-10-10T12:39+00:00"), "Lisbon", PR_LINKS)
        self.assertIn('href="https://github.com/o/r/pull/7"', html)
        self.assertIn('href="https://github.com/o/r/actions/runs/1"', html)
        self.assertIn("ci · passed · 12:00 UTC in 4m 30s", html)
        self.assertIn("lint · running · 12:30 UTC elapsed 9m 00s", html)
        self.assertIn("deploy · failed", html)
        self.assertIn("ci-live-failed", html)
        self.assertNotIn("own run", html)

    def test_task_row_shows_pr_link_and_runs(self):
        t = task()
        CL.refresh([t], fake(), NOW)
        R.PR_LINKS_NOW = PR_LINKS
        row = R._row(t, "full-progress", {})
        self.assertIn('href="https://github.com/o/r/pull/8"', row)
        self.assertIn("lint · running", row)
        self.assertIn("actions/runs/3", row)

    def test_branch_task_without_pr_takes_runs_of_its_branch(self):
        t = {"id": "DS9", "status": "Running", "item": "x"}
        data = [dict(RUNS[0]), dict(RUNS[1], headBranch="other")]
        n = CL.refresh([t], lambda a: (0, json.dumps(data)), NOW)
        self.assertEqual(n, 1)
        self.assertEqual([r["name"] for r in t["ci_runs"]["runs"]], ["ci"])

    def test_failed_fetch_keeps_the_old_runs(self):
        t = release()
        CL.refresh([t], fake(), NOW)
        before = json.dumps(t["ci_runs"])
        self.assertEqual(CL.refresh([t], fake(fail=True), "2026-10-10T13:00:00+00:00"), 0)
        self.assertEqual(json.dumps(t["ci_runs"]), before)
        html = R.release_timeline([t], R._parse_iso("2026-10-10T13:00+00:00"), "Lisbon", PR_LINKS)
        self.assertIn("as of 12:39 UTC", html)

    def test_raising_runner_keeps_the_old_runs(self):
        t = release()
        CL.refresh([t], fake(), NOW)
        before = json.dumps(t["ci_runs"])

        def boom(args):
            raise OSError("no gh")
        CL.refresh([t], boom, "2026-10-10T13:00:00+00:00")
        self.assertEqual(json.dumps(t["ci_runs"]), before)

    def test_no_gh_skips_the_fetch(self):
        os.environ["CLAUDE_ARTIFACTS_NO_GH"] = "1"
        calls, t = [], release()
        self.assertEqual(CL.refresh([t], fake(calls), NOW), 0)
        self.assertEqual(calls, [])
        self.assertNotIn("ci_runs", t)

    def test_live_and_dropped_tasks_are_not_fetched(self):
        calls, t = [], dict(task(), status="Live")
        CL.refresh([t], fake(calls), NOW)
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
