"""Load guard (DL-77, DL-78, DL-79): measurement parsers per OS, cache, limits precedence, classification,
refusal message, fail-open, notices, the runner gate and the doctor's runner check."""
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from _helpers import SCRIPTS, make_root
import hooklib as H
import load as L
import load_guard as G
import runner_load_gate as R
import delivery_doctor as D

MEMINFO = "MemTotal:       32000000 kB\nMemFree:         1000000 kB\nMemAvailable:    4800000 kB\nCached: 3000000 kB\n"
STAT_A = "cpu  1000 0 1000 8000 0 0 0 0 0 0\ncpu0 1 1 1 1\n"
STAT_B = "cpu  1500 0 1500 9000 0 0 0 0 0 0\n"
VM_STAT = ("Mach Virtual Memory Statistics: (page size of 16384 bytes)\nPages free:     100000.\nPages active:   300000.\n"
           "Pages inactive:  200000.\nPages speculative: 20000.\nPages wired down: 150000.\n")
TOP = "Processes: 400\nCPU usage: 20.0% user, 10.0% sys, 70.0% idle\nCPU usage: 40.0% user, 25.0% sys, 35.0% idle\n"
PS = ("node 80.5 900000\nchrome 40.0 4000000\nvitest worker 30.0 700000\nsystemd 0.0 10000\n"
      "/usr/bin/python3 5.0 300000\n")
PWSH = '"Name","CPU","WorkingSet64"\n"chrome","50.5","4000000000"\n"node","300","900000000"\n"idle","0","8"\n'


def env(**kw):
    """Environment for a test: machine file and cache in a fresh temp folder, no fixed sample."""
    d = tempfile.mkdtemp(prefix="load-")
    base = {"DELIVERY_MACHINE_CONFIG": os.path.join(d, "machine.json"), "DELIVERY_LOAD_CACHE": os.path.join(d, "c.json")}
    base.update(kw)
    return mock.patch.dict(os.environ, base)


def call(tool, **ti):
    return {"tool_name": tool, "tool_input": ti}


class Parsers(unittest.TestCase):
    def test_linux(self):
        self.assertEqual(L.parse_meminfo(MEMINFO), 85.0)
        self.assertEqual(L.cpu_between(L.parse_proc_stat(STAT_A), L.parse_proc_stat(STAT_B)), 50.0)
        with self.assertRaises(ValueError):
            L.parse_meminfo("nothing")
        with self.assertRaises(ValueError):
            L.parse_proc_stat("intr 1 2")

    def test_macos(self):
        # 16384-byte pages, 1,000,000 pages of memory, 320,000 of them free+inactive+speculative -> 68% in use
        self.assertEqual(L.parse_vm_stat(VM_STAT, 16384 * 1000000), 68.0)
        self.assertEqual(L.parse_top_cpu(TOP), 65.0)
        with self.assertRaises(ValueError):
            L.parse_top_cpu("no cpu line")

    def test_windows_cpu_from_times(self):
        # GetSystemTimes: busy = kernel + user - idle; the pair of readings is what cpu_between sees
        self.assertEqual(L.cpu_between((100, 1000), (400, 1500)), 60.0)
        self.assertEqual(L.cpu_between((5, 5), (5, 5)), 0.0)

    def test_process_names(self):
        top = L.parse_ps(PS, 3)
        self.assertEqual(top["cpu"], ["node", "chrome", "vitest worker"])
        self.assertEqual(top["mem"][0], "chrome")
        win = L.parse_powershell_csv(PWSH, 2)
        self.assertEqual(win["cpu"], ["node", "chrome"])
        self.assertEqual(win["mem"], ["chrome", "node"])


