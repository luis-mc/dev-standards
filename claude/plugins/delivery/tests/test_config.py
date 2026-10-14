import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from _helpers import L, make_root
from test_watch import FakeShell, NOW, SHA, OLD, routes_for_green, runs, seed, watcher
import delivery_config as C

# the config of comics-organizer PR #351 (CO159-delivery-setup), trimmed to the keys under test
COMICS = {
    "caps": {"cloud": 8, "local": 3, "total": 5}, "work_root": "C:/ComicsWork", "tz": "Europe/Lisbon",
    "base": "master", "train_label_re": r"\b(?:T-\d{4}-\d{2}-\d{2}-\d+|release/\d+[a-z]?)\b",
    "release_branch_re": "^(release|claude)/", "train_branch_re": "^(release|claude)/",
    "brief_markers": ["BRIEF.md"], "checks_off": [], "no_attribution": True, "watch_interval": 600,
    "enforcement": {"mode": "block", "block_ceiling": 3, "log_every_block": True},
    "watcher": {"push_trains": True, "open_prs": True, "merge_on_green": True, "merge_flag": "--merge",
                "never_auto_merge": True},
    "local_runners": ["GameRoomPC"],
    "runners": [{"name": "GameRoomPC", "os": "Windows", "repair": ["powershell -Command x"]},
                {"name": "GameRoomPC-linux", "os": "Linux", "repair": [["docker", "restart", "c"]]},
                {"name": "NUC8-linux", "os": "Linux", "repair": []}],
    "runner_plan": {"retry_seconds": 300, "runner_max_retries": 0, "cancel_replaced_runs": True,
                    "hold_dependabot_during_train": True, "heavy_local_jobs_yield": True, "report_command": "x"},
}


class SpawnShell(FakeShell):
    def __init__(self, routes=None):
        super().__init__(routes)
        self.spawned = []
        self.exit = None

    def spawn(self, argv, cwd=None):
        self.spawned.append(list(argv))
        outer = self

        class Child:
            def poll(self):
                return outer.exit
        return Child()


class ValidateTests(unittest.TestCase):
    def test_real_comics_config_and_template_are_valid(self):
        self.assertEqual(C.validate_config(COMICS), ([], []))
        tpl = Path(__file__).resolve().parents[2] / "project-setup/skills/claude-setup/assets/delivery-config.json"
        self.assertEqual(C.validate_config(json.loads(tpl.read_text(encoding="utf-8"))), ([], []))

    def test_0_1_0_config_and_empty_config_stay_valid(self):
        old = {"caps": {"cloud": 8, "local": 3}, "tz": "UTC", "runners": [], "watcher_interval_s": 600,
               "runner_plan": {"retry_seconds": 300, "report_command": ""}, "_doc": "x"}
        self.assertEqual(C.validate_config(old), ([], []))
        self.assertEqual(C.validate_config({}), ([], []))

    def test_task_spelling_merge_method_and_heavy_jobs_yield(self):
        cfg = {"watcher": {"merge_method": "merge"}, "runner_plan": {"heavy_jobs_yield": False}}
        self.assertEqual(C.validate_config(cfg), ([], []))

    def test_unknown_keys_warn_comments_do_not(self):
        e, w = C.validate_config({"bogus": 1, "_note": 2, "watcher": {"merge_on_gren": True}, "runners": [{"name": "a", "x": 1}]})
        self.assertEqual(e, [])
        self.assertEqual(sorted(w), sorted(["bogus: unknown key (ignored)", "watcher.merge_on_gren: unknown key (ignored)",
                                            "runners[0].x: unknown key (ignored)"]))

    def test_errors_name_the_path(self):
        cases = [({"enforcement": {"mode": "stop"}}, "enforcement.mode"),
                 ({"enforcement": {"block_ceiling": 0}}, "enforcement.block_ceiling"),
                 ({"enforcement": {"log_every_block": "yes"}}, "enforcement.log_every_block"),
                 ({"watcher": {"push_trains": 1}}, "watcher.push_trains"),
                 ({"watcher": {"merge_flag": "--auto"}}, "watcher.merge_flag"),
                 ({"watcher": {"never_auto_merge": False}}, "watcher.never_auto_merge"),
                 ({"runners": [{"os": "x"}]}, "runners[0]"),
                 ({"runners": [{"name": "a", "repair": [5]}]}, "runners[0].repair[0]"),
                 ({"runners": [{"name": "a", "repair": [[]]}]}, "runners[0].repair[0]"),
                 ({"caps": {"cloud": -1}}, "caps.cloud"),
                 ({"checks_off": ["nope"]}, "checks_off[0]"),
                 ({"train_label_re": "("}, "train_label_re"),
                 ({"tz": "Mars/Base"}, "tz"),
                 ({"tz": 5}, "tz")]
        for cfg, where in cases:
            e, _ = C.validate_config(cfg)
            self.assertTrue(any(x.startswith(where) for x in e), (cfg, e))

    def test_cli_exit_codes(self):
        root = make_root({"enforcement": {"mode": "stop"}})
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(C.main(["validate", "--root", str(root)]), 1)
        self.assertIn("error: enforcement.mode", buf.getvalue())
        (root / ".delivery" / "config.json").write_text(json.dumps({"x": 1}))
        with redirect_stdout(io.StringIO()):
            self.assertEqual(C.main(["validate", "--root", str(root)]), 0)
            self.assertEqual(C.main(["validate", "--root", str(root), "--strict"]), 1)
        (root / ".delivery" / "config.json").write_text("{nope")
        with redirect_stdout(io.StringIO()):
            self.assertEqual(C.main(["validate", "--root", str(root)]), 2)
        (root / ".delivery" / "config.json").unlink()
        with redirect_stdout(io.StringIO()):
            self.assertEqual(C.main(["validate", "--root", str(root)]), 0)

    def test_cli_json_output(self):
        root = make_root({"x": 1})
        buf = io.StringIO()
        with redirect_stdout(buf):
            C.main(["validate", "--root", str(root), "--json"])
        out = json.loads(buf.getvalue())
        self.assertEqual((out["status"], out["errors"], len(out["warnings"])), ("ok", [], 1))

    def test_accessors_default_to_0_1_0_behaviour(self):
        self.assertEqual(C.enforcement({}), {"mode": "block", "block_ceiling": 3, "log_every_block": False})
        self.assertEqual(C.enforcement({"enforcement": {"mode": "x", "block_ceiling": "5", "log_every_block": 1}}),
                         {"mode": "block", "block_ceiling": 3, "log_every_block": False})
        self.assertEqual(C.enforcement({"enforcement": {"mode": "warn", "block_ceiling": 5}})["block_ceiling"], 5)
        self.assertTrue(all(C.watcher_flags({}).values()))
        self.assertFalse(C.runner_plan_flags({"runner_plan": {"heavy_local_jobs_yield": False}})["heavy_jobs_yield"])
        self.assertFalse(C.runner_plan_flags({"runner_plan": {"heavy_jobs_yield": False, "heavy_local_jobs_yield": True}})["heavy_jobs_yield"])

    def test_load_tz_failure_is_loud(self):
        with self.assertRaises(ValueError) as cm:
            C.load_tz("Mars/Base")
        self.assertIn("tzdata", str(cm.exception))


