"""DL30: pool detect, plan, sizing, run, doctor checks, supervisor, add and remove agent, section 13 summary. No Docker."""
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from _helpers import make_root  # noqa: F401  (sets sys.path to the scripts folder)
import delivery_runner_pool as P
import delivery_ci_setup as S

POOL = Path(__file__).resolve().parent.parent / "templates" / "runner-pool"
sys.path.insert(0, str(POOL))
import pool_agents as A  # noqa: E402
import pool_supervisor as SUP  # noqa: E402


REPOS = [
    {"full_name": "owner/example-app", "private": True, "permissions": {"admin": True}},
    {"full_name": "owner/public-app", "private": False, "permissions": {"admin": True}},
    {"full_name": "owner/not-mine", "private": True, "permissions": {"admin": False}},
    {"full_name": "owner/locked", "private": True, "permissions": {"admin": True}},
]
RUNNERS = {
    "owner/example-app": {"runners": [
        {"id": 7, "name": "host1-old", "os": "Windows", "status": "online", "busy": False, "labels": [{"name": "self-hosted"}]},
        {"id": 8, "name": "main-app1", "os": "Linux", "status": "online", "busy": False,
         "labels": [{"name": "self-hosted"}, {"name": "pool-main"}]}]},
    "owner/public-app": {"runners": []},
}


class FakeProbe(P.Probe):
    platform = "linux"

    def __init__(self, files=None, tmp=None):
        self.files = files or {}
        self.calls = []
        self.runner_dirs = ["C:/Work/runners"]
        self.wslconfig = "C:/Users/u1/.wslconfig"
        self.slept = 0

    def sh(self, argv, input=None, timeout=60):
        self.calls.append((argv, input))
        if argv[:2] == ["docker", "ps"] and "label=" + P.LABEL in argv:
            return 0, "abc\tpool-main-pool-1\tUp 2 hours\n"
        if argv[:2] == ["docker", "ps"]:
            return 0, "abc\tpool-main-pool-1\t\"tini\"\ndef\told-runner\t\"./bin/Runner.Listener run\"\n"
        if argv[0] == "systemctl":
            return 0, "actions.runner.owner-example-app.host1.service loaded active running GitHub runner\n"
        return 0, ""

    def gh(self, args, input=None):
        self.calls.append((["gh"] + list(args), input))
        return 0, ""

    def gh_json(self, args):
        path = next((a for a in args if a.startswith(("user/repos", "repos/"))), "")
        if path.startswith("user/repos"):
            return [REPOS[:2], REPOS[2:]], None
        repo = path[len("repos/"):].split("/actions")[0]
        if repo == "owner/locked":
            return None, "gh refused (admin rights needed?)"
        return RUNNERS.get(repo, {"runners": []}), None

    def read_text(self, path):
        p = path.replace("\\", "/")
        return self.files[p] if p in self.files else (super().read_text(path) if not p.startswith("C:") else None)

    def listdir(self, path):
        pre = path.rstrip("/") + "/"
        mine = sorted({k[len(pre):].split("/")[0] for k in self.files if k.startswith(pre)})
        return mine or (super().listdir(path) if not path.startswith("C:") else [])

    def isfile(self, path):
        return path.replace("\\", "/") in self.files or (not path.startswith("C:") and os.path.isfile(path))

    def sleep(self, sec):
        self.slept += 1


FILES = {
    "C:/Work/runners/app1/.runner": '\ufeff{"agentId": 7, "agentName": "host1-old", "gitHubUrl": "https://github.com/owner/example-app"}',
    "C:/Work/runners/app1/.credentials": "SECRET",
    "C:/Users/u1/.wslconfig": "[wsl2]\nmemory=12GB\nprocessors=6\n",
}