class Cache(unittest.TestCase):
    def test_reuse_within_ttl_and_smoothing(self):
        calls = []

        def measure(cpu):
            def f():
                calls.append(cpu)
                return {"mem": 50.0, "cpu": cpu, "at": 0}
            return f
        with env():
            a = L.sample(now=1000, measure=measure(90))
            self.assertFalse(a["cached"])
            b = L.sample(now=1005, measure=measure(10))          # younger than 10 s: no new measurement
            self.assertTrue(b["cached"])
            self.assertEqual(calls, [90])
            c = L.sample(now=1020, measure=measure(30))           # older than 10 s: measured, CPU smoothed over both
            self.assertFalse(c["cached"])
            self.assertEqual(c["cpu"], 60.0)
            d = L.sample(now=1100, measure=measure(20))           # the old ones left the 30 s window
            self.assertEqual(d["cpu"], 20.0)

    def test_no_sleep_and_delta_from_saved_raw(self):
        raws = iter([(1000, 10000), (1500, 11000)])
        with env(), mock.patch.object(L.time, "sleep", side_effect=AssertionError("slept")) as sl, \
                mock.patch.object(L, "sys", mock.Mock(platform="linux")), \
                mock.patch.object(L, "_read_text", side_effect=lambda p: MEMINFO if "meminfo" in p else "x"), \
                mock.patch.object(L, "parse_proc_stat", side_effect=lambda t: next(raws)), \
                mock.patch.object(L, "_loadavg_cpu", return_value=7.0):
            a = L.sample(now=time.time())
            self.assertEqual(a["cpu"], 7.0)                       # first call: load average fallback
            b = L.sample(now=time.time() + 20)
            self.assertEqual(b["cpu"], round((7.0 + 50.0) / 2, 1))  # 500 busy of 1000 total, smoothed with the first
            sl.assert_not_called()

    def test_delta_and_fallbacks(self):
        now = time.time()
        with mock.patch.object(L, "sys", mock.Mock(platform="linux")), \
                mock.patch.object(L, "_read_text", side_effect=lambda p: MEMINFO if "meminfo" in p else STAT_B), \
                mock.patch.object(L, "_loadavg_cpu", return_value=None):
            s = L.measure_now({"raw": [1000, 10000], "at": now - 5})
            self.assertEqual(L.cpu_between((1000, 10000), tuple(s["raw"])), s["cpu"])
            old = L.measure_now({"raw": [1000, 10000], "at": now - 601})
            self.assertIsNone(old["cpu"])                          # too old and no load average: unknown
            self.assertIsNone(L.measure_now()["cpu"])
        with env(), mock.patch.object(L, "measure_now", return_value={"mem": 50.0, "cpu": None, "at": 1.0}):
            self.assertEqual(L.sample(now=1)["cpu"], 0.0)

    def test_unwritable_cache_still_works(self):
        blocker = Path(tempfile.mkdtemp(prefix="load-")) / "file"
        blocker.write_text("x")                                    # a file where the folder should be
        with env(DELIVERY_LOAD_CACHE=str(blocker / "x" / "c.json")):
            s = L.sample(now=5, measure=lambda: {"mem": 1.0, "cpu": 2.0, "at": 0})
            self.assertEqual((s["mem"], s["cpu"]), (1.0, 2.0))

    def test_default_cache_is_per_user_not_shared_temp(self):
        d = tempfile.mkdtemp(prefix="home-")
        with mock.patch.dict(os.environ, {"HOME": d, "USERPROFILE": d}):
            os.environ.pop("DELIVERY_LOAD_CACHE", None)
            os.environ.pop("DELIVERY_MACHINE_CONFIG", None)
            path = Path(L.cache_file())
            self.assertEqual(path.parent, Path(os.path.expanduser("~")) / ".claude")
            self.assertNotEqual(str(path.parent), tempfile.gettempdir())

    def test_write_leaves_no_temp_file_and_makes_folder(self):
        d = Path(tempfile.mkdtemp(prefix="load-")) / "new" / "dir"
        with env(DELIVERY_LOAD_CACHE=str(d / "c.json")):
            L.sample(now=100, measure=lambda: {"mem": 1.0, "cpu": 2.0, "at": 0})
            L.sample(now=200, measure=lambda: {"mem": 1.0, "cpu": 2.0, "at": 0})
        self.assertEqual([x.name for x in d.iterdir()], ["c.json"])

    def test_corrupt_cache_is_ignored(self):
        d = Path(tempfile.mkdtemp(prefix="load-"))
        (d / "c.json").write_text("{not json")
        with env(DELIVERY_LOAD_CACHE=str(d / "c.json")):
            s = L.sample(now=5, measure=lambda: {"mem": 1.0, "cpu": 2.0, "at": 0})
            self.assertFalse(s["cached"])
            self.assertEqual(len(json.loads((d / "c.json").read_text())["samples"]), 1)

    def test_unmeasurable_raises(self):
        def boom():
            raise OSError("no /proc")
        with env(), self.assertRaises(OSError):
            L.sample(now=1, measure=boom)


