"""DL30: pool detect, plan, sizing, run, doctor checks, supervisor, add and remove agent, section 13 summary. No Docker."""
import json
import math
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest import mock

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


def _is_fake_path(path):
    """DL105: only the made-up Windows paths of these tests are fake. A real temp folder on drive C: is not."""
    return str(path).replace("\\", "/").startswith(("C:/Work", "C:/Users/u1"))


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
        return self.files[p] if p in self.files else (super().read_text(path) if not _is_fake_path(p) else None)

    def listdir(self, path):
        pre = path.rstrip("/") + "/"
        mine = sorted({k[len(pre):].split("/")[0] for k in self.files if k.startswith(pre)})
        return mine or (super().listdir(path) if not _is_fake_path(path) else [])

    def isfile(self, path):
        return path.replace("\\", "/") in self.files or (not _is_fake_path(path) and os.path.isfile(path))

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

    @mock.patch.object(P, "MIN_POOL_GIB", 0.0)  # DL105: the subject is the Docker ceiling, not the pool floor
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
            if os.name != "nt":  # DL105: POSIX modes do not exist on Windows
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
        if os.name != "nt":  # DL105: POSIX modes do not exist on Windows
            self.assertEqual(os.stat(os.path.join(self.d, "app1", "db.env")).st_mode & 0o077, 0)

    def test_add_is_safe_to_repeat(self):
        A.add_agent("app1", "owner/example-app", "T", "main", True, self.file, self.d, self.run_)
        n = len(self.calls)
        self.assertIn("already", A.add_agent("app1", "owner/example-app", "T", "main", True, self.file, self.d, self.run_))
        again = [c[0] for c in self.calls[n:]]
        self.assertTrue(again and all(cmd in ("psql", "chown", "chmod") for cmd in again), again)  # database refresh (D104) and temp folder (DL87)

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


class DL86GhTests(unittest.TestCase):
    def test_dockerfile_installs_pinned_gh(self):
        import re
        d = (POOL / "Dockerfile").read_text(encoding="utf-8")
        self.assertRegex(d, r"ARG GH_VERSION=\d+\.\d+\.\d+")
        self.assertRegex(d, r"ARG GH_SHA256=[0-9a-f]{64}\b")
        self.assertIn("github.com/cli/cli/releases/download", d)
        self.assertIn('"${GH_SHA256}  /tmp/gh.tgz" | sha256sum -c', d)
        self.assertIn("/usr/local/bin/gh", d)
        step = d.index("GH_SHA256=")
        browsers = d.index('if [ "$POOL_BROWSERS" = "chromium" ]')
        self.assertLess(step, browsers)
        gh_run = d[step:d.index("\n# The runner tarball")]
        self.assertNotIn("POOL_BROWSERS", gh_run)

    def test_pool_check_lists_gh(self):
        y = (POOL / "pool-check.yml").read_text(encoding="utf-8")
        loop = [l for l in y.splitlines() if "for t in" in l][0]
        self.assertIn(" gh;", loop)
        self.assertIn("gh --version", y)


if __name__ == "__main__":
    unittest.main()


# --- DL40: setup and plan fixes (fixtures only: no Docker, no network) --------------------------------------------------

WIN_SERVICE = json.dumps({"Name": "actions.runner.owner-example-app.host1-app1", "State": "Running",
                          "PathName": '"C:\\Work\\runners\\winapp\\bin\\RunnerService.exe"'})
WIN_FILES = {
    "C:/Work/runners/winapp/.runner": '{"agentId": 7, "agentName": "host1-old", "gitHubUrl": "https://github.com/owner/example-app"}',
    "C:/Users/u1/.wslconfig": "[wsl2]\nmemory=12GB\nprocessors=6\n",
}


class WinProbe(FakeProbe):
    """A Windows host: one runner service, Docker only inside WSL, memory known."""
    platform = "win32"

    def __init__(self, files=None, mem=(32.0, 10.0), cpus=16):
        super().__init__(files)
        self.runner_dirs = []
        self.mem, self.cpus = mem, cpus

    def sh(self, argv, input=None, timeout=60):
        self.calls.append((argv, input))
        if argv[0] == "powershell":
            return 0, WIN_SERVICE
        if argv[0] == "docker":
            return None  # not on the Windows PATH
        if argv[:2] == ["wsl", "docker"] and "label=" + P.LABEL in argv:
            return 0, ""
        if argv[:2] == ["wsl", "docker"]:
            return 0, 'c1\tlinux-runner\t"./bin/Runner.Listener run"\n'
        return 0, ""

    def python(self):
        return "C:/Python/python.exe"

    def cpu_count(self):
        return self.cpus

    def machine_dir(self):
        return "C:/ProgramData/luismc-delivery"

    def memory_gib(self):
        return self.mem


class P1DeriveTests(unittest.TestCase):
    def setUp(self):
        self.found = P.detect(FakeProbe(dict(FILES)))

    def test_no_repos_derives_private_repos_with_a_runner(self):
        pl = P.plan(self.found, [], [])
        self.assertTrue(pl["derived"])
        self.assertIn("agent:owner/example-app", [s["id"] for s in pl["steps"]])
        self.assertFalse([s for s in pl["steps"] if s.get("repo") == "owner/public-app"])

    def test_workflow_with_self_hosted_label_counts(self):
        self.found["github"]["repos"][2]["private"] = True
        self.found["github"]["repos"][2]["self_hosted_workflows"] = True
        self.found["github"]["repos"][2]["runners"] = []
        self.assertIn("owner/locked", P.derive_repos(self.found)[0])

    def test_windows_repos_come_from_windows_runners(self):
        lin, win = P.derive_repos(self.found)
        self.assertEqual(win, ["owner/example-app"])
        self.assertEqual(lin, ["owner/example-app"])

    def test_nothing_derived_refuses_to_plan_removals(self):
        for r in self.found["github"]["repos"]:
            r["runners"] = []
        pl = P.plan(self.found, [], [])
        self.assertEqual(pl["steps"], [])
        self.assertIn("No runner is removed", pl["blocked"])

    def test_workflow_scan_reads_only_private_repos(self):
        probe = FakeProbe(dict(FILES))
        gh = probe.gh
        calls = []
        probe.gh = lambda a, input=None: (calls.append(a), gh(a, input))[1]
        P.detect(probe)
        self.assertTrue(all("owner/public-app" not in " ".join(a) or "workflows" not in " ".join(a) for a in calls))

    def test_removals_only_for_planned_repos(self):
        self.found["github"]["repos"][2]["runners"] = [{"id": 9, "name": "other", "os": "Linux", "status": "online",
                                                       "busy": False, "labels": []}]
        pl = P.plan(self.found, ["owner/example-app"])
        self.assertFalse([s for s in pl["steps"] if s["id"].startswith("remove:owner/locked")])


class P2DeleteMarkTests(unittest.TestCase):
    def test_runner_removal_is_a_deletion_naming_the_runner(self):
        pl = P.plan(P.detect(FakeProbe(dict(FILES))), ["owner/example-app"])
        s = next(x for x in pl["steps"] if x["action"] == "remove-runner")
        self.assertTrue(s["delete"])
        self.assertIn("host1-old", s["names"][0])

    def test_run_asks_for_the_delete_yes_on_runner_removal(self):
        pl = P.plan(P.detect(FakeProbe(dict(FILES))), ["owner/example-app"])
        asked = []
        P.run({"pool": "main", "refused": [], "steps": [x for x in pl["steps"] if x["action"] == "remove-runner"]},
              ask=lambda s: True, ask_delete=lambda s: (asked.append(s["names"]), False)[1], say=lambda m: None)
        self.assertTrue(asked)


