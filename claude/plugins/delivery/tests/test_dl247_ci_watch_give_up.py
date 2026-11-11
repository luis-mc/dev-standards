"""DL247: ci_watch gives up with its own exit code (5) on every give-up path, resolves the repository once at
start and passes --repo to every later gh call. Stubbed gh and clock."""
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

SHA = "a" * 40
REPO = "owner/name"


def run_obj(conclusion="success"):
    return {"databaseId": 7, "workflowName": "ci", "status": "completed", "conclusion": conclusion,
            "event": "push", "headSha": SHA}


def watch(argv, handler):
    """handler(args) -> JSON value or raises GhError. Returns (code, stderr, calls)."""
    calls = []

    def gh_json(args):
        calls.append(list(args))
        return handler(args)

    err = io.StringIO()
    with mock.patch.object(cw.shutil, "which", return_value="gh"), \
            mock.patch.object(cw, "gh_json", side_effect=gh_json), \
            mock.patch.object(cw, "gh_text", return_value=""), \
            mock.patch.object(cw, "warn_queued_jobs"), \
            mock.patch.object(cw.fallback_launch, "check_and_launch"), \
            mock.patch.object(cw, "waiting_for_held_jobs", return_value=False), \
            mock.patch.object(cw, "print_slowest_job_summary"), \
            mock.patch.object(cw, "ledger_ci"), \
            mock.patch.object(cw, "finish", side_effect=lambda code, *a, **k: code), \
            mock.patch.object(cw.time, "sleep"), \
            contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
        code = cw.main(argv)
    return code, err.getvalue(), calls


def fail(args):
    raise cw.GhError("not a git repository")


def repo_ok(args):
    return {"nameWithOwner": REPO} if args[:2] == ["repo", "view"] else None


class GiveUp(unittest.TestCase):
    base = [SHA, "--interval", "0", "--timeout", "100"]

    def test_code_is_new(self):
        self.assertNotIn(cw.GIVE_UP_EXIT, (0, 1, 2, 4))

    def test_run_list_fails_five_times(self):
        def h(args):
            return repo_ok(args) if args[:2] == ["repo", "view"] else fail(args)
        code, err, calls = watch(self.base, h)
        self.assertEqual(code, cw.GIVE_UP_EXIT)
        self.assertIn("giving up, gh failed 5 times", err)
        self.assertEqual(sum(c[:2] == ["run", "list"] for c in calls), 5)

    def test_status_watch_fails_five_times(self):
        def h(args):
            return repo_ok(args) if args[:2] == ["repo", "view"] else fail(args)
        code, err, _ = watch(self.base + ["--context", "shard"], h)
        self.assertEqual(code, cw.GIVE_UP_EXIT)
        self.assertIn("giving up, gh failed 5 times", err)

    def test_open_pr_lookup_fails_five_times(self):
        def h(args):
            if args[:2] == ["repo", "view"]:
                return {"nameWithOwner": REPO}
            if args[:2] == ["run", "list"]:
                return [run_obj()]
            return fail(args)  # run view fails
        code, err, _ = watch(self.base, h)
        self.assertEqual(code, cw.GIVE_UP_EXIT)
        self.assertIn("giving up, gh failed 5 times", err)


class Repo(unittest.TestCase):
    def test_every_call_after_start_carries_repo(self):
        def h(args):
            if args[:2] == ["repo", "view"]:
                return {"nameWithOwner": REPO}
            if args[:2] == ["run", "list"]:
                return [run_obj()]
            if args[:2] == ["run", "view"]:
                return {"jobs": [{"conclusion": "success", "steps": []}]}
            return []
        code, _, calls = watch([SHA, "--interval", "0"], h)
        self.assertEqual(code, 0)
        self.assertEqual(calls[0][:2], ["repo", "view"])
        later = calls[1:]
        self.assertTrue(later)
        for c in later:
            if c[0] == "api":
                self.assertIn(f"repos/{REPO}/", c[1])
            else:
                self.assertEqual(c[c.index("--repo") + 1], REPO, c)

    def test_repo_option_skips_lookup(self):
        def h(args):
            if args[:2] == ["run", "list"]:
                return [run_obj()]
            return {"jobs": [{"conclusion": "success", "steps": []}]} if args[:2] == ["run", "view"] else []
        code, _, calls = watch([SHA, "--interval", "0", "--repo", "x/y"], h)
        self.assertEqual(code, 0)
        self.assertNotIn(["repo", "view"], [c[:2] for c in calls])
        self.assertTrue(all("x/y" in " ".join(c) for c in calls))

    def test_no_repo_exits_at_once(self):
        code, err, calls = watch([SHA, "--interval", "0"], fail)
        self.assertEqual(code, 2)
        self.assertIn("could not resolve the repository", err)
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