class Limits(unittest.TestCase):
    def test_precedence_project_over_machine_over_default(self):
        with env() as _:
            self.assertEqual(L.limits(), {"memory_pct": 85.0, "cpu_pct": 60.0})
            Path(os.environ["DELIVERY_MACHINE_CONFIG"]).write_text(json.dumps({"load_limits": {"memory_pct": 80, "cpu_pct": 50}}))
            self.assertEqual(L.limits(), {"memory_pct": 80.0, "cpu_pct": 50.0})
            self.assertEqual(L.limits({"load_limits": {"cpu_pct": 70}}), {"memory_pct": 80.0, "cpu_pct": 70.0})
            self.assertEqual(L.limits({"load_limits": {"memory_pct": 0, "cpu_pct": "x"}}),
                             {"memory_pct": 80.0, "cpu_pct": 50.0})        # invalid values fall through

    def test_over_names_the_numbers(self):
        lim = {"memory_pct": 85.0, "cpu_pct": 60.0}
        self.assertEqual(L.over({"mem": 85, "cpu": 60}, lim), [])
        self.assertEqual(L.over({"mem": 91.5, "cpu": 61}, lim), ["memory 91.5% > 85%", "CPU 61% > 60%"])


HEAVY = [
    ("Bash", "pnpm test"), ("Bash", "pnpm --filter web test"), ("Bash", "pnpm check:branch"), ("Bash", "npm run build"),
    ("Bash", "yarn e2e"), ("Bash", "pnpm exec vitest run"), ("Bash", "npx playwright test"), ("Bash", "vitest"),
    ("Bash", "jest --ci"), ("Bash", "python -m pytest -q"), ("Bash", "pytest tests/"), ("Bash", "turbo run build"),
    ("Bash", "tsc -b"), ("Bash", "cargo build --release"), ("Bash", "dotnet build"), ("Bash", "msbuild app.sln"),
    ("Bash", "docker compose up -d"), ("Bash", "docker-compose build"), ("Bash", "docker build ."),
    ("Bash", "ffmpeg -i a.mov b.mp4"), ("Bash", "pnpm install"), ("Bash", "npm ci"), ("Bash", "cd app && pnpm build"),
    ("Bash", "rtk pnpm test"), ("PowerShell", "pnpm check:branch; echo done"), ("Bash", "sleep 600 &"),
    ("Bash", "node server.js", ), ("Agent", None), ("Workflow", None),
]
LIGHT_CALLS = [
    ("Bash", "git status"), ("Bash", "gh pr view 3"), ("Bash", "ls -la"), ("Bash", "cat README.md"),
    ("Bash", "grep -rn foo ."), ("Bash", "rtk read file.ts"), ("Bash", "python3 -c 'print(1)'"),
    ("Bash", "pnpm install --offline"), ("Bash", "git commit -m 'pnpm test and vitest'"), ("Bash", "echo vitest"),
    ("Bash", "pnpm lint"), ("Bash", "tail -f log &"), ("PowerShell", "Get-ChildItem"),
]


class Classify(unittest.TestCase):
    def test_heavy(self):
        for tool, cmd in HEAVY:
            ti = {"command": cmd} if cmd else {}
            if cmd == "node server.js":
                ti["run_in_background"] = True
            with self.subTest(cmd=cmd or tool):
                self.assertTrue(G.classify(tool, ti)[0])

    def test_light(self):
        for tool, cmd in LIGHT_CALLS:
            with self.subTest(cmd=cmd):
                self.assertFalse(G.classify(tool, {"command": cmd})[0])

    def test_cloud_launches_are_never_heavy(self):
        self.assertFalse(G.classify("Agent", {"isolation": "remote"})[0])
        self.assertFalse(G.classify("Agent", {"isolation": "cloud"})[0])
        self.assertFalse(G.classify("RemoteTrigger", {"action": "run"})[0])
        self.assertTrue(G.classify("Agent", {"isolation": "worktree"})[0])

    def test_configured_heavy_commands(self):
        cfg = {"heavy_commands": [r"make\s+all", "pnpm test:full", "("]}
        self.assertTrue(G.classify("Bash", {"command": "make   all"}, cfg)[0])
        self.assertTrue(G.classify("Bash", {"command": "echo x; mytool pnpm test:full"}, cfg)[0])
        self.assertFalse(G.classify("Bash", {"command": "make clean"}, cfg)[0])

    def test_background_light_command_is_not_heavy(self):
        self.assertFalse(G.classify("Bash", {"command": "git fetch", "run_in_background": True})[0])
        self.assertTrue(G.classify("Bash", {"command": "python3 build_all.py", "run_in_background": True})[0])