class P3WindowsServiceTests(unittest.TestCase):
    def setUp(self):
        self.found = P.detect(WinProbe(dict(WIN_FILES)))
        self.pl = P.plan(self.found, ["owner/example-app"])

    def test_service_step_prints_stop_and_delete_and_is_a_named_deletion(self):
        s = next(x for x in self.pl["steps"] if x["action"] == "windows-service-remove")
        self.assertTrue(s["elevated"] and s["delete"])
        self.assertEqual(s["printed"], ['sc.exe stop "actions.runner.owner-example-app.host1-app1"',
                                        'sc.exe delete "actions.runner.owner-example-app.host1-app1"'])
        self.assertIn("Windows service actions.runner.owner-example-app.host1-app1", s["names"])

    def test_service_step_comes_before_folder_delete_and_check_reads_the_service(self):
        ids = [x["id"] for x in self.pl["steps"]]
        self.assertLess(ids.index("winsvc-remove:actions.runner.owner-example-app.host1-app1"),
                        ids.index("delete-folder:C:/Work/runners/winapp"))
        step = next(x for x in self.pl["steps"] if x["action"] == "windows-service-remove")
        self.assertFalse(P.default_check(step, WinProbe()))  # still there
        gone = WinProbe()
        gone.sh = lambda argv, input=None, timeout=60: (0, "")
        self.assertTrue(P.default_check(step, gone))

    def test_run_prints_then_checks_the_service_step(self):
        step = next(x for x in self.pl["steps"] if x["action"] == "windows-service-remove")
        said = []
        gone = WinProbe()
        gone.sh = lambda argv, input=None, timeout=60: (0, "")
        orig = P.Probe
        P.Probe = lambda: gone
        try:
            r = P.run({"pool": "main", "refused": [], "steps": [step]}, ask=lambda s: True, ask_delete=lambda s: True,
                      say=said.append, check=lambda s: False)
        finally:
            P.Probe = orig
        self.assertTrue(any("sc.exe delete" in m for m in said))
        self.assertEqual(r["done"], [step["id"]])


class P4HostLoadTaskTests(unittest.TestCase):
    def setUp(self):
        self.pl = P.plan(P.detect(WinProbe(dict(WIN_FILES))), ["owner/example-app"])

    def test_task_uses_absolute_paths_and_runs_at_boot_not_every_minute(self):
        t = next(x for x in self.pl["steps"] if x["id"] == "host-load-task")
        text = " ".join(t["printed"])
        self.assertNotIn("/SC MINUTE", text)
        self.assertIn("/SC ONSTART", text)
        self.assertIn('C:\\Python\\python.exe', text)
        self.assertIn('C:\\ProgramData\\luismc-delivery\\host-load\\host-load-loop.py', text)
        self.assertNotIn(" load.py", text)

    def test_files_step_comes_first_and_the_loop_sleeps_15_seconds(self):
        ids = [x["id"] for x in self.pl["steps"]]
        self.assertLess(ids.index("host-load-files"), ids.index("host-load-task"))
        self.assertIn("time.sleep(15)", P.LOOP_SCRIPT)

    def test_files_handler_copies_load_and_writes_the_loop(self):
        with tempfile.TemporaryDirectory() as d:
            ok, _ = P.Executor(FakeProbe()).run({"action": "host-load-files", "dest": os.path.join(d, "hl")})
            self.assertTrue(ok)
            self.assertEqual(sorted(os.listdir(os.path.join(d, "hl")))[:2], ["host-load-loop.py", "load.py"])

    def test_no_task_on_a_host_that_is_not_windows(self):
        pl = P.plan(P.detect(FakeProbe(dict(FILES))), ["owner/example-app"])
        self.assertFalse([x for x in pl["steps"] if x["id"].startswith("host-load")])


class P5WslTests(unittest.TestCase):
    def test_wsl_step_and_restart_added_when_ceiling_is_too_low(self):
        found = P.detect(WinProbe(dict(WIN_FILES)))
        found["wsl"]["memory"] = 4.0
        cap = P.measured_sizing(found)
        pl = P.plan(found, ["owner/example-app"], cap=cap)
        ids = [x["id"] for x in pl["steps"]]
        self.assertIn("wslconfig", ids)
        self.assertLess(ids.index("wslconfig"), ids.index("wsl-restart"))
        self.assertLess(ids.index("wsl-restart"), ids.index("pool-files"))

    def test_enough_ceiling_is_already_set_and_no_restart(self):
        found = P.detect(WinProbe(dict(WIN_FILES)))
        found["wsl"]["processors"] = 12
        pl = P.plan(found, ["owner/example-app"], cap=P.sizing(32, 10, 16, docker_gib=12))
        self.assertEqual(next(x for x in pl["steps"] if x["id"] == "wslconfig")["state"], "already")
        self.assertNotIn("wsl-restart", [x["id"] for x in pl["steps"]])

    def test_set_wsl_values_replaces_in_section_and_keeps_other_lines(self):
        out = P.set_wsl_values("[wsl2]\nmemory=4GB\nswap=0\n[user]\ndefault=u\n", 10, 5)
        self.assertEqual(out, "[wsl2]\nmemory=10GB\nswap=0\nprocessors=5\n[user]\ndefault=u\n")
        self.assertEqual(P.set_wsl_values("", 8, 4), "\n[wsl2]\nmemory=8GB\nprocessors=4\n")

    def test_restart_refused_while_a_job_runs(self):
        probe = FakeProbe(dict(FILES))
        gj = probe.gh_json
        probe.gh_json = lambda a: ({"runners": [{"id": 1, "name": "r", "os": "Linux", "status": "online", "busy": True,
                                                 "labels": []}]}, None) if "runners" in " ".join(a) else gj(a)
        ok, why = P.Executor(probe).run({"action": "wsl-restart"})
        self.assertFalse(ok)
        self.assertNotIn(["wsl", "--shutdown"], [c[0] for c in probe.calls])

    def test_wslconfig_handler_writes_and_keeps_a_backup(self):
        with tempfile.TemporaryDirectory() as d:
            probe = FakeProbe()
            probe.wslconfig = os.path.join(d, ".wslconfig")
            probe.read_text = lambda p: Path(p).read_text() if os.path.exists(p) else None
            Path(probe.wslconfig).write_text("[wsl2]\nmemory=4GB\n")
            ok, _ = P.Executor(probe).run({"action": "wslconfig", "cap": {"wsl": {"memory": 10, "processors": 5}}})
            self.assertTrue(ok)
            self.assertIn("memory=10GB", Path(probe.wslconfig).read_text())
            self.assertIn("memory=4GB", Path(probe.wslconfig + ".bak").read_text())


class P6DetectTests(unittest.TestCase):
    def setUp(self):
        self.found = P.detect(WinProbe(dict(WIN_FILES)))

    def test_service_image_path_gives_the_folder(self):
        self.assertEqual(self.found["services"][0]["folder"], "C:/Work/runners/winapp")
        self.assertEqual(self.found["folders"][0]["path"], "C:/Work/runners/winapp")
        self.assertEqual(self.found["folders"][0]["repo"], "owner/example-app")

    def test_service_folder_without_runner_file_is_still_listed(self):
        found = P.detect(WinProbe({}))
        self.assertEqual([f["path"] for f in found["folders"]], ["C:/Work/runners/winapp"])

    def test_containers_inside_wsl_docker_found_read_only(self):
        c = self.found["containers"]
        self.assertEqual([(x["name"], x["via"]) for x in c], [("linux-runner", "wsl")])
        self.assertTrue(all(a[0] in ("docker", "wsl") and "rm" not in a for a, _ in WinProbe().calls))

    def test_delete_container_goes_through_wsl(self):
        probe = WinProbe()
        P.Executor(probe).run({"action": "delete-container", "container": "linux-runner", "via": "wsl"})
        self.assertEqual(probe.calls[-1][0], ["wsl", "docker", "rm", "-f", "linux-runner"])

    def test_host_figures_measured(self):
        self.assertEqual(self.found["host"]["total_gib"], 32.0)
        self.assertEqual(self.found["host"]["cpus"], 16)

    def test_measured_sizing_gives_a_cap_without_hand_numbers(self):
        cap = P.measured_sizing(self.found)
        self.assertIsNotNone(cap)
        self.assertEqual(cap["mem_gib"], 10.0)  # min(room 17.2, wsl 12) - 1 - 1
        self.assertEqual(cap["measured"]["cpus"], 16)
        pl = P.plan(self.found, ["owner/example-app"], cap=cap)
        self.assertIsNotNone(pl["cap"])

    def test_hand_numbers_win_over_measured(self):
        cap = P.measured_sizing(self.found, total_gib=64, used_gib=0, cpus=8, docker_gib=40)
        self.assertEqual(cap["measured"]["total_gib"], 64)

    def test_unmeasurable_memory_gives_none(self):
        found = P.detect(WinProbe(dict(WIN_FILES), mem=None))
        self.assertIsNone(P.measured_sizing(found))

    def test_a_refused_sizing_blocks_the_plan(self):
        pl = P.plan(self.found, ["owner/example-app"], cap=P.sizing(8, 7, 4))
        self.assertEqual(pl["steps"], [])
        self.assertIn("Sizing refused", pl["blocked"])