class DetectTests(unittest.TestCase):
    def setUp(self):
        self.probe = FakeProbe(dict(FILES))
        self.found = P.detect(self.probe)

    def test_github_only_admin_repos_and_api_refusal_named(self):
        names = [r["repo"] for r in self.found["github"]["repos"]]
        self.assertEqual(names, ["owner/example-app", "owner/public-app", "owner/locked"])
        locked = self.found["github"]["repos"][2]
        self.assertIn("refused", locked["error"])
        self.assertEqual(len(self.found["github"]["repos"][0]["runners"]), 2)

    def test_folders_services_containers_wsl(self):
        self.assertEqual(self.found["folders"][0]["repo"], "owner/example-app")
        self.assertEqual(self.found["folders"][0]["agent_id"], 7)
        self.assertEqual(self.found["services"][0]["kind"], "systemd")
        self.assertEqual({c["name"]: c["pool"] for c in self.found["containers"]}, {"pool-main-pool-1": True, "old-runner": False})
        self.assertEqual((self.found["wsl"]["memory"], self.found["wsl"]["processors"]), (12.0, 6))

    def test_credentials_never_read(self):
        read = []
        orig = self.probe.read_text
        self.probe.read_text = lambda p: (read.append(p), orig(p))[1]
        P.detect(self.probe)
        self.assertFalse([p for p in read if "credentials" in p])

    def test_json_mode_is_valid_json(self):
        self.assertIn("github", json.loads(P.detect(self.probe, json=True)))


class SizingTests(unittest.TestCase):
    def test_cap_and_wsl_values(self):
        r = P.sizing(32, 10, 16, docker_gib=24)
        self.assertEqual((r["mem_gib"], r["cpus"]), (15.0, 9.5))
        self.assertTrue(r["ok"])

    def test_docker_ceiling_wins_when_smaller(self):
        self.assertEqual(P.sizing(64, 4, 8, docker_gib=8)["mem_gib"], 6.0)

    def test_refuses_below_largest_shard(self):
        r = P.sizing(16, 8, 8, largest_shard_gib=8)
        self.assertFalse(r["ok"])
        self.assertIn("largest Linux shard", r["message"])

    def test_no_room_left(self):
        self.assertFalse(P.sizing(8, 7, 4)["ok"])


class PlanTests(unittest.TestCase):
    def setUp(self):
        self.found = P.detect(FakeProbe(dict(FILES)))

    def test_public_repo_refused_and_gets_no_step(self):
        pl = P.plan(self.found, ["owner/example-app", "owner/public-app"], pool="main")
        self.assertEqual([r["repo"] for r in pl["refused"]], ["owner/public-app"])
        self.assertIn("public repository", pl["refused"][0]["reason"])
        self.assertFalse([s for s in pl["steps"] if s.get("repo") == "owner/public-app"])

    def test_old_runners_removed_pool_runner_kept_and_agent_already(self):
        pl = P.plan(self.found, ["owner/example-app"], pool="main")
        ids = [s["id"] for s in pl["steps"]]
        self.assertIn("remove:owner/example-app:host1-old", ids)
        self.assertNotIn("remove:owner/example-app:main-app1", ids)
        agent = next(s for s in pl["steps"] if s["id"] == "agent:owner/example-app")
        self.assertEqual(agent["state"], "already")

    def test_deletions_name_what_goes_and_come_after_removal(self):
        pl = P.plan(self.found, ["owner/example-app"])
        dels = [s for s in pl["steps"] if s["delete"]]
        self.assertTrue(dels and all(s["names"] for s in dels))
        ids = [s["id"] for s in pl["steps"]]
        self.assertLess(ids.index("idle"), ids.index("remove:owner/example-app:host1-old"))
        self.assertLess(ids.index("remove:owner/example-app:host1-old"), ids.index("machine-config"))

    def test_windows_service_is_elevated_one_per_repo_with_both_hooks(self):
        pl = P.plan(self.found, [], ["owner/example-app"])
        svc = [s for s in pl["steps"] if s["action"] == "windows-service"]
        self.assertEqual(len(svc), 1)
        self.assertTrue(svc[0]["elevated"])
        text = " ".join(svc[0]["printed"])
        self.assertIn("JOB_STARTED", text)
        self.assertIn("JOB_COMPLETED", text)
        self.assertTrue(any("administrator shell" in n for n in pl["needs"]))

    def test_variables_use_pool_label(self):
        pl = P.plan(self.found, ["owner/example-app"], pool="main", serial=True)
        v = next(s for s in pl["steps"] if s["id"] == "var:CI_RUNS_ON:owner/example-app")
        self.assertEqual(json.loads(v["value"]), ["self-hosted", "linux", "pool-main"])


