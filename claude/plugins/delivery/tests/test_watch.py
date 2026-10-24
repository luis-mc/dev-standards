import json
import os
import unittest
from datetime import datetime, timedelta, timezone

from _helpers import L, make_root
import delivery_watch as W

NOW = datetime(2026, 10, 14, 12, 0, tzinfo=timezone.utc)
SHA = "a" * 40
OLD = "b" * 40


class FakeShell:
    """Mocks gh and git. `routes` maps a tuple prefix of argv to (rc, stdout) or a callable."""

    def __init__(self, routes=None):
        self.routes = routes or {}
        self.calls = []

    def run(self, argv, cwd=None, timeout=120):
        self.calls.append(list(argv))
        best = None
        for prefix, resp in self.routes.items():
            if tuple(argv[:len(prefix)]) == prefix and (best is None or len(prefix) > len(best[0])):
                best = (prefix, resp)
        if best is None:
            return 1, "", "unrouted"
        resp = best[1](argv) if callable(best[1]) else best[1]
        return resp[0], resp[1], ""

    def writes(self):
        kinds = (("gh", "pr", "merge"), ("gh", "pr", "create"), ("gh", "run", "cancel"),
                 ("gh", "run", "rerun"), ("git", "push"))
        return [c for c in self.calls if any(tuple(c[:len(k)]) == k for k in kinds)]


def runs(*items):
    return json.dumps([{"databaseId": i, "status": s, "conclusion": c, "headSha": h, "headBranch": b,
                        "event": "push", "workflowName": "ci"} for (i, s, c, h, b) in items])


def seed(root, trains=(), **extra):
    def fn(led):
        for t in trains:
            tr = L.new_train(led, t.pop("branch"))
            tr.update(t)
        led.update(extra)
    L.update(root, fn)


def routes_for_green(pr=10, head=SHA, branch="release/29"):
    return {
        ("gh", "pr", "view", str(pr)): (0, json.dumps({"headRefOid": head, "state": "OPEN"})),
        ("gh", "run", "list", "--commit"): (0, runs((1, "completed", "success", head, branch))),
        ("gh", "run", "list", "--branch"): (0, "[]"),
        ("gh", "run", "list", "--status"): (0, "[]"),
        ("gh", "pr", "merge"): (0, ""),
        ("gh", "api"): (1, ""),
    }


def watcher(root, sh, **kw):
    return W.Watcher(root, sh=sh, now=lambda: NOW, out=lambda *_: None, **kw)