class ServiceFolderTests(unittest.TestCase):
    def test_paths(self):
        self.assertEqual(P.service_folder('"C:\\r\\a\\bin\\RunnerService.exe"'), "C:/r/a")
        self.assertEqual(P.service_folder('C:\\r\\a\\RunnerService.exe -x'), "C:/r/a")
        self.assertEqual(P.service_folder(None), "")


# --- DL41: the pool command (fixtures only) -------------------------------------------------------------------------------

class PoolCommandTests(unittest.TestCase):
    def run_cmd(self, action, *extra, probe=None):
        from unittest import mock
        import argparse
        probe = probe or FakeProbe(dict(FILES))
        probe.memory_gib = lambda: (32.0, 4.0)
        probe.cpu_count = lambda: 8
        args = argparse.Namespace(action=action, repos=None, windows_repos=None, pool="main", total_gib=None, used_gib=None,
                                  cpus=None, docker_gib=None, largest_shard_gib=None, yes=False, yes_delete=None)
        for k, v in zip(extra[::2], extra[1::2]):
            setattr(args, k, v)
        out = StringIO()
        with mock.patch.object(P, "Probe", lambda: probe), redirect_stdout(out):
            rc = S.cmd_pool(args, ".")
        return rc, out.getvalue()

    def test_cap_measured_without_flags(self):
        rc, text = self.run_cmd("pool-plan")
        self.assertEqual(rc, 0)
        self.assertIn("Pool cap:", text)

    def test_flags_override_measured(self):
        _, a = self.run_cmd("pool-plan")
        _, b = self.run_cmd("pool-plan", "total_gib", 64.0, "cpus", 16.0)
        self.assertNotEqual([x for x in a.splitlines() if x.startswith("Pool cap")],
                            [x for x in b.splitlines() if x.startswith("Pool cap")])

    def test_unmeasurable_asks_for_numbers(self):
        probe = FakeProbe(dict(FILES))
        from unittest import mock
        import argparse
        probe.memory_gib = lambda: None
        probe.cpu_count = lambda: None
        args = argparse.Namespace(action="pool-plan", repos=None, windows_repos=None, pool="main", total_gib=None,
                                  used_gib=None, cpus=None, docker_gib=None, largest_shard_gib=None)
        err = StringIO()
        from contextlib import redirect_stderr
        with mock.patch.object(P, "Probe", lambda: probe), redirect_stderr(err):
            self.assertEqual(S.cmd_pool(args, "."), 1)
        self.assertIn("--total-gib", err.getvalue())

    def test_derived_repos_named_in_plan(self):
        _, text = self.run_cmd("pool-plan")
        self.assertIn("none named, taken from GitHub", text)
        self.assertIn("owner/example-app", text)

    def test_named_repos_no_derived_line(self):
        _, text = self.run_cmd("pool-plan", "repos", "owner/example-app")
        self.assertNotIn("none named", text)

    def test_run_prints_plan_then_summary(self):
        _, text = self.run_cmd("pool-run")
        self.assertLess(text.index("Plan (nothing has changed yet)"), text.index("Left for you"))
        self.assertIn("What you can do now", text)

    def test_check_uses_step_action(self):
        from unittest import mock
        calls = []
        orig = P.default_check
        with mock.patch.object(P, "default_check", lambda st, pr=None: calls.append(st["action"]) or False):
            self.run_cmd("pool-run", "yes", True)
        self.assertTrue(all(a != "windows-service" for a in calls))


class DL63HostLoadCheckTests(unittest.TestCase):
    STEP = {"action": "host-load-task"}

    def probe(self, schtasks, age):
        p = FakeProbe()
        p.sh = lambda argv, input=None, timeout=60: schtasks
        p.host_load = lambda: (({"mem": 40.0, "cpu": 10.0}, age) if age is not None else (None, None))
        return p

    def test_denied_query_with_a_fresh_file_passes(self):
        self.assertTrue(P.default_check(self.STEP, self.probe((1, ""), 12.0)))

    def test_denied_query_with_a_stale_or_missing_file_is_not_done(self):
        self.assertFalse(P.default_check(self.STEP, self.probe((1, ""), 300.0)))
        self.assertFalse(P.default_check(self.STEP, self.probe((1, ""), None)))
        self.assertFalse(P.default_check(self.STEP, self.probe(None, None)))

    def test_a_good_query_passes_first(self):
        self.assertTrue(P.default_check(self.STEP, self.probe((0, "TaskName"), None)))


class DL63RunnerVersionTests(unittest.TestCase):
    def probe(self, data):
        p = FakeProbe()
        p.gh_json = lambda args: (data, None) if data is not None else (None, "gh cannot run")
        return p

    @staticmethod
    def release(v, sha="a" * 64):
        return {"tag_name": "v" + v, "assets": [{"name": "actions-runner-linux-x64-%s.tar.gz" % v, "digest": "sha256:" + sha}]}

    def test_latest_release_and_digest_are_used(self):
        self.assertEqual(P.resolve_runner(self.probe(self.release("2.400.1"))), ("2.400.1", "a" * 64, "latest release"))

    def test_fallback_when_the_api_cannot_be_reached_or_has_no_digest(self):
        for data in (None, {"tag_name": "v2.400.1", "assets": []}, {"tag_name": "v2.100.0", "assets": []}):
            v, sha, _ = P.resolve_runner(self.probe(data))
            self.assertEqual((v, sha), (P.RUNNER_VERSION, P.RUNNER_SHA256))

    def test_pinned_fallback_is_above_the_floor_and_templates_match(self):
        self.assertIsNone(P.below_floor(P.RUNNER_VERSION))
        self.assertIn("2.329.0", P.below_floor("2.321.0"))
        self.assertIn("ARG RUNNER_VERSION=" + P.RUNNER_VERSION, (POOL / "Dockerfile").read_text())
        self.assertIn(":-" + P.RUNNER_VERSION + "}", (POOL / "compose.yaml").read_text())

    def test_runner_sha_works_with_the_chosen_version_and_the_fallback(self):
        self.assertEqual(P.runner_sha(self.probe(self.release("2.400.1", "b" * 64)), "2.400.1"), "b" * 64)
        self.assertEqual(P.runner_sha(self.probe(None)), P.RUNNER_SHA256)
        self.assertIsNone(P.runner_sha(self.probe(None), "2.400.1"))

    def test_pool_files_write_the_version_to_env(self):
        with tempfile.TemporaryDirectory() as d:
            dest = os.path.join(d, "pools", "main")
            P.write_pool_files("main", {"cpus": 2.0, "mem_gib": 6.0}, dest=dest, runner_version="2.400.1")
            self.assertIn("RUNNER_VERSION=2.400.1", Path(dest, ".env").read_text())

    def test_pool_up_refuses_a_version_below_the_floor(self):
        probe = FakeProbe()
        probe.read_text = lambda path: "RUNNER_VERSION=2.321.0\n"
        ok, why = P.Executor(probe).run({"action": "pool-up", "pool": "main"})
        self.assertFalse(ok)
        self.assertIn("below 2.329.0", why)