def cfg_root(**over):
    cfg = {"runners": [{"name": "r1"}]}
    cfg.update(over)
    return make_root(cfg)


class WatcherObeysConfigTests(unittest.TestCase):
    def merges(self, sh):
        return [c for c in sh.calls if c[:3] == ["gh", "pr", "merge"]]

    def test_merge_on_green_false_never_merges(self):
        root = make_root({"watcher": {"merge_on_green": False}})
        seed(root, [{"branch": "release/29", "pr": 10, "state": "ci"}])
        sh = FakeShell(routes_for_green())
        watcher(root, sh).run_once()
        self.assertEqual(self.merges(sh), [])
        self.assertEqual(L.load(root)["trains"][0]["state"], "green")

    def test_merge_waits_when_head_moved_since_green_run(self):
        root = make_root()
        seed(root, [{"branch": "release/29", "pr": 10, "state": "ci"}])
        r = routes_for_green()
        heads = iter([SHA, OLD])      # the first read is the green run's head, the second sees a new push
        r[("gh", "pr", "view", "10")] = lambda argv: (0, json.dumps({"headRefOid": next(heads), "state": "OPEN"}))
        sh = FakeShell(r)
        watcher(root, sh).run_once()
        self.assertEqual(self.merges(sh), [])
        led = L.load(root)
        self.assertIn("merge.head_moved", [e["kind"] for e in led["events"]])
        self.assertEqual(led["trains"][0]["state"], "green")

    def test_merge_pins_the_head_commit(self):
        root = make_root()
        seed(root, [{"branch": "release/29", "pr": 10, "state": "ci"}])
        sh = FakeShell(routes_for_green())
        watcher(root, sh).run_once()
        self.assertEqual(self.merges(sh), [["gh", "pr", "merge", "10", "--merge", "--match-head-commit", SHA]])

    def _two_trains(self, cfg):
        root = make_root(cfg)
        seed(root, [{"branch": "release/29", "pr": 10, "state": "ci"},
                    {"branch": "release/30", "state": "joined", "release_no": 30}])
        r = routes_for_green()
        r[("git", "push")] = (0, "")
        r[("gh", "pr", "list", "--head")] = (0, "[]")
        r[("gh", "pr", "create")] = (0, "https://github.com/o/r/pull/11\n")
        return root, FakeShell(r)

    def test_push_trains_false_pushes_nothing(self):
        root, sh = self._two_trains({"watcher": {"push_trains": False}})
        watcher(root, sh).run_once()
        self.assertEqual(len(self.merges(sh)), 1)
        self.assertFalse(any(c[0] == "git" and c[1] == "push" for c in sh.calls))
        self.assertEqual(L.load(root)["trains"][1]["state"], "joined")

    def test_open_prs_false_pushes_but_opens_no_pr(self):
        root, sh = self._two_trains({"watcher": {"open_prs": False}})
        watcher(root, sh).run_once()
        self.assertTrue(any(c[0] == "git" and c[1] == "push" for c in sh.calls))
        self.assertFalse(any(c[:3] == ["gh", "pr", "create"] for c in sh.calls))

    def test_cancel_replaced_runs_false_cancels_nothing(self):
        root = make_root({"runner_plan": {"cancel_replaced_runs": False}})
        seed(root, [{"branch": "release/29", "pr": 10, "state": "ci"}])
        r = routes_for_green()
        r[("gh", "run", "list", "--branch")] = (0, runs((7, "in_progress", None, OLD, "release/29")))
        sh = FakeShell(r)
        watcher(root, sh).run_once()
        self.assertFalse(any(c[:3] == ["gh", "run", "cancel"] for c in sh.calls))

    def test_hold_dependabot_false_leaves_other_runs_and_still_releases_held(self):
        root = make_root({"runner_plan": {"hold_dependabot_during_train": False}})
        seed(root, [{"branch": "release/29", "pr": 10, "state": "ci"}], held_runs=[{"id": 50, "branch": "dependabot/x"}])
        r = routes_for_green()
        r[("gh", "run", "list", "--commit")] = (0, runs((1, "in_progress", None, SHA, "release/29")))
        r[("gh", "run", "list", "--status")] = (0, runs((60, "in_progress", None, "c" * 40, "dependabot/y")))
        r[("gh", "run", "cancel")] = (0, "")
        r[("gh", "run", "rerun")] = (0, "")
        sh = FakeShell(r)
        watcher(root, sh).run_once()
        self.assertFalse(any(c[:3] == ["gh", "run", "cancel"] for c in sh.calls))
        self.assertEqual([c for c in sh.calls if c[:3] == ["gh", "run", "rerun"]], [["gh", "run", "rerun", "50"]])

    def test_defaults_without_config_keep_0_1_0_behaviour(self):
        root = make_root()
        seed(root, [{"branch": "release/29", "pr": 10, "state": "ci"}])
        r = routes_for_green()
        r[("gh", "run", "list", "--branch")] = (0, runs((7, "in_progress", None, OLD, "release/29")))
        r[("gh", "run", "cancel")] = (0, "")
        sh = FakeShell(r)
        watcher(root, sh).run_once()
        self.assertTrue(any(c[:3] == ["gh", "run", "cancel"] for c in sh.calls))
        self.assertEqual(len(self.merges(sh)), 1)