class MergeTests(unittest.TestCase):
    def test_green_current_head_merges_with_merge_flag_never_auto(self):
        root = make_root()
        seed(root, [{"branch": "release/29", "pr": 10, "state": "ci"}])
        sh = FakeShell(routes_for_green())
        watcher(root, sh).run_once()
        merges = [c for c in sh.calls if c[:3] == ["gh", "pr", "merge"]]
        self.assertEqual(merges, [["gh", "pr", "merge", "10", "--merge", "--match-head-commit", SHA]])
        self.assertFalse(any("--auto" in c for c in sh.calls))
        t = L.load(root)["trains"][0]
        self.assertEqual(t["state"], "merged")
        self.assertEqual((t["ci"]["head_sha"], t["ci"]["state"]), (SHA, "success"))
        self.assertIsNotNone(t["green_at"])
        self.assertIsNotNone(t["merged_at"])

    def test_ci_read_by_commit_of_current_head_only(self):
        root = make_root()
        seed(root, [{"branch": "release/29", "pr": 10, "state": "ci",
                     "ci": {"head_sha": OLD, "run_ids": [], "state": "success", "started_at": None}}])
        r = routes_for_green()
        r[("gh", "run", "list", "--commit")] = lambda argv: (0, runs((2, "in_progress", None, SHA, "release/29")))
        sh = FakeShell(r)
        watcher(root, sh).run_once()
        listed = [c for c in sh.calls if c[:4] == ["gh", "run", "list", "--commit"]]
        self.assertEqual(listed[0][4], SHA)
        self.assertEqual(listed[0][5:7], ["--workflow", "ci.yml"])
        self.assertEqual(sh.writes(), [])  # stored success on the old head does not merge
        self.assertEqual(L.load(root)["trains"][0]["ci"]["state"], "running")

    def test_no_run_yet_or_failure_never_merges(self):
        for resp, state in (("[]", "ci"), (runs((1, "completed", "failure", SHA, "x")), "red")):
            root = make_root()
            seed(root, [{"branch": "release/29", "pr": 10, "state": "ci"}])
            r = routes_for_green()
            r[("gh", "run", "list", "--commit")] = (0, resp)
            sh = FakeShell(r)
            watcher(root, sh).run_once()
            self.assertEqual(sh.writes(), [])
            self.assertEqual(L.load(root)["trains"][0]["state"], state)

    def test_mixed_runs_one_pending_does_not_merge(self):
        root = make_root()
        seed(root, [{"branch": "release/29", "pr": 10, "state": "ci"}])
        r = routes_for_green()
        r[("gh", "run", "list", "--commit")] = (0, runs((1, "completed", "success", SHA, "x"), (2, "queued", None, SHA, "x")))
        sh = FakeShell(r)
        watcher(root, sh).run_once()
        self.assertEqual(sh.writes(), [])

    def test_hold_blocks_merge_until_released_or_expired(self):
        root = make_root()
        seed(root, [{"branch": "release/29", "pr": 10, "state": "ci",
                     "hold": {"reason": "owner wants to look", "by": "owner", "until": None}}])
        sh = FakeShell(routes_for_green())
        watcher(root, sh).run_once()
        self.assertEqual(sh.writes(), [])
        t = L.load(root)["trains"][0]
        self.assertEqual(t["state"], "green")  # CI is recorded, the merge waits
        # hold expired
        def fn(led):
            led["trains"][0]["hold"]["until"] = "2026-10-14T11:00:00Z"
        L.update(root, fn)
        sh2 = FakeShell(routes_for_green())
        watcher(root, sh2).run_once()
        self.assertEqual([c for c in sh2.writes() if c[:3] == ["gh", "pr", "merge"]], [["gh", "pr", "merge", "10", "--merge", "--match-head-commit", SHA]])

    def test_failed_merge_is_recorded_and_state_stays_green(self):
        root = make_root()
        seed(root, [{"branch": "release/29", "pr": 10, "state": "ci"}])
        r = routes_for_green()
        r[("gh", "pr", "merge")] = (1, "")
        watcher(root, FakeShell(r)).run_once()
        led = L.load(root)
        self.assertEqual(led["trains"][0]["state"], "green")
        self.assertIn("merge.failed", [e["kind"] for e in led["events"]])

    def test_auto_merge_guard(self):
        w = watcher(make_root(), FakeShell())
        with self.assertRaises(AssertionError):
            w.act(["gh", "pr", "merge", "1", "--auto", "--merge"])

    def test_dry_run_prints_and_does_nothing(self):
        root = make_root()
        seed(root, [{"branch": "release/29", "pr": 10, "state": "ci"}])
        sh = FakeShell(routes_for_green())
        lines = []
        w = W.Watcher(root, sh=sh, dry_run=True, now=lambda: NOW, out=lines.append)
        w.run_once()
        self.assertEqual(sh.writes(), [])
        self.assertTrue(any(l == "dry-run: gh pr merge 10 --merge --match-head-commit " + SHA for l in lines))
        self.assertEqual(L.load(root)["trains"][0]["state"], "ci")  # nothing written


