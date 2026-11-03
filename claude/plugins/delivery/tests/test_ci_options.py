"""DL15: CI options per OS: config, delivery_ci.py, the installer, the doctor check and the watcher's reading of statuses."""
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest import mock

from _helpers import L, make_root
import delivery_ci as CI
import delivery_ci_install as INS
import delivery_config as C
import delivery_doctor as D
import delivery_watch as W
from test_watch import FakeShell, NOW, SHA, routes_for_green, seed, watcher
from test_watch import make_root as watch_root

TABLE = {"schema": 1, "shards": [
    {"id": "unit-linux", "os": "linux", "commands": ["echo ok"], "context": "unit (linux)"},
    {"id": "unit-win", "os": "windows", "commands": ["echo ok"]},
]}


def write_table(root, table=TABLE):
    p = Path(root) / "scripts" / "delivery"
    p.mkdir(parents=True, exist_ok=True)
    (p / "ci-shards.json").write_text(json.dumps(table))


def cli(main, *argv):
    out, err = StringIO(), StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = main(list(argv))
    return code, out.getvalue(), err.getvalue()


class ConfigTests(unittest.TestCase):
    def test_no_default_option(self):
        self.assertEqual(C.ci_options({}), {})
        self.assertEqual(C.ci_options({"ci": {"options": {"linux": "nope", "plan9": "cloud"}}}), {})

    def test_options_are_read(self):
        cfg = {"ci": {"options": {"linux": "cloud", "windows": "self-hosted", "macos": "github-hosted"}}}
        self.assertEqual(C.ci_options(cfg), cfg["ci"]["options"])

    def test_bad_option_is_a_schema_error_and_old_config_stays_valid(self):
        root = make_root({"ci": {"options": {"linux": "docker"}}})
        errors, _w, _s = C.validate_file(C.config_file(root))
        self.assertTrue(any("linux" in e for e in errors), errors)
        ok = make_root({"runners": [{"name": "r", "os": "windows"}], "local_runners": ["r"]})
        self.assertEqual(C.validate_file(C.config_file(ok))[0], [])
        good = make_root({"ci": {"options": {"linux": "cloud"}, "cloud": {"repo": "o/r", "status_token_env": "TOK", "branches": ["release/*"]}}})
        self.assertEqual(C.validate_file(C.config_file(good))[0], [])

    def test_shard_table_loading(self):
        root = make_root({})
        self.assertIn("no shard table", C.load_shards(str(root), {})[1])
        write_table(root)
        shards, err = C.load_shards(str(root), {})
        self.assertIsNone(err)
        self.assertEqual([s["context"] for s in shards], ["unit (linux)", "unit-win"])
        write_table(root, {"shards": [{"id": "a", "os": "beos", "commands": ["x"]}]})
        self.assertIn("os must be", C.load_shards(str(root), {})[1])
        write_table(root, {"shards": [{"id": "a", "os": "linux", "commands": ["x"]}, {"id": "a", "os": "linux", "commands": ["x"]}]})
        self.assertIn("twice", C.load_shards(str(root), {})[1])

    def test_cloud_contexts_only_for_cloud_oses(self):
        root = make_root({})
        write_table(root)
        cfg = {"ci": {"options": {"linux": "cloud", "windows": "github-hosted"}}}
        self.assertEqual(C.cloud_contexts(str(root), cfg), ["unit (linux)"])


class CommandTests(unittest.TestCase):
    def test_set_show_unset(self):
        root = make_root({"tz": "UTC"})
        r = str(root)
        self.assertEqual(cli(CI.main, "show", "--root", r)[1].splitlines()[0], "linux    not chosen")
        self.assertEqual(cli(CI.main, "set", "--os", "linux", "--option", "3", "--root", r)[0], 0)
        self.assertEqual(cli(CI.main, "set", "--os", "windows", "--option", "self-hosted", "--root", r)[0], 0)
        cfg = json.loads(C.config_file(root).read_text() if hasattr(C.config_file(root), "read_text") else open(C.config_file(root)).read())
        self.assertEqual(cfg["ci"]["options"], {"linux": "cloud", "windows": "self-hosted"})
        self.assertEqual(cfg["tz"], "UTC")           # other keys stay
        code, out, _ = cli(CI.main, "show", "--root", r, "--json")
        self.assertEqual({x["os"]: x["letter"] for x in json.loads(out)}, {"linux": "c", "windows": "a", "macos": None})
        self.assertEqual({x["os"]: x["number"] for x in json.loads(out)}, {"linux": 3, "windows": 1, "macos": None})
        self.assertIn("Option 3 (cloud)", cli(CI.main, "show", "--root", r)[1])
        self.assertEqual(cli(CI.main, "unset", "--os", "linux", "--root", r)[0], 0)
        self.assertNotIn("linux", C.ci_options(json.load(open(C.config_file(root)))))

    def test_refuses_bad_values_and_changes_nothing(self):
        root = make_root({})
        before = open(C.config_file(root)).read()
        self.assertEqual(cli(CI.main, "set", "--os", "linux", "--option", "d", "--root", str(root))[0], 1)
        code, _, err = cli(CI.main, "set", "--os", "linux", "--option", "4", "--root", str(root))
        self.assertEqual(code, 1)
        self.assertIn("Option 4", err)
        self.assertEqual(cli(CI.main, "set", "--os", "amiga", "--option", "a", "--root", str(root))[0], 1)
        self.assertEqual(open(C.config_file(root)).read(), before)

    def test_all_sets_every_os_and_a_missing_delivery_folder_is_2(self):
        root = make_root({})
        self.assertEqual(cli(CI.main, "set", "--os", "all", "--option", "b", "--root", str(root))[0], 0)
        self.assertEqual(set(C.ci_options(json.load(open(C.config_file(root)))).values()), {"github-hosted"})
        self.assertEqual(cli(CI.main, "show", "--root", tempfile.mkdtemp())[0], 2)