class DL63SizingTests(unittest.TestCase):
    def found(self, used, vm, pool_gib=0.0, others=(), other_gib=0.0, wsl=12.0):
        class Pr(WinProbe):
            def memory_gib(s):
                return (32.0, used)

            def wsl_vm_gib(s):
                return vm

            def container_gib(s):
                return {"pool": pool_gib, "other": other_gib, "others": list(others)}
        f = P.detect(Pr(dict(WIN_FILES)))
        f["wsl"]["memory"] = wsl
        return f

    def test_a_rerun_with_the_pool_running_gives_the_same_cap(self):
        first = P.measured_sizing(self.found(used=10.0, vm=0.0))
        # the pool and WSL now run: the VM holds 9 GiB, which must not count as used
        second = P.measured_sizing(self.found(used=19.0, vm=9.0))
        self.assertEqual(first["mem_gib"], second["mem_gib"])
        self.assertEqual(first["wsl"], second["wsl"])

    def test_without_a_vm_the_pool_containers_are_left_out(self):
        a = self.found(used=10.0, vm=0.0)
        b = self.found(used=14.0, vm=0.0, pool_gib=4.0)
        self.assertEqual(a["host"]["used_gib"], b["host"]["used_gib"])

    def test_wsl_memory_never_drops_below_current_when_other_containers_run(self):
        cap = P.measured_sizing(self.found(used=20.0, vm=0.0, others=["old-runner"], other_gib=3.0, wsl=14.0))
        self.assertGreaterEqual(cap["wsl"]["memory"], 14)
        self.assertGreaterEqual(cap["wsl"]["memory"], 3 + cap["mem_gib"] + 2)

    @mock.patch.object(P, "MIN_POOL_GIB", 0.0)  # DL105: the subject is the room for other containers, not the pool floor
    def test_pool_cap_leaves_room_for_other_containers(self):
        alone = P.sizing(32, 5, 16, docker_gib=12)
        shared = P.sizing(32, 5, 16, docker_gib=12, other_gib=4.0, others_run=True, wsl_current=12)
        self.assertEqual(shared["mem_gib"], alone["mem_gib"] - 4)

    def test_container_gib_splits_pool_from_others(self):
        p = FakeProbe()

        def sh(argv, input=None, timeout=60):
            if argv[1] == "ps":
                return 0, "pool-main-pool-1\t1\nold-runner\t\n"
            return 0, "pool-main-pool-1\t2GiB / 8GiB\nold-runner\t512MiB / 8GiB\n"
        p.sh = sh
        out = p.container_gib()
        self.assertEqual((out["pool"], out["other"], out["others"]), (2.0, 0.5, ["old-runner"]))

    def test_plan_shows_old_and_new_values(self):
        found = self.found(used=10.0, vm=0.0, wsl=4.0)
        found["pool_env"] = {"POOL_MEM": "1.0g", "POOL_CPUS": "2.0"}
        pl = P.plan(found, ["owner/example-app"], cap=P.measured_sizing(found))
        titles = {s["id"]: s["title"] for s in pl["steps"]}
        self.assertIn("memory 4GB ->", titles["wslconfig"])
        self.assertIn("processors 6 ->", titles["wslconfig"])
        self.assertIn("POOL_MEM 1.0g ->", titles["pool-files"])
        self.assertIn("POOL_CPUS 2.0 ->", titles["pool-files"])

    def test_wslconfig_handler_reports_old_and_new(self):
        with tempfile.TemporaryDirectory() as d:
            probe = FakeProbe()
            probe.wslconfig = os.path.join(d, ".wslconfig")
            probe.read_text = lambda p: Path(p).read_text() if os.path.exists(p) else None
            Path(probe.wslconfig).write_text("[wsl2]\nmemory=4GB\nprocessors=2\n")
            ok, why = P.Executor(probe).run({"action": "wslconfig", "cap": {"wsl": {"memory": 10, "processors": 5}}})
            self.assertIn("memory 4GB -> 10GB", why)
            self.assertIn("processors 2 -> 5", why)