class GreenNeedsEveryRequiredWorkflowTests(unittest.TestCase):
    def run_with(self, cfg, per_workflow, state="ci", green_at=None):
        root = make_root(cfg)
        seed(root, [{"branch": "release/41", "pr": 10, "state": state, "green_at": green_at}])
        routes = routes_for_green()

        def listing(argv):
            wf = argv[argv.index("--workflow") + 1]
            return 0, runs(*per_workflow.get(wf, []))
        routes[("gh", "run", "list", "--commit")] = listing
        sh = FakeShell(routes)
        watcher(root, sh).run_once()
        return root, sh

    def train(self, root):
        return L.load(root)["trains"][0]

    def test_sibling_workflow_success_does_not_green_while_ci_runs(self):
        cfg = {"watcher": {"ci_workflows": ["ci.yml", "installer.yml"]}}
        root, sh = self.run_with(cfg, {"ci.yml": [(1, "in_progress", None, SHA, "release/41")],
                                       "installer.yml": [(2, "completed", "success", SHA, "release/41")]})
        t = self.train(root)
        self.assertNotEqual(t["state"], "green")
        self.assertIsNone(t["green_at"])
        self.assertEqual([c for c in sh.calls if c[:3] == ["gh", "pr", "merge"]], [])

    def test_missing_required_workflow_is_not_green(self):
        cfg = {"watcher": {"ci_workflows": ["ci.yml", "installer.yml"]}}
        root, _ = self.run_with(cfg, {"ci.yml": [(1, "completed", "success", SHA, "release/41")]})
        self.assertIsNone(self.train(root)["green_at"])

    def test_all_required_workflows_success_is_green_and_skipped_is_not_success(self):
        cfg = {"watcher": {"ci_workflows": ["ci.yml", "installer.yml"]}}
        ok = (1, "completed", "success", SHA, "release/41")
        root, _ = self.run_with(cfg, {"ci.yml": [ok], "installer.yml": [(2, "completed", "success", SHA, "r")]})
        self.assertTrue(self.train(root)["green_at"])
        root, _ = self.run_with(cfg, {"ci.yml": [ok], "installer.yml": [(2, "completed", "skipped", SHA, "r")]})
        self.assertIsNone(self.train(root)["green_at"])

    def test_failed_required_workflow_is_red(self):
        root, _ = self.run_with({}, {"ci.yml": [(1, "completed", "failure", SHA, "release/41")]})
        self.assertEqual(self.train(root)["state"], "red")

    def test_green_is_revoked_when_a_required_run_is_running_again(self):
        root, sh = self.run_with({}, {"ci.yml": [(1, "completed", "success", SHA, "r"), (3, "in_progress", None, SHA, "r")]},
                                 state="green", green_at="2026-10-14T11:00:00Z")
        t = self.train(root)
        self.assertEqual((t["state"], t["green_at"]), ("ci", None))
        self.assertEqual([c for c in sh.calls if c[:3] == ["gh", "pr", "merge"]], [])

    def test_latest_run_of_a_workflow_counts(self):
        root, _ = self.run_with({}, {"ci.yml": [(1, "completed", "failure", SHA, "r"), (2, "completed", "success", SHA, "r")]})
        self.assertTrue(self.train(root)["green_at"])