class InstallTests(unittest.TestCase):
    def test_install_writes_and_keeps(self):
        root = tempfile.mkdtemp()
        code, out, _ = cli(INS.main, "install", "--track", "ts", "--root", root)
        self.assertEqual(code, 0, out)
        for rel in ("scripts/delivery/branch_gate.py", "scripts/delivery/cloud_shard.py", "scripts/delivery/cloud_status.py",
                    "scripts/delivery/gate.json", ".github/workflows/ci.yml", ".github/workflows/train-cleanup.yml"):
            self.assertTrue(os.path.isfile(os.path.join(root, rel)), rel)
        self.assertFalse(os.path.exists(os.path.join(root, "scripts/delivery/CONTRACT.md")))
        mine = os.path.join(root, ".github/workflows/ci.yml")
        open(mine, "w").write("mine\n")
        code, out, _ = cli(INS.main, "install", "--track", "ts", "--root", root)
        self.assertIn("kept", out)
        self.assertEqual(open(mine).read(), "mine\n")

    def test_update_overwrites_scripts_and_keeps_project_files(self):
        root = tempfile.mkdtemp()
        cli(INS.main, "install", "--track", "go", "--root", root)
        script = os.path.join(root, "scripts/delivery/join.py")
        gate = os.path.join(root, "scripts/delivery/gate.json")
        open(script, "w").write("old\n")
        open(gate, "w").write("{}\n")
        code, out, _ = cli(INS.main, "update", "--track", "go", "--root", root)
        self.assertEqual(code, 0)
        self.assertIn("overwritten scripts/delivery/join.py", out)
        self.assertIn("differs     scripts/delivery/gate.json", out)
        self.assertNotEqual(open(script).read(), "old\n")
        self.assertEqual(open(gate).read(), "{}\n")

    def test_dry_run_writes_nothing_and_bad_track_is_1(self):
        root = tempfile.mkdtemp()
        self.assertEqual(cli(INS.main, "install", "--track", "rust", "--root", root, "--dry-run")[0], 0)
        self.assertEqual(os.listdir(root), [])
        self.assertEqual(cli(INS.main, "install", "--track", "cobol", "--root", root)[0], 1)

    def test_every_track_has_a_template_folder_and_the_ci_files(self):
        for track in INS.TRACKS:
            rels = {p[0] for p in INS.plan(track, tempfile.mkdtemp(), "install")}
            self.assertIn(".github/workflows/ci.yml", rels, track)
            self.assertIn("scripts/delivery/gate.json", rels, track)
            self.assertIn("scripts/delivery/ci_watch.py", rels, track)