class Refusal(unittest.TestCase):
    def test_over_limit_refuses_with_numbers_limits_processes_and_advice(self):
        ps = Path(tempfile.mkdtemp()) / "ps.txt"
        ps.write_text(PS)
        with env(DELIVERY_LOAD="91,20", DELIVERY_PS=str(ps)):
            msg = G.check_call(call("Bash", command="pnpm test"), {})
        self.assertIn("memory 91% > 85%", msg)
        self.assertIn("memory 91% (limit 85%), CPU 20% (limit 60%)", msg)
        self.assertIn("CPU: node, chrome", msg)
        self.assertIn("wait", msg)
        self.assertIn("nothing is killed", msg)

    def test_under_limit_and_light_pass(self):
        with env(DELIVERY_LOAD="50,20"):
            self.assertIsNone(G.check_call(call("Bash", command="pnpm test"), {}))
        with env(DELIVERY_LOAD="99,99"):
            self.assertIsNone(G.check_call(call("Bash", command="git status"), {}))
            self.assertIsNone(G.check_call(call("Agent", isolation="remote"), {}))
            self.assertIsNone(G.check_call(call("RemoteTrigger", action="run"), {}))

    def test_project_limits_and_checks_off(self):
        with env(DELIVERY_LOAD="70,70"):
            self.assertIsNone(G.check_call(call("Bash", command="vitest"), {"load_limits": {"cpu_pct": 80}}))
            self.assertIsNotNone(G.check_call(call("Bash", command="vitest"), {"load_limits": {"memory_pct": 60}}))
            self.assertIsNone(G.check_call(call("Bash", command="vitest"), {"checks_off": ["DL-77"]}))

    def test_fail_open_when_unmeasurable(self):
        with env(), mock.patch.object(L, "measure_now", side_effect=OSError("no /proc")), \
                mock.patch.object(H, "warn") as w:
            self.assertIsNone(G.check_call(call("Bash", command="pnpm test"), {}))
            self.assertTrue(w.called)

    def test_notice_text(self):
        with env(DELIVERY_LOAD="50,20"):
            self.assertIsNone(G.notice({}))
        with env(DELIVERY_LOAD="50,75"):
            n = G.notice({})
        self.assertIn("CPU 75% > 60%", n)
        self.assertIn("Hold new heavy work", n)


def run_hook(script, data, **extra):
    d = tempfile.mkdtemp(prefix="hk-")
    e = dict(os.environ, DELIVERY_MACHINE_CONFIG=os.path.join(d, "m.json"), DELIVERY_LOAD_CACHE=os.path.join(d, "c.json"))
    e.update(extra)
    p = subprocess.run([sys.executable, "-I", str(SCRIPTS / script)], input=json.dumps(data).encode(),
                       capture_output=True, env=e, timeout=60)
    return p.returncode, p.stdout.decode().strip(), p.stderr.decode().strip()