class DL63PoolAgentTests(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.file = os.path.join(self.d, "agents.json")
        self.calls = []

    def run_(self, argv, **kw):
        self.calls.append((argv, kw))
        return R()

    def test_role_and_database_are_two_separate_psql_calls_in_order(self):
        A.create_db("app1", self.d, "r-app1", self.run_)
        psql = [(a, k) for a, k in self.calls if a[0] == "psql"]
        self.assertEqual(len(psql), 2)
        role, db = psql[0][1]["input"], psql[1][1]["input"]
        self.assertIn("CREATE ROLE", role)
        self.assertNotIn("CREATE DATABASE", role)
        self.assertIn("CREATE DATABASE", db)
        self.assertNotIn("CREATE ROLE", db)
        self.assertIn("NOT EXISTS", db)
        self.assertIn("IF EXISTS", role)
        self.assertNotIn("-c", psql[0][0] + psql[1][0])

    def test_rerun_with_runner_file_skips_config_and_finishes_the_rest(self):
        os.makedirs(os.path.join(self.d, "app1"))
        Path(self.d, "app1", ".runner").write_text("{}")
        msg = A.add_agent("app1", "owner/example-app", "T", "main", True, self.file, self.d, self.run_)
        self.assertIn("added", msg)
        self.assertFalse([a for a, _ in self.calls if "./config.sh" in a])
        self.assertEqual(len([a for a, _ in self.calls if a[0] == "psql"]), 2)
        self.assertTrue(os.path.exists(os.path.join(self.d, "app1", "db.env")))
        self.assertEqual(json.loads(Path(self.file).read_text())["agents"][0]["slug"], "app1")

    def test_failed_database_step_names_the_step(self):
        def bad(argv, **kw):
            return R(1, "boom") if argv[0] == "psql" else R()
        with self.assertRaises(A.PoolError) as cm:
            A.add_agent("app1", "owner/example-app", "T", "main", True, self.file, self.d, bad)
        self.assertIn("database setup", str(cm.exception))
        self.assertFalse(os.path.exists(self.file) and json.loads(Path(self.file).read_text())["agents"])


class DockerCpuCapTests(unittest.TestCase):
    def test_cap_stays_below_docker_cpus(self):
        self.assertEqual(P.cap_cpus(19.0, 19), 18)
        self.assertEqual(P.cap_cpus(5.0, 2), 1)
        self.assertEqual(P.cap_cpus(3.0, 19), 3.0)

    def test_sizing_caps_at_ncpu_minus_one(self):
        self.assertEqual(P.sizing(64, 0, 32, docker_cpus=2)["cpus"], 1)
        self.assertEqual(P.sizing(64, 0, 40, docker_cpus=19)["cpus"], 18)

    def test_ncpu_comes_from_docker_then_wslconfig_then_host(self):
        class Docker(FakeProbe):
            def sh(self, argv, input=None, timeout=60):
                return (0, "19\n") if argv[:2] == ["docker", "info"] else (1, "")
        self.assertEqual(P.docker_ncpu(Docker()), 19)
        probe = FakeProbe({"C:/Users/u1/.wslconfig": "[wsl2]\nprocessors=6\n"})
        probe.sh = lambda argv, input=None, timeout=60: None
        self.assertEqual(P.docker_ncpu(probe), 6)
        bare = FakeProbe()
        bare.sh = lambda argv, input=None, timeout=60: None
        bare.cpu_count = lambda: 4
        self.assertEqual(P.docker_ncpu(bare), 4)

    def test_pool_files_cap_follows_docker(self):
        class Docker(FakeProbe):
            def sh(self, argv, input=None, timeout=60):
                return (0, "19\n") if argv[:2] == ["docker", "info"] else (0, "")
        seen = {}
        orig = P.write_pool_files
        P.write_pool_files = lambda pool, cap, runner_version=None, **k: seen.update(cap=cap) or "dest"
        try:
            ok, _ = P.Executor(Docker()).run(P._step("f", "F", "pool-files", pool="main", cap={"cpus": 19.0, "mem_gib": 40.0}))
        finally:
            P.write_pool_files = orig
        self.assertTrue(ok)
        self.assertEqual(seen["cap"]["cpus"], 18)


class RunsOnWarningTests(unittest.TestCase):
    def run_step(self, files, repo_path):
        probe = FakeProbe(files)
        return P.Executor(probe).run(P._step("v", "V", "set-variable", repo="owner/example-app", name="CI_RUNS_ON",
                                             value="[]", repo_path=repo_path))

    def test_lists_workflows_that_do_not_read_it(self):
        with tempfile.TemporaryDirectory() as d:
            wf = os.path.join(d, ".github", "workflows")
            os.makedirs(wf)
            Path(wf, "ci.yml").write_text("jobs:\n  a:\n    runs-on: ubuntu-latest\n")
            Path(wf, "e2e.yml").write_text("jobs:\n  a:\n    runs-on: ubuntu-latest\n")
            Path(wf, "cleanup.yml").write_text("jobs:\n  a:\n    runs-on: ${{ vars.CI_RUNS_ON }}\n")
            probe = P.Probe()
            ex = P.Executor(probe)
            probe.gh = lambda args, input=None: (0, "")
            ok, text = ex.run(P._step("v", "V", "set-variable", repo="owner/example-app", name="CI_RUNS_ON",
                                      value="[]", repo_path=d))
        self.assertTrue(ok)
        self.assertIn("do not read it: ci.yml, e2e.yml.", text)
        self.assertNotIn("cleanup.yml", text)
        self.assertIn("vars.CI_RUNS_ON || 'ubuntu-latest'", text)

    def test_no_local_checkout_skips_with_a_note(self):
        ok, text = self.run_step({}, None)
        self.assertTrue(ok)
        self.assertIn("not checked out here", text)


class BrowsersTests(unittest.TestCase):
    def test_chromium_goes_to_env_and_the_build(self):
        with tempfile.TemporaryDirectory() as d:
            dest = os.path.join(d, "pools", "main")
            P.write_pool_files("main", {"cpus": 2.0, "mem_gib": 6.0}, dest=dest, browsers="chromium")
            self.assertIn("POOL_BROWSERS=chromium", Path(dest, ".env").read_text())
        self.assertIn("POOL_BROWSERS: ${POOL_BROWSERS:-none}", (POOL / "compose.yaml").read_text())

    def test_default_is_none(self):
        with tempfile.TemporaryDirectory() as d:
            dest = os.path.join(d, "pools", "main")
            P.write_pool_files("main", {"cpus": 2.0, "mem_gib": 6.0}, dest=dest)
            self.assertIn("POOL_BROWSERS=none", Path(dest, ".env").read_text())
            P.write_pool_files("main", {"cpus": 2.0, "mem_gib": 6.0}, dest=dest, browsers="firefox")
            self.assertIn("POOL_BROWSERS=none", Path(dest, ".env").read_text())
        self.assertIn("ARG POOL_BROWSERS=none", (POOL / "Dockerfile").read_text())

    def test_pool_up_passes_the_build_arg(self):
        probe = FakeProbe()
        probe.read_text = lambda path: "RUNNER_VERSION=2.400.1\nPOOL_BROWSERS=chromium\n"
        seen = {}
        orig = P.subprocess.run
        P.subprocess.run = lambda argv, **k: seen.update(env=k.get("env")) or type("R", (), {"returncode": 0, "stderr": ""})()
        orig_sha = P.runner_sha
        P.runner_sha = lambda probe, version=None: "a" * 64
        try:
            ok, _ = P.Executor(probe).run({"action": "pool-up", "pool": "main"})
        finally:
            P.subprocess.run = orig
            P.runner_sha = orig_sha
        self.assertTrue(ok)
        self.assertEqual(seen["env"]["POOL_BROWSERS"], "chromium")

    def test_plan_step_text_says_what_the_image_holds(self):
        found = P.detect(FakeProbe(dict(FILES)))
        chromium = next(s for s in P.plan(found, ["owner/example-app"], browsers="chromium")["steps"] if s["id"] == "pool-files")
        self.assertIn("Chromium system libraries", chromium["title"])
        self.assertIn("300-400 MB", chromium["title"])
        plain = next(s for s in P.plan(found, ["owner/example-app"])["steps"] if s["id"] == "pool-files")
        self.assertIn("no Chromium libraries", plain["title"])

    def test_dockerfile_has_the_conditional_install_deps_line(self):
        df = (POOL / "Dockerfile").read_text()
        self.assertIn('"$POOL_BROWSERS" = "chromium"', df)
        self.assertIn("playwright@${PLAYWRIGHT_VERSION} install-deps chromium", df)
        self.assertEqual(df.count("ARG PLAYWRIGHT_VERSION="), 1)

    def test_browser_step_uses_a_checked_node_20_or_newer(self):
        """DL76: Ubuntu 24.04's apt Node is 18, too old for Playwright; the step uses a checked Node tarball."""
        import re
        df = (POOL / "Dockerfile").read_text()
        self.assertNotIn("install -y --no-install-recommends nodejs npm", df)
        major = int(re.search(r"ARG NODE_VERSION=(\d+)\.", df).group(1))
        self.assertGreaterEqual(major, 20)
        self.assertRegex(df, r"ARG NODE_SHA256=[0-9a-f]{64}")
        self.assertIn('echo "${NODE_SHA256}  /tmp/node.tar.xz" | sha256sum -c -', df)
        self.assertIn("rm -rf /opt/node-build", df)

    def test_warning_lists_workflows_that_need_root(self):
        with tempfile.TemporaryDirectory() as d:
            wf = os.path.join(d, ".github", "workflows")
            os.makedirs(wf)
            Path(wf, "e2e.yml").write_text("jobs:\n  a:\n    runs-on: ${{ vars.CI_RUNS_ON }}\n    steps:\n      - run: npx playwright install --with-deps chromium\n")
            Path(wf, "deps.yml").write_text("jobs:\n  a:\n    runs-on: ${{ vars.CI_RUNS_ON }}\n    steps:\n      - run: sudo apt-get install -y jq\n")
            Path(wf, "clean.yml").write_text("jobs:\n  a:\n    runs-on: ${{ vars.CI_RUNS_ON }}\n    steps:\n      - run: npx playwright install chromium\n")
            probe = P.Probe()
            probe.gh = lambda args, input=None: (0, "")
            ok, text = P.Executor(probe).run(P._step("v", "V", "set-variable", repo="owner/example-app", name="CI_RUNS_ON",
                                                     value="[]", repo_path=d))
        self.assertTrue(ok)
        self.assertIn("need root to install packages, which pool jobs do not have: deps.yml, e2e.yml.", text)
        self.assertNotIn("clean.yml", text)
        self.assertIn("browsers: chromium", text)


PNPM_V9 = "packages:\n\n  '@playwright/test@1.55.0':\n    resolution: {integrity: x}\n\n  playwright-core@1.55.0:\n    resolution: {integrity: y}\n\n  playwright@1.55.0:\n    resolution: {integrity: z}\n"
PNPM_V6 = "packages:\n\n  /@playwright/test@1.49.1:\n    resolution: {integrity: x}\n"
NPM_V3 = json.dumps({"lockfileVersion": 3, "packages": {"": {}, "node_modules/@playwright/test": {"version": "1.62.1"},
                                                         "node_modules/playwright-core": {"version": "9.9.9"}}})
NPM_V1 = json.dumps({"lockfileVersion": 1, "dependencies": {"@playwright/test": {"version": "1.40.0"}}})
YARN_V1 = '"@playwright/test@^1.40.0", "@playwright/test@^1.41.0":\n  version "1.41.2"\n  resolved "x"\n\nleft-pad@^1.0.0:\n  version "9.9.9"\n'
YARN_BERRY = '"@playwright/test@npm:^1.50.0":\n  version: 1.50.1\n  resolution: "@playwright/test@npm:1.50.1"\n'


class PlaywrightVersionTests(unittest.TestCase):
    def files(self, **by_path):
        return FakeProbe({path: text for path, text in by_path.items()})

    def test_each_lockfile_format(self):
        self.assertEqual(P.playwright_in_pnpm(PNPM_V9), ["1.55.0"])
        self.assertEqual(P.playwright_in_pnpm(PNPM_V6), ["1.49.1"])
        self.assertEqual(P.playwright_in_npm(NPM_V3), ["1.62.1"])
        self.assertEqual(P.playwright_in_npm(NPM_V1), ["1.40.0"])
        self.assertEqual(P.playwright_in_yarn(YARN_V1), ["1.41.2"])
        self.assertEqual(P.playwright_in_yarn(YARN_BERRY), ["1.50.1"])
        self.assertEqual(P.playwright_in_npm("not json"), [])
        self.assertEqual(P.playwright_in_pnpm(None), [])

    def test_highest_wins_across_repos_and_files(self):
        probe = self.files(**{"C:/Work/a/pnpm-lock.yaml": PNPM_V6, "C:/Work/b/yarn.lock": YARN_BERRY, "C:/Work/b/package-lock.json": NPM_V1})
        self.assertEqual(P.detect_playwright(probe, ["C:/Work/a", "C:/Work/b"]), ("1.50.1", os.path.join("C:/Work/b", "yarn.lock")))
        self.assertEqual(P.detect_playwright(self.files(**{"C:/Work/a/package-lock.json": NPM_V3, "C:/Work/b/pnpm-lock.yaml": PNPM_V9}),
                                             ["C:/Work/a", "C:/Work/b"])[0], "1.62.1")

    def test_ten_is_higher_than_nine(self):
        probe = self.files(**{"C:/Work/a/pnpm-lock.yaml": PNPM_V6.replace("1.49.1", "1.9.0"), "C:/Work/b/pnpm-lock.yaml": PNPM_V6.replace("1.49.1", "1.10.0")})
        self.assertEqual(P.detect_playwright(probe, ["C:/Work/a", "C:/Work/b"])[0], "1.10.0")

    def test_order_flag_then_detected_then_pin(self):
        probe = self.files(**{"C:/Work/a/pnpm-lock.yaml": PNPM_V9})
        self.assertEqual(P.resolve_playwright(probe, "chromium", "1.70.0", ["C:/Work/a"]), ("1.70.0", "flag"))
        version, source = P.resolve_playwright(probe, "chromium", None, ["C:/Work/a"])
        self.assertEqual(version, "1.55.0")
        self.assertTrue(source.startswith("detected from "))
        self.assertIn("pnpm-lock.yaml", source)
        self.assertEqual(P.resolve_playwright(probe, "chromium", None, []), (P.PLAYWRIGHT_VERSION, "pinned"))
        self.assertEqual(P.resolve_playwright(probe, "none", "1.70.0", ["C:/Work/a"]), (None, None))

    def test_pin_is_the_same_everywhere(self):
        self.assertEqual(P.PLAYWRIGHT_VERSION, "1.65.0")
        self.assertIn("ARG PLAYWRIGHT_VERSION=1.65.0", (POOL / "Dockerfile").read_text())
        self.assertIn("PLAYWRIGHT_VERSION: ${PLAYWRIGHT_VERSION:-1.65.0}", (POOL / "compose.yaml").read_text())

    def test_plan_step_names_version_and_source(self):
        found = P.detect(FakeProbe(dict(FILES)))
        probe = self.files(**{"C:/Work/a/pnpm-lock.yaml": PNPM_V9})
        step = lambda **k: next(s for s in P.plan(found, ["owner/example-app"], probe=probe, **k)["steps"] if s["id"] == "pool-files")
        s = step(browsers="chromium", repo_paths=["C:/Work/a"])
        self.assertEqual(s["playwright_version"], "1.55.0")
        self.assertIn("Playwright 1.55.0 (detected from", s["title"])
        s = step(browsers="chromium", repo_paths=["C:/Work/a"], playwright_version="1.60.0")
        self.assertIn("Playwright 1.60.0 (flag)", s["title"])
        s = step(browsers="chromium")
        self.assertIn("Playwright 1.65.0 (pinned)", s["title"])
        self.assertNotIn("Playwright", step()["title"])

    def test_env_and_build_arg_carry_the_version(self):
        with tempfile.TemporaryDirectory() as d:
            dest = os.path.join(d, "pools", "main")
            P.write_pool_files("main", {"cpus": 2.0, "mem_gib": 6.0}, dest=dest, browsers="chromium", playwright_version="1.55.0")
            self.assertIn("PLAYWRIGHT_VERSION=1.55.0", Path(dest, ".env").read_text())
            P.write_pool_files("main", {"cpus": 2.0, "mem_gib": 6.0}, dest=dest, playwright_version="bad")
            self.assertIn("PLAYWRIGHT_VERSION=1.65.0", Path(dest, ".env").read_text())
        probe = FakeProbe()
        probe.read_text = lambda path: "RUNNER_VERSION=2.400.1\nPOOL_BROWSERS=chromium\nPLAYWRIGHT_VERSION=1.55.0\n"
        seen = {}
        orig, orig_sha = P.subprocess.run, P.runner_sha
        P.subprocess.run = lambda argv, **k: seen.update(env=k.get("env")) or type("R", (), {"returncode": 0, "stderr": ""})()
        P.runner_sha = lambda probe, version=None: "a" * 64
        try:
            ok, _ = P.Executor(probe).run({"action": "pool-up", "pool": "main"})
        finally:
            P.subprocess.run, P.runner_sha = orig, orig_sha
        self.assertTrue(ok)
        self.assertEqual(seen["env"]["PLAYWRIGHT_VERSION"], "1.55.0")

    def test_flag_form_is_checked(self):
        for bad in ("1.62", "v1.62.1", "1.62.1-beta", ""):
            self.assertFalse(P.valid_playwright_version(bad))
        self.assertTrue(P.valid_playwright_version("1.62.1"))
        err = StringIO()
        from contextlib import redirect_stderr
        with redirect_stderr(err), redirect_stdout(StringIO()):
            rc = P.main(["plan", "--browsers", "chromium", "--playwright-version", "1.62", "--total-gib", "16", "--cpus", "8"])
        self.assertEqual(rc, 2)


class BaseImageTests(unittest.TestCase):
    """DL71: pnpm's standalone binary needs libatomic1; pool-check proves the image has it."""

    def test_dockerfile_installs_libatomic_and_common_tools(self):
        df = (POOL / "Dockerfile").read_text()
        for pkg in ("libatomic1", "xz-utils", "unzip", "zip", "jq"):
            self.assertIn(pkg, df)

    def test_pool_check_checks_libatomic(self):
        self.assertIn("libatomic.so.1", (POOL / "pool-check.yml").read_text())


def _win_found(labels=("Self-hosted", "Windows"), folder="C:/actions-runners/example-app", name="host1-example-app"):
    return {"host": {"platform": "win32", "machine_dir": "C:/ProgramData/luismc-delivery", "python": "C:/Py/python.exe"},
            "github": {"repos": [{"repo": "owner/example-app", "private": True, "error": None, "runners": [
                {"id": 3, "name": name, "os": "Windows", "status": "online", "busy": False, "labels": list(labels)}]}]},
            "services": [{"name": "actions.runner.owner-example-app.host1-app1", "kind": "windows-service", "folder": folder}],
            "folders": [{"path": folder, "agent_id": 3, "name": name, "repo": "owner/example-app"}],
            "containers": [], "wsl": {}, "pool_env": {}}


class DL74Tests(unittest.TestCase):
    def test_save_in_place_when_replace_is_busy(self):
        import errno
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "agents.json")
            Path(path).write_text("{}")
            real = os.replace

            def busy(a, b):
                raise OSError(errno.EBUSY, "Device or resource busy")
            os.replace = busy
            try:
                A.save(path, {"agents": [{"slug": "app1"}]})
            finally:
                os.replace = real
            self.assertEqual(json.loads(Path(path).read_text()), {"agents": [{"slug": "app1"}]})
            self.assertFalse(os.path.exists(path + ".tmp"))

    def test_save_other_errors_still_raise(self):
        import errno
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "agents.json")
            real = os.replace
            os.replace = lambda a, b: (_ for _ in ()).throw(OSError(errno.EACCES, "no"))
            try:
                with self.assertRaises(OSError):
                    A.save(path, {"agents": []})
            finally:
                os.replace = real

    def test_rerun_keeps_a_runner_equal_to_the_plan(self):
        pl = P.plan(_win_found(), [], ["owner/example-app"])
        ids = [s["id"] for s in pl["steps"]]
        self.assertFalse([i for i in ids if i.startswith(("remove:", "winsvc-remove:", "delete-folder:"))])
        svc = next(s for s in pl["steps"] if s["action"] == "windows-service")
        self.assertEqual(svc["state"], "already")

    def test_rerun_removes_a_stale_runner(self):
        pl = P.plan(_win_found(folder="C:/old/app1"), [], ["owner/example-app"])
        ids = [s["id"] for s in pl["steps"]]
        self.assertIn("remove:owner/example-app:host1-example-app", ids)
        self.assertIn("delete-folder:C:/old/app1", ids)
        pl = P.plan(_win_found(labels=("self-hosted", "linux")), [], ["owner/example-app"])
        self.assertIn("remove:owner/example-app:host1-example-app", [s["id"] for s in pl["steps"]])

    def test_pool_label_case_does_not_matter(self):
        f = {"github": {"repos": [{"repo": "o/r", "runners": [{"labels": ["Pool-Main"], "status": "online"}]}]}}
        self.assertTrue(P._pool_has(f, "main", "o/r"))

    def test_doctor_compares_runner_labels_case_insensitively(self):
        item = {"id": "runner:main-app1", "check": "runner", "labels": ["linux", "self-hosted"]}
        runners = {"runners": [{"name": "main-app1", "status": "online", "labels": [{"name": "Linux"}, {"name": "Self-hosted"}]}]}
        orig = S._gh_json
        S._gh_json = lambda root, args: (runners, None)
        try:
            self.assertEqual(S.check_item(None, {}, item)[0], "ok")
        finally:
            S._gh_json = orig

    def test_hook_files_are_copied_with_the_full_python_path(self):
        with tempfile.TemporaryDirectory() as d:
            pl = P.plan(_win_found(), [], ["owner/example-app"])
            step = next(s for s in pl["steps"] if s["action"] == "runner-hooks")
            self.assertTrue(step["dest"].endswith("/runner-hooks"))
            step = dict(step, dest=os.path.join(d, "runner-hooks"), python="C:/Py/python.exe")
            ok, _ = P.Executor(FakeProbe()).run(step)
            self.assertTrue(ok)
            for n in ("runner_load_gate.py", "runner_job_done.py", "load.py", "machine_slots.py"):
                self.assertTrue(os.path.isfile(os.path.join(d, "runner-hooks", n)), n)
            text = Path(d, "runner-hooks", "runner_load_gate.ps1").read_text()
            self.assertIn("C:\\Py\\python.exe", text)
            self.assertIn("runner_load_gate.py", text)
            printed = " ".join(next(s for s in pl["steps"] if s["action"] == "windows-service")["printed"])
            self.assertIn("C:/ProgramData/luismc-delivery/runner-hooks/runner_load_gate.ps1", printed)


