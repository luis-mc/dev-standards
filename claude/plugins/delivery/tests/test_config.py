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

# a real project's config, trimmed to the keys under test
SAMPLE_PROJECT = {
    "caps": {"cloud": 8, "local": 3, "total": 5}, "work_root": "C:/Work", "tz": "Europe/Lisbon",
    "base": "master", "train_label_re": r"\b(?:T-\d{4}-\d{2}-\d{2}-\d+|release/\d+[a-z]?)\b",
    "release_branch_re": "^(release|claude)/", "train_branch_re": "^(release|claude)/",
    "brief_markers": ["BRIEF.md"], "checks_off": [], "no_attribution": True, "watch_interval": 600,
    "enforcement": {"mode": "block", "block_ceiling": 3, "log_every_block": True},
    "watcher": {"push_trains": True, "open_prs": True, "merge_on_green": True, "merge_flag": "--merge",
                "never_auto_merge": True},
    "local_runners": ["build-pc"],
    "runners": [{"name": "build-pc", "os": "Windows", "repair": ["powershell -Command x"]},
                {"name": "build-pc-linux", "os": "Linux", "repair": [["docker", "restart", "c"]]},
                {"name": "NUC8-linux", "os": "Linux", "repair": []}],
    "runner_plan": {"cancel_replaced_runs": True,
                    "hold_dependabot_during_train": True},
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
    def test_sample_project_config_and_template_are_valid(self):
        self.assertEqual(C.validate_config(SAMPLE_PROJECT), ([], []))
        tpl = Path(__file__).resolve().parents[1] / "templates/shared/.delivery/config.json"
        self.assertEqual(C.validate_config(json.loads(tpl.read_text(encoding="utf-8"))), ([], []))

    def test_0_1_0_config_and_empty_config_stay_valid(self):
        old = {"caps": {"cloud": 8, "local": 3}, "tz": "UTC", "runners": [], "watcher_interval_s": 600,
               "runner_plan": {}, "_doc": "x"}
        self.assertEqual(C.validate_config(old), ([], []))
        self.assertEqual(C.validate_config({}), ([], []))

    def test_task_spelling_merge_method_and_heavy_jobs_yield(self):
        cfg = {"watcher": {"merge_method": "merge"}, "runner_plan": {"cancel_replaced_runs": False}}
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
        r[("gh", "pr", "view", "10")] = lambda argv: (
            0, json.dumps({"isDraft": False} if "createdAt,isDraft" in argv else {"headRefOid": next(heads), "state": "OPEN"}))
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
        # DL381: a cancel needs a run for the newer head, a human head commit and no failed job
        r[("gh", "run", "list", "--branch")] = (0, runs((7, "in_progress", None, OLD, "release/29"),
                                                        (8, "in_progress", None, SHA, "release/29")))
        r[("gh", "api")] = (0, json.dumps({"author": {"login": "alice"}, "committer": {"login": "alice"}}))
        r[("gh", "run", "view")] = (0, json.dumps({"jobs": [{"conclusion": "success"}]}))
        r[("gh", "run", "cancel")] = (0, "")
        sh = FakeShell(r)
        watcher(root, sh).run_once()
        self.assertTrue(any(c[:3] == ["gh", "run", "cancel"] for c in sh.calls))
        self.assertEqual(len(self.merges(sh)), 1)