class Hooks(unittest.TestCase):
    def test_pre_tool_exit_2_without_delivery_folder(self):
        bare = tempfile.mkdtemp(prefix="bare-")
        rc, out, err = run_hook("hook_pre_tool.py", {"tool_name": "Bash", "cwd": bare, "tool_input": {"command": "pnpm test"}},
                                DELIVERY_LOAD="95,10")
        self.assertEqual(rc, 2)
        self.assertIn("DL-77", err)
        self.assertEqual(out, "")

    def test_pre_tool_allows_light_and_under_limit(self):
        bare = tempfile.mkdtemp(prefix="bare-")
        self.assertEqual(run_hook("hook_pre_tool.py", {"tool_name": "Bash", "cwd": bare, "tool_input": {"command": "git status"}},
                                  DELIVERY_LOAD="95,95")[0], 0)
        self.assertEqual(run_hook("hook_pre_tool.py", {"tool_name": "PowerShell", "cwd": bare, "tool_input": {"command": "pnpm test"}},
                                  DELIVERY_LOAD="10,10")[0], 0)

    def test_pre_tool_project_warn_mode_allows(self):
        root = make_root({"enforcement": {"mode": "warn"}})
        rc, out, err = run_hook("hook_pre_tool.py", {"tool_name": "Bash", "cwd": str(root), "tool_input": {"command": "vitest"}},
                                DELIVERY_LOAD="95,10")
        self.assertEqual(rc, 0)
        self.assertIn("warn mode", json.loads(out)["systemMessage"])

    def test_pre_tool_project_limit_override(self):
        root = make_root({"load_limits": {"memory_pct": 99}})
        rc, _, _ = run_hook("hook_pre_tool.py", {"tool_name": "Bash", "cwd": str(root), "tool_input": {"command": "vitest"}},
                            DELIVERY_LOAD="95,10")
        self.assertEqual(rc, 0)

    def test_session_start_and_stop_notice(self):
        root = make_root()
        rc, out, _ = run_hook("hook_session_start.py", {"cwd": str(root), "session_id": "s"}, DELIVERY_LOAD="50,80")
        j = json.loads(out)
        self.assertIn("DL-78", j["hookSpecificOutput"]["additionalContext"])
        rc, out, _ = run_hook("hook_stop.py", {"cwd": str(root), "session_id": "s"}, DELIVERY_LOAD="50,80")
        self.assertIn("CPU 80% > 60%", json.loads(out)["systemMessage"])
        rc, out, _ = run_hook("hook_stop.py", {"cwd": str(root), "session_id": "s"}, DELIVERY_LOAD="50,10")
        self.assertNotIn("DL-78", out)

    def test_notice_without_delivery_folder(self):
        bare = tempfile.mkdtemp(prefix="bare-")
        rc, out, _ = run_hook("hook_stop.py", {"cwd": bare}, DELIVERY_LOAD="95,10")
        self.assertIn("memory 95%", json.loads(out)["systemMessage"])

    def test_hooks_json_covers_new_tools(self):
        hooks = json.loads((SCRIPTS.parent / "hooks" / "hooks.json").read_text())
        pre = hooks["hooks"]["PreToolUse"][0]["matcher"].split("|")
        for t in ("Bash", "PowerShell", "Agent", "Workflow", "RemoteTrigger", "AskUserQuestion", "Write"):
            self.assertIn(t, pre)
        self.assertIn("with or without .delivery/", hooks["description"])


class Gate(unittest.TestCase):
    LIM = {"memory_pct": 85.0, "cpu_pct": 60.0}

    def drive(self, loads, cfg=None):
        """Run wait() over a scripted series of (mem, cpu) samples on a fake clock."""
        t = [0.0]
        it = iter(loads)
        logs = []

        def sample():
            m, c = next(it)
            return {"mem": m, "cpu": c}

        def sleep(sec):
            t[0] += sec
        rc = R.wait(self.LIM, dict(R.DEFAULTS, **(cfg or {})), sample=sample, sleep=sleep, clock=lambda: t[0], log=logs.append)
        return rc, logs, t[0]

    def test_passes_at_once_when_under(self):
        rc, logs, waited = self.drive([(50, 10)])
        self.assertEqual((rc, waited), (0, 0))
        self.assertIn("under the limits", logs[0])

    def test_waits_then_passes_and_logs_what_it_waited_for(self):
        rc, logs, waited = self.drive([(90, 10), (90, 80), (50, 10)])
        self.assertEqual(rc, 0)
        self.assertEqual(waited, 30)
        self.assertIn("holding the job", logs[0])
        self.assertIn("waited for CPU, memory", logs[-1])

    def test_times_out_with_clear_log(self):
        rc, logs, _ = self.drive([(90, 10)] * 50, {"max_wait_min": 1.0})
        self.assertEqual(rc, 1)
        self.assertIn("TIMED OUT", logs[-1])
        self.assertIn("memory 90% > 85%", logs[-1])

    def test_timeout_run_mode_lets_job_go(self):
        rc, logs, _ = self.drive([(90, 10)] * 50, {"max_wait_min": 1.0, "on_timeout": "run"})
        self.assertEqual(rc, 0)
        self.assertIn("starting the job anyway", logs[-1])

    def test_unmeasurable_fails_open(self):
        def boom():
            raise OSError("nope")
        logs = []
        self.assertEqual(R.wait(self.LIM, R.DEFAULTS, sample=boom, log=logs.append), 0)
        self.assertIn("cannot measure", logs[0])

    def test_settings_precedence(self):
        with env():
            Path(os.environ["DELIVERY_MACHINE_CONFIG"]).write_text(json.dumps({"runner_gate": {"max_wait_min": 5, "poll_sec": 3}}))
            self.assertEqual(R.settings()["max_wait_min"], 5.0)
            with mock.patch.dict(os.environ, {"DELIVERY_GATE_MAX_WAIT_MIN": "7"}):
                self.assertEqual(R.settings()["max_wait_min"], 7.0)
            self.assertEqual(R.settings()["poll_sec"], 3.0)
        with env():
            self.assertEqual((R.settings()["max_wait_min"], R.settings()["poll_sec"]), (30.0, 15.0))

    def test_script_end_to_end(self):
        d = tempfile.mkdtemp()
        e = dict(os.environ, DELIVERY_LOAD="10,10", DELIVERY_GATE_LOG=os.path.join(d, "g.log"),
                 DELIVERY_MACHINE_CONFIG=os.path.join(d, "m.json"))
        p = subprocess.run([sys.executable, "-I", str(SCRIPTS / "runner_load_gate.py")], capture_output=True, env=e, timeout=60)
        self.assertEqual(p.returncode, 0)
        self.assertIn("under the limits", Path(d, "g.log").read_text())
        e["DELIVERY_LOAD"] = "99,10"
        e["DELIVERY_GATE_POLL_SEC"] = "0"
        p = subprocess.run([sys.executable, "-I", str(SCRIPTS / "runner_load_gate.py"), "--max-wait-min", "0"],
                           capture_output=True, env=e, timeout=60)
        self.assertEqual(p.returncode, 1)
        self.assertIn("TIMED OUT", Path(d, "g.log").read_text())


