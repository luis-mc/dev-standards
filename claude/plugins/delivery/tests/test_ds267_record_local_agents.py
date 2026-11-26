"""DS267: a local agent with no ```delivery block still gets a ledger row (DL-123); a finished one is closed;
a Running task with no agent and no CI is warned about (DL-124)."""
import json
import subprocess
import sys
import unittest
from datetime import timedelta
from pathlib import Path

from _helpers import make_root, L, SCRIPTS
import hook_post_tool as P
import hook_stop as S


def registry(root, rows):
    d = Path(root) / "docs" / "project"
    d.mkdir(parents=True, exist_ok=True)
    (d / "registry.json").write_text(json.dumps({"tasks": rows}))


def call(root, prompt, bg=True, resp=None, model="sonnet"):
    data = {"hook_event_name": "PostToolUse", "tool_name": "Agent", "cwd": str(root), "session_id": "s1",
            "tool_input": {"prompt": prompt, "run_in_background": bg, "model": model},
            "tool_response": resp if resp is not None else {"agentId": "ag1"}}
    P.handle(data, root=root)
    return L.load(root)


class Infer(unittest.TestCase):
    def test_branch_first(self):
        g = P.infer_task("Task DS1 is old. Branch `DS258-fix-it` from main.")
        self.assertEqual(g, {"task": "DS258", "branch": "DS258-fix-it"})
        self.assertEqual(P.infer_task("work on branch DL418-x now")["task"], "DL418")

    def test_task_mention_and_window(self):
        self.assertEqual(P.infer_task("Please do Task DS77 now")["task"], "DS77")
        self.assertEqual(P.infer_task("Fix the thing (DS5)")["task"], "DS5")
        self.assertEqual(P.infer_task("x" * 610 + " Task DS77"), {})
        self.assertEqual(P.infer_task("no id here"), {})

    def test_record_filters(self):
        root = make_root()
        registry(root, [{"id": "DS9", "status": "Running"}])
        self.assertEqual(P.infer_task("Branch DS258-a, then Task DS9", root)["task"], "DS9")
        self.assertEqual(P.infer_task("Branch DS258-a", root), {})


class Record(unittest.TestCase):
    def test_row_without_block(self):
        root = make_root()
        led = call(root, "Do Task DS258 on branch DS258-slug please")
        row = led["agents"][0]
        self.assertEqual((row["task"], row["state"], row["model"], row["id"]), ("DS258", "running", "sonnet", "ag1"))
        self.assertEqual(row["branch"], "DS258-slug")
        self.assertEqual(row["where"], "local")

    def test_no_match_keeps_no_task_event(self):
        root = make_root()
        led = call(root, "just do something")
        self.assertEqual(led["agents"], [])
        self.assertTrue(any(e.get("kind", e.get("event")) == "agent.no_task" or "agent.no_task" in json.dumps(e)
                            for e in led["events"]))

    def test_block_still_wins(self):
        root = make_root()
        led = call(root, "```delivery\ntask: DS1\n```\nBranch DS2-x")
        self.assertEqual(led["agents"][0]["task"], "DS1")

    def test_foreground_is_done(self):
        root = make_root()
        led = call(root, "Task DS4", bg=False)
        self.assertEqual(led["agents"][0]["state"], "done")

    def test_paths_recorded(self):
        root = make_root()
        led = call(root, "Task DS4", resp={"agentId": "a", "outputFile": "/x/out", "worktreePath": "/x/wt"})
        self.assertEqual((led["agents"][0]["log_path"], led["agents"][0]["worktree"]), ("/x/out", "/x/wt"))


class Close(unittest.TestCase):
    def row(self, **kw):
        base = {"task": "DS1", "where": "local", "id": "a", "state": "running", "started": L.iso(),
                "eta": None, "last_activity": L.iso()}
        base.update(kw)
        return base

    def run_close(self, row, minutes=0):
        root = make_root()
        led = L.load(root)
        led["agents"].append(row)
        L.save(root, led) if hasattr(L, "save") else L.update(root, lambda x: x["agents"].append(row))
        got = L.close_local_agents(root, L.utcnow() + timedelta(minutes=minutes))
        return got, L.load(root)["agents"][0]["state"]

    def test_day_old_row_closed_and_a_late_row_is_not(self):
        self.assertEqual(self.run_close(self.row(), 24 * 60 + 1)[1], "done")
        self.assertEqual(self.run_close(self.row(eta={"total_min": 10}), 121)[1], "running")  # past its eta: DL-32 asks

    def test_gone_worktree_or_output(self):
        self.assertEqual(self.run_close(self.row(worktree="/no/such/dir-ds267"))[1], "done")
        self.assertEqual(self.run_close(self.row(log_path="/no/such/out-ds267"))[1], "done")

    def test_cloud_untouched(self):
        self.assertEqual(self.run_close(self.row(where="cloud"), 999)[1], "running")


class RunningIdle(unittest.TestCase):
    def setUp(self):
        self.root = make_root()
        registry(self.root, [{"id": "DS1", "status": "Running"}, {"id": "DS2", "status": "Built"}])

    def check(self, agents=(), trains=()):
        led = {"agents": list(agents), "trains": list(trains)}
        return S.check_running_idle(str(self.root), led, {})

    def test_warns(self):
        got = self.check()
        self.assertEqual(len(got), 1)
        self.assertIn("DS1 is Running but no agent is working on it: set it Built, Waiting or Needs you", got[0][1])

    def test_quiet_with_agent_or_ci(self):
        self.assertEqual(self.check(agents=[{"task": "DS1", "state": "running"}]), [])
        self.assertEqual(self.check(trains=[{"state": "ci", "cargo": [{"task": "DS1"}]}]), [])
        self.assertEqual(self.check(trains=[{"state": "pushed", "branch": "DS1-x"}]), [])
        self.assertEqual(len(self.check(agents=[{"task": "DS1", "state": "done"}])), 1)

    def test_stop_hook_warns_without_blocking(self):
        (Path(self.root) / ".delivery" / "ledger.json").write_text(json.dumps({"schema": 1}))
        p = subprocess.run([sys.executable, str(SCRIPTS / "hook_stop.py")], input=json.dumps({"cwd": str(self.root)}),
                           capture_output=True, text=True)
        out = json.loads(p.stdout)
        self.assertNotIn("decision", out)
        self.assertIn("DS1 is Running but no agent", out["systemMessage"])


if __name__ == "__main__":
    unittest.main()
