"""DL341 (D298): the pool covers every runner on the machine across OSes. Mocked gh and probe; runs on Linux."""
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from _helpers import make_root  # noqa: F401  (puts the scripts folder on sys.path)
import delivery_runner_pool as P
import delivery_ci_setup as S
import pool_status as PS
from test_dl310_windows_runner import REPO, Probe as WinProbe, found, plan, runner

SRC = Path(__file__).resolve().parents[1] / "templates" / "runner-pool"
spec = importlib.util.spec_from_file_location("pool_supervisor_dl341", SRC / "pool_supervisor.py")
SUP = importlib.util.module_from_spec(spec)
spec.loader.exec_module(SUP)
spec = importlib.util.spec_from_file_location("pool_agents_dl341", SRC / "pool_agents.py")
AG = importlib.util.module_from_spec(spec)
spec.loader.exec_module(AG)

LINUX = {"slug": "app", "user": "r-app", "repo": "owner/app", "private": True,
         "labels": ["self-hosted", "linux", "x64", "pool-main", "repo-app"]}
WIN = P.windows_registry_entry("main", "owner/app", "host1-app", "actions.runner.owner-app.host1-app", "ci-app",
                               "C:/actions-runners/app")


class FileProbe(WinProbe):
    """A probe over a real temp pool folder, with canned gh answers."""

    def __init__(self, root, gh_runners=None, runs=None, **kw):
        super().__init__(**kw)
        self.root, self.gh_runners, self.runs = root, gh_runners or {}, runs or {}

    def read_text(self, path):
        try:
            return Path(path).read_text(encoding="utf-8")
        except OSError:
            return None

    def listdir(self, path):
        return sorted(os.listdir(path)) if os.path.isdir(path) else []

    def isfile(self, path):
        return os.path.isfile(path)

    def gh_json(self, args):
        url = args[1]
        if "/actions/runners" in url:
            repo = url.split("/")[1] + "/" + url.split("/")[2]
            r = self.gh_runners.get(repo)
            return (None, "no") if r is None else ({"runners": [
                {"id": x["id"], "name": x["name"], "os": x["os"], "status": x["status"], "busy": x["busy"],
                 "labels": [{"name": l} for l in x["labels"]]} for x in r]}, None)
        if "/jobs" in url:
            return {"jobs": self.runs.get(("jobs", url.split("/")[5]), [])}, None
        state = url.split("status=")[1].split("&")[0]
        return {"workflow_runs": self.runs.get(state, [])}, None


