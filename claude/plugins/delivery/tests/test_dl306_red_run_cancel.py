"""DL306: on a train head, the first red job cancels the other runs of that head and ends the watch.
Stubbed gh (no network, no clock)."""
import contextlib
import io
import sys
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
SHARED = HERE.parent / "templates" / "shared" / "scripts" / "delivery"
sys.path.insert(0, str(SHARED))

import ci_watch as cw  # noqa: E402

SHA = "b" * 40
REPO = "owner/name"


def run(rid, status, conclusion=None, name="ci"):
    return {"databaseId": rid, "workflowName": name, "status": status, "conclusion": conclusion,
            "event": "pull_request", "headSha": SHA}


class FakeGh:
    """Runs: 1 in progress with a failed job, 2 in progress, 3 completed green."""

    def __init__(self, branch, runs=None, jobs=None):
        self.branch = branch
        self.runs = runs or [run(1, "in_progress"), run(2, "in_progress", name="lint"), run(3, "completed", "success", "x")]
        self.jobs = jobs if jobs is not None else {
            1: [{"name": "rust", "status": "completed", "conclusion": "failure"},
                {"name": "web", "status": "in_progress", "conclusion": None}],
            2: [{"name": "lint", "status": "in_progress", "conclusion": None}]}
        self.calls = []

    def __call__(self, args):
        self.calls.append(list(args))
        if args[:2] == ["repo", "view"]:
            return {"nameWithOwner": REPO}
        if args[:2] == ["run", "list"]:
            return self.runs
        if args[:2] == ["run", "view"]:
            rid = int(args[2])
            if "headBranch" in args:
                return {"headBranch": self.branch}
            return {"jobs": self.jobs.get(rid, [])}
        if args[:2] == ["run", "cancel"]:
            return None
        return None

    def cancelled(self):
        return [c[2] for c in self.calls if c[:2] == ["run", "cancel"]]


def watch(fake, extra=(), config=(True, r"^release/")):
    out = io.StringIO()
    with mock.patch.object(cw.shutil, "which", return_value="gh"), \
            mock.patch.object(cw, "gh_json", side_effect=fake), \
            mock.patch.object(cw, "gh_text", return_value=""), \
            mock.patch.object(cw, "warn_queued_jobs"), \
            mock.patch.object(cw.fallback_launch, "check_and_launch"), \
            mock.patch.object(cw, "waiting_for_held_jobs", return_value=False), \
            mock.patch.object(cw, "print_slowest_job_summary"), \
            mock.patch.object(cw, "load_cancel_config", return_value=config), \
            mock.patch.object(cw, "ledger_ci"), \
            mock.patch.object(cw, "finish", side_effect=lambda code, *a, **k: code), \
            mock.patch.object(cw.time, "sleep"), \
            contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        code = cw.main([SHA, "--interval", "0", "--timeout", "100", *extra])
    return code, out.getvalue()