class RedRerunTests(unittest.TestCase):
    def red_train(self, root):
        seed(root, [{"branch": "release/29", "pr": 10, "state": "red",
                     "ci": {"head_sha": SHA, "run_ids": [1], "state": "failure", "started_at": None}}])

    def test_red_rerun_green_on_same_head_merges(self):
        root = make_root()
        self.red_train(root)
        sh = FakeShell(routes_for_green())      # run 1 is now completed/success: the owner re-ran it
        watcher(root, sh).run_once()
        merges = [c for c in sh.calls if c[:3] == ["gh", "pr", "merge"]]
        self.assertEqual(merges, [["gh", "pr", "merge", "10", "--merge", "--match-head-commit", SHA]])
        self.assertFalse(any("--auto" in c for c in sh.calls))
        t = L.load(root)["trains"][0]
        self.assertEqual((t["state"], t["ci"]["state"]), ("merged", "success"))
        self.assertIsNotNone(t["green_at"])

    def test_red_rerun_green_with_hold_goes_green_without_merging(self):
        root = make_root()
        self.red_train(root)
        L.update(root, lambda led: led["trains"][0].update(hold={"reason": "look", "by": "owner", "until": None}))
        sh = FakeShell(routes_for_green())
        watcher(root, sh).run_once()
        self.assertEqual(sh.writes(), [])
        self.assertEqual(L.load(root)["trains"][0]["state"], "green")

    def test_red_stays_red_with_no_newer_run_and_costs_one_check(self):
        root = make_root()
        self.red_train(root)
        r = routes_for_green()
        r[("gh", "run", "list", "--commit")] = (0, runs((1, "completed", "failure", SHA, "release/29")))
        sh = FakeShell(r)
        before = L.load(root)["trains"][0]
        watcher(root, sh).run_once()
        self.assertEqual(sh.writes(), [])
        self.assertEqual([c[:3] for c in sh.calls if c[:2] == ["gh", "pr"]], [["gh", "pr", "view"]])
        self.assertEqual(len([c for c in sh.calls if c[:3] == ["gh", "run", "list"]]), 1)
        t = L.load(root)["trains"][0]
        self.assertEqual((t["state"], t["ci"]), ("red", before["ci"]))

    def test_red_with_rerun_still_running_stays_red(self):
        root = make_root()
        self.red_train(root)
        r = routes_for_green()
        r[("gh", "run", "list", "--commit")] = (0, runs((1, "in_progress", None, SHA, "release/29")))
        sh = FakeShell(r)
        watcher(root, sh).run_once()
        self.assertEqual(sh.writes(), [])
        self.assertEqual(L.load(root)["trains"][0]["state"], "red")

    def moved(self, new_runs, **cfg):
        root = make_root()
        self.red_train(root)
        r = routes_for_green(head=OLD)
        r[("gh", "run", "list", "--commit")] = (0, new_runs)
        sh = FakeShell(r)
        watcher(root, sh).run_once()
        return sh, L.load(root)["trains"][0]

    def test_red_old_head_new_head_green_goes_green_and_merges(self):
        sh, t = self.moved(runs((7, "completed", "success", OLD, "release/29")))
        self.assertEqual([c for c in sh.calls if c[:3] == ["gh", "pr", "merge"]],
                         [["gh", "pr", "merge", "10", "--merge", "--match-head-commit", OLD]])
        self.assertEqual((t["state"], t["ci"]["head_sha"], t["ci"]["run_ids"]), ("merged", OLD, [7]))

    def test_red_old_head_new_head_running_becomes_running(self):
        sh, t = self.moved(runs((7, "in_progress", None, OLD, "release/29")))
        self.assertEqual(sh.writes(), [])
        self.assertEqual((t["state"], t["ci"]["head_sha"], t["ci"]["state"]), ("ci", OLD, "running"))

    def test_red_old_head_new_head_red_stays_red_on_new_head(self):
        sh, t = self.moved(runs((7, "completed", "failure", OLD, "release/29")))
        self.assertEqual(sh.writes(), [])
        self.assertEqual((t["state"], t["ci"]["head_sha"], t["ci"]["run_ids"]), ("red", OLD, [7]))

    def test_string_ci_does_not_crash_and_logs_once(self):
        root = make_root()
        seed(root, [{"branch": "release/29", "pr": 10, "state": "red", "ci": "failure"}])
        msgs = []
        sh = FakeShell(routes_for_green())
        w = W.Watcher(root, sh=sh, now=lambda: NOW, out=msgs.append)
        w.run_once()
        w.run_once()
        self.assertEqual(len([m for m in msgs if "not a dict" in m]), 1)
        self.assertIsInstance(L.load(root)["trains"][0]["ci"], dict)

    def test_string_ci_on_a_running_train_does_not_crash(self):
        root = make_root()
        seed(root, [{"branch": "release/29", "pr": 10, "state": "ci", "ci": "running"}])
        watcher(root, FakeShell(routes_for_green())).run_once()
        self.assertEqual(L.load(root)["trains"][0]["state"], "merged")