class RunTests(unittest.TestCase):
    def mk(self, steps):
        return {"pool": "main", "steps": steps, "refused": []}

    def test_stops_on_failure_and_lists_what_is_left(self):
        steps = [P._step("a", "A", "x"), P._step("b", "B", "x"), P._step("c", "C", "x")]
        said = []
        res = P.run(self.mk(steps), lambda s: True, lambda s: True, said.append,
                    execute=lambda s: (s["id"] != "b", "reason"))
        self.assertEqual(res["done"], ["a"])
        self.assertEqual(res["failed"]["id"], "b")
        self.assertEqual(res["left"], ["b", "c"])
        self.assertTrue(any(l.startswith("Left to do") for l in said))

    def test_no_yes_runs_nothing(self):
        ran = []
        P.run(self.mk([P._step("a", "A", "x")]), lambda s: False, lambda s: True, lambda l: None,
              execute=lambda s: (ran.append(s), (True, ""))[1])
        self.assertEqual(ran, [])

    def test_deletion_needs_its_own_yes_naming_what_goes(self):
        step = P._step("d", "Delete", "x", delete=True, names=["C:/Work/runners/app1"])
        ran, said = [], []
        res = P.run(self.mk([step]), lambda s: True, lambda s: False, said.append, execute=lambda s: (ran.append(1), (True, ""))[1])
        self.assertEqual(ran, [])
        self.assertTrue(any("C:/Work/runners/app1" in l for l in said))
        self.assertEqual(res["left"], ["d"])

    def test_elevated_step_is_printed_then_checked(self):
        step = P._step("e", "Service", "x", elevated=True, printed=["do this line"])
        said = []
        res = P.run(self.mk([step]), lambda s: True, lambda s: True, said.append, check=lambda s: False)
        self.assertIn("    do this line", said)
        self.assertEqual(res["failed"]["id"], "e")
        res = P.run(self.mk([step]), lambda s: True, lambda s: True, lambda l: None, check=lambda s: True)
        self.assertEqual(res["done"], ["e"])

    def test_already_set_step_is_skipped(self):
        step = P._step("a", "A", "x")
        step["state"] = "already"
        ran = []
        res = P.run(self.mk([step]), lambda s: True, lambda s: True, lambda l: None, execute=lambda s: (ran.append(1), (True, ""))[1])
        self.assertEqual((ran, res["done"]), ([], ["a"]))

    def test_executor_add_agent_pipes_token_and_never_prints_it(self):
        probe = FakeProbe()
        probe.gh = lambda a, input=None: (0, "TOKEN123\n")
        out = StringIO()
        with redirect_stdout(out):
            ok, detail = P.Executor(probe).run(P._step("g", "G", "add-agent", repo="owner/example-app", pool="main", slug="example-app"))
        self.assertTrue(ok)
        argv, stdin = probe.calls[-1]
        self.assertEqual(stdin, "TOKEN123\n")
        self.assertNotIn("TOKEN123", " ".join(argv) + detail + out.getvalue())

    def test_machine_config_step_without_machine_layer_fails_with_reason(self):
        old = P.MS
        P.MS = None
        try:
            ok, detail = P.Executor(FakeProbe()).run(P._step("m", "M", "machine-config"))
        finally:
            P.MS = old
        self.assertFalse(ok)
        self.assertIn("machine layer", detail)

    def test_machine_config_goes_through_the_helper_never_a_file(self):
        class FakeMS:
            wrote = None
            @staticmethod
            def machine_config():
                return {"ci_slots": 2}
            @staticmethod
            def write_machine_config(cfg):
                FakeMS.wrote = cfg
        old, P.MS = P.MS, FakeMS
        try:
            ok, _ = P.Executor(FakeProbe()).run(P._step("m", "M", "machine-config", limits={"ci_slots": 3}))
        finally:
            P.MS = old
        self.assertTrue(ok)
        self.assertEqual(FakeMS.wrote["ci_slots"], 3)