class Pool(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = self.tmp.name
        self.pdir = os.path.join(self.root, "pools", "main")
        os.makedirs(self.pdir)
        Path(self.pdir, "compose.yaml").write_text("services: {}\n")
        self.patch = mock.patch.object(P, "pool_dir", lambda pool: os.path.join(self.root, "pools", pool))
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def write(self, entries):
        Path(self.pdir, "agents.json").write_text(json.dumps({"agents": entries}))

    def read(self):
        return json.loads(Path(self.pdir, "agents.json").read_text())["agents"]


class Registry(Pool):
    def test_round_trip_with_mixed_os(self):
        self.write([LINUX])
        probe = FileProbe(self.root)
        entries, data = P.registry_read(probe, "main")
        P.registry_write("main", P.registry_upsert(data, WIN))
        got = self.read()
        self.assertEqual([P.entry_os(a) for a in got], ["linux", "windows"])
        self.assertEqual([P.entry_kind(a) for a in got], ["container", "service"])
        self.assertEqual(got[0], LINUX)  # the Linux entry is untouched, and reads as linux/container without the keys
        P.registry_write("main", P.registry_upsert(P.registry_read(probe, "main")[1], dict(WIN, account="ci-other")))
        self.assertEqual(len(self.read()), 2)
        self.assertEqual(self.read()[1]["account"], "ci-other")

    def test_entry_has_the_required_keys(self):
        for k in ("os", "kind", "service", "account", "folder", "repo", "route"):
            self.assertIn(k, WIN)
        self.assertEqual((WIN["os"], WIN["kind"], WIN["route"]), ("windows", "service", "app"))

    def test_container_loader_ignores_service_entries(self):
        f = Path(self.root, "a.json")
        f.write_text(json.dumps({"agents": [LINUX, WIN, dict(WIN, user="r-x", slug="x")]}))
        self.assertEqual([a["slug"] for a in SUP.load_agents(str(f))], ["app"])

    def test_add_agent_and_role_checks_skip_service_entries(self):
        agents = [LINUX, WIN]
        self.assertEqual(AG.check_db_roles("other", ["r1"], agents), ["r1"])
        self.assertEqual(AG.next_slug("app", agents), "app-2")
        f = Path(self.root, "b.json")
        f.write_text(json.dumps({"agents": [WIN]}))
        AG.create_db = lambda *a, **k: None
        AG.kvm_usable = lambda *a, **k: False
        run = lambda *a, **k: mock.Mock(returncode=0, stdout="", stderr="")  # noqa: E731
        msg = AG.add_agent("app", "owner/app", "tok", "main", True, str(f), os.path.join(self.root, "agents"), run=run)
        self.assertIn("added", msg)  # no join to the Windows entry's route
        self.assertEqual(len(json.loads(f.read_text())["agents"]), 2)


class WindowsSetup(Pool):
    def test_register_labels_and_registry_step(self):
        pl = plan(found(), WinProbe(admin=True))
        svc = next(s for s in pl["steps"] if s["id"] == "winsvc:" + REPO)
        self.assertEqual(svc["labels"], ["self-hosted", "Windows", "X64", "pool-main", "repo-example-app"])
        text = P.windows_runner_script(next(s for s in plan(found(), WinProbe(admin=False))["steps"] if s["id"] == "winsvc:" + REPO))
        self.assertIn("--labels 'self-hosted,Windows,X64,pool-main,repo-example-app'", text)
        self.assertIn("registry:" + REPO, [s["id"] for s in pl["steps"]])

    def test_registry_step_writes_only_its_entry(self):
        self.write([LINUX])
        pl = plan(found(), WinProbe())
        step = next(s for s in pl["steps"] if s["id"] == "registry:" + REPO)
        ok, _ = P.Executor(FileProbe(self.root)).run(step)
        self.assertTrue(ok)
        got = self.read()
        self.assertEqual(got[0], LINUX)
        self.assertEqual((got[1]["name"], got[1]["os"], got[1]["kind"], got[1]["account"]), ("host1-example-app", "windows", "service", "ci-example-app"))
        self.assertIn("actions.runner.owner-example-app.host1-example-app", got[1]["service"])

    def test_route_follows_an_existing_linux_entry(self):
        self.write([dict(LINUX, repo=REPO, route="shared")])
        pl = plan(found(), FileProbe(self.root))
        svc = next(s for s in pl["steps"] if s["id"] == "winsvc:" + REPO)
        self.assertIn("repo-shared", svc["labels"])

    def test_existing_runner_without_pool_labels_gets_them(self):
        r = runner("host1-example-app", rid=7)
        svcs = [{"name": "actions.runner.x", "kind": "windows-service", "folder": "C:/actions-runners/example-app", "account": ".\\ci-example-app"}]
        folders = [{"path": "C:/actions-runners/example-app", "agent_id": 7, "name": "host1-example-app", "repo": REPO}]
        pl = plan(found([r], svcs, folders), WinProbe())
        step = next(s for s in pl["steps"] if s["id"] == "win-labels:" + REPO)
        self.assertEqual(step["labels"], ["pool-main", "repo-example-app"])
        probe = WinProbe()
        ok, _ = P.Executor(probe).run(step)
        self.assertTrue(ok)
        argv = probe.calls[-1][0]
        self.assertEqual(argv[:4], ["gh", "api", "-X", "POST"])
        self.assertIn("repos/%s/actions/runners/7/labels" % REPO, argv)
        self.assertIn("labels[]=pool-main", argv)

    def test_runner_with_pool_labels_gets_no_label_step_and_labels_are_not_removed(self):
        r = runner("host1-example-app", rid=7, labels=("self-hosted", "Windows", "X64", "pool-main", "repo-example-app"))
        svcs = [{"name": "actions.runner.x", "kind": "windows-service", "folder": "C:/actions-runners/example-app", "account": ".\\ci-example-app"}]
        folders = [{"path": "C:/actions-runners/example-app", "agent_id": 7, "name": "host1-example-app", "repo": REPO}]
        ids = [s["id"] for s in plan(found([r], svcs, folders), WinProbe())["steps"]]
        self.assertNotIn("win-labels:" + REPO, ids)
        self.assertFalse([i for i in ids if i.startswith("label-remove")])

    def test_runs_on_suggestion(self):
        pl = plan(found(), WinProbe())
        var = next(s for s in pl["steps"] if s["id"] == "var:CI_RUNS_ON_WINDOWS:" + REPO)
        self.assertEqual(json.loads(var["value"]), ["self-hosted", "Windows", "X64", "pool-main", "repo-example-app"])
        self.assertEqual(P.windows_runs_on([]), ["self-hosted", "Windows", "X64"])  # the old value still builds


class Remove(Pool):
    def test_remove_drops_only_that_entry(self):
        other = dict(WIN, name="host1-other", repo="owner/other", folder="C:/actions-runners/other")
        self.write([LINUX, WIN, other])
        probe = FileProbe(self.root)
        ok, text = P.Executor(probe).run({"action": "windows-runner-remove", "pool": "main", "runner": "host1-app", "repo": "owner/app",
                                          "folder": "C:/actions-runners/app"})
        self.assertTrue(ok, text)
        self.assertEqual([a.get("name") or a.get("slug") for a in self.read()], ["app", "host1-other"])
        self.assertIn("remove-token", json.dumps(probe.calls))

    def test_failed_unregister_keeps_the_entry(self):
        self.write([WIN])
        probe = FileProbe(self.root)
        probe.sh = lambda argv, input=None, timeout=60: (1, "boom")
        ok, _ = P.Executor(probe).run({"action": "windows-runner-remove", "pool": "main", "runner": "host1-app", "repo": "owner/app",
                                       "folder": "C:/actions-runners/app"})
        self.assertFalse(ok)
        self.assertEqual(len(self.read()), 1)

    def test_registry_drop_leaves_linux_entry_of_same_name(self):
        self.write([dict(LINUX, slug="host1-app"), WIN])
        ok, _ = P.Executor(FileProbe(self.root)).run({"action": "registry-drop", "pool": "main", "runner": "host1-app"})
        self.assertTrue(ok)
        self.assertEqual([a.get("slug") for a in self.read()], ["host1-app"])

    def test_cli_needs_yes(self):
        self.write([WIN])
        probe = FileProbe(self.root)
        args = mock.Mock(runner="host1-app", pool="main", yes=False)
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(S.cmd_pool_remove(args, P, probe), 0)
        self.assertIn("Nothing changed", buf.getvalue())
        self.assertEqual(len(self.read()), 1)


GH = {"owner/app": [
    runner("main-app", rid=1, os_="Linux", labels=("self-hosted", "linux", "x64", "pool-main", "repo-app")),
    runner("host1-app", rid=2, busy=True, labels=("self-hosted", "Windows", "X64", "pool-main", "repo-app")),
    runner("stray", rid=3, os_="Linux", labels=("self-hosted", "linux", "pool-main"))]}
GH["owner/app"][0]["name"] = "main-app"


class Status(Pool):
    def setUp(self):
        super().setUp()
        self.write([LINUX, WIN])
        self.runs = {"in_progress": [{"id": 11, "name": "ci"}], "queued": [{"id": 12, "name": "ci"}],
                     "completed": [{"id": 10, "name": "ci"}],
                     ("jobs", "11"): [{"status": "in_progress", "name": "test-win", "runner_name": "host1-app"}],
                     ("jobs", "10"): [{"status": "completed", "name": "test", "runner_name": "main-app", "conclusion": "success",
                                       "completed_at": "2026-11-14T10:00:00Z"},
                                      {"status": "completed", "name": "hosted", "runner_name": "GitHub Actions 3", "conclusion": "success"}]}
        self.probe = FileProbe(self.root, GH, self.runs)

    def report(self):
        with mock.patch.object(PS, "machine_part", return_value={
                "limits": {"memory_pct": 85, "cpu_pct": 60}, "ci_slots": 2, "light_slots": 1, "heavy_slots": 1, "local_heavy": 2,
                "host_load": {"mem": 41.0, "cpu": 12.0, "age_s": 5},
                "slots": [{"slot": 1, "free": False, "repo": "owner/app", "job": "test-win", "run_id": 11, "age_s": 30, "stale": False},
                          {"slot": 2, "free": True}], "light": [{"slot": 1, "free": True}], "heavy": [], "queue": []}):
            return PS.collect(self.probe, root=self.root)

    def test_json_joins_registry_and_github(self):
        rep = self.report()
        by = {r["name"]: r for r in rep["runners"]}
        self.assertEqual((by["main-app"]["os"], by["main-app"]["kind"], by["main-app"]["state"]), ("linux", "container", "online"))
        self.assertEqual((by["host1-app"]["os"], by["host1-app"]["kind"], by["host1-app"]["state"]), ("windows", "service", "busy"))
        self.assertEqual(by["host1-app"]["job"], "test-win #11")
        self.assertFalse(by["stray"]["registry"])
        self.assertEqual([j["job"] for j in rep["jobs"]["running"]], ["test-win"])
        self.assertEqual(len(rep["jobs"]["queued"]), 1)
        self.assertEqual([j["job"] for j in rep["jobs"]["finished"]], ["test"])  # hosted runner jobs are not listed
        json.dumps(rep)

    def test_text_table(self):
        text = PS.render_text(self.report())
        for want in ("Machine", "CI slots: 1 of 2 in use", "main-app", "host1-app", "windows", "service", "busy", "test-win #11",
                     "NO", "queue: empty", "last finished on pool runners"):
            self.assertIn(want, text)

    def test_missing_registry_runner_and_unreadable_gh(self):
        self.probe.gh_runners = {"owner/app": []}
        rows = {r["name"]: r for r in self.report()["runners"]}
        self.assertEqual(rows["host1-app"]["state"], "missing")
        self.probe.gh_runners = {}
        rep = self.report()
        self.assertEqual({r["state"] for r in rep["runners"]}, {"unknown"})
        self.assertTrue(rep["notes"])


class Doctor(Pool):
    def findings(self, gh, entries):
        out = []
        P.registry_checks(lambda n, st, d: out.append((n, st, d)), FileProbe(self.root, gh), "main", entries)
        return {n: (st, d) for n, st, d in out}

    def test_all_clear(self):
        gh = {"owner/app": [GH["owner/app"][0], GH["owner/app"][1]]}
        got = self.findings(gh, [LINUX, WIN])
        self.assertEqual({st for st, _ in got.values()}, {"ok"})

    def test_untracked_github_runner(self):
        got = self.findings(GH, [LINUX, WIN])
        self.assertEqual(got["registry-untracked"][0], "warn")
        self.assertIn("stray", got["registry-untracked"][1])

    def test_registry_entry_without_github_runner(self):
        got = self.findings({"owner/app": [GH["owner/app"][0]]}, [LINUX, WIN])
        self.assertEqual(got["registry-missing"][0], "warn")
        self.assertIn("host1-app", got["registry-missing"][1])

    def test_windows_runner_without_pool_labels(self):
        bare = runner("host1-app", rid=2)
        got = self.findings({"owner/app": [GH["owner/app"][0], bare]}, [LINUX, WIN])
        self.assertEqual(got["windows-labels"][0], "warn")
        self.assertIn("host1-app", got["windows-labels"][1])

    def test_doctor_checks_run_on_a_pool_folder(self):
        self.write([LINUX, WIN])
        probe = FileProbe(self.root, {"owner/app": GH["owner/app"][:2]})
        out = P.doctor_checks(self.root, probe)
        ids = {c["id"]: c for c in out}
        self.assertEqual(ids["pool.main.users"]["status"], "ok")  # the service entry is not a user-less container agent
        self.assertIn("pool.main.registry-missing", ids)


if __name__ == "__main__":
    unittest.main()
