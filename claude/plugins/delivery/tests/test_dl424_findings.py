"""DL424 cancel_old_run lifts the train freeze; DL425 docs/config-only pushes skip typecheck and lint;
DL426 the gate result is also read from the other worktrees of the repository."""
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "templates" / "shared" / "scripts" / "delivery"))
import cancel_old_run as C  # noqa: E402
import delivery_common as dc  # noqa: E402
import train_freeze as T  # noqa: E402


def git(cwd, *a):
    return subprocess.run(["git", "-c", "user.email=a@example.com", "-c", "user.name=t", *a],
                          cwd=str(cwd), capture_output=True, text=True, check=True).stdout.strip()


class Cancel(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.d, True)
        (self.d / ".delivery").mkdir()
        self.calls = []
        self.runs = [{"databaseId": 11, "workflowName": "ci", "status": "in_progress"},
                     {"databaseId": 12, "workflowName": "old", "status": "completed"}]
        self.old = (C.gh, dc.main_checkout_root, dc.ledger_record)
        C.gh = self.fake_gh
        dc.main_checkout_root = lambda cwd=None: self.d
        self.ledger = []
        dc.ledger_record = lambda root, op, **kw: self.ledger.append((op, kw)) or True
        self.addCleanup(self.restore)

    def restore(self):
        C.gh, dc.main_checkout_root, dc.ledger_record = self.old

    def fake_gh(self, *args, repo=None):
        self.calls.append(args)
        if args[:2] == ("pr", "view"):
            return 0, json.dumps({"headRefOid": "a" * 40, "headRefName": "fix-x"}), ""
        if args[:2] == ("run", "list"):
            return 0, json.dumps(self.runs), ""
        return 0, "", ""

    def run_main(self, *argv):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = C.main(list(argv))
        return code, buf.getvalue()

    def test_cancels_only_active_runs_and_records(self):
        code, out = self.run_main("--pr", "7")
        self.assertEqual(code, 0, out)
        self.assertIn(("run", "cancel", "11"), self.calls)
        self.assertNotIn(("run", "cancel", "12"), self.calls)
        self.assertIn("11", json.loads((self.d / dc.CANCELLED_RUNS_PATH).read_text()))
        self.assertEqual(self.ledger[0][0], "ci")
        self.assertEqual(self.ledger[0][1]["state"], "cancelled")
        self.assertEqual(self.ledger[0][1]["pr"], 7)

    def test_dry_run_cancels_nothing(self):
        code, _ = self.run_main("--pr", "7", "--dry-run")
        self.assertEqual(code, 0)
        self.assertFalse(any(c[:2] == ("run", "cancel") for c in self.calls))
        self.assertFalse((self.d / dc.CANCELLED_RUNS_PATH).exists())

    def test_freeze_lets_a_cancelled_run_pass(self):
        prs = [{"number": 7, "isDraft": False, "url": "u", "headRefOid": "a" * 40}]

        def fake_json(args, timeout):
            return prs if args[0] == "pr" else [dict(r) for r in self.runs]

        old = T.gh_json
        T.gh_json = fake_json
        self.addCleanup(setattr, T, "gh_json", old)
        self.assertIsNotNone(T.find_freeze("fix-x", 1))  # frozen before the cancel
        self.run_main("--pr", "7")
        self.assertIsNone(T.find_freeze("fix-x", 1))  # still "in_progress" on GitHub, but cancelled on request

    def test_freeze_message_names_the_command(self):
        prs = [{"number": 7, "isDraft": False, "url": "u", "headRefOid": "a" * 40}]
        old = T.gh_json
        T.gh_json = lambda args, timeout: prs if args[0] == "pr" else [dict(self.runs[0])]
        self.addCleanup(setattr, T, "gh_json", old)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = T.main(["--branch", "fix-x"])
        self.assertEqual(code, 1)
        self.assertIn("cancel_old_run.py --pr 7", err.getvalue())