class VerifyAndDoctorTests(unittest.TestCase):
    def test_verify_ok_and_missing_label(self):
        probe = FakeProbe()
        self.assertEqual(P.verify(probe, ["owner/example-app"], "main")[0]["status"], "ok")
        self.assertEqual(P.verify(probe, ["owner/example-app"], "other")[0]["status"], "fail")
        self.assertEqual(P.verify(probe, ["owner/locked"], "main")[0]["status"], "fail")

    def test_doctor_skip_without_pool(self):
        with tempfile.TemporaryDirectory() as d:
            res = P.doctor_checks(d, FakeProbe())
        self.assertEqual([c["status"] for c in res], ["skip"])

    def _pool(self, d, compose="services: {}\n", env="POOL_CPUS=2\nPOOL_MEM=8g\n", agents=None):
        pd = Path(d, "pools", "main")
        pd.mkdir(parents=True)
        (pd / "compose.yaml").write_text(compose)
        (pd / ".env").write_text(env)
        (pd / "agents.json").write_text(json.dumps({"agents": agents if agents is not None else
                                                    [{"slug": "a", "user": "r-a", "repo": "o/a", "private": True}]}))

    def test_doctor_ok(self):
        with tempfile.TemporaryDirectory() as d:
            self._pool(d)
            res = P.doctor_checks(d, FakeProbe())
        by = {c["id"].split(".")[-1]: c for c in res}
        for k in ("socket", "cap", "users", "private", "running"):
            self.assertEqual(by[k]["status"], "ok", by[k])

    def test_doctor_fails_socket_shared_user_public_agent_no_cap(self):
        with tempfile.TemporaryDirectory() as d:
            self._pool(d, compose="- /var/run/docker.sock:/x", env="",
                       agents=[{"slug": "a", "user": "r-a", "repo": "o/a", "private": True},
                               {"slug": "b", "user": "r-a", "repo": "o/b", "private": False}])
            res = P.doctor_checks(d, FakeProbe())
        by = {c["id"].split(".")[-1]: c["status"] for c in res}
        self.assertEqual((by["socket"], by["cap"], by["users"], by["private"]), ("fail",) * 4)
        for c in res:
            self.assertIn(c["status"], ("ok", "warn", "fail", "skip"))
            self.assertTrue(c["id"].startswith("pool."))


class PoolFilesTests(unittest.TestCase):
    def test_env_holds_cap_only_and_password_file_is_private(self):
        with tempfile.TemporaryDirectory() as d:
            dest = os.path.join(d, "pools", "main")
            P.write_pool_files("main", {"cpus": 2.0, "mem_gib": 6.0}, dest=dest)
            env = Path(dest, ".env").read_text()
            self.assertIn("POOL_CPUS=2.0", env)
            self.assertIn("POOL_MEM=6.0g", env)
            self.assertNotIn("PASSWORD", env.upper())
            self.assertEqual(os.stat(os.path.join(dest, "db-admin.pw")).st_mode & 0o077, 0)
            self.assertTrue(os.path.exists(os.path.join(dest, "pool_supervisor.py")))
            self.assertFalse(os.path.exists(os.path.join(dest, "pool-check.yml")))

    def test_templates_have_label_sha_check_tini_and_no_socket(self):
        df = (POOL / "Dockerfile").read_text()
        self.assertIn("dev.luismc.runner-pool", df)
        self.assertIn("sha256sum -c", df)
        self.assertIn("tini", df)
        compose = (POOL / "compose.yaml").read_text()
        self.assertNotIn("docker.sock", compose)
        self.assertIn("/machine", compose)
        self.assertIn("mem_limit", compose)
        self.assertIn("postgres", compose)


