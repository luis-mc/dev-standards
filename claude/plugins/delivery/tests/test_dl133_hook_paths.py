"""DL133 (Git Bash and WSL paths in the DL-53 check) and DL136 (postpone warning). Pure functions; no network."""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import hook_pre_tool as P  # noqa: E402

CFG = {"work_root": "C:/Work"}


def worktree_denied(path, cwd="C:/Work/app1"):
    try:
        P.check_worktree(["git", "worktree", "add", path], CFG, cwd)
    except P.Deny:
        return True
    return False


class WorktreePaths(unittest.TestCase):
    def test_windows_form(self):
        self.assertFalse(worktree_denied("C:/Work/app1-t1"))
        self.assertFalse(worktree_denied("c:\\work\\app1-t1"))

    def test_git_bash_form(self):
        self.assertFalse(worktree_denied("/c/Work/app1-t1"))
        self.assertFalse(worktree_denied("/c/work/app1-t1"))

    def test_wsl_form(self):
        self.assertFalse(worktree_denied("/mnt/c/Work/app1-t1"))

    def test_outside_is_denied(self):
        self.assertTrue(worktree_denied("/c/Other/app1-t1"))
        self.assertTrue(worktree_denied("/d/Work/app1-t1"))
        self.assertTrue(worktree_denied("/mnt/c/Workshop/x"))
        self.assertTrue(worktree_denied("C:/Elsewhere/x"))


class PostponeWarning(unittest.TestCase):
    AT = datetime(2026, 1, 10, 12, 0, tzinfo=timezone.utc)

    def call(self, minutes, answered=False, action="update", questions=True):
        when = (self.AT + timedelta(minutes=minutes)).isoformat()
        qs = [{"id": "Q1", "answered_at": "x" if answered else None}] if questions else []
        data = {"tool_input": {"action": action, "body": {"run_once_at": when}}}
        return P.check_postpone({"owner_questions": qs}, data, self.AT)

    def test_warns_when_soon_and_open(self):
        self.assertIn("DL136", self.call(10))
        self.assertIn("DL136", self.call(10, action="create"))

    def test_quiet_otherwise(self):
        self.assertIsNone(self.call(180))
        self.assertIsNone(self.call(10, answered=True))
        self.assertIsNone(self.call(10, questions=False))
        self.assertIsNone(self.call(10, action="list"))


if __name__ == "__main__":
    unittest.main()