class RedRunCancel(unittest.TestCase):
    def test_release_head_cancels_in_progress_runs(self):
        fake = FakeGh("release/1.2")
        code, out = watch(fake)
        self.assertEqual(code, 1)
        self.assertEqual(sorted(fake.cancelled()), ["1", "2"])
        self.assertIn("FAILED job: rust", out)
        self.assertIn("push freeze lifted", out)
        self.assertEqual(out.count("did not succeed"), 0)

    def test_cancels_use_this_repo_and_head_only(self):
        fake = FakeGh("release/1.2")
        watch(fake)
        for call in fake.calls:
            if call[:2] == ["run", "cancel"]:
                self.assertEqual(call[3:], ["--repo", REPO])
        self.assertTrue(all(r["headSha"] == SHA for r in fake.runs))

    def test_agent_branch_is_not_cancelled(self):
        fake = FakeGh("DL1-some-task")
        fake.runs[0]["status"] = "in_progress"
        # the run ends red later: first poll keeps waiting, so complete it on the second list
        polls = {"n": 0}
        base = fake.__call__

        def handler(args):
            if args[:2] == ["run", "list"]:
                polls["n"] += 1
                if polls["n"] >= 2:
                    return [run(1, "completed", "failure"), run(2, "completed", "success", "lint")]
            return base(args)
        fake2 = mock.Mock(side_effect=handler)
        code, _ = watch(fake2)
        self.assertEqual(code, 1)
        self.assertFalse([c for c in fake2.call_args_list if c.args[0][:2] == ["run", "cancel"]])

    def test_flag_keeps_old_behaviour(self):
        fake = FakeGh("release/1.2")
        polls = {"n": 0}
        base = fake.__call__

        def handler(args):
            if args[:2] == ["run", "list"]:
                polls["n"] += 1
                if polls["n"] >= 2:
                    return [run(1, "completed", "failure"), run(2, "completed", "success", "lint")]
            return base(args)
        fake2 = mock.Mock(side_effect=handler)
        code, _ = watch(fake2, ["--no-cancel-on-red"])
        self.assertEqual(code, 1)
        self.assertGreaterEqual(polls["n"], 2)  # waited for the run to end
        self.assertFalse([c for c in fake2.call_args_list if c.args[0][:2] == ["run", "cancel"]])

    def test_config_off_keeps_old_behaviour(self):
        fake = FakeGh("release/1.2")
        polls = {"n": 0}
        base = fake.__call__

        def handler(args):
            if args[:2] == ["run", "list"]:
                polls["n"] += 1
                if polls["n"] >= 2:
                    return [run(1, "completed", "failure")]
            return base(args)
        fake2 = mock.Mock(side_effect=handler)
        code, _ = watch(fake2, config=(False, r"^release/"))
        self.assertEqual(code, 1)
        self.assertFalse([c for c in fake2.call_args_list if c.args[0][:2] == ["run", "cancel"]])

    def test_all_green_cancels_nothing(self):
        fake = FakeGh("release/1.2", runs=[run(1, "completed", "success"), run(2, "completed", "success", "lint")])
        code, _ = watch(fake)
        self.assertEqual(code, 0)
        self.assertEqual(fake.cancelled(), [])

    def test_running_green_cancels_nothing(self):
        polls = {"n": 0}
        fake = FakeGh("release/1.2", jobs={1: [{"name": "a", "status": "in_progress", "conclusion": None}]})

        def handler(args):
            if args[:2] == ["run", "list"]:
                polls["n"] += 1
                return [run(1, "in_progress")] if polls["n"] < 3 else [run(1, "completed", "success")]
            return fake(args)
        fake2 = mock.Mock(side_effect=handler)
        code, _ = watch(fake2)
        self.assertEqual(code, 0)
        self.assertFalse([c for c in fake2.call_args_list if c.args[0][:2] == ["run", "cancel"]])

    def test_cancel_error_still_fails_without_second_report(self):
        fake = FakeGh("release/1.2")
        base = fake.__call__

        def handler(args):
            if args[:2] == ["run", "cancel"]:
                raise cw.GhError("gh run cancel failed (1): nope")
            return base(args)
        code, out = watch(mock.Mock(side_effect=handler))
        self.assertEqual(code, 1)
        self.assertIn("FAILED job: rust", out)

    def test_train_regex_from_config(self):
        fake = FakeGh("train/7")
        code, _ = watch(fake, config=(True, r"^train/"))
        self.assertEqual(code, 1)
        self.assertEqual(sorted(fake.cancelled()), ["1", "2"])


class ConfigLoad(unittest.TestCase):
    def test_defaults_and_values(self):
        import json
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "c.json"
            self.assertEqual(cw.load_cancel_config(str(p), Path(d)), (True, r"^release/"))
            p.write_text(json.dumps({"ci_watch": {"cancel_on_red": False}, "train_branch_re": "^t/"}), encoding="utf-8")
            self.assertEqual(cw.load_cancel_config(str(p), Path(d)), (False, "^t/"))


if __name__ == "__main__":
    unittest.main()