class FakeProc:
    def __init__(self):
        self.code = None
        self.terminated = False

    def poll(self):
        return self.code

    def terminate(self):
        self.terminated = True
        self.code = 0

    def kill(self):
        self.code = -9


class SupervisorTests(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.file = os.path.join(self.d, "agents.json")
        self.now = [0.0]
        self.procs = []
        Path(self.file).write_text(json.dumps({"agents": [{"slug": "a", "user": "r-a"}, {"slug": "b", "user": "r-b"}, {"slug": "bad"}]}))
        self.sup = SUP.Supervisor(self.file, self.d, spawn=self._spawn, clock=lambda: self.now[0])

    def _spawn(self, agent):
        p = FakeProc()
        self.procs.append((agent["slug"], p))
        return p

    def test_one_agent_per_user_and_bad_entry_skipped(self):
        self.sup.tick()
        self.assertEqual(sorted(s for s, _ in self.procs), ["a", "b"])

    def test_dead_agent_restarts_with_backoff(self):
        self.sup.tick()
        self.procs[0][1].code = 1
        self.now[0] = 1
        self.sup.tick()
        self.assertEqual(len(self.procs), 2)  # still waiting
        self.now[0] = 3
        self.sup.tick()
        self.assertEqual(len(self.procs), 3)
        self.procs[2][1].code = 1
        self.now[0] = 4
        self.sup.tick()
        self.now[0] = 6
        self.sup.tick()
        self.assertEqual(len(self.procs), 3)  # second failure waits 4 s
        self.now[0] = 9
        self.sup.tick()
        self.assertEqual(len(self.procs), 4)

    def test_removed_agent_is_stopped(self):
        self.sup.tick()
        Path(self.file).write_text(json.dumps({"agents": [{"slug": "a", "user": "r-a"}]}))
        self.sup.tick()
        self.assertTrue(dict(self.procs)["b"].terminated)

    def test_graceful_stop_waits_for_running_jobs_then_stops_starting(self):
        self.sup.tick()
        slept = []
        for _, p in self.procs:
            p.terminate = lambda p=p: None  # a running job: the agent does not end at once

        def sleep(_):
            slept.append(1)
            if len(slept) == 3:
                for _, p in self.procs:
                    p.code = 0
        self.sup.stop(grace_sec=100, sleep=sleep)
        self.assertEqual(len(slept), 3)
        n = len(self.procs)
        self.sup.tick()
        self.assertEqual(len(self.procs), n)

    def test_stop_kills_after_grace(self):
        self.sup.tick()
        for _, p in self.procs:
            p.terminate = lambda: None

        def sleep(_):
            self.now[0] += 60
        self.sup.stop(grace_sec=100, sleep=sleep)
        self.assertTrue(all(p.code == -9 for _, p in self.procs))

    def test_missing_file_means_no_agents(self):
        self.assertEqual(SUP.load_agents(os.path.join(self.d, "none.json")), [])


class R:
    def __init__(self, code=0, err=""):
        self.returncode, self.stderr, self.stdout = code, err, ""


class AgentTests(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.file = os.path.join(self.d, "agents.json")
        self.calls = []

    def run_(self, argv, **kw):
        self.calls.append(argv)
        return R()

    def test_add_writes_agent_hooks_and_db_login_without_printing_token(self):
        msg = A.add_agent("app1", "owner/example-app", "TOK999", "main", True, self.file, self.d, self.run_)
        self.assertIn("added", msg)
        data = json.loads(Path(self.file).read_text())
        self.assertEqual(data["agents"][0]["user"], "r-app1")
        self.assertIn("pool-main", data["agents"][0]["labels"])
        env = Path(self.d, "app1", ".env").read_text()
        self.assertIn("HOOK_JOB_STARTED", env)
        self.assertIn("HOOK_JOB_COMPLETED", env)
        self.assertNotIn("TOK999", env + Path(self.file).read_text() + msg)
        self.assertEqual(os.stat(os.path.join(self.d, "app1", "db.env")).st_mode & 0o077, 0)

    def test_add_is_safe_to_repeat(self):
        A.add_agent("app1", "owner/example-app", "T", "main", True, self.file, self.d, self.run_)
        n = len(self.calls)
        self.assertIn("already", A.add_agent("app1", "owner/example-app", "T", "main", True, self.file, self.d, self.run_))
        self.assertEqual(len(self.calls), n)

    def test_add_refuses_unasserted_private(self):
        with self.assertRaises(A.PoolError) as cm:
            A.add_agent("app1", "owner/example-app", "T", "main", False, self.file, self.d, self.run_)
        self.assertIn("public", str(cm.exception))
        self.assertEqual(self.calls, [])

    def test_failure_text_hides_token(self):
        def bad(argv, **kw):
            return R(1, "bad token TOK999") if "config.sh" in " ".join(argv) else R()
        with self.assertRaises(A.PoolError) as cm:
            A.add_agent("app1", "owner/example-app", "TOK999", "main", True, self.file, self.d, bad)
        self.assertNotIn("TOK999", str(cm.exception))

    def test_remove_keeps_folder_unless_told(self):
        A.add_agent("app1", "owner/example-app", "T", "main", True, self.file, self.d, self.run_)
        self.calls.clear()
        msg = A.remove_agent("app1", "T", self.file, self.d, self.run_)
        self.assertIn("folder kept", msg)
        self.assertEqual(json.loads(Path(self.file).read_text())["agents"], [])
        self.assertFalse([c for c in self.calls if c[0] == "rm"])
        self.assertIn("not in the pool", A.remove_agent("app1", "T", self.file, self.d, self.run_))

    def test_main_reads_token_from_stdin_and_prints_no_token(self):
        out, err = StringIO(), StringIO()
        from contextlib import redirect_stderr
        with redirect_stdout(out), redirect_stderr(err):
            rc = A.main(["add", "app1", "owner/example-app", "--agents", self.file, "--base", self.d], stdin=StringIO("TOKXYZ\n"))
        self.assertEqual(rc, 1)  # no --private
        self.assertNotIn("TOKXYZ", out.getvalue() + err.getvalue())
        with redirect_stdout(out), redirect_stderr(err):
            self.assertEqual(A.main(["add", "app1", "owner/example-app"], stdin=StringIO("")), 1)


class SummaryTests(unittest.TestCase):
    def test_plan_has_section_13_parts(self):
        found = P.detect(FakeProbe(dict(FILES)))
        pl = P.plan(found, ["owner/example-app"], ["owner/example-app"])
        text = "\n".join(S.render_plan(pl, found))
        for part in ("Plan (nothing has changed yet)", "Writes on this machine", "Changes outside the repository", "Needs you", "minutes"):
            self.assertIn(part, text)
        self.assertIn("you run it", text)
        self.assertIn("asks a second yes", text)

    def test_summary_three_parts_numbered_left(self):
        lines = S.render_summary(["wrote pool files"], ["Run X in an administrator shell.", "Set Y."], S.can_do_now("main"))
        text = "\n".join(lines)
        self.assertLess(text.index("Done"), text.index("Left for you"))
        self.assertLess(text.index("Left for you"), text.index("What you can do now"))
        self.assertIn("  1. Run X", text)
        self.assertIn("  2. Set Y.", text)
        self.assertIn("gh workflow run pool-check.yml", text)

    def test_summary_when_nothing_changed(self):
        text = "\n".join(S.render_summary([], [], S.can_do_now("main")))
        self.assertIn("everything was already set", text)
        self.assertIn("nothing", text)


if __name__ == "__main__":
    unittest.main()
