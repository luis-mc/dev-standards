"""DL235: ci_watch polls every 60 s, backs off while queued, waits out a low GitHub quota, watches several
commits and runs in one process; the pre-tool hook blocks `gh run watch` without --interval 60+. Stubbed gh and clock."""
import contextlib
import io
import sys
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
SHARED = HERE.parent / "templates" / "shared" / "scripts" / "delivery"
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "scripts"))
sys.path.insert(0, str(SHARED))

import ci_watch as cw  # noqa: E402
import hook_pre_tool as P  # noqa: E402
import hooklib as H  # noqa: E402

A, B = "a" * 40, "b" * 40


def run(rid, sha, status, conclusion=None):
    return {"databaseId": rid, "workflowName": "ci", "status": status, "conclusion": conclusion,
            "event": "push", "headSha": sha}


def watch(argv, polls, rate=None, run_commits=None):
    """polls: {sha: [run list per poll]}. Returns (code, out, sleeps, rate_calls)."""
    iters = {k: iter(v) for k, v in polls.items()}
    sleeps = []
    rate_calls = []

    def list_runs(sha, *a, **k):
        return next(iters[sha])

    def gh_json(args):
        if args[:2] == ["api", "rate_limit"]:
            rate_calls.append(1)
            return rate or {"resources": {"core": {"remaining": 4000, "reset": 0}}}
        if args[:2] == ["run", "view"] and args[4:5] == ["headSha"]:
            return {"headSha": run_commits[args[2]]}
        return {"jobs": []}

    out = io.StringIO()
    with mock.patch.object(cw.shutil, "which", return_value="gh"), \
            mock.patch.object(cw, "resolve_repo", side_effect=lambda r: r or "acme/widget"), \
            mock.patch.object(cw, "resolve_sha", side_effect=lambda s, r: s), \
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
            mock.patch.object(cw.time, "sleep", side_effect=sleeps.append), \
            contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        code = cw.main(argv)
    return code, out.getvalue(), sleeps, rate_calls


class Interval(unittest.TestCase):
    def test_default_is_60(self):
        code, _, sleeps, _ = watch([A, "--no-fallback"], {A: [[run(1, A, "in_progress")], [run(1, A, "completed", "success")]]})
        self.assertEqual((code, sleeps), (0, [60.0]))

    def test_minimum_is_30(self):
        self.assertEqual(cw.effective_interval(5), 30.0)
        self.assertEqual(cw.effective_interval(45), 45)
        self.assertEqual(cw.effective_interval(0.1), 0.1)

    def test_backoff_while_queued_then_reset(self):
        q = [run(1, A, "queued")]
        done = [run(1, A, "completed", "success")]
        code, _, sleeps, _ = watch([A, "--no-fallback"], {A: [q, q, q, q, [run(1, A, "in_progress")], done]})
        self.assertEqual(code, 0)
        self.assertEqual(sleeps, [90.0, 120.0, 120.0, 120.0, 60.0])

    def test_next_delay_caps(self):
        self.assertEqual(cw.next_delay(60, 100, True, 120), 120)
        self.assertEqual(cw.next_delay(60, 100, False, 120), 60)


class Quota(unittest.TestCase):
    def test_low_quota_sleeps_until_reset_and_does_not_fail(self):
        slept = []
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            got = cw.quota_guard(None, 200, sleep=slept.append, now=lambda: 1000.0,
                                 read=lambda r: (50, 1100.0))
        self.assertEqual(slept, [101.0])
        self.assertEqual(got, 101.0)
        self.assertIn("resets at", out.getvalue())

    def test_enough_quota_or_unreadable_does_not_sleep(self):
        slept = []
        self.assertEqual(cw.quota_guard(None, 200, sleep=slept.append, read=lambda r: (4000, 0.0)), 0.0)
        self.assertEqual(cw.quota_guard(None, 200, sleep=slept.append, read=lambda r: None), 0.0)
        self.assertEqual(slept, [])

    def test_watch_survives_low_quota(self):
        low = {"resources": {"core": {"remaining": 10, "reset": 0}}}
        code, out, sleeps, _ = watch([A, "--no-fallback"], {A: [[run(1, A, "completed", "success")]]}, rate=low)
        self.assertEqual(code, 0)
        self.assertIn("quota low", out)

    def test_one_rate_read_per_cycle(self):
        q = [run(1, A, "in_progress")]
        _, _, _, rate_calls = watch([A, "--no-fallback"], {A: [q, q, [run(1, A, "completed", "success")]]})
        self.assertEqual(len(rate_calls), 3)


class Many(unittest.TestCase):
    def test_two_commits_one_process(self):
        done = lambda s: [run(1, s, "completed", "success")]
        code, out, sleeps, _ = watch([A, B, "--no-fallback"], {A: [done(A)], B: [[run(2, B, "in_progress")], done(B)]})
        self.assertEqual(code, 0)
        self.assertEqual(out.count("succeeded"), 2)
        self.assertEqual(sleeps, [60.0])

    def test_failure_in_one_fails_the_exit(self):
        code, _, _, _ = watch([A, B, "--no-fallback"], {A: [[run(1, A, "completed", "success")]],
                                                          B: [[run(2, B, "completed", "failure")]]})
        self.assertEqual(code, 1)

    def test_run_ids_map_to_commits(self):
        code, out, _, _ = watch(["--run", "77", "--no-fallback"], {A: [[run(77, A, "completed", "success")]]},
                                run_commits={"77": A})
        self.assertEqual(code, 0)
        self.assertIn(A[:10], out)


class Hook(unittest.TestCase):
    def verdict(self, cmd):
        try:
            for seg in H.segments(cmd):
                if H.starts_with(seg, ["gh", "run", "watch"]):
                    P.check_run_watch(seg)
        except P.Deny as d:
            return str(d)
        return None

    def test_blocks_without_interval(self):
        self.assertIn("DL-95", self.verdict("gh run watch 123") or "")
        self.assertIn("DL-95", self.verdict("gh run watch 123 --interval 30") or "")

    def test_allows_interval_60(self):
        self.assertIsNone(self.verdict("gh run watch 123 --interval 60"))
        self.assertIsNone(self.verdict("gh run watch 123 -i 120"))
        self.assertIsNone(self.verdict("gh run watch 123 --interval=90"))


if __name__ == "__main__":
    unittest.main()