class NextTrainTests(unittest.TestCase):
    def test_merge_then_push_next_joined_train_and_open_ready_pr(self):
        root = make_root()
        seed(root, [{"branch": "release/29", "pr": 10, "state": "ci"},
                    {"branch": "release/30", "state": "joined", "release_no": 30, "cargo": [{"task": "CO1"}]}])
        r = routes_for_green()
        r[("git", "push")] = (0, "")
        r[("gh", "pr", "list", "--head")] = (0, "[]")
        r[("gh", "pr", "create")] = (0, "https://github.com/o/r/pull/11\n")
        sh = FakeShell(r)
        watcher(root, sh, repo="o/r").run_once()
        order = [c[:3] if c[0] == "gh" else c[:2] for c in sh.writes()]
        self.assertEqual(order, [["gh", "pr", "merge"], ["git", "push"], ["gh", "pr", "create"]])
        create = [c for c in sh.calls if c[:3] == ["gh", "pr", "create"]][0]
        self.assertNotIn("--draft", create)
        self.assertEqual(create[create.index("--head") + 1], "release/30")
        led = L.load(root)
        t1, t2 = led["trains"]
        self.assertEqual(t1["state"], "merged")
        self.assertEqual((t2["state"], t2["pr"]), ("ci", 11))
        self.assertIsNotNone(t2["pushed_at"])

    def test_next_train_not_pushed_while_another_train_ci_runs_or_when_held(self):
        root = make_root()
        seed(root, [{"branch": "release/29", "pr": 10, "state": "ci"},
                    {"branch": "release/30", "state": "joined"}])
        r = routes_for_green()
        r[("gh", "run", "list", "--commit")] = (0, runs((1, "in_progress", None, SHA, "release/29")))
        sh = FakeShell(r)
        watcher(root, sh).run_once()
        self.assertFalse(any(c[0] == "git" and c[1] == "push" for c in sh.calls))
        # merged but the next train is on hold
        root2 = make_root()
        seed(root2, [{"branch": "release/29", "pr": 10, "state": "ci"},
                     {"branch": "release/30", "state": "joined", "hold": {"reason": "r", "by": "owner"}}])
        sh2 = FakeShell(routes_for_green())
        watcher(root2, sh2).run_once()
        self.assertTrue(any(c[:3] == ["gh", "pr", "merge"] for c in sh2.calls))
        self.assertFalse(any(c[0] == "git" and c[1] == "push" for c in sh2.calls))

    def test_existing_open_pr_is_reused(self):
        root = make_root()
        seed(root, [{"branch": "release/29", "pr": 10, "state": "ci"}, {"branch": "release/30", "state": "joined"}])
        r = routes_for_green()
        r[("git", "push")] = (0, "")
        r[("gh", "pr", "list", "--head")] = (0, json.dumps([{"number": 55}]))
        sh = FakeShell(r)
        watcher(root, sh).run_once()
        self.assertFalse(any(c[:3] == ["gh", "pr", "create"] for c in sh.calls))
        self.assertEqual(L.load(root)["trains"][1]["pr"], 55)