class RunnerGuardTests(unittest.TestCase):
    def script(self, root):
        p = Path(root) / "scripts" / "delivery"
        p.mkdir(parents=True)
        (p / "runner_plan.py").write_text("# stub")
        return str(p / "runner_plan.py")

    def test_watcher_launches_runner_guard_once_and_relaunches_after_exit(self):
        root = cfg_root()
        script = self.script(root)
        sh = SpawnShell({("gh", "api"): (1, "")})
        w = watcher(root, sh, repo="o/r")
        w.run_once()
        w.run_once()
        self.assertEqual(len(sh.spawned), 1)
        self.assertEqual(sh.spawned[0][1:], [script, "runners", "--root", str(root), "--repo", "o/r"])
        sh.exit = 5
        w.run_once()
        self.assertEqual(len(sh.spawned), 2)
        kinds = [e["kind"] for e in L.load(root)["events"]]
        self.assertIn("runner.guard_started", kinds)
        self.assertIn("runner.guard_exit", kinds)

    def test_not_launched_without_runners_or_when_switched_off(self):
        for cfg in ({}, {"runners": [{"name": "r1"}], "watcher": {"manage_runners": False}}):
            root = make_root(cfg)
            self.script(root)
            sh = SpawnShell({("gh", "api"): (1, "")})
            watcher(root, sh).run_once()
            self.assertEqual(sh.spawned, [])

    def test_missing_script_is_reported_once(self):
        root = cfg_root()
        lines = []
        sh = SpawnShell({("gh", "api"): (1, "")})
        w = W_watcher(root, sh, lines)
        w.run_once()
        w.run_once()
        self.assertEqual(sh.spawned, [])
        self.assertEqual(len([l for l in lines if "runner_plan.py was not found" in l]), 1)

    def test_dry_run_only_prints(self):
        root = cfg_root()
        self.script(root)
        sh = SpawnShell({("gh", "api"): (1, "")})
        lines = []
        import delivery_watch as W
        W.Watcher(root, sh=sh, dry_run=True, now=lambda: NOW, out=lines.append).run_once()
        self.assertEqual(sh.spawned, [])
        self.assertTrue(any(l.startswith("dry-run: ") and "runners" in l for l in lines))


def W_watcher(root, sh, lines):
    import delivery_watch as W
    return W.Watcher(root, sh=sh, now=lambda: NOW, out=lines.append)


if __name__ == "__main__":
    unittest.main()
