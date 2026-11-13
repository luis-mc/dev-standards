"""DL298: the watcher counts every pull_request run on the head, only runs made after the PR was ready."""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_watch as T   # noqa: E402
import delivery_ledger as L   # noqa: E402

SHA = T.SHA


def run(i, wf, status="completed", concl="success", event="pull_request", created="2026-10-14T10:00:00Z"):
    return {"databaseId": i, "status": status, "conclusion": concl if status == "completed" else None,
            "headSha": SHA, "headBranch": "release/41", "event": event, "workflowName": wf,
            "workflowDatabaseId": i * 1000, "createdAt": created}


def go(everything, cfg=None, draft=False, ready=None, created="2026-10-14T09:00:00Z"):
    """Run one watcher pass. `everything` is the head's run list; the configured ci.yml is answered from it."""
    root = T.make_root(cfg or {})
    T.seed(root, [{"branch": "release/41", "pr": 10, "state": "ci", "green_at": None}])
    routes = T.routes_for_green()
    routes[("gh", "pr", "view", "10")] = lambda argv: (0, json.dumps(
        {"headRefOid": SHA, "state": "OPEN", "isDraft": draft, "createdAt": created}))
    routes[("gh", "api")] = (0, "\n".join(ready or []))

    def listing(argv):
        if "--workflow" in argv:
            wf = argv[argv.index("--workflow") + 1]
            return 0, json.dumps([r for r in everything if r["workflowName"] + ".yml" == wf])
        return 0, json.dumps(everything)
    routes[("gh", "run", "list", "--commit")] = listing
    sh = T.FakeShell(routes)
    T.watcher(root, sh).run_once()
    return L.load(root)["trains"][0], sh


class HeadRuns(unittest.TestCase):
    def test_extra_failure_is_red(self):
        t, sh = go([run(1, "ci"), run(2, "paths", concl="failure")])
        self.assertEqual(t["state"], "red")
        self.assertEqual([c for c in sh.calls if c[:3] == ["gh", "pr", "merge"]], [])

    def test_extra_running_is_not_green(self):
        t, sh = go([run(1, "ci"), run(2, "paths", status="in_progress")])
        self.assertIsNone(t["green_at"])
        self.assertEqual([c for c in sh.calls if c[:3] == ["gh", "pr", "merge"]], [])

    def test_extra_absent_is_green(self):
        t, _ = go([run(1, "ci")])
        self.assertTrue(t["green_at"])

    def test_extra_success_is_green(self):
        t, _ = go([run(1, "ci"), run(2, "paths")])
        self.assertTrue(t["green_at"])

    def test_draft_time_runs_are_ignored(self):
        old = "2026-10-14T08:00:00Z"
        t, _ = go([run(1, "ci", created=old), run(2, "paths", created=old)],
                  ready=["2026-10-14T09:30:00Z"])
        self.assertIsNone(t["green_at"])     # ci.yml has no run after the ready time: queued
        t, _ = go([run(1, "ci", created=old), run(3, "ci", status="in_progress", created="2026-10-14T09:40:00Z")],
                  ready=["2026-10-14T09:30:00Z"])
        self.assertIsNone(t["green_at"])
        t, _ = go([run(1, "ci", created=old), run(3, "ci", created="2026-10-14T09:40:00Z")],
                  ready=["2026-10-14T09:30:00Z"])
        self.assertTrue(t["green_at"])

    def test_last_ready_event_wins(self):
        t, _ = go([run(1, "ci", created="2026-10-14T09:40:00Z")],
                  ready=["2026-10-14T09:10:00Z", "2026-10-14T09:50:00Z"])
        self.assertIsNone(t["green_at"])

    def test_still_draft_is_never_green(self):
        t, sh = go([run(1, "ci")], draft=True)
        self.assertIsNone(t["green_at"])
        self.assertEqual([c for c in sh.calls if c[:3] == ["gh", "pr", "merge"]], [])

    def test_ignore_workflows_excludes_one(self):
        t, _ = go([run(1, "ci"), run(2, "paths", concl="failure")], cfg={"watcher": {"ignore_workflows": ["paths"]}})
        self.assertTrue(t["green_at"])

    def test_ignore_workflows_by_file_name(self):
        root = T.make_root({"watcher": {"ignore_workflows": ["nightly.yml"]}})
        wf = Path(root) / ".github" / "workflows"
        wf.mkdir(parents=True)
        (wf / "nightly.yml").write_text("name: Nightly checks\non: pull_request\n")
        import delivery_watch as W
        w = W.Watcher(root, sh=T.FakeShell(), out=lambda *_: None, ci_runs=False)
        self.assertIn("nightly checks", w._ignored_names())

    def test_push_and_schedule_runs_do_not_count(self):
        t, _ = go([run(1, "ci"), run(2, "other", concl="failure", event="push"),
                   run(3, "cron", status="in_progress", event="schedule")])
        self.assertTrue(t["green_at"])

    def test_extras_logged_once(self):
        out = []
        root = T.make_root({})
        T.seed(root, [{"branch": "release/41", "pr": 10, "state": "ci", "green_at": None}])
        import delivery_watch as W
        routes = T.routes_for_green()
        routes[("gh", "run", "list", "--commit")] = lambda argv: (
            0, "[]" if "--workflow" in argv else json.dumps([run(2, "paths", status="in_progress")]))
        w = W.Watcher(root, sh=T.FakeShell(routes), now=lambda: T.NOW, out=out.append, ci_runs=False)
        w.run_once()
        w.run_once()
        self.assertEqual(len([x for x in out if "joined the required set" in x]), 1)


if __name__ == "__main__":
    unittest.main()