class DocsOnly(unittest.TestCase):
    INERT = ["docs/**"]

    def test_classification(self):
        yes = ["docs/a.html", "README.md", ".delivery/config.json", "gate.yml", "notes/x.txt"]
        for f in yes:
            self.assertTrue(dc.docs_config_only([f], self.INERT), f)
        for f in ["src/app.ts", "package.json", "pnpm-lock.yaml", "a/tsconfig.base.json", "x.py"]:
            self.assertFalse(dc.docs_config_only(["docs/a.md", f], self.INERT), f)
        self.assertFalse(dc.docs_config_only([], self.INERT))

    def test_plan_step_skips_typecheck_and_lint_only(self):
        ctx = SimpleNamespace(docs_config_only=True)
        for name, skipped in (("typecheck", True), ("lint", True), ("secrets", False)):
            step = {"name": name, "scope": "always", "run": "x"}
            run, _cmd, why = dc.plan_step(step, SimpleNamespace(
                docs_config_only=True, cfg={}, files=[], widened=False, changed_dirs=[], affected_dirs=[],
                packages=[], full=False, base="b", package_kinds={}))
            self.assertEqual(run, not skipped, name)
            if skipped:
                self.assertIn("docs/config-only", why)
        del ctx

    def test_code_push_still_runs_the_step(self):
        step = {"name": "typecheck", "scope": "always", "run": "x"}
        run, _cmd, _why = dc.plan_step(step, SimpleNamespace(
            docs_config_only=False, cfg={}, files=["a.ts"], widened=False, changed_dirs=[], affected_dirs=[],
            packages=[], full=False, base="b", package_kinds={}))
        self.assertTrue(run)


class GateResultWorktrees(unittest.TestCase):
    def setUp(self):
        base = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, base, True)
        self.main = base / "main"
        self.main.mkdir()
        git(self.main, "init", "-q", "-b", "main")
        (self.main / "f").write_text("x")
        git(self.main, "add", ".")
        git(self.main, "commit", "-qm", "c")
        self.wt = base / "wt"
        git(self.main, "worktree", "add", "-q", "-b", "b", str(self.wt))
        self.addCleanup(subprocess.run, ["git", "worktree", "prune"], cwd=str(self.main))

    def put(self, root, head):
        p = root / ".delivery"
        p.mkdir(exist_ok=True)
        (p / "gate-result.json").write_text(json.dumps({"head": head}))

    def test_reads_the_worktree_that_ran_the_gate(self):
        self.put(self.wt, "h1")
        self.assertEqual(dc.find_gate_result(self.main, "h1"), {"head": "h1"})

    def test_own_checkout_file_still_wins_when_it_matches(self):
        self.put(self.main, "h1")
        self.put(self.wt, "h1")
        os.utime(self.wt / ".delivery" / "gate-result.json", (9e9, 9e9))
        self.assertEqual(dc.find_gate_result(self.main, "h1"), {"head": "h1"})
        self.assertEqual(dc.find_gate_result(self.wt, "h1"), {"head": "h1"})

    def test_newest_matching_worktree_file(self):
        other = self.wt.parent / "wt2"
        git(self.main, "worktree", "add", "-q", "-b", "c", str(other))
        self.put(self.wt, "h1")
        self.put(other, "h1")
        (other / ".delivery" / "gate-result.json").write_text(json.dumps({"head": "h1", "n": 2}))
        os.utime(self.wt / ".delivery" / "gate-result.json", (1000, 1000))
        self.assertEqual(dc.find_gate_result(self.main, "h1"), {"head": "h1", "n": 2})

    def test_no_match_returns_own_file_for_the_mismatch_message(self):
        self.put(self.main, "old")
        self.put(self.wt, "other")
        self.assertEqual(dc.find_gate_result(self.main, "new"), {"head": "old"})

    def test_none_when_no_file(self):
        self.assertIsNone(dc.find_gate_result(self.main, "h"))


if __name__ == "__main__":
    unittest.main()