class PoolCheckTriggerTests(unittest.TestCase):
    """DL77: pool-check runs on a push of its own file, so it can run before it reaches the default branch."""

    def test_pool_check_has_dispatch_and_own_path_push(self):
        text = (POOL / "pool-check.yml").read_text()
        self.assertIn("workflow_dispatch:", text)
        self.assertIn("push:", text)
        self.assertIn("- .github/workflows/pool-check.yml", text)


class DL79MemPerCpuTests(unittest.TestCase):
    def test_memory_limits_the_cpus(self):
        # 8 GiB pool memory, 19 CPUs wanted -> floor(8 / 1.5) = 5
        self.assertEqual(P.cap_mem_cpus(19.0, 8.0), 5)
        # 32 GiB and 8 CPUs: the CPU cap wins
        self.assertEqual(P.cap_mem_cpus(8.0, 32.0), 8)
        self.assertEqual(P.cap_mem_cpus(8.0, 1.0), 1)

    def test_sizing_applies_it_and_shows_it(self):
        r = P.sizing(32, 0, 40, docker_gib=14)
        self.assertEqual(r["cpus"], math.floor(r["mem_gib"] / P.MIN_GIB_PER_CPU))
        self.assertIn("GiB per CPU", r["cpus_text"])

    def test_env_has_cpuset_and_int(self):
        with tempfile.TemporaryDirectory() as d:
            dest = os.path.join(d, "pools", "main")
            P.write_pool_files("main", {"cpus": 5.0, "mem_gib": 8.0}, dest=dest)
            env = Path(dest, ".env").read_text()
        self.assertIn("POOL_CPUSET=0-4", env)
        self.assertIn("POOL_CPUS_INT=5", env)

    def test_compose_has_cpuset_and_hint(self):
        compose = (POOL / "compose.yaml").read_text()
        self.assertIn("cpuset: ${POOL_CPUSET:-}", compose)
        self.assertIn("CI_MAX_PARALLEL: ${POOL_CPUS_INT", compose)

    def _doctor(self, env):
        with tempfile.TemporaryDirectory() as d:
            pd = Path(d, "pools", "main")
            pd.mkdir(parents=True)
            (pd / "compose.yaml").write_text("services: {}\n")
            (pd / ".env").write_text(env)
            (pd / "agents.json").write_text(json.dumps({"agents": []}))
            res = P.doctor_checks(d, FakeProbe())
        return {c["id"].split(".")[-1]: c for c in res}["mem-per-cpu"]

    def _doctor_agents(self, env, n):
        with tempfile.TemporaryDirectory() as d:
            pd = Path(d, "pools", "main")
            pd.mkdir(parents=True)
            (pd / "compose.yaml").write_text("services: {}\n")
            (pd / ".env").write_text(env)
            agents = [{"slug": "a%d" % i, "user": "r-a%d" % i, "repo": "o/a%d" % i, "private": True} for i in range(n)]
            (pd / "agents.json").write_text(json.dumps({"agents": agents}))
            res = P.doctor_checks(d, FakeProbe())
        return {c["id"].split(".")[-1]: c for c in res}.get("mem-per-agent")

    def test_doctor_warns_under_four_gib_per_agent(self):
        c = self._doctor_agents("POOL_CPUS=4\nPOOL_MEM=8g\n", 3)
        self.assertEqual(c["status"], "warn")
        for text in ("POOL_MEM", "3 agents", "fewer agents"):
            self.assertIn(text, c["detail"])
        self.assertEqual(self._doctor_agents("POOL_CPUS=4\nPOOL_MEM=8g\n", 1)["status"], "ok")

    def test_doctor_warns_under_one_gib_per_cpu(self):
        c = self._doctor("POOL_CPUS=19.0\nPOOL_MEM=8.0g\n")
        self.assertEqual(c["status"], "warn")
        self.assertIn("8.0", c["detail"])
        self.assertIn("19.0", c["detail"])
        self.assertIn("setup", c["detail"])
        self.assertEqual(self._doctor("POOL_CPUS=4\nPOOL_MEM=8g\n")["status"], "ok")


