"""DL127/DL132/DL138/DL139: agent-check, agents closed on cleanup, ledger root from the common dir, train matched or
made by ci_watch, every workflow watched. Fakes only; no network."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
SHARED = HERE.parent / "templates" / "shared" / "scripts" / "delivery"
sys.path.insert(0, str(SHARED))

from _helpers import make_root, L  # noqa: E402
import ci_watch as cw  # noqa: E402


def ledger(root):
    return json.loads((Path(root) / ".delivery" / "ledger.json").read_text())


def seed(root, agents=(), trains=()):
    L.update(root, lambda led: (led["agents"].extend(agents), led["trains"].extend(trains)))


class AgentCheck(unittest.TestCase):
    def test_check_sets_last_checked(self):
        root = make_root()
        seed(root, [{"id": "a1", "task": "T1", "state": "running", "last_checked": None}])
        self.assertEqual(L.main(["--root", str(root), "agent-check", "T1"]), 0)
        self.assertTrue(ledger(root)["agents"][0]["last_checked"])

    def test_check_unknown_agent_fails(self):
        root = make_root()
        self.assertEqual(L.main(["--root", str(root), "agent-check", "nope"]), 1)

    def test_agents_done_closes_cargo_and_branch(self):
        root = make_root()
        seed(root, [{"id": "a1", "task": "T1", "state": "running"},
                    {"id": "a2", "task": "T9", "branch": "T9-x", "state": "running"},
                    {"id": "a3", "task": "T7", "state": "running"}])
        L.update(root, lambda led: L.new_train(led, "rel", cargo=[{"task": "T1"}]))
        L.update(root, lambda led: led["trains"][0].update(pr=5))
        self.assertTrue(L.record(root, "agents_done", pr=5, branches=["T9-x"], by="cleanup.py"))
        states = {a["task"]: a["state"] for a in ledger(root)["agents"]}
        self.assertEqual(states, {"T1": "done", "T9": "done", "T7": "running"})

    def test_stale_agents_reads_project_record(self):
        root = make_root()
        d = Path(root) / "docs" / "project"
        d.mkdir(parents=True)
        (d / "f.html").write_text('<tr data-task="T1"><td><span class="status-chip status-live">Live</span></td></tr>'
                                  '<tr data-task="T2"><td><span class="status-chip status-running">x</span></td></tr>')
        (d / "bad.html").write_bytes(b"\xff\xfe<tr")
        led = {"agents": [{"task": "T1", "state": "running"}, {"task": "T2", "state": "running"}]}
        self.assertEqual(L.stale_agents(root, led), [("T1", "live")])
        self.assertEqual(L.stale_agents(Path(root) / "missing", led), [])


class TrainForCi(unittest.TestCase):
    def test_creates_train_for_branch(self):
        root = make_root()
        self.assertTrue(L.record(root, "ci", sha="a" * 40, state="success", branch="feat", pr=3, create=True))
        t = ledger(root)["trains"]
        self.assertEqual(len(t), 1)
        self.assertEqual((t[0]["branch"], t[0]["pr"], t[0]["state"]), ("feat", 3, "green"))
        L.record(root, "ci", sha="b" * 40, state="success", branch="feat", pr=3, create=True)
        self.assertEqual(len(ledger(root)["trains"]), 1)

    def test_matches_by_branch_without_second_train(self):
        root = make_root()
        L.update(root, lambda led: L.new_train(led, "feat"))
        L.record(root, "ci", sha="a" * 40, state="failure", branch="feat", pr=4, create=True)
        t = ledger(root)["trains"]
        self.assertEqual((len(t), t[0]["pr"], t[0]["state"]), (1, 4, "red"))

    def test_plan_twice_same_branch_one_train(self):
        root = make_root()
        L.main(["--root", str(root), "plan", "--branch", "feat"])
        L.main(["--root", str(root), "plan", "--branch", "feat"])
        self.assertEqual(len(ledger(root)["trains"]), 1)


class LedgerRoot(unittest.TestCase):
    def test_worktree_resolves_main_checkout(self):
        base = Path(tempfile.mkdtemp(prefix="dl127-")).resolve()
        main, wt = base / "main", base / "wt"
        git = lambda *a, cwd=main: subprocess.run(["git", *a], cwd=cwd, check=True, capture_output=True)
        main.mkdir()
        git("init", "-q", "-b", "main")
        git("-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-q", "--allow-empty", "-m", "i")
        (main / ".delivery").mkdir()
        git("worktree", "add", "-q", str(wt), "-b", "x")
        import os
        old = os.getcwd()
        try:
            os.chdir(wt)
            self.assertEqual(cw.ledger_root().resolve(), main)
        finally:
            os.chdir(old)


class AllWorkflows(unittest.TestCase):
    def test_collect_merges_other_workflows(self):
        calls = []
        runs = {"ci.yml": [{"databaseId": 1, "headSha": "s"}],
                None: [{"databaseId": 1, "headSha": "s"}, {"databaseId": 2, "headSha": "s", "conclusion": "failure"}]}

        def fake(sha, wf, repo):
            calls.append(wf)
            return [dict(r) for r in runs[wf]]
        orig = cw.list_runs
        cw.list_runs = fake
        try:
            got = cw.collect_runs("s", "ci.yml", None)
            self.assertEqual([r["databaseId"] for r in got], [1, 2])
            self.assertEqual(len(cw.collect_runs("s", "ci.yml", None, only_workflow=True)), 1)
        finally:
            cw.list_runs = orig


if __name__ == "__main__":
    unittest.main()