class RunTidyTests(unittest.TestCase):
    def test_cancel_runs_superseded_by_newer_head(self):
        root = make_root()
        seed(root, [{"branch": "release/29", "pr": 10, "state": "ci"}])
        r = routes_for_green()
        r[("gh", "run", "list", "--branch")] = (0, runs((7, "in_progress", None, OLD, "release/29"),
                                                         (8, "in_progress", None, SHA, "release/29"),
                                                         (9, "completed", "failure", OLD, "release/29")))
        r[("gh", "run", "list", "--commit")] = (0, runs((8, "in_progress", None, SHA, "release/29")))
        r[("gh", "run", "cancel")] = (0, "")
        sh = FakeShell(r)
        watcher(root, sh).run_once()
        self.assertEqual([c for c in sh.calls if c[:3] == ["gh", "run", "cancel"]][0][3], "7")
        self.assertEqual(len([c for c in sh.calls if c[:3] == ["gh", "run", "cancel"]]), 1)

    def test_hold_dependabot_while_train_ci_runs_then_rerun_after(self):
        root = make_root()
        seed(root, [{"branch": "release/29", "pr": 10, "state": "ci"}])
        r = routes_for_green()
        r[("gh", "run", "list", "--commit")] = (0, runs((1, "in_progress", None, SHA, "release/29")))
        dep = runs((50, "in_progress", None, "c" * 40, "dependabot/npm/x"), (51, "queued", None, SHA, "release/29"),
                   (52, "in_progress", None, "d" * 40, "main"))
        r[("gh", "run", "list", "--status")] = (0, dep)
        r[("gh", "run", "cancel")] = (0, "")
        sh = FakeShell(r)
        watcher(root, sh).run_once()
        cancelled = [c[3] for c in sh.calls if c[:3] == ["gh", "run", "cancel"]]
        self.assertEqual(set(cancelled), {"50"})  # not the train's own run, not the base branch
        held = L.load(root)["held_runs"]
        self.assertEqual([h["id"] for h in held], [50])
        self.assertFalse(any(c[:3] == ["gh", "run", "rerun"] for c in sh.calls))

        # the train goes green and merges: the held run is re-run
        r2 = routes_for_green()
        r2[("gh", "run", "rerun")] = (0, "")
        sh2 = FakeShell(r2)
        watcher(root, sh2).run_once()
        self.assertEqual([c for c in sh2.calls if c[:3] == ["gh", "run", "rerun"]], [["gh", "run", "rerun", "50"]])
        self.assertEqual(L.load(root)["held_runs"], [])

    def test_no_hold_when_no_train_ci_runs(self):
        root = make_root()
        seed(root, [{"branch": "release/29", "state": "joined"}])
        r = {("gh", "run", "list", "--status"): (0, runs((50, "in_progress", None, "c" * 40, "dependabot/x"))),
             ("gh", "api"): (1, "")}
        sh = FakeShell(r)
        watcher(root, sh).run_once()
        self.assertEqual(sh.writes(), [])


