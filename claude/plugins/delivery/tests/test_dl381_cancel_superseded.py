"""DL381: cancel_superseded cancels only with a newer run, a human head, and no failed job."""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_watch as T   # noqa: E402
import delivery_ledger as L   # noqa: E402

OLD = "a" * 40
NEW = "b" * 40


def run(i, sha, status="in_progress"):
    return {"databaseId": i, "status": status, "conclusion": None, "headSha": sha, "headBranch": "release/41",
            "event": "push", "workflowName": "ci"}


def go(data, commit=(0, json.dumps({"author": {"login": "alice"}, "committer": {"login": "alice"}})),
       jobs=(0, json.dumps({"jobs": [{"conclusion": "success"}]})), cfg=None):
    root = T.make_root(cfg or {})
    T.seed(root, [{"branch": "release/41", "pr": 10, "state": "ci"}])
    routes = {("gh", "run", "list"): (0, json.dumps(data)), ("gh", "api"): commit, ("gh", "run", "view"): jobs}
    sh = T.FakeShell(routes)
    w = T.watcher(root, sh)
    done = w.cancel_superseded(L.load(root)["trains"][0], NEW)
    events = [e for e in L.load(root)["events"] if e["kind"].startswith("ci.cancel")]
    return done, sh, events


class CancelSuperseded(unittest.TestCase):
    def test_human_head_with_own_run_cancels(self):
        done, sh, ev = go([run(1, OLD), run(2, NEW)])
        self.assertEqual(done, [1])
        self.assertEqual(len(sh.writes()), 1)
        self.assertEqual([e["kind"] for e in ev], ["ci.cancel_superseded"])

    def test_no_newer_run(self):
        done, sh, ev = go([run(1, OLD)])
        self.assertEqual((done, sh.writes()), ([], []))
        self.assertIn("no_newer_run", ev[0]["detail"] if "detail" in ev[0] else json.dumps(ev[0]))
        self.assertEqual(ev[0]["kind"], "ci.cancel_skipped")

    def test_bot_head(self):
        bot = (0, json.dumps({"author": {"login": "github-actions[bot]"}, "committer": {"login": "web-flow"}}))
        done, sh, ev = go([run(1, OLD), run(2, NEW)], commit=bot)
        self.assertEqual((done, sh.writes()), ([], []))
        self.assertIn("bot_head", json.dumps(ev[0]))

    def test_red_run_skipped_then_cancelled_with_cancel_on_red(self):
        red = (0, json.dumps({"jobs": [{"conclusion": "failure"}, {"conclusion": None}]}))
        done, sh, ev = go([run(1, OLD), run(2, NEW)], jobs=red)
        self.assertEqual((done, sh.writes()), ([], []))
        self.assertIn("red_run", json.dumps(ev[0]))
        done, sh, ev = go([run(1, OLD), run(2, NEW)], jobs=red, cfg={"ci_watch": {"cancel_on_red": True}})
        self.assertEqual(done, [1])

    def test_commit_lookup_fails(self):
        done, sh, ev = go([run(1, OLD), run(2, NEW)], commit=(1, ""))
        self.assertEqual((done, sh.writes()), ([], []))
        self.assertIn("unknown", json.dumps(ev[0]))

    def test_jobs_lookup_fails(self):
        done, sh, ev = go([run(1, OLD), run(2, NEW)], jobs=(1, ""))
        self.assertEqual((done, sh.writes()), ([], []))
        self.assertIn("unknown", json.dumps(ev[0]))


if __name__ == "__main__":
    unittest.main()
