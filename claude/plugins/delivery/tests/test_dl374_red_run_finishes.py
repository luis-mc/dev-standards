"""DL374 / DL-97, DL-98: a red release run finishes; no fail-fast on release PR CI. gh is stubbed."""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
SHARED = HERE.parent / "templates" / "shared" / "scripts" / "delivery"
sys.path.insert(0, str(HERE.parent / "scripts"))
sys.path.insert(0, str(SHARED))

import cancel_joined_runs as CJ  # noqa: E402
import delivery_doctor as D  # noqa: E402
import hook_pre_tool as P  # noqa: E402
import hooklib as H  # noqa: E402

CFG = {"join_branch_re": r"^release/\d+[a-z]?$"}


def state(branch, status, jobs):
    return {"headBranch": branch, "status": status, "jobs": jobs}


RED_RUNNING = [{"status": "completed", "conclusion": "failure"}, {"status": "in_progress", "conclusion": ""}]
RED_DONE = [{"status": "completed", "conclusion": "failure"}, {"status": "completed", "conclusion": "success"}]
GREEN_RUNNING = [{"status": "completed", "conclusion": "success"}, {"status": "in_progress", "conclusion": ""}]


def verdict(cmd, st):
    """(denial or None, warnings) for a command with gh run view returning st (None: gh fails)."""
    err = io.StringIO()
    with mock.patch.object(P, "read_run_state", return_value=st), contextlib.redirect_stderr(err):
        try:
            for seg in H.segments(cmd):
                if P.cancel_run_id(seg):
                    w = P.check_cancel_red_run(seg, cmd, CFG, ".")
                    if w:
                        print(w, file=sys.stderr)
        except P.Deny as d:
            return str(d), err.getvalue()
    return None, err.getvalue()


class Hook(unittest.TestCase):
    def test_refuses_red_release_run_with_running_job(self):
        msg, _ = verdict("gh run cancel 55", state("release/12", "in_progress", RED_RUNNING))
        self.assertIn("DL-97", msg)
        self.assertIn("D105", msg)
        self.assertIn("blocks-all", msg)

    def test_refuses_api_cancel(self):
        msg, _ = verdict("gh api -X POST repos/o/r/actions/runs/55/cancel", state("release/12", "in_progress", RED_RUNNING))
        self.assertIn("DL-97", msg)

    def test_allows_green_finished_other_branch_and_escape(self):
        self.assertIsNone(verdict("gh run cancel 55", state("release/12", "in_progress", GREEN_RUNNING))[0])
        self.assertIsNone(verdict("gh run cancel 55", state("release/12", "in_progress", RED_DONE))[0])
        self.assertIsNone(verdict("gh run cancel 55", state("release/12", "completed", RED_RUNNING))[0])
        self.assertIsNone(verdict("gh run cancel 55", state("DL1-x", "in_progress", RED_RUNNING))[0])
        self.assertIsNone(verdict("gh run cancel 55  # D105: blocks-all", state("release/12", "in_progress", RED_RUNNING))[0])

    def test_gh_failure_allows_with_warning(self):
        msg, err = verdict("gh run cancel 55", None)
        self.assertIsNone(msg)
        self.assertIn("DL-97", err)

    def test_read_run_state_fails_open(self):
        with mock.patch.object(P.subprocess, "run", side_effect=OSError("no gh")):
            self.assertIsNone(P.read_run_state("5", "."))


class Joined(unittest.TestCase):
    def test_skips_red_running_run(self):
        views = {"1": RED_RUNNING, "2": GREEN_RUNNING}

        def gh(*args, repo=None):
            return 0, json.dumps({"status": "in_progress", "jobs": views[args[2]]}), ""

        with mock.patch.object(CJ, "gh", side_effect=gh):
            self.assertTrue(CJ.is_red_and_running(1, None))
            self.assertFalse(CJ.is_red_and_running(2, None))
        with mock.patch.object(CJ, "gh", return_value=(1, "", "boom")):
            self.assertFalse(CJ.is_red_and_running(1, None))

    def test_main_skips_unless_blocks_all(self):
        runs = [{"databaseId": 1, "headBranch": "a", "headSha": "s", "status": "in_progress"}]
        calls = []

        def gh(*args, repo=None):
            calls.append(args)
            if args[:2] == ("run", "view"):
                return 0, json.dumps({"jobs": RED_RUNNING}), ""
            return 0, "", ""

        for extra, cancelled in (([], 0), (["--blocks-all"], 1)):
            calls.clear()
            out = io.StringIO()
            with mock.patch.object(CJ, "git", return_value=(0, "", "")), mock.patch.object(CJ, "gh", side_effect=gh), \
                    mock.patch.object(CJ, "plan", return_value=runs), contextlib.redirect_stdout(out):
                CJ.main(["--into", "x", "--yes"] + extra)
            self.assertEqual(sum(1 for c in calls if c[:2] == ("run", "cancel")), cancelled, out.getvalue())


WF = """name: ci
on:
  pull_request:
    branches: [main]
jobs:
  suite:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        shard: [1, 2]
    steps:
      - run: echo hi
  js:
    runs-on: ubuntu-latest
    steps:
      - run: npx vitest --bail 1
"""


class Doctor(unittest.TestCase):
    def root(self, text):
        d = tempfile.mkdtemp()
        os.makedirs(os.path.join(d, ".github", "workflows"))
        Path(d, ".github", "workflows", "ci.yml").write_text(text)
        return d

    def test_warns_on_matrix_and_bail(self):
        res = D.check_fail_fast(self.root(WF), {})
        self.assertTrue(res[0])
        self.assertIn("DL-98", res[1])
        self.assertIn("matrix without fail-fast", res[1])
        self.assertIn("--bail", res[1])

    def test_quiet_when_fail_fast_false(self):
        wf = WF.replace("      matrix:", "      fail-fast: false\n      matrix:").replace(" --bail 1", "")
        self.assertIsNone(D.check_fail_fast(self.root(wf), {}))

    def test_quiet_when_on(self):
        cfg = {"ci": {"jobs": {"suite": {"fail_fast": "on"}, "js": {"fail_fast": "on"}}}}
        self.assertIsNone(D.check_fail_fast(self.root(WF), cfg))

    def test_quiet_when_not_a_pr_workflow(self):
        self.assertIsNone(D.check_fail_fast(self.root(WF.replace("pull_request", "push")), {}))

    def test_shipped_ts_template_is_clean(self):
        t = (HERE.parent / "templates" / "ts" / ".github" / "workflows" / "ci.yml").read_text()
        self.assertEqual(D.fail_fast_findings(t, "ci.yml", {}), [])


if __name__ == "__main__":
    unittest.main()