class HookInterpreterTests(unittest.TestCase):
    """DL81: a job's setup-python must not change the python the pool hooks run."""

    def test_hooks_and_agent_tools_use_the_image_python(self):
        for name in ("hooks/job-started.sh", "hooks/job-completed.sh", "pool-add-agent", "pool-remove-agent"):
            text = (POOL / name).read_text()
            self.assertIn("exec /usr/bin/python3 ", text, name)
            self.assertNotIn("exec python3 ", text, name)
            self.assertIn("unset PYTHONHOME PYTHONPATH LD_LIBRARY_PATH", text, name)


class DL84DbEnvTests(unittest.TestCase):
    """DL84: db.env has PG values, pool-db-env loads them, --db-createdb is an opt-in."""

    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.file = os.path.join(self.d, "agents.json")
        self.sql = []

    def run_(self, argv, **kw):
        if kw.get("input"):
            self.sql.append(kw["input"])
        return R()

    def add(self, createdb=False, slug="app1"):
        A.add_agent(slug, "owner/example-app", "T", "main", True, self.file, self.d, self.run_, createdb=createdb)

    def test_db_env_has_all_keys(self):
        self.add()
        keys = [l.split("=", 1)[0] for l in Path(self.d, "app1", "db.env").read_text().splitlines()]
        self.assertEqual(keys, ["DATABASE_URL", "PGHOST", "PGPORT", "PGUSER", "PGPASSWORD", "PGDATABASE"])
        self.assertIn("PGPORT=5432", Path(self.d, "app1", "db.env").read_text())

    def test_createdb_only_with_flag(self):
        self.add(createdb=True)
        text = "\n".join(self.sql)
        self.assertIn("CREATE ROLE u_app1 LOGIN CREATEDB", text)
        self.assertIn("ALTER ROLE u_app1 LOGIN CREATEDB", text)
        self.assertTrue(json.loads(Path(self.file).read_text())["agents"][0]["createdb"])
        self.sql.clear()
        self.add(slug="app2")
        text = "\n".join(self.sql)
        self.assertNotIn("CREATEDB", text.replace("CREATE DATABASE", ""))
        self.assertNotIn("createdb", json.loads(Path(self.file).read_text())["agents"][1])

    def test_rerun_with_flag_alters_existing_role(self):
        self.add()
        self.sql.clear()
        self.add(createdb=True)
        text = "\n".join(self.sql)
        self.assertIn("ALTER ROLE u_app1 LOGIN CREATEDB", text)
        self.assertTrue(json.loads(Path(self.file).read_text())["agents"][0]["createdb"])
        self.sql.clear()
        self.add()
        text = "\n".join(self.sql)
        self.assertIn("ALTER ROLE u_app1 LOGIN CREATEDB", text)  # the stored opt-in stays; a rerun never narrows it

    def test_rerun_refreshes_old_db_env_and_keeps_password(self):
        self.add()
        env = Path(self.d, "app1", "db.env")
        env.write_text("DATABASE_URL" + "=" + "postgresql://" + "u_app1:oldpw" + "@db/db_app1" + chr(10))  # an agent added before DL84
        self.sql.clear()
        self.add()
        text = env.read_text()
        self.assertIn("PGPASSWORD=oldpw", text)
        self.assertIn("PGDATABASE=db_app1", text)
        joined = "\n".join(self.sql)
        self.assertIn("ALTER ROLE u_app1 LOGIN PASSWORD 'oldpw'", joined)
        self.assertNotIn("CREATEDB", joined.replace("CREATE DATABASE", ""))
        self.assertIn("REVOKE CONNECT ON DATABASE db_app1 FROM PUBLIC", joined)

    def test_connect_isolation(self):
        self.add()
        text = "\n".join(self.sql)
        self.assertIn("REVOKE CONNECT ON DATABASE db_app1 FROM PUBLIC", text)
        self.assertIn("GRANT CONNECT ON DATABASE db_app1 TO u_app1", text)

    def test_pool_db_env_text_and_dockerfile(self):
        text = (POOL / "pool-db-env").read_text()
        self.assertTrue(text.startswith("#!/bin/sh"))
        self.assertNotIn("python", text)
        self.assertIn("::add-mask::", text)
        self.assertIn("PGPASSWORD|DATABASE_URL", text)
        self.assertIn('"$GITHUB_ENV"', text)
        self.assertIn("-f", text)
        self.assertIn("pool-db-env", (POOL / "Dockerfile").read_text())

    def test_pool_db_env_runs(self):
        import shutil
        import subprocess
        sh = shutil.which("sh")
        if not sh:
            self.skipTest("no sh")
        home = tempfile.mkdtemp()
        genv = os.path.join(home, "gh_env")
        Path(genv).write_text("")
        script = str(POOL / "pool-db-env")
        r = subprocess.run([sh, script], env={"HOME": home, "GITHUB_ENV": genv, "PATH": "/usr/bin:/bin"},
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0)
        self.assertEqual(Path(genv).read_text(), "")
        env_text = "".join("%s=%s\n" % kv for kv in (("DATABASE_URL", "postgresql://" + "u:pw" + "@h:5432/d"),
                                                     ("PGHOST", "h"), ("PGPASSWORD", "pw")))
        Path(home, "db.env").write_text(env_text)
        r = subprocess.run([sh, script], env={"HOME": home, "GITHUB_ENV": genv, "PATH": "/usr/bin:/bin"},
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0)
        self.assertIn("::add-mask::pw", r.stdout)
        self.assertIn("::add-mask::postgresql://" + "u:pw" + "@h:5432/d", r.stdout)
        self.assertEqual(Path(genv).read_text(), env_text)


