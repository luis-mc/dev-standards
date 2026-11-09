"""DL151: stale_agents reads the project record; the session summary lists open agents of finished tasks."""
import json
import unittest
from pathlib import Path

from _helpers import make_root, L
import hook_session_start as S


def registry(root, rows, rec="docs/project"):
    d = Path(root) / rec
    d.mkdir(parents=True, exist_ok=True)
    (d / "registry.json").write_text(json.dumps({"tasks": rows}))


def agents(*rows):
    return {"agents": list(rows)}


class StaleAgents(unittest.TestCase):
    def test_lists_open_agents_of_closed_tasks(self):
        root = make_root()
        registry(root, [{"id": "T1", "status": "Live"}, {"id": "T2", "status": "Built"}, {"id": "T3", "status": "Dropped"},
                        {"id": "T4", "status": "Building"}])
        led = agents({"task": "T1", "id": "a1", "state": "running"}, {"task": "T2", "id": "a2", "state": "pushed"},
                     {"task": "T3", "id": "a3", "state": "done"}, {"task": "T4", "id": "a4", "state": "running"},
                     {"task": "T3", "id": "a5", "state": "failed"}, {"task": "T3", "id": "a6", "state": "queued"})
        got = L.stale_agents(root, led=led)
        self.assertEqual([(r["task"], r["id"], r["status"]) for r in got],
                         [("T1", "a1", "live"), ("T2", "a2", "built"), ("T3", "a6", "dropped")])

    def test_explicit_record_and_record_dir(self):
        root = make_root()
        led = agents({"task": "T1", "id": "a1", "state": "running"})
        self.assertEqual(len(L.stale_agents(root, {"T1": "Live"}, led)), 1)
        Path(root, "docs").mkdir()
        Path(root, "docs", "docs.json").write_text(json.dumps({"record_dir": "docs/rec"}))
        registry(root, [{"id": "T1", "status": "Live"}], "docs/rec")
        self.assertEqual(len(L.stale_agents(root, led=led)), 1)

    def test_no_record_says_nothing(self):
        root = make_root()
        self.assertEqual(L.stale_agents(root, led=agents({"task": "T1", "id": "a1", "state": "running"})), [])
        Path(root, "docs", "project").mkdir(parents=True)
        Path(root, "docs", "project", "registry.json").write_text("{bad")
        self.assertEqual(L.stale_agents(root, led=agents({"task": "T1", "id": "a1", "state": "running"})), [])

    def test_session_summary(self):
        root = make_root()
        registry(root, [{"id": "T1", "status": "Live"}])
        led = L.empty_ledger()
        led["agents"] = [{"task": "T1", "id": "a1", "state": "running"}]
        lines = S.summary(root, {"check_min": 60}, led, S.H.now())
        text = "\n".join(lines)
        self.assertIn("Needing a check", text)
        self.assertIn("a1", text)
        self.assertIn("Live", text)
        self.assertIn("agent-done a1 --by session --result", text)

    def test_session_summary_silent_without_record(self):
        root = make_root()
        led = L.empty_ledger()
        led["agents"] = [{"task": "T1", "id": "a1", "state": "running"}]
        text = "\n".join(S.summary(root, {"check_min": 60}, led, S.H.now()))
        self.assertNotIn("Needing a check (", text)


if __name__ == "__main__":
    unittest.main()