class AgentTests(unittest.TestCase):
    def agent(self, **kw):
        a = {"task": "CO152", "where": "local", "id": "ag1", "branch": "CO152-x", "head_sha": SHA,
             "started": "2026-10-14T10:00:00Z", "last_activity": "2026-10-14T11:50:00Z",
             "eta": {"total_min": 25, "breakdown": {"setup": 5, "work": 12, "checks": 8}}, "state": "running"}
        a.update(kw)
        return a

    def run_agent(self, agent, ls_out="", fetcher=None):
        root = make_root()
        seed(root, agents=[agent])
        sh = FakeShell({("git", "ls-remote"): (0, ls_out), ("gh", "api"): (1, "")})
        W.Watcher(root, sh=sh, now=lambda: NOW, out=lambda *_: None, routine_fetcher=fetcher).run_once()
        return L.load(root)["agents"][0], sh

    def test_branch_moved_updates_head_and_activity(self):
        a, sh = self.run_agent(self.agent(), "%s\trefs/heads/CO152-x\n" % OLD)
        self.assertEqual((a["head_sha"], a["state"], a["last_activity"]), (OLD, "pushed", "2026-10-14T12:00:00Z"))
        self.assertEqual(sh.calls[0], ["git", "ls-remote", "origin", "refs/heads/CO152-x"])

    def test_stalled_when_idle_over_twice_work_estimate(self):
        old = self.agent(last_activity="2026-10-14T11:30:00Z")  # 30 min idle > 2 * 12
        a, _ = self.run_agent(old, "%s\trefs/heads/CO152-x\n" % SHA)
        self.assertEqual(a["state"], "stalled")

    def test_not_stalled_just_inside_the_limit(self):
        a, _ = self.run_agent(self.agent(last_activity="2026-10-14T11:37:00Z"), "%s\trefs/heads/CO152-x\n" % SHA)
        self.assertEqual(a["state"], "running")  # 23 min idle <= 24

    def test_stalled_agent_recovers_on_new_push(self):
        a, _ = self.run_agent(self.agent(state="stalled", last_activity="2026-10-14T09:00:00Z"), "%s\trefs/heads/CO152-x\n" % OLD)
        self.assertEqual(a["state"], "pushed")

    def test_log_mtime_counts_as_activity(self):
        import tempfile
        fd, path = tempfile.mkstemp()
        os.close(fd)
        os.utime(path, (NOW.timestamp(), NOW.timestamp()))
        a, _ = self.run_agent(self.agent(log_path=path, last_activity="2026-10-14T09:00:00Z"), "%s\trefs/heads/CO152-x\n" % SHA)
        self.assertEqual(a["state"], "running")
        self.assertEqual(a["last_activity"], "2026-10-14T12:00:00Z")

    def test_routine_status_via_injected_fetcher(self):
        a, _ = self.run_agent(self.agent(where="cloud", id="trig_1"), "",
                              lambda ag: {"state": "done", "last_activity": "2026-10-14T11:59:00Z"})
        self.assertEqual((a["state"], a["last_activity"]), ("done", "2026-10-14T11:59:00Z"))

    def test_finished_agents_are_left_alone(self):
        a, sh = self.run_agent(self.agent(state="done"))
        self.assertEqual(a["state"], "done")
        self.assertFalse(any(c[0] == "git" for c in sh.calls))


class RunnersInstallsHeartbeatTests(unittest.TestCase):
    def test_runners_installs_and_heartbeat(self):
        import tempfile
        state = tempfile.mktemp(suffix=".json")
        with open(state, "w") as fh:
            json.dump({"version": "0.1.6212", "state": "done", "ended": "2026-10-14T11:00:00Z"}, fh)
        root = make_root({"install_state_files": [{"product": "home", "path": state}], "local_runners": ["GameRoomPC-linux"]})
        seed(root, runners=[{"name": "GameRoomPC-linux", "paused_by": "B14-build"}])
        payload = {"runners": [{"name": "GameRoomPC-linux", "status": "online", "busy": True,
                                "labels": [{"name": "self-hosted"}, {"name": "Linux"}]}]}
        sh = FakeShell({("gh", "api"): (0, json.dumps(payload))})
        watcher(root, sh).run_once("2026-10-14T11:00:00Z")
        led = L.load(root)
        self.assertEqual(sh.calls[-1][:2], ["gh", "api"])
        self.assertIn("actions/runners", sh.calls[-1][2])
        r = led["runners"][0]
        self.assertEqual((r["online"], r["busy"], r["local"], r["paused_by"]), (True, True, True, "B14-build"))
        self.assertEqual(r["labels"], ["self-hosted", "Linux"])
        self.assertEqual((led["installs"][0]["product"], led["installs"][0]["version"], led["installs"][0]["state"]),
                         ("home", "0.1.6212", "done"))
        hb = led["watchers"][0]
        self.assertEqual((hb["pid"], hb["kind"], hb["heartbeat_at"]), (os.getpid(), "delivery_watch", "2026-10-14T12:00:00Z"))
        watcher(root, sh).run_once("2026-10-14T11:00:00Z")
        self.assertEqual(len(L.load(root)["watchers"]), 1)

    def test_one_failing_pass_does_not_stop_the_rest(self):
        root = make_root()
        w = watcher(root, FakeShell())
        w.pass_trains = lambda: 1 / 0
        w.run_once()
        self.assertEqual(len(L.load(root)["watchers"]), 1)


if __name__ == "__main__":
    unittest.main()
