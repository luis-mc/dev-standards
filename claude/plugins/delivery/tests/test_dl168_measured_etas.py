"""DL168: measured ETAs. The estimate, the launch check (DL-30), and the ledger show line."""
import contextlib
import io
import json
import unittest
from argparse import Namespace
from datetime import datetime, timedelta, timezone

from _helpers import make_root
import delivery_eta as E
import delivery_ledger as L
import hook_pre_tool as P
import hooklib as H

T0 = datetime(2026, 11, 1, 10, 0, tzinfo=timezone.utc)


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def agent(i, took, eta=30, where="cloud"):
    s = T0 + timedelta(hours=i)
    return {"id": "a%d" % i, "task": "T%d" % i, "where": where, "state": "done", "started": iso(s),
            "finished_at": iso(s + timedelta(minutes=took)), "eta": {"total_min": eta}}


def make(agents=None, trains=None):
    root = make_root()
    led = L.empty_ledger()
    led["agents"] = agents or []
    led["trains"] = trains or []
    (root / ".delivery" / "ledger.json").write_text(json.dumps(led))
    return root


def brief(eta, reason=False):
    r = "eta-reason: a big refactor\n" if reason else ""
    return ("```delivery\ntask: X1\neta: setup 3 + work %d + checks 5 = %d min\n%s```\nDo it (no UI change)"
            % (eta - 8, eta, r))


def launch(root, text):
    body = {"session_context": {"effort_level": "medium", "model": "sonnet"},
            "mcp_connections": [], "clear_mcp_connections": True,
            "events": [{"data": {"message": {"content": text}}}]}
    data = {"tool_name": "RemoteTrigger", "tool_input": {"action": "create", "body": body}, "cwd": str(root)}
    try:
        P.check_launch(H.load_config(str(root)), H.load_ledger(str(root)), data, "cloud")
    except P.Deny as d:
        return str(d)
    return None


class EstimateTests(unittest.TestCase):
    def test_median_and_p75(self):
        root = make([agent(i, m) for i, m in enumerate([10, 12, 14, 16, 40])])
        r = E.estimate(root, "agent", "cloud")
        self.assertEqual((r["n"], r["median"], r["p75"]), (5, 14.0, 16.0))

    def test_no_history_below_three(self):
        root = make([agent(0, 10), agent(1, 12)])
        r = E.estimate(root, "agent")
        self.assertFalse(r["history"])
        self.assertIsNone(r["median"])
        self.assertIn("no history", E.describe(r))

    def test_where_filter(self):
        root = make([agent(i, 10, where="local") for i in range(4)])
        self.assertEqual(E.estimate(root, "agent", "cloud")["n"], 0)

    def test_ci_and_join(self):
        trains = []
        for i in range(3):
            s = T0 + timedelta(hours=i)
            trains.append({"id": "t%d" % i, "joined_at": iso(s), "pushed_at": iso(s + timedelta(minutes=6)),
                           "ci": {"run_started_at": iso(s), "run_completed_at": iso(s + timedelta(minutes=4))}})
        root = make(trains=trains)
        self.assertEqual(E.estimate(root, "ci")["median"], 4.0)
        self.assertEqual(E.estimate(root, "join")["median"], 6.0)


class HookTests(unittest.TestCase):
    def test_refuses_inflated_eta(self):
        root = make([agent(i, 12) for i in range(6)])
        out = launch(root, brief(60))
        self.assertIn("DL-30", out)
        self.assertIn("median of 12", out)
        self.assertIn("p75 12", out)
        self.assertIn("eta-reason", out)

    def test_allows_with_reason(self):
        root = make([agent(i, 12) for i in range(6)])
        self.assertIsNone(launch(root, brief(60, reason=True)))

    def test_allows_few_samples(self):
        root = make([agent(i, 12) for i in range(4)])
        self.assertIsNone(launch(root, brief(60)))

    def test_allows_eta_near_measured(self):
        root = make([agent(i, 12) for i in range(6)])
        self.assertIsNone(launch(root, brief(18)))


class ShowTests(unittest.TestCase):
    def show(self, root):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            L._cmd_show(root, Namespace(json=False))
        return buf.getvalue()

    def test_show_prints_eta_vs_took(self):
        root = make([agent(i, 12, eta=30) for i in range(3)])
        out = self.show(root)
        self.assertIn("eta 30 min, took 12 min", out)
        self.assertIn("cloud agents: eta median 30 min vs actual median 12 min (last 20)", out)

    def test_old_rows_without_finished_at_load(self):
        old = {"id": "o1", "task": "O1", "where": "cloud", "state": "done", "started": iso(T0)}
        root = make([old])
        self.assertIn("agent O1", self.show(root))
        self.assertEqual(E.estimate(root, "agent")["n"], 0)

    def test_agent_done_sets_finished_at(self):
        root = make()
        led = L.empty_ledger()
        led["agents"] = [{"id": "a1", "task": "T1", "state": "running", "started": iso(T0)}]
        (root / ".delivery" / "ledger.json").write_text(json.dumps(led))
        L._cmd_agent_done(root, Namespace(agent="T1", by="session", result="ready"))
        self.assertTrue(L.load(root)["agents"][0].get("finished_at"))


if __name__ == "__main__":
    unittest.main()
