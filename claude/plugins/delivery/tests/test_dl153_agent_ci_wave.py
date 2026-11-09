"""DL153: agent_ci.py picks branches from the ledger, --task, --branch or --all. Fake git and gh, temp ledger."""
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

TPL = Path(__file__).resolve().parent.parent / "templates" / "shared"
sys.path.insert(0, str(TPL / "scripts" / "delivery"))
import agent_ci as A  # noqa: E402

BRANCHES = ["claude/RS6-x", "claude/RS7-y", "claude/DL153-z", "claude/OLD1-w"]


class Wave(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ledger = str(Path(self.tmp.name) / "ledger.json")
        self.cfg = dict(A.DEFAULTS)
        self.cfg["branch_prefix"] = "claude/"
        self.started = []
        saved = (A.git, A.branches, A.report_state, A.started_for_ci, A.ci_ref, A.subprocess.run)
        self.addCleanup(lambda: (setattr(A, "git", saved[0]), setattr(A, "branches", saved[1]),
                                 setattr(A, "report_state", saved[2]), setattr(A, "started_for_ci", saved[3]),
                                 setattr(A, "ci_ref", saved[4]), setattr(A.subprocess, "run", saved[5])))
        A.git = lambda *a: "abc123456789\n" if a[0] == "rev-parse" else ""
        A.branches = lambda prefix: [b for b in BRANCHES if b.startswith(prefix)]
        A.report_state = lambda b, c: "done"
        A.started_for_ci = lambda b, s, c: False
        A.ci_ref = lambda b, base, c, push=True: A.ci_branch(b, c)
        self.cfg["require_e2e"] = False

    def write(self, agents):
        Path(self.ledger).write_text(json.dumps({"agents": agents}), encoding="utf-8")

    def run_pass(self, **kw):
        out = StringIO()
        with redirect_stdout(out):
            got = A.one_pass(self.cfg, dry_run=True, ledger=self.ledger, **kw)
        return got, out.getvalue()

    def test_plain_pass_takes_open_agents_only(self):
        self.write([
            {"task": "RS6", "branch": "claude/RS6-x", "state": "running"},
            {"task": "RS7", "branch": "claude/RS7-y", "state": "done"},
            {"task": "DL153", "branch": None, "state": "running"},
            {"task": "OLD1", "branch": "claude/OLD1-w", "state": "failed"},
        ])
        got, _ = self.run_pass()
        self.assertEqual(got, ["claude/RS6-x", "claude/DL153-z"])

    def test_task_flag(self):
        got, _ = self.run_pass(tasks=["RS7", "OLD1"])
        self.assertEqual(got, ["claude/RS7-y", "claude/OLD1-w"])

    def test_branch_flag(self):
        got, _ = self.run_pass(names=["origin/claude/DL153-z"])
        self.assertEqual(got, ["claude/DL153-z"])

    def test_all_flag_keeps_old_scan(self):
        got, _ = self.run_pass(all_=True)
        self.assertEqual(got, BRANCHES)

    def test_no_ledger_no_flags_starts_nothing(self):
        got, out = self.run_pass()
        self.assertEqual(got, [])
        self.assertIn("--task", out)
        self.assertIn("--all", out)

    def test_prefix_with_project_letters(self):
        self.assertEqual(A.task_of("claude/RS6-x", "claude/RS"), "RS6")
        self.assertEqual(A.task_of("claude/DL153-agent-ci", "claude/"), "DL153")
        self.assertEqual(A.task_of("claude/RS6-x", "claude/"), "RS6")
        self.cfg["branch_prefix"] = "claude/RS"
        self.assertEqual(A.ci_branch("claude/RS6-x", self.cfg), "ci/RS6")


if __name__ == "__main__":
    unittest.main()