class DL87AgentTmpTests(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.file = os.path.join(self.d, "agents.json")
        self.calls = []

    def run_(self, argv, **kw):
        self.calls.append(argv)
        return R()

    def lines(self, slug="app1"):
        return Path(self.d, slug, ".env").read_text().splitlines()

    def test_add_writes_three_lines_and_creates_the_folder(self):
        A.add_agent("app1", "owner/example-app", "T", "main", True, self.file, self.d, self.run_)
        tmp = os.path.join(self.d, "app1", "tmp")
        for key in ("TMPDIR", "TMP", "TEMP"):
            self.assertIn("%s=%s" % (key, tmp), self.lines())
        self.assertTrue(os.path.isdir(tmp))
        if os.name != "nt":  # DL105: POSIX modes do not exist on Windows
            self.assertEqual(os.stat(tmp).st_mode & 0o777, 0o700)
        self.assertIn(["chown", "r-app1:r-app1", tmp], self.calls)
        self.assertIn(["chmod", "0700", tmp], self.calls)

    def test_rerun_adds_missing_lines_once(self):
        A.add_agent("app1", "owner/example-app", "T", "main", True, self.file, self.d, self.run_)
        env = Path(self.d, "app1", ".env")
        env.write_text("DELIVERY_MACHINE_DIR=/machine\nTMPDIR=/x")
        A.add_agent("app1", "owner/example-app", "T", "main", True, self.file, self.d, self.run_)
        A.add_agent("app1", "owner/example-app", "T", "main", True, self.file, self.d, self.run_)
        lines = self.lines()
        self.assertEqual(lines.count("DELIVERY_MACHINE_DIR=/machine"), 1)
        self.assertIn("TMPDIR=/x", lines)
        self.assertEqual(len([x for x in lines if x.startswith("TMP=")]), 1)
        self.assertEqual(len([x for x in lines if x.startswith("TEMP=")]), 1)


HOOKS = POOL / "hooks"


class DL87HookTests(unittest.TestCase):
    def test_both_hooks_clean_then_exec(self):
        for name in ("job-started.sh", "job-completed.sh"):
            text = (HOOKS / name).read_text()
            self.assertIn('/agents/*', text)
            self.assertIn('find /tmp -mindepth 1 -maxdepth 1 -user "$(id -u)" -exec rm -rf {} +', text)
            self.assertGreaterEqual(text.count("|| true"), 2)
            self.assertNotIn("find -L", text)
            self.assertLess(text.index("clean_tmp\n"), text.index("exec /usr/bin/python3"))
            self.assertTrue(text.rstrip().splitlines()[-1].startswith("exec /usr/bin/python3"))

    @unittest.skipUnless(__import__("shutil").which("sh"), "sh not available")
    def test_clean_function_empties_temp_folder_and_keeps_it(self):
        import re
        import subprocess
        for name in ("job-started.sh", "job-completed.sh"):
            text = (HOOKS / name).read_text()
            func = re.search(r"clean_tmp\(\) \{.*?\n\}\n", text, re.S).group(0)
            root = tempfile.mkdtemp()
            agent_tmp, fake_tmp, outside = (os.path.join(root, n) for n in ("agents_tmp", "tmp", "outside"))
            for p in (agent_tmp, fake_tmp, outside):
                os.mkdir(p)
            Path(outside, "keep").write_text("x")
            os.mkdir(os.path.join(agent_tmp, "sub"))
            Path(agent_tmp, "sub", "f").write_text("x")
            Path(agent_tmp, ".hidden").write_text("x")
            try:
                os.symlink(outside, os.path.join(agent_tmp, "link"))
            except OSError as exc:  # DL105: Windows without the symlink privilege
                self.skipTest("cannot make symlinks here: %s" % exc)
            Path(fake_tmp, "gitleaks.tmp").write_text("x")
            func = func.replace("/agents/*", root + "/*").replace("find /tmp", "find " + fake_tmp)
            r = subprocess.run(["sh", "-c", func + "\nclean_tmp\n"], env={"PATH": os.environ["PATH"], "TMPDIR": agent_tmp},
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(os.listdir(agent_tmp), [])
            self.assertEqual(os.listdir(fake_tmp), [])
            self.assertTrue(Path(outside, "keep").exists())
            # not under /agents: left alone
            Path(agent_tmp, "stay").write_text("x")
            r = subprocess.run(["sh", "-c", func + "\nclean_tmp\n"], env={"PATH": os.environ["PATH"], "TMPDIR": "/nowhere"},
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0)
            self.assertTrue(Path(agent_tmp, "stay").exists())