class DoctorRunner(unittest.TestCase):
    def fake_runner(self, hook=None):
        d = Path(tempfile.mkdtemp(prefix="actions-runner-"))
        (d / ".runner").write_text("{}")
        if hook:
            (d / ".env").write_text("FOO=1\nACTIONS_RUNNER_HOOK_JOB_STARTED=%s\n" % hook)
        return d

    def test_no_runner_is_ok(self):
        with env(DELIVERY_RUNNER_DIRS=tempfile.mkdtemp()), mock.patch.dict(os.environ):
            os.environ.pop("ACTIONS_RUNNER_HOOK_JOB_STARTED", None)
            ok, detail = D.check_runner(None, {})
        self.assertTrue(ok)
        self.assertIn("no self-hosted runner", detail)

    def test_runner_without_hook_fails_with_fix(self):
        d = self.fake_runner()
        with env(DELIVERY_RUNNER_DIRS=str(d)), mock.patch.dict(os.environ):
            os.environ.pop("ACTIONS_RUNNER_HOOK_JOB_STARTED", None)
            ok, detail = D.check_runner(None, {})
        self.assertFalse(ok)
        self.assertIn("CI runner gate", detail)

    def test_runner_with_hook_ok(self):
        d = self.fake_runner("/opt/plugin/scripts/runner_load_gate.sh")
        with env(DELIVERY_RUNNER_DIRS=str(d)), mock.patch.dict(os.environ):
            os.environ.pop("ACTIONS_RUNNER_HOOK_JOB_STARTED", None)
            self.assertTrue(D.check_runner(None, {})[0])

    def test_env_var_set(self):
        with env(DELIVERY_RUNNER_DIRS=tempfile.mkdtemp(), ACTIONS_RUNNER_HOOK_JOB_STARTED="/x/runner_load_gate.sh"):
            self.assertTrue(D.check_runner(None, {})[0])
        with env(DELIVERY_RUNNER_DIRS=tempfile.mkdtemp(), ACTIONS_RUNNER_HOOK_JOB_STARTED="/x/other.sh"):
            self.assertFalse(D.check_runner(None, {})[0])


class Schema(unittest.TestCase):
    def test_config_with_load_limits_validates(self):
        import delivery_config as C
        e, _ = C.validate_config({"load_limits": {"memory_pct": 80, "cpu_pct": 50}, "heavy_commands": ["make all"]})
        self.assertEqual(e, [])
        e, _ = C.validate_config({"load_limits": {"cpu_pct": "x"}})
        self.assertTrue(e)


if __name__ == "__main__":
    unittest.main()