class OptionNameTests(unittest.TestCase):
    def test_numbers_letters_and_names_all_work(self):
        for raw, want in (("1", "self-hosted"), ("a", "self-hosted"), ("Option 2", "github-hosted"), ("cloud", "cloud")):
            self.assertEqual(CI.normalise_option(raw), want)
        self.assertIsNone(CI.normalise_option("4"))

    def test_fallback_block_is_in_the_schema_and_empty(self):
        schema = json.load(open(os.path.join(os.path.dirname(C.__file__), "..", "references", "config-schema.json")))
        fb = schema["properties"]["ci"]["properties"]["fallback"]
        self.assertEqual((fb["type"], fb["properties"]), ("object", {}))
        root = make_root({"ci": {"fallback": {}}})
        errors, warnings, _s = C.validate_file(C.config_file(root))
        self.assertEqual((errors, warnings), ([], []))

    def test_runner_texts_never_say_this_pc(self):
        base = os.path.join(os.path.dirname(C.__file__), "..")
        for rel in ("README.md", "scripts/delivery_ci.py", "scripts/delivery_doctor.py", "scripts/delivery_config.py",
                    "references/config-schema.json", "templates/shared/scripts/delivery/CONTRACT.md"):
            text = open(os.path.join(base, rel), encoding="utf-8").read().lower()
            self.assertNotIn("this pc", text, rel)
            self.assertNotIn("owner's runners", text, rel)
        self.assertIn("any machines you run", C.CI_OPTION_TEXT["self-hosted"])

    def test_add_runner_prints_steps_for_each_os(self):
        for os_name, needle in (("linux", "./config.sh"), ("windows", "config.cmd"), ("macos", "./svc.sh")):
            code, out, _ = cli(CI.main, "add-runner", "--os", os_name, "--labels", "self-hosted,%s,big" % os_name)
            self.assertEqual(code, 0)
            self.assertIn(needle, out)
            self.assertIn("--labels self-hosted,%s,big" % os_name, out)
            self.assertIn("waits more than 10 min", out)
            self.assertIn("another machine", out)
        self.assertEqual(cli(CI.main, "add-runner", "--os", "amiga")[0], 1)


class DoctorTests(unittest.TestCase):
    def ci(self, root, cfg=None):
        with mock.patch.dict(os.environ, {"CLOUD_STATUS_TOKEN": ""}):
            return D.check_ci(str(root), cfg if cfg is not None else json.load(open(C.config_file(root))))

    def test_nothing_chosen_and_no_table_is_ok(self):
        ok, detail = self.ci(make_root({}))
        self.assertTrue(ok)
        self.assertIn("no CI option chosen", detail)

    def test_shard_for_an_os_that_was_not_chosen_fails(self):
        root = make_root({"ci": {"options": {"linux": "github-hosted"}}})
        write_table(root)
        (Path(root) / ".github" / "workflows").mkdir(parents=True)
        (Path(root) / ".github" / "workflows" / "ci.yml").write_text("on: push\n")
        ok, detail = self.ci(root)
        self.assertFalse(ok)
        self.assertIn("windows", detail)
        self.assertIn("delivery_ci.py set", detail)

    def test_option_a_needs_a_runner_for_the_os(self):
        cfg = {"ci": {"options": {"linux": "self-hosted", "windows": "self-hosted"}},
               "runners": [{"name": "pc", "os": "Windows", "labels": ["self-hosted", "windows"]}]}
        root = make_root(cfg)
        write_table(root)
        ok, detail = self.ci(root)
        self.assertFalse(ok)
        self.assertIn("no linux runner", detail)
        self.assertNotIn("no windows runner", detail)

    def test_option_1_names_the_steps_for_a_second_machine(self):
        cfg = {"ci": {"options": {"linux": "self-hosted", "windows": "self-hosted"}},
               "runners": [{"name": "pc", "os": "Windows", "labels": ["self-hosted", "windows"]},
                           {"name": "box", "os": "Linux", "labels": ["self-hosted", "linux", "big"]}]}
        root = make_root(cfg)
        write_table(root)
        ok, detail = self.ci(root)
        self.assertTrue(ok, detail)
        self.assertIn("another machine", detail)
        self.assertIn("waits more than 10 min", detail)
        self.assertIn("linux: 1 runner(s) (box)", detail)
        self.assertIn("./config.sh", detail)                           # the Linux steps
        self.assertIn("--labels self-hosted,linux,big", detail)        # the machine's own labels
        self.assertIn("config.cmd", detail)                            # the Windows steps
        self.assertIn("Option 1", D.check_ci(str(root), cfg)[1])

    def test_missing_runner_failure_names_the_by_hand_steps(self):
        root = make_root({"ci": {"options": {"linux": "self-hosted"}}})
        ok, detail = self.ci(root)
        self.assertFalse(ok)
        self.assertIn("Option 1", detail)
        self.assertIn("by hand", detail)
        self.assertIn("./config.sh", detail)

    def test_option_b_needs_a_workflow_file(self):
        root = make_root({"ci": {"options": {"linux": "github-hosted", "windows": "github-hosted"}}})
        write_table(root)
        self.assertIn("no workflow file", self.ci(root)[1])
        wf = Path(root) / ".github" / "workflows"
        wf.mkdir(parents=True)
        (wf / "ci.yml").write_text("on: push\n")
        self.assertTrue(self.ci(root)[0])

    def test_option_c_needs_repo_token_name_branches_and_unique_contexts(self):
        root = make_root({"ci": {"options": {"linux": "cloud", "windows": "cloud"}}})
        write_table(root)
        ok, detail = self.ci(root)
        self.assertFalse(ok)
        for part in ("ci.cloud.repo", "ci.cloud.status_token_env", "ci.cloud.branches"):
            self.assertIn(part, detail)
        full = {"ci": {"options": {"linux": "cloud", "windows": "cloud"},
                       "cloud": {"repo": "o/r", "status_token_env": "CLOUD_STATUS_TOKEN", "branches": ["release/*"]}}}
        ok, detail = self.ci(make_root(full), full)
        self.assertFalse(ok)                                   # no shard table in that root
        root2 = make_root(full)
        write_table(root2)
        ok, detail = self.ci(root2, full)
        self.assertTrue(ok, detail)
        self.assertIn("CLOUD_STATUS_TOKEN is not set here", detail)
        dup = dict(TABLE, shards=[dict(TABLE["shards"][0]), dict(TABLE["shards"][1], context="unit (linux)")])
        write_table(root2, dup)
        self.assertIn("share the status context", self.ci(root2, full)[1])

    def test_ci_check_is_part_of_the_run(self):
        root = make_root({})
        self.assertIn("ci", {r["check"] for r in D.run_checks(str(root))})


