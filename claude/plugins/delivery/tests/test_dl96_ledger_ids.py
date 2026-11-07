"""DL96: one cloud launch, two ids (trig_ routine id, cse_ run id), one agent entry."""
import argparse
import unittest

from _helpers import L, make_root
import hook_post_tool as H
import hook_stop as S
import hooklib as HL

BLOCK = "```delivery\ntask: DV152\nbranch: DV152-x\n```\nDo it"


def seed(root, rows):
    L.update(root, lambda led: led["agents"].extend(rows))


def row(ident, **kw):
    r = {"task": "DV152", "where": "cloud", "id": ident, "branch": "DV152-x", "state": "running",
         "started": L.iso(), "eta": None, "last_checked": None}
    r.update(kw)
    return r


class LinkTests(unittest.TestCase):
    def test_run_of_known_trigger_links_not_second_row(self):
        root = make_root()
        body = {"action": "create", "body": {"events": [{"data": {"message": {"content": BLOCK}}}]}}
        H.handle({"hook_event_name": "PostToolUse", "tool_name": "RemoteTrigger", "tool_input": body,
                  "tool_response": {"id": "trig_abc"}}, root)
        run = {"action": "run", "trigger_id": "trig_abc"}
        H.handle({"hook_event_name": "PostToolUse", "tool_name": "RemoteTrigger", "tool_input": run,
                  "tool_response": {"session_id": "cse_111", "trigger_id": "trig_abc"}}, root)
        agents = L.load(root)["agents"]
        self.assertEqual(len(agents), 1)
        self.assertEqual(agents[0]["id"], "trig_abc")
        self.assertIn("cse_111", agents[0]["run_ids"])

    def test_agent_eta_and_done_accept_either_id(self):
        root = make_root()
        seed(root, [row("trig_abc", run_ids=["cse_111"])])
        ns = argparse.Namespace(agent="cse_111", setup=5, work=30, checks=10, basis="two files")
        self.assertEqual(L._cmd_agent_eta(root, ns), 0)
        self.assertEqual(L.load(root)["agents"][0]["eta"]["total_min"], 45)
        done = argparse.Namespace(agent="trig_abc", by="session", result="ready")
        self.assertEqual(L._cmd_agent_done(root, done), 0)
        agents = L.load(root)["agents"]
        self.assertEqual((len(agents), agents[0]["state"]), (1, "done"))

    def test_old_ledger_with_two_rows_merges_on_read(self):
        root = make_root()
        seed(root, [row("trig_abc", trigger_id="trig_abc"), row("cse_111", task=None, branch=None, trigger_id="trig_abc")])
        agents = L.load(root)["agents"]
        self.assertEqual(len(agents), 1)
        self.assertEqual(agents[0]["run_ids"], ["cse_111"])
        self.assertEqual(len(HL.load_ledger(str(root))["agents"]), 1)

    def test_stop_asks_dl30_once(self):
        led = {"agents": [row("trig_abc"), row("cse_111", trigger_id="trig_abc")]}
        L.merge_agent_rows(led)
        found = [k for k, _ in S.check_agents(led, {"check_min": 10_000}, HL.now()) if k.startswith("DL-30")]
        self.assertEqual(found, ["DL-30:trig_abc"])

    def test_unrelated_runs_stay_separate(self):
        led = {"agents": [row("trig_a", task="A", branch="a"), row("cse_b", task="B", branch="b")]}
        self.assertEqual(L.merge_agent_rows(led), 0)

    def test_older_alt_ids_migrate(self):
        led = {"agents": [row("trig_a", alt_ids=["cse_z"])]}
        L.merge_agent_rows(led)
        self.assertEqual(led["agents"][0]["run_ids"], ["cse_z"])
        self.assertNotIn("alt_ids", led["agents"][0])


if __name__ == "__main__":
    unittest.main()
