import json
import os
import unittest
from pathlib import Path
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


class AdoptPrTests(unittest.TestCase):
    """DS95: a train pushed by hand whose PR was already open gets that PR from `gh pr list --head`."""

    def routes(self, prs):
        r = routes_for_green(pr=103, branch="DS90-integration")
        r[("gh", "pr", "list", "--head")] = (0, json.dumps([{"number": n} for n in prs]))
        return r

    def test_pushed_train_without_pr_adopts_the_open_pr_and_merges_at_green(self):
        root = make_root()
        seed(root, [{"branch": "DS90-integration", "state": "pushed"}])
        sh = FakeShell(self.routes([103]))
        watcher(root, sh).run_once()
        led = L.load(root)
        t = led["trains"][0]
        self.assertEqual((t["pr"], t["state"]), (103, "merged"))
        self.assertIn("train.pr_adopted", [e["kind"] for e in led["events"]])
        self.assertIn(["gh", "pr", "merge", "103", "--merge", "--match-head-commit", SHA], sh.calls)

    def test_adopted_pr_gives_the_train_its_head_sha(self):
        # DS97: the adopted train's head is known, so a CI result matches it by sha
        root = make_root()
        seed(root, [{"branch": "DS90-integration", "state": "pushed"}])
        r = self.routes([103])
        r[("gh", "pr", "list", "--head")] = (0, json.dumps([{"number": 103, "headRefOid": SHA}]))
        w = watcher(root, FakeShell(r))
        w.adopt_pr(L.load(root)["trains"][0])
        self.assertEqual(L.load(root)["trains"][0]["ci"]["head_sha"], SHA)

    def test_two_open_prs_for_the_branch_adopt_nothing(self):
        root = make_root()
        seed(root, [{"branch": "DS90-integration", "state": "pushed"}])
        sh = FakeShell(self.routes([103, 104]))
        watcher(root, sh).run_once()
        t = L.load(root)["trains"][0]
        self.assertEqual((t["pr"], t["state"]), (None, "pushed"))
        self.assertEqual(sh.writes(), [])

    def test_held_train_is_not_adopted(self):
        root = make_root()
        seed(root, [{"branch": "DS90-integration", "state": "pushed",
                     "hold": {"reason": "owner asked", "by": "owner", "until": None}}])
        sh = FakeShell(self.routes([103]))
        watcher(root, sh).run_once()
        self.assertIsNone(L.load(root)["trains"][0]["pr"])
        self.assertFalse(any(c[:3] == ["gh", "pr", "list"] for c in sh.calls))


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
                    {"branch": "release/30", "state": "joined", "release_no": 30, "cargo": [{"task": "DV1"}]}])
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

    def _create_body(self, summaries):
        root = make_root()
        seed(root, [{"branch": "release/29", "pr": 10, "state": "ci"},
                    {"branch": "release/30", "state": "joined", "release_no": 30, "cargo": [{"task": "DV1"}]}])
        if summaries is not None:
            os.makedirs(os.path.join(str(root), ".delivery"), exist_ok=True)
            with open(os.path.join(str(root), ".delivery", "docs-summaries.md"), "w", encoding="utf-8") as f:
                f.write(summaries)
        r = routes_for_green()
        r[("git", "push")] = (0, "")
        r[("gh", "pr", "list", "--head")] = (0, "[]")
        r[("gh", "pr", "create")] = (0, "https://github.com/o/r/pull/11\n")
        sh = FakeShell(r)
        watcher(root, sh, repo="o/r").run_once()
        create = [c for c in sh.calls if c[:3] == ["gh", "pr", "create"]][0]
        return create[create.index("--body") + 1]

    def test_ready_pr_body_carries_docs_summaries_when_present(self):
        body = self._create_body("## Docs\n- DV1: moved the guide\n")
        self.assertTrue(body.startswith("Train "))
        self.assertIn("DV1", body.splitlines()[0])
        self.assertTrue(body.endswith("## Docs\n- DV1: moved the guide"), body)

    def test_ready_pr_body_without_or_with_empty_summaries_is_the_train_line(self):
        self.assertEqual(self._create_body(None).count("\n"), 0)
        self.assertEqual(self._create_body("  \n").count("\n"), 0)

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
        a = {"task": "DV152", "where": "local", "id": "ag1", "branch": "DV152-x", "head_sha": SHA,
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
        a, sh = self.run_agent(self.agent(), "%s\trefs/heads/DV152-x\n" % OLD)
        self.assertEqual((a["head_sha"], a["state"], a["last_activity"]), (OLD, "pushed", "2026-10-14T12:00:00Z"))
        self.assertEqual(sh.calls[0], ["git", "ls-remote", "origin", "refs/heads/DV152-x"])

    def test_stalled_when_idle_over_twice_work_estimate(self):
        old = self.agent(last_activity="2026-10-14T11:30:00Z")  # 30 min idle > 2 * 12
        a, _ = self.run_agent(old, "%s\trefs/heads/DV152-x\n" % SHA)
        self.assertEqual(a["state"], "stalled")

    def test_not_stalled_just_inside_the_limit(self):
        a, _ = self.run_agent(self.agent(last_activity="2026-10-14T11:37:00Z"), "%s\trefs/heads/DV152-x\n" % SHA)
        self.assertEqual(a["state"], "running")  # 23 min idle <= 24

    def test_stalled_agent_recovers_on_new_push(self):
        a, _ = self.run_agent(self.agent(state="stalled", last_activity="2026-10-14T09:00:00Z"), "%s\trefs/heads/DV152-x\n" % OLD)
        self.assertEqual(a["state"], "pushed")

    def test_log_mtime_counts_as_activity(self):
        import tempfile
        fd, path = tempfile.mkstemp()
        os.close(fd)
        os.utime(path, (NOW.timestamp(), NOW.timestamp()))
        a, _ = self.run_agent(self.agent(log_path=path, last_activity="2026-10-14T09:00:00Z"), "%s\trefs/heads/DV152-x\n" % SHA)
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
        root = make_root({"install_state_files": [{"product": "app", "path": state}], "local_runners": ["build-pc-linux"]})
        seed(root, runners=[{"name": "build-pc-linux", "paused_by": "B14-build"}])
        payload = {"runners": [{"name": "build-pc-linux", "status": "online", "busy": True,
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
                         ("app", "0.1.6212", "done"))
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


class RunnerScriptPathTests(unittest.TestCase):
    def test_inside_outside_and_absolute_outside(self):
        import tempfile
        msgs = []
        inside = make_root({"runner_plan": {"script": "tools/rp.py"}})
        (inside / "tools").mkdir()
        (inside / "tools" / "rp.py").write_text("")
        w = W.Watcher(inside, sh=FakeShell(), now=lambda: NOW, out=lambda *a: msgs.append(" ".join(map(str, a))))
        self.assertEqual(w.runner_script(), str(inside / "tools" / "rp.py"))
        self.assertEqual(msgs, [])
        outside_dir = tempfile.mkdtemp(prefix="dl-out-")
        script = os.path.join(outside_dir, "rp.py")
        open(script, "w").close()
        for value in (os.path.relpath(script, str(inside)), script):
            msgs.clear()
            root = make_root({"runner_plan": {"script": value}})
            w = W.Watcher(root, sh=FakeShell(), now=lambda: NOW, out=lambda *a: msgs.append(" ".join(map(str, a))))
            self.assertIsNone(w.runner_script())
            self.assertIn("outside the repository root", msgs[0])


# --- CO688: reconcile what the hook could not see ------------------------------------------------------------

def pr_list_route(branch, number=847, head=SHA, draft=False):
    return {("gh", "pr", "list", "--head", branch): (0, json.dumps([{"number": number, "headRefOid": head, "isDraft": draft}]))}


class ReconcileTests(unittest.TestCase):
    def test_watcher_adopts_pr_of_a_planned_train(self):
        # PR 847 (release/132): the train was planned an hour after the push and the PR, so it sat in `planned`
        # for ever; adopt_pr only looked at pushed/ci trains
        root = make_root()
        seed(root, [{"branch": "release/132", "state": "planned"}])
        routes = {**routes_for_green(pr=847, head=SHA, branch="release/132"), **pr_list_route("release/132"),
                  ("gh", "run", "list", "--commit"): (0, runs((1, "in_progress", None, SHA, "release/132")))}
        watcher(root, FakeShell(routes)).run_once()
        t = L.load(root)["trains"][0]
        self.assertEqual(t["pr"], 847)
        self.assertEqual(t["ci"]["head_sha"], SHA)
        self.assertEqual(t["state"], "ci")
        self.assertIn("train.pr_adopted", [e["kind"] for e in L.load(root)["events"]])

    def test_a_draft_pr_is_adopted_but_does_not_start_ci(self):
        root = make_root()
        seed(root, [{"branch": "release/132", "state": "joined"}])
        routes = {**routes_for_green(pr=847, head=SHA, branch="release/132"), **pr_list_route("release/132", draft=True)}
        watcher(root, FakeShell(routes)).run_once()
        t = L.load(root)["trains"][0]
        self.assertEqual((t["pr"], t["state"]), (847, "joined"))

    def test_no_open_pr_leaves_a_planned_train_alone(self):
        root = make_root()
        seed(root, [{"branch": "release/132", "state": "planned"}])
        routes = {("gh", "pr", "list", "--head"): (0, "[]")}
        watcher(root, FakeShell(routes)).run_once()
        t = L.load(root)["trains"][0]
        self.assertEqual((t["pr"], t["state"]), (None, "planned"))

    def test_train_with_a_pr_and_a_moved_head_is_repointed(self):
        root = make_root()
        seed(root, [{"branch": "release/134", "state": "joined", "pr": 849,
                     "ci": {"head_sha": OLD, "run_ids": [5], "state": "failure", "started_at": None}}])
        routes = {("gh", "pr", "view", "849"): (0, json.dumps({"headRefOid": SHA, "state": "OPEN"})),
                  ("gh", "run", "list", "--commit"): (0, "[]")}
        watcher(root, FakeShell(routes)).run_once()
        t = L.load(root)["trains"][0]
        self.assertEqual(t["ci"]["head_sha"], SHA)
        self.assertEqual(t["ci"]["run_ids"], [])
        self.assertEqual(t["state"], "ci")
        self.assertIn("train.repushed", [e["kind"] for e in L.load(root)["events"]])

    def test_red_train_is_still_repointed(self):
        root = make_root()
        seed(root, [{"branch": "release/134", "state": "red", "pr": 849,
                     "ci": {"head_sha": OLD, "run_ids": [5], "state": "failure", "started_at": None}}])
        routes = {("gh", "pr", "view", "849"): (0, json.dumps({"headRefOid": SHA, "state": "OPEN"})),
                  ("gh", "run", "list", "--commit"): (0, "[]")}
        watcher(root, FakeShell(routes)).run_once()
        self.assertEqual(L.load(root)["trains"][0]["ci"]["head_sha"], SHA)

    def test_guard_started_is_logged_once_not_every_pass(self):
        root = make_root({"runners": [{"name": "r1"}], "watcher": {"manage_runners": True}})
        script = root / "scripts" / "delivery"
        script.mkdir(parents=True)
        (script / "runner_plan.py").write_text("")

        class Child:
            def poll(self):
                return 0

        class Shell(FakeShell):
            def spawn(self, argv, cwd=None):
                return Child()
        w = watcher(root, Shell())
        for _ in range(5):
            w.pass_runner_guard()
        kinds = [e["kind"] for e in L.load(root)["events"]]
        self.assertEqual(kinds.count("runner.guard_started"), 1, kinds)
        self.assertEqual(len([a for a in w.actions if "runners" in a]), 5, "it is still relaunched every pass")


def iso_ago(minutes):
    return L.iso(NOW - timedelta(minutes=minutes))


def agent_row(**kw):
    a = {"task": "DS33", "id": "trig_01", "where": "cloud", "state": "running", "branch": "claude/DS33-x",
         "started": iso_ago(120), "last_checked": iso_ago(40), "last_activity": iso_ago(60),
         "eta": {"breakdown": {"setup": 5, "work": 20, "checks": 10}}}
    a.update(kw)
    return a


def seed_agents(root, *rows):
    L.update(root, lambda led: led["agents"].extend(rows))


def pr_routes(commit_min_ago=5, draft=True, state="OPEN", runs_json="[]"):
    pr = [{"number": 7, "headRefName": "claude/DS33-x", "headRefOid": SHA, "isDraft": draft, "state": state,
           "updatedAt": iso_ago(1), "commits": [{"committedDate": iso_ago(commit_min_ago)}]}]
    return {("gh", "pr", "list"): (0, json.dumps(pr)), ("gh", "run", "list", "--commit"): (0, runs_json)}


class AgentCheckTests(unittest.TestCase):
    def test_running_cloud_row_gets_last_checked_and_fields(self):
        root = make_root()
        seed_agents(root, agent_row())
        sh = FakeShell(pr_routes(commit_min_ago=5))
        watcher(root, sh).pass_checks()
        a = L.load(root)["agents"][0]
        self.assertEqual(a["last_checked"], L.iso(NOW))
        self.assertEqual(a["head_sha"], SHA)
        self.assertEqual(a["branch"], "claude/DS33-x")
        self.assertEqual(a["last_activity"], iso_ago(5))
        self.assertFalse(a["stalled"])
        self.assertIn("PR #7 draft", a["check_note"])
        self.assertEqual(a["state"], "running")
        self.assertEqual(sh.writes(), [])

    def test_task_prefix_search_when_no_branch(self):
        root = make_root()
        seed_agents(root, agent_row(branch=None))
        sh = FakeShell(pr_routes())
        watcher(root, sh).pass_checks()
        self.assertTrue(any("head:claude/DS33-" in c for c in sh.calls if c[:3] == ["gh", "pr", "list"]))
        self.assertEqual(L.load(root)["agents"][0]["last_checked"], L.iso(NOW))

    def test_recent_check_is_skipped_and_interval_is_configurable(self):
        root = make_root()
        seed_agents(root, agent_row(last_checked=iso_ago(10)))
        sh = FakeShell(pr_routes())
        watcher(root, sh).pass_checks()
        self.assertEqual(sh.calls, [])
        root = make_root({"watcher": {"check_interval_min": 5}})
        seed_agents(root, agent_row(last_checked=iso_ago(10)))
        watcher(root, FakeShell(pr_routes())).pass_checks()
        self.assertEqual(L.load(root)["agents"][0]["last_checked"], L.iso(NOW))

    def test_stalled_flag_when_idle_beyond_work_plus_checks(self):
        root = make_root()
        seed_agents(root, agent_row(last_activity=iso_ago(200)))
        watcher(root, FakeShell(pr_routes(commit_min_ago=45))).pass_checks()    # limit is 30 min
        a = L.load(root)["agents"][0]
        self.assertTrue(a["stalled"])
        self.assertIn("STALLED", a["check_note"])
        self.assertEqual(a["state"], "running")

    def test_local_row_uses_log_mtime_and_branch_head(self):
        root = make_root()
        log = Path(root) / "agent.log"
        log.write_text("x")
        os.utime(log, (NOW.timestamp() - 120, NOW.timestamp() - 120))
        seed_agents(root, agent_row(where="local", id="loc1", log_path=str(log), branch="DS33-x"))
        sh = FakeShell({("git", "ls-remote"): (0, SHA + "\trefs/heads/DS33-x\n")})
        watcher(root, sh).pass_checks()
        a = L.load(root)["agents"][0]
        self.assertEqual(a["head_sha"], SHA)
        self.assertEqual(a["last_activity"], iso_ago(2))
        self.assertFalse(a["stalled"])

    def test_no_state_flip_by_guess(self):
        # a merged PR with green runs and a long silence still leaves the row running
        root = make_root()
        seed_agents(root, agent_row(last_activity=iso_ago(500)))
        done = runs((1, "completed", "success", SHA, "claude/DS33-x"))
        watcher(root, FakeShell(pr_routes(commit_min_ago=400, draft=False, state="MERGED", runs_json=done))).pass_checks()
        a = L.load(root)["agents"][0]
        self.assertEqual(a["state"], "running")
        self.assertTrue(a["stalled"])

    def test_non_running_rows_are_not_checked(self):
        root = make_root()
        seed_agents(root, agent_row(state="done", last_checked=None))
        sh = FakeShell(pr_routes())
        watcher(root, sh).pass_checks()
        self.assertEqual(sh.calls, [])
        self.assertIsNone(L.load(root)["agents"][0]["last_checked"])


class AtomicWriteRetryTests(unittest.TestCase):
    def test_winerror5_is_retried_then_succeeds(self):
        calls = []

        def flaky(a, b):
            calls.append(1)
            if len(calls) < 4:
                e = PermissionError(13, "Access is denied")
                e.winerror = 5
                raise e
        slept = []
        L.replace_retry("t", "p", replace=flaky, sleep=slept.append)
        self.assertEqual(len(calls), 4)
        self.assertEqual(len(slept), 3)

    def test_persistent_denial_raises_and_other_errors_do_not_retry(self):
        def always(a, b):
            e = PermissionError(13, "Access is denied")
            e.winerror = 5
            raise e
        with self.assertRaises(PermissionError):
            L.replace_retry("t", "p", replace=always, sleep=lambda s: None)
        n = []

        def other(a, b):
            n.append(1)
            raise FileNotFoundError("x")
        with self.assertRaises(FileNotFoundError):
            L.replace_retry("t", "p", replace=other, sleep=lambda s: None)
        self.assertEqual(len(n), 1)

    def test_ledger_written_utf8_without_newline_translation(self):
        root = make_root()
        L.update(root, lambda led: led["agents"].append({"task": "café"}))
        raw = L.ledger_path(root).read_bytes()
        self.assertNotIn(b"\r\n", raw)
        self.assertIn("café".encode("utf-8"), raw)


if __name__ == "__main__":
    unittest.main()