class WatcherStatusTests(unittest.TestCase):
    def setup(self, options, statuses):
        cfg = {"ci": {"options": options}}
        root = watch_root(cfg)
        write_table(root)
        seed(root, [{"branch": "release/29", "pr": 10, "state": "ci"}])
        routes = routes_for_green()
        routes[("gh", "run", "list", "--commit")] = (0, "[]")
        routes[("gh", "api")] = (0, json.dumps({"statuses": statuses}))
        return root, FakeShell(routes)

    def train(self, root):
        return L.load(root)["trains"][0]

    def test_cloud_only_success_merges_without_any_workflow(self):
        root, sh = self.setup({"linux": "cloud", "windows": "cloud"},
                              [{"id": 1, "context": "unit (linux)", "state": "success"},
                               {"id": 2, "context": "unit-win", "state": "success"}])
        watcher(root, sh).run_once()
        self.assertIn(self.train(root)["state"], ("green", "merged"))
        self.assertFalse([c for c in sh.calls if c[:5] == ["gh", "run", "list", "--commit", SHA]])
        self.assertTrue([c for c in sh.calls if c[:3] == ["gh", "pr", "merge"]])

    def test_pending_or_missing_status_is_not_green_and_failure_is_red(self):
        root, sh = self.setup({"linux": "cloud", "windows": "cloud"}, [{"id": 1, "context": "unit (linux)", "state": "success"}])
        watcher(root, sh).run_once()
        self.assertNotEqual(self.train(root)["state"], "green")
        self.assertFalse([c for c in sh.calls if c[:3] == ["gh", "pr", "merge"]])
        root, sh = self.setup({"linux": "cloud", "windows": "cloud"},
                              [{"id": 1, "context": "unit (linux)", "state": "success"},
                               {"id": 2, "context": "unit-win", "state": "failure"}])
        watcher(root, sh).run_once()
        self.assertEqual(self.train(root)["state"], "red")

    def test_mixed_options_need_the_workflow_and_the_statuses(self):
        root, sh = self.setup({"linux": "github-hosted", "windows": "cloud"}, [])
        sh.routes[("gh", "run", "list", "--commit")] = (0, json.dumps(
            [{"databaseId": 1, "status": "completed", "conclusion": "success", "headSha": SHA, "headBranch": "release/29",
              "event": "push", "workflowName": "ci"}]))
        watcher(root, sh).run_once()
        self.assertNotEqual(self.train(root)["state"], "green")          # the windows status is missing
        sh.routes[("gh", "api")] = (0, json.dumps({"statuses": [{"id": 5, "context": "unit-win", "state": "success"}]}))
        watcher(root, sh).run_once()
        self.assertIn(self.train(root)["state"], ("green", "merged"))

    def test_a_status_from_another_context_does_not_count(self):
        root, sh = self.setup({"windows": "cloud"}, [{"id": 1, "context": "other", "state": "success"}])
        watcher(root, sh).run_once()
        self.assertNotEqual(self.train(root)["state"], "green")

    def test_without_ci_options_nothing_changes(self):
        root = watch_root({})
        seed(root, [{"branch": "release/29", "pr": 10, "state": "ci"}])
        sh = FakeShell(routes_for_green())
        watcher(root, sh).run_once()
        self.assertIn(self.train(root)["state"], ("green", "merged"))


if __name__ == "__main__":
    unittest.main()
