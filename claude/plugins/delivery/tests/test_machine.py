"""DL32 (DL-79, DL-90, DL-91): machine config, CI slots, queue, slot log, the gate, the job-done hook, host load and
the local heavy limit. Every test uses its own machine folder; nothing touches the real one."""
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
import delivery_ci as CI
import delivery_config as C
import delivery_doctor as D
import hooklib as H
import load as L
import load_guard as G
import machine_slots as MS
import runner_job_done as RJD
import runner_load_gate as R


def machine(**kw):
    """A fresh machine folder in the environment; returns the patcher (use as a context manager)."""
    d = tempfile.mkdtemp(prefix="mach-")
    base = {"DELIVERY_MACHINE_DIR": d, "DELIVERY_LOCAL_HEAVY_DIR": os.path.join(d, "heavy"),
            "DELIVERY_MACHINE_CONFIG": os.path.join(d, "old.json"), "DELIVERY_LOAD_CACHE": os.path.join(d, "c.json"),
            "DELIVERY_IN_CONTAINER": "0", "DELIVERY_HOLDER_PID": str(os.getpid())}
    base.update(kw)
    for k in ("GITHUB_EVENT_PATH", "GITHUB_REF", "GITHUB_REPOSITORY", "GITHUB_RUN_ID", "GITHUB_JOB", "DELIVERY_SHARD",
              "GITHUB_WORKSPACE", "GITHUB_SHA", "DELIVERY_LOAD"):
        base.setdefault(k, "")
    return mock.patch.dict(os.environ, base)


def ident(job="unit", run=1, repo="owner/example-app", **kw):
    return dict({"repo": repo, "run_id": run, "run_attempt": 1, "job": job, "shard": "", "runner": "host1-pool-app1"}, **kw)


def dead_pid():
    p = subprocess.Popen([sys.executable, "-c", "pass"])
    p.wait()
    return p.pid


class Config(unittest.TestCase):
    def test_machine_dir_env_programdata_and_posix(self):
        with mock.patch.dict(os.environ, {"DELIVERY_MACHINE_DIR": "/x/machine"}):
            self.assertEqual(MS.machine_dir(), "/x/machine")
        env = {k: v for k, v in os.environ.items() if k != "DELIVERY_MACHINE_DIR"}
        env["PROGRAMDATA"] = "C:/ProgramData"
        with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(sys, "platform", "win32"):
            self.assertEqual(MS.machine_dir(), os.path.join("C:/ProgramData", "luismc-delivery"))
        with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(sys, "platform", "linux"):
            self.assertEqual(MS.machine_dir(), "/etc/luismc-delivery")

    def test_defaults_roundtrip_and_bad_values(self):
        with machine():
            self.assertEqual(MS.machine_config(), MS.DEFAULT_CONFIG)
            written = MS.write_machine_config({"ci_slots": 3, "load_limits": {"cpu_pct": 50}, "runner_dirs": ["C:/Work/r1"],
                                               "runner_gate": {"max_wait_min": 5}})
            got = MS.machine_config()
            self.assertEqual(got, written)
            self.assertEqual((got["ci_slots"], got["load_limits"], got["runner_dirs"]), (3, {"memory_pct": 85, "cpu_pct": 50}, ["C:/Work/r1"]))
            self.assertEqual(got["runner_gate"], {"max_wait_min": 5, "poll_sec": 15})
            self.assertTrue(os.path.isdir(MS.slots_dir()) and os.path.isdir(MS.queue_dir()))
            Path(MS.config_path()).write_text(json.dumps({"ci_slots": 0, "local_heavy": "x", "slot_stale_min": True,
                                                          "load_limits": {"memory_pct": 500}}))
            self.assertEqual(MS.machine_config(), MS.DEFAULT_CONFIG)
            Path(MS.config_path()).write_text("not json")
            self.assertEqual(MS.machine_config(), MS.DEFAULT_CONFIG)

    def test_write_refuses_unknown_keys(self):
        with machine():
            with self.assertRaises(ValueError):
                MS.write_machine_config({"ci_slotz": 2})
            with self.assertRaises(ValueError):
                MS.write_machine_config([])


class Slots(unittest.TestCase):
    def test_take_until_full_free_and_take_again(self):
        with machine():
            cfg = MS.machine_config()
            a, b = MS.take_slot(ident("a"), cfg), MS.take_slot(ident("b"), cfg)
            self.assertEqual(sorted([a["slot"], b["slot"]]), [1, 2])
            self.assertIsNone(MS.take_slot(ident("c"), cfg))
            self.assertEqual(MS.free_count(cfg), 0)
            self.assertTrue(MS.free_slot(a))
            self.assertFalse(MS.free_slot(a))                       # a second free does nothing
            c = MS.take_slot(ident("c"), cfg)
            self.assertEqual(c["slot"], a["slot"])

    def test_free_with_a_wrong_token_keeps_the_lock(self):
        with machine():
            a = MS.take_slot(ident("a"))
            self.assertFalse(MS.free_slot(dict(a, token="not-mine")))
            self.assertEqual(MS.free_count(), 1)                     # one of two slots still free, a still held
            self.assertEqual(MS.read_slots()[a["slot"] - 1]["holder"]["token"], a["token"])

    def test_race_two_processes_never_share_one_slot(self):
        """Two processes take and free one slot 500 times each; a create-new marker inside the slot proves no overlap."""
        with machine() as _:
            MS.write_machine_config({"ci_slots": 1})
            inside = os.path.join(MS.machine_dir(), "inside")
            code = (
                "import os, sys, time\n"
                "sys.path.insert(0, %r)\n"
                "import machine_slots as MS\n"
                "bad = got = 0\n"
                "for i in range(500):\n"
                "    lock = MS.take_slot({'repo': 'o/r', 'run_id': os.getpid(), 'run_attempt': 1, 'job': 'j', 'shard': '', 'runner': 'r'})\n"
                "    if lock is None:\n"
                "        continue\n"
                "    got += 1\n"
                "    try:\n"
                "        fd = os.open(%r, os.O_CREAT | os.O_EXCL | os.O_WRONLY); os.close(fd)\n"
                "    except FileExistsError:\n"
                "        bad += 1\n"
                "    else:\n"
                "        os.unlink(%r)\n"
                "    MS.free_slot(lock)\n"
                "print(got, bad)\n" % (str(SCRIPTS), inside, inside))
            procs = [subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE, text=True) for _ in range(2)]
            results = [p.communicate(timeout=240)[0].split() for p in procs]
            for p in procs:
                self.assertEqual(p.returncode, 0)
            self.assertEqual([r[1] for r in results], ["0", "0"], "two processes held the one slot at once")
            self.assertGreater(sum(int(r[0]) for r in results), 100)
            self.assertEqual(MS.free_count(), 1)
            lines = MS.read_log()
            self.assertEqual(sum(1 for l in lines if "released_at" in l), sum(int(r[0]) for r in results))

    def test_dead_holder_is_freed_at_once_and_logged(self):
        with machine():
            lock = MS.take_slot(ident("a"))
            rec = json.loads(Path(MS.slot_path(lock["slot"])).read_text())
            rec["pid"] = dead_pid()
            Path(MS.slot_path(lock["slot"])).write_text(json.dumps(rec))
            freed = MS.free_stale()
            self.assertEqual([f["slot"] for f in freed], [lock["slot"]])
            self.assertIn("gone", freed[0]["reason"])
            self.assertEqual(MS.free_count(), 2)
            last = MS.read_log()[-1]
            self.assertEqual((last["outcome"], last["job"], last["slot"]), ("stale-freed", "a", lock["slot"]))

    def test_live_holder_and_other_host_stay_old_slot_is_freed(self):
        with machine():
            MS.write_machine_config({"slot_stale_min": 10})
            live = MS.take_slot(ident("live"))
            foreign = MS.take_slot(ident("foreign"))
            rec = json.loads(Path(MS.slot_path(foreign["slot"])).read_text())
            rec.update(pid=dead_pid(), host="another-host")
            Path(MS.slot_path(foreign["slot"])).write_text(json.dumps(rec))
            self.assertEqual(MS.free_stale(), [])                     # live process; a dead pid on another host is not judged
            now = time.time() + 11 * 60
            freed = MS.free_stale(now=now)
            self.assertEqual(sorted(f["slot"] for f in freed), [1, 2])
            self.assertTrue(all("older than 10 min" in f["reason"] for f in freed))
            self.assertIsNotNone(live)

    def test_unreadable_lock_is_only_freed_by_age(self):
        with machine():
            os.makedirs(MS.slots_dir(), exist_ok=True)
            Path(MS.slot_path(1)).write_text("")
            self.assertEqual(MS.free_stale(), [])                     # new and unreadable: no judgement yet
            old = time.time() - 3 * 3600
            os.utime(MS.slot_path(1), (old, old))
            freed = MS.free_stale()
            self.assertEqual([f["slot"] for f in freed], [1])
            self.assertEqual(MS.read_log()[-1]["outcome"], "stale-freed")

    def test_find_held_matches_the_job(self):
        with machine():
            a = MS.take_slot(ident("a", run=5))
            MS.take_slot(ident("a", run=6))
            held = MS.find_held(ident("a", run=5))
            self.assertEqual([h["slot"] for h in held], [a["slot"]])
            self.assertEqual(MS.find_held(ident("other", run=5)), [])


class Queue(unittest.TestCase):
    def event(self, payload, ref="refs/heads/feature", name="push"):
        p = tempfile.mkdtemp(prefix="ev-")
        path = os.path.join(p, "event.json")
        Path(path).write_text(json.dumps(payload))
        return {"GITHUB_EVENT_PATH": path, "GITHUB_REF": ref, "GITHUB_EVENT_NAME": name}

    def test_priority_from_the_event_file(self):
        self.assertEqual(MS.priority_from_event(self.event({"pull_request": {"draft": False}}, "refs/pull/1/merge", "pull_request")), 0)
        self.assertEqual(MS.priority_from_event(self.event({"pull_request": {"draft": True}}, "refs/pull/1/merge", "pull_request")), 1)
        repo = {"repository": {"default_branch": "main"}}
        self.assertEqual(MS.priority_from_event(self.event(repo, "refs/heads/main")), 0)
        self.assertEqual(MS.priority_from_event(self.event(repo, "refs/heads/claude/DL1-x")), 1)
        self.assertEqual(MS.priority_from_event({}), 1)
        self.assertEqual(MS.priority_from_event({"GITHUB_EVENT_PATH": "/no/such/file"}), 1)

    def test_order_ready_pr_and_default_branch_first_then_first_come(self):
        with machine():
            t1 = MS.enqueue(ident("branch1"), priority=1, now=1000.0)
            t2 = MS.enqueue(ident("branch2"), priority=1, now=1001.0)
            t3 = MS.enqueue(ident("ready-pr"), priority=0, now=1002.0)
            t4 = MS.enqueue(ident("main-run"), priority=0, now=1003.0)
            order = [t["job"] for t in MS.queue_list(now=1010.0)]
            self.assertEqual(order, ["ready-pr", "main-run", "branch1", "branch2"])
            self.assertTrue(MS.is_first(t3, now=1010.0))
            self.assertFalse(MS.is_first(t1, now=1010.0))
            MS.dequeue(t3)
            MS.dequeue(t4)
            self.assertTrue(MS.is_first(t1, now=1010.0))
            self.assertIsNotNone(t2)

    def test_dead_gate_and_old_tickets_are_dropped(self):
        with machine():
            MS.write_machine_config({"slot_stale_min": 10})
            live = MS.enqueue(ident("live"), priority=1)
            dead = MS.enqueue(ident("dead"), priority=1)
            p = os.path.join(MS.queue_dir(), dead["file"])
            rec = json.loads(Path(p).read_text())
            rec["gate_pid"] = dead_pid()
            Path(p).write_text(json.dumps(rec))
            self.assertEqual([t["job"] for t in MS.queue_list()], ["live"])
            self.assertFalse(os.path.exists(p))
            self.assertEqual(MS.queue_list(now=time.time() + 11 * 60), [])
            self.assertIsNotNone(live)


class SlotLog(unittest.TestCase):
    def test_log_lines_and_trim(self):
        with machine():
            lock = MS.take_slot(ident("a", shard="unit-1"), queued_ts=time.time() - 30)
            MS.free_slot(lock)
            first, second = MS.read_log()
            for key in ("repo", "run_id", "run_attempt", "job", "shard", "runner"):
                self.assertIn(key, first)
            self.assertIn("queued_at", first)
            self.assertIn("slot_at", first)
            self.assertNotIn("released_at", first)
            self.assertEqual((second["outcome"], second["slot"], second["job"]), ("ran", lock["slot"], "a"))
            self.assertIn("released_at", second)
            self.assertEqual(MS.LOG_MAX_LINES, 5000)
            for i in range(60):
                MS.write_log({"n": i}, max_lines=50)
            lines = MS.read_log()
            self.assertEqual(len(lines), 50)
            self.assertEqual(lines[-1]["n"], 59)
            self.assertEqual(lines[0]["n"], 10)


class Gate(unittest.TestCase):
    CFG = {"max_wait_min": 1, "poll_sec": 10, "on_timeout": "fail"}
    LIM = {"memory_pct": 85.0, "cpu_pct": 60.0}

    class Clock:
        def __init__(self):
            self.t = 0.0

        def __call__(self):
            return self.t

        def sleep(self, s):
            self.t += s

    class FakeMarker:
        def __init__(self, lost=False):
            self.started = self.stopped = 0
            self.on = False
            self.lost = lost

        def start(self):
            self.started += 1
            self.on = True

        def stop(self):
            if self.on:
                self.stopped += 1
            self.on = False

        def claim_lost(self):
            return self.lost

    def run_gate(self, sample, marker=None, cfg=None, **kw):
        clock = self.Clock()
        lines = []
        marker = marker or self.FakeMarker()
        code, lock = R.queue_wait(self.LIM, cfg or self.CFG, ident("unit", shard="unit-1"), sample=sample, sleep=clock.sleep,
                                  clock=clock, log=lines.append, marker=marker, priority=1, **kw)
        return code, lock, lines, marker

    def test_free_slot_and_quiet_machine_goes_at_once(self):
        with machine():
            code, lock, lines, marker = self.run_gate(lambda: {"mem": 50, "cpu": 10})
            self.assertEqual((code, lock["slot"]), (0, 1))
            self.assertEqual(marker.started, 0)                       # never waited: no wait marker
            self.assertEqual(MS.queue_list(), [])                      # ticket removed
            self.assertEqual(MS.free_count(), 1)

    def test_waits_for_load_then_goes_and_keeps_the_wait_marker_while_waiting(self):
        with machine():
            seq = iter([{"mem": 95, "cpu": 10}, {"mem": 95, "cpu": 10}, {"mem": 50, "cpu": 10}])
            code, lock, lines, marker = self.run_gate(lambda: next(seq))
            self.assertEqual(code, 0)
            self.assertEqual((marker.started, marker.stopped), (1, 1))
            self.assertTrue(any("holding the job" in l and "memory 95% > 85%" in l for l in lines))

    def test_all_slots_busy_times_out_with_exit_1_and_removes_ticket_and_marker(self):
        with machine():
            cfg = MS.machine_config()
            MS.take_slot(ident("a"), cfg)
            MS.take_slot(ident("b"), cfg)
            code, lock, lines, marker = self.run_gate(lambda: {"mem": 10, "cpu": 10})
            self.assertEqual((code, lock), (1, None))
            self.assertTrue(any("no free slot" in l for l in lines))
            self.assertTrue(any("TIMED OUT" in l for l in lines))
            self.assertEqual(MS.queue_list(), [])
            self.assertEqual((marker.started, marker.stopped), (1, 1))

    def test_on_timeout_run_goes_without_a_slot(self):
        with machine():
            MS.take_slot(ident("a")), MS.take_slot(ident("b"))
            code, lock, _, _ = self.run_gate(lambda: {"mem": 10, "cpu": 10}, cfg=dict(self.CFG, on_timeout="run"))
            self.assertEqual((code, lock), (0, None))

    def test_a_ticket_ahead_holds_this_job_even_with_a_free_slot(self):
        with machine():
            MS.enqueue(ident("ahead"), priority=0)                     # a live gate (this process) is first
            code, lock, lines, _ = self.run_gate(lambda: {"mem": 10, "cpu": 10})
            self.assertEqual(code, 1)
            self.assertTrue(any("1 ahead in the queue" in l for l in lines))
            self.assertEqual(MS.free_count(), 2)

    def test_a_stale_slot_is_freed_while_waiting(self):
        with machine():
            cfg = MS.machine_config()
            a = MS.take_slot(ident("a"), cfg)
            MS.take_slot(ident("b"), cfg)
            rec = json.loads(Path(MS.slot_path(a["slot"])).read_text())
            rec["pid"] = dead_pid()
            Path(MS.slot_path(a["slot"])).write_text(json.dumps(rec))
            code, lock, lines, _ = self.run_gate(lambda: {"mem": 10, "cpu": 10})
            self.assertEqual((code, lock["slot"]), (0, a["slot"]))
            self.assertTrue(any("freed slot" in l and "holder process gone" in l for l in lines))

    def test_claim_lost_exits_3_and_frees_the_slot(self):
        with machine():
            code, lock, lines, marker = self.run_gate(lambda: {"mem": 10, "cpu": 10}, marker=self.FakeMarker(lost=True))
            self.assertEqual((code, lock), (3, None))
            self.assertEqual(MS.free_count(), 2)
            self.assertEqual(MS.read_log()[-1]["outcome"], "claim-lost")
            self.assertTrue(any("claim lost" in l for l in lines))

    def test_unmeasurable_load_does_not_hold_the_job(self):
        with machine():
            def boom():
                raise OSError("no /proc")
            code, lock, lines, _ = self.run_gate(boom)
            self.assertEqual(code, 0)
            self.assertTrue(any("cannot measure" in l for l in lines))

    def test_main_without_the_layer_is_the_old_load_gate(self):
        with machine(DELIVERY_LOAD="10,10"):
            self.assertFalse(R.layer_ready())
            self.assertEqual(R.main(["--log", os.path.join(MS.machine_dir(), "g.log")]), 0)
            self.assertEqual(MS.queue_list(), [])

    def test_main_with_the_layer_takes_a_slot_and_job_done_frees_it(self):
        with machine(DELIVERY_LOAD="10,10", GITHUB_REPOSITORY="owner/example-app", GITHUB_RUN_ID="77", GITHUB_JOB="unit",
                     RUNNER_NAME="host1-pool-app1"):
            MS.write_machine_config({})
            self.assertEqual(R.main([]), 0)
            held = MS.find_held(MS.ident_from_env())
            self.assertEqual(len(held), 1)
            self.assertEqual(MS.read_log()[0]["run_id"], 77)
            result = RJD.done(log=lambda l: None)
            self.assertEqual(result["freed"], [held[0]["slot"]])
            self.assertEqual(MS.free_count(), 2)
            self.assertEqual(MS.read_log()[-1]["outcome"], "ran")
            self.assertEqual(RJD.done(log=lambda l: None)["freed"], [])    # a second call frees nothing

    def test_main_over_the_load_limit_times_out_with_exit_1(self):
        with machine(DELIVERY_LOAD="99,99", DELIVERY_GATE_MAX_WAIT_MIN="0.001", DELIVERY_GATE_POLL_SEC="0.01"):
            MS.write_machine_config({})
            self.assertEqual(R.main([]), 1)
            self.assertEqual(MS.queue_list(), [])
            self.assertEqual(MS.free_count(), 2)

    def test_settings_read_machine_json_over_the_old_file(self):
        with machine():
            Path(os.environ["DELIVERY_MACHINE_CONFIG"]).write_text(json.dumps({"runner_gate": {"max_wait_min": 9}}))
            self.assertEqual(R.settings()["max_wait_min"], 9)
            MS.write_machine_config({"runner_gate": {"max_wait_min": 4}})
            self.assertEqual(R.settings()["max_wait_min"], 4)


class JobDone(unittest.TestCase):
    def test_work_folder_only_inside__work(self):
        base = tempfile.mkdtemp(prefix="runner-")
        ws = os.path.join(base, "_work", "app1", "app1")
        os.makedirs(ws)
        self.assertEqual(RJD.work_folder({"GITHUB_WORKSPACE": ws}), os.path.abspath(ws))
        self.assertIsNone(RJD.work_folder({"GITHUB_WORKSPACE": os.path.join(base, "_work")}))
        self.assertIsNone(RJD.work_folder({"GITHUB_WORKSPACE": base}))
        self.assertIsNone(RJD.work_folder({}))

    def test_empties_the_workspace_and_keeps_the_folder(self):
        with machine():
            base = tempfile.mkdtemp(prefix="runner-")
            ws = os.path.join(base, "_work", "app1", "app1")
            os.makedirs(os.path.join(ws, "node_modules", "x"))
            Path(ws, "a.txt").write_text("x")
            sibling = os.path.join(base, "_work", "other")
            os.makedirs(sibling)
            env = {"GITHUB_WORKSPACE": ws, "GITHUB_REPOSITORY": "owner/example-app", "GITHUB_RUN_ID": "9", "GITHUB_JOB": "unit"}
            with mock.patch.dict(os.environ, env):
                result = RJD.done(log=lambda l: None)
            self.assertEqual(result["freed"], [])
            self.assertEqual(os.listdir(ws), [])
            self.assertTrue(os.path.isdir(sibling))
            with mock.patch.dict(os.environ, env):
                Path(ws, "b.txt").write_text("x")
                RJD.done(log=lambda l: None, keep_work=True)
            self.assertTrue(os.path.exists(os.path.join(ws, "b.txt")))

    def test_main_never_fails(self):
        with machine(GITHUB_WORKSPACE=""):
            self.assertEqual(RJD.main(["--log", os.path.join(MS.machine_dir(), "x.log")]), 0)


class HostLoad(unittest.TestCase):
    def write_host(self, mem, cpu, age=0):
        MS._mkdir(MS.machine_dir())
        Path(MS.host_load_path()).write_text(json.dumps({"mem": mem, "cpu": cpu, "at": time.time() - age}))

    def test_fresh_host_file_wins_over_own_figures(self):
        with machine():
            self.write_host(93, 12, age=5)
            with mock.patch.object(L, "measure_now", return_value={"mem": 20.0, "cpu": 5.0, "at": time.time()}):
                s = L.sample()
            self.assertEqual((s["mem"], s["cpu"], s["host"]), (93.0, 12.0, "file"))

    def test_stale_host_file_falls_back_to_own_figures(self):
        with machine():
            self.write_host(93, 12, age=61)
            with mock.patch.object(L, "measure_now", return_value={"mem": 20.0, "cpu": 5.0, "at": time.time()}):
                s = L.sample()
            self.assertEqual((s["mem"], s["cpu"], s["host"]), (20.0, 5.0, "stale"))

    def test_no_host_file_is_own(self):
        with machine():
            with mock.patch.object(L, "measure_now", return_value={"mem": 20.0, "cpu": 5.0, "at": time.time()}):
                self.assertEqual(L.sample()["host"], "own")

    def test_write_mode_writes_host_load_json(self):
        with machine():
            with mock.patch.object(L, "measure_now", return_value={"mem": 44.0, "cpu": 7.0, "at": time.time()}):
                self.assertEqual(L.main(["--write"]), 0)
            data = json.loads(Path(MS.host_load_path()).read_text())
            self.assertEqual((data["mem"], data["cpu"]), (44.0, 7.0))
            mem, age = L.read_host_load()[0], L.read_host_load()[1]
            self.assertEqual(mem["mem"], 44.0)
            self.assertLess(age, 5)

    def cgroup(self, current, maximum, usec, cpu_max="max 100000"):
        d = tempfile.mkdtemp(prefix="cg-")
        Path(d, "memory.current").write_text("%d\n" % current)
        Path(d, "memory.max").write_text("%s\n" % maximum)
        Path(d, "cpu.stat").write_text("usage_usec %d\nuser_usec 1\nsystem_usec 1\n" % usec)
        Path(d, "cpu.max").write_text(cpu_max + "\n")
        return d

    def test_container_figures_from_cgroup_v2(self):
        d = self.cgroup(900, 1000, 1_000_000, "200000 100000")
        with mock.patch.dict(os.environ, {"DELIVERY_CGROUP_DIR": d}):
            first = L.measure_container(None, now=100.0)
            self.assertEqual(first["mem"], 90.0)
            self.assertIsNone(first["cpu"])                         # no previous reading
            Path(d, "cpu.stat").write_text("usage_usec %d\n" % (1_000_000 + 10_000_000))
            second = L.measure_container({"cg": first["cg"]}, now=110.0)
            self.assertEqual(second["cpu"], 50.0)                   # 10 CPU-seconds in 10 s of 2 CPUs
        d2 = self.cgroup(900, "max", 5)
        with mock.patch.dict(os.environ, {"DELIVERY_CGROUP_DIR": d2}):
            self.assertIsNone(L.measure_container(None, now=1.0)["mem"])    # uncapped memory: no figure
        with mock.patch.dict(os.environ, {"DELIVERY_CGROUP_DIR": "/no/such"}):
            self.assertIsNone(L.measure_container(None))

    def test_the_worse_of_host_and_container_decides(self):
        with machine():
            self.write_host(40, 10, age=1)
            d = self.cgroup(950, 1000, 1)
            with mock.patch.dict(os.environ, {"DELIVERY_CGROUP_DIR": d, "DELIVERY_IN_CONTAINER": "1"}), \
                    mock.patch.object(L, "measure_now", return_value={"mem": 20.0, "cpu": 5.0, "at": time.time()}):
                s = L.sample()
            self.assertEqual((s["mem"], s["host"]), (95.0, "file"))
            self.assertTrue(L.over(s, {"memory_pct": 85.0, "cpu_pct": 60.0}))

    def test_parsers(self):
        self.assertEqual(L.parse_cpu_stat("usage_usec 42\nuser_usec 1\n"), 42)
        self.assertEqual(L.parse_cpu_max("150000 100000"), 1.5)
        self.assertIsNone(L.parse_cpu_max("max 100000"))
        with self.assertRaises(ValueError):
            L.parse_cpu_stat("nothing")


class Limits(unittest.TestCase):
    def test_machine_json_first_old_file_as_fallback_and_differences(self):
        with machine():
            old = Path(os.environ["DELIVERY_MACHINE_CONFIG"])
            old.write_text(json.dumps({"load_limits": {"memory_pct": 70, "cpu_pct": 40}}))
            self.assertEqual(L.limits(), {"memory_pct": 70.0, "cpu_pct": 40.0})        # new file missing: the old one
            self.assertEqual(L.legacy_differs(), [])
            MS.write_machine_config({"load_limits": {"memory_pct": 80, "cpu_pct": 40}})
            self.assertEqual(L.limits(), {"memory_pct": 80.0, "cpu_pct": 40.0})        # new file first
            self.assertEqual(L.legacy_differs(), ["memory_pct"])

    def test_project_can_lower_never_raise(self):
        with machine():
            MS.write_machine_config({"load_limits": {"memory_pct": 80, "cpu_pct": 50}})
            self.assertEqual(L.limits({"load_limits": {"memory_pct": 70}}), {"memory_pct": 70.0, "cpu_pct": 50.0})
            self.assertEqual(L.limits({"load_limits": {"memory_pct": 95, "cpu_pct": 99}}), {"memory_pct": 80.0, "cpu_pct": 50.0})

    def test_config_accessors(self):
        m = MS.normalise_config({"local_heavy": 3, "cloud_ci_sessions": 8, "load_limits": {"memory_pct": 80}})
        self.assertEqual(C.effective_machine_limits({"local_heavy": 1, "ci": {"fallback": {"cloud_ci_sessions": 20}}}, m),
                         {"local_heavy": 1, "cloud_ci_sessions": 8, "memory_pct": 80, "cpu_pct": 60})
        self.assertEqual(C.machine_limits({"local_heavy": 0, "load_limits": {"cpu_pct": 500}}),
                         {"local_heavy": None, "cloud_ci_sessions": None, "memory_pct": None, "cpu_pct": None})
        errors, _ = C.validate_config({"local_heavy": 0})
        self.assertTrue(errors)
        errors, _ = C.validate_config({"local_heavy": 2, "ci": {"fallback": {"cloud_ci_sessions": 5}}})
        self.assertEqual(errors, [])


def call(tool, **ti):
    return {"tool_name": tool, "tool_input": ti, "session_id": "s1"}


def run_hook(name, payload, **env):
    e = dict(os.environ, **env)
    p = subprocess.run([sys.executable, "-I", str(SCRIPTS / name)], input=json.dumps(payload).encode(), capture_output=True,
                       env=e, timeout=60)
    return p.returncode, p.stdout.decode(), p.stderr.decode()


class LocalHeavy(unittest.TestCase):
    def test_counts_from_pre_to_post_and_refuses_at_the_limit(self):
        with machine(DELIVERY_LOAD="10,10"):
            a, b, c = (dict(call("Bash", command=cmd), tool_use_id="t%d" % i) for i, cmd in enumerate(("pnpm test", "vitest", "pytest")))
            self.assertIsNone(G.check_call(a, {}))
            self.assertTrue(G.heavy_begin(a, {}))
            self.assertTrue(G.heavy_begin(b, {}))
            msg = G.check_call(c, {})
            self.assertIn("DL-91", msg)
            self.assertIn("2 of 2", msg)
            self.assertIn("pnpm test", msg)
            self.assertIn("vitest", msg)
            self.assertTrue(G.heavy_end(a))
            self.assertIsNone(G.check_call(c, {}))                   # one ended: room again
            light = call("Bash", command="git status")
            self.assertFalse(G.heavy_begin(light, {}))
            self.assertIsNone(G.check_call(light, {}))
            self.assertIsNone(G.check_call(call("Agent", isolation="remote"), {}))

    def test_light_and_off(self):
        with machine(DELIVERY_LOAD="10,10"):
            G.heavy_begin(call("Bash", command="vitest"), {})
            G.heavy_begin(call("Bash", command="pnpm build"), {})
            self.assertIsNone(G.check_call(call("Bash", command="ls"), {}))
            self.assertIsNone(G.check_call(call("Bash", command="pytest"), {"checks_off": ["DL-91"]}))

    def test_project_may_lower_not_raise(self):
        with machine(DELIVERY_LOAD="10,10"):
            MS.write_machine_config({"local_heavy": 2})
            G.heavy_begin(call("Bash", command="vitest"), {})
            self.assertIsNotNone(G.check_call(call("Bash", command="pytest"), {"local_heavy": 1}))
            self.assertIsNone(G.check_call(call("Bash", command="pytest"), {"local_heavy": 9}))
            self.assertEqual(G.local_heavy_limit({"local_heavy": 9}), 2)

    def test_local_agents_come_from_the_ledger(self):
        with machine(DELIVERY_LOAD="10,10"):
            ledger = {"agents": [{"state": "running", "where": "local", "task": "T1"},
                                 {"state": "running", "where": "local", "task": "T2"},
                                 {"state": "running", "where": "cloud", "task": "T3"},
                                 {"state": "done", "where": "local", "task": "T4"}]}
            msg = G.check_call(call("Bash", command="vitest"), {}, ledger)
            self.assertIn("agent: T1", msg)
            self.assertNotIn("T3", msg)
            self.assertNotIn("T4", msg)
            self.assertIsNone(G.check_call(call("Bash", command="vitest"), {}, {"agents": ledger["agents"][2:]}))

    def test_dead_process_and_old_entries_are_dropped(self):
        with machine():
            G.heavy_begin(dict(call("Bash", command="vitest"), tool_use_id="t1"), {})
            path = os.path.join(G.heavy_dir(), "t1.json")
            rec = json.loads(Path(path).read_text())
            rec["pid"] = dead_pid()
            Path(path).write_text(json.dumps(rec))
            self.assertEqual(G.heavy_running(), [])
            self.assertFalse(os.path.exists(path))
            G.heavy_begin(dict(call("Bash", command="vitest"), tool_use_id="t2"), {})
            self.assertEqual(G.heavy_running(now=time.time() + 3 * 3600), [])

    def test_hooks_pre_counts_post_ends_in_a_project_and_outside(self):
        for root in (make_root(), None):
            with machine(DELIVERY_LOAD="10,10") as _:
                cwd = str(root) if root else tempfile.mkdtemp(prefix="plain-")
                env = {"DELIVERY_LOCAL_HEAVY_DIR": os.environ["DELIVERY_LOCAL_HEAVY_DIR"],
                       "DELIVERY_MACHINE_DIR": os.environ["DELIVERY_MACHINE_DIR"], "DELIVERY_LOAD": "10,10"}

                def payload(cmd, i, event):
                    return {"tool_name": "Bash", "cwd": cwd, "session_id": "s1", "tool_use_id": "u%d" % i,
                            "hook_event_name": event, "tool_input": {"command": cmd}}
                self.assertEqual(run_hook("hook_pre_tool.py", payload("vitest", 1, "PreToolUse"), **env)[0], 0)
                self.assertEqual(run_hook("hook_pre_tool.py", payload("pytest", 2, "PreToolUse"), **env)[0], 0)
                rc, _, err = run_hook("hook_pre_tool.py", payload("pnpm test", 3, "PreToolUse"), **env)
                self.assertEqual(rc, 2)
                self.assertIn("DL-91", err)
                rc, _, _ = run_hook("hook_post_tool.py", payload("vitest", 1, "PostToolUse"), **env)
                self.assertEqual(rc, 0)
                self.assertEqual(run_hook("hook_pre_tool.py", payload("pnpm test", 3, "PreToolUse"), **env)[0], 0)

    def test_a_call_another_rule_denies_is_not_counted(self):
        with machine(DELIVERY_LOAD="10,10"):
            root = make_root({"enforcement": {"mode": "block"}})
            env = {"DELIVERY_LOCAL_HEAVY_DIR": os.environ["DELIVERY_LOCAL_HEAVY_DIR"],
                   "DELIVERY_MACHINE_DIR": os.environ["DELIVERY_MACHINE_DIR"], "DELIVERY_LOAD": "10,10"}
            data = {"tool_name": "Bash", "cwd": str(root), "session_id": "s1", "tool_use_id": "u9",
                    "tool_input": {"command": "gh pr merge 5 --squash && pnpm test"}}
            run_hook("hook_pre_tool.py", data, **env)
            self.assertEqual(G.heavy_running(), [])


class SlotsCommand(unittest.TestCase):
    def test_slots_command_prints_holders_queue_and_waits(self):
        with machine():
            MS.take_slot(ident("unit", run=12, shard="unit-1"))
            MS.enqueue(ident("lint", run=13), priority=1)
            MS.enqueue(ident("e2e", run=14), priority=0)
            out = []
            with mock.patch("builtins.print", side_effect=lambda *a, **k: out.append(" ".join(map(str, a)))):
                self.assertEqual(CI.main(["slots"]), 0)
            text = "\n".join(out)
            self.assertIn("slot 1  owner/example-app run 12 job unit (unit-1)", text)
            self.assertIn("slot 2  free", text)
            self.assertLess(text.index("run 14"), text.index("run 13"))          # ready first
            self.assertIn("first (ready PR or default branch)", text)
            out.clear()
            with mock.patch("builtins.print", side_effect=lambda *a, **k: out.append(" ".join(map(str, a)))):
                CI.main(["slots", "--json"])
            data = json.loads(out[0])
            self.assertEqual([s["free"] for s in data["slots"]], [False, True])
            self.assertEqual(len(data["queue"]), 2)


class DoctorMachine(unittest.TestCase):
    def cfg(self, option=None):
        return {"ci": {"options": {"linux": option}}} if option else {}

    def test_not_used_without_option_1_or_a_machine_folder(self):
        with machine():
            ok, detail, items = D.check_machine(make_root(), self.cfg())
            self.assertTrue(ok)
            self.assertEqual(items[0]["status"], "skip")

    def test_option_1_without_machine_json_fails(self):
        with machine(DELIVERY_GH=""):
            ok, detail, items = D.check_machine(make_root(), self.cfg("self-hosted"))
            self.assertFalse(ok)
            self.assertIn("machine.json is missing", detail)

    def test_healthy_layer_and_stale_slot_and_old_files(self):
        with machine(DELIVERY_RUNNER_DIRS=""):
            MS.write_machine_config({})
            L.write_host_load({"mem": 10, "cpu": 10})
            root = make_root()
            with mock.patch.object(D.H, "gh", return_value=(0, json.dumps([{"name": "CI_RUNS_ON", "value": "[\"self-hosted\"]"}]))):
                ok, detail, items = D.check_machine(root, self.cfg("self-hosted"))
            by = {i["id"]: i for i in items}
            self.assertTrue(ok, detail)
            self.assertEqual((by["machine.config"]["status"], by["machine.slots"]["status"], by["machine.hostload"]["status"],
                              by["machine.runs_on"]["status"]), ("ok", "ok", "ok", "ok"))
            self.assertEqual(by["pool"]["status"], "skip")                          # no pool module on this branch
            lock = MS.take_slot(ident("a"))
            rec = json.loads(Path(MS.slot_path(lock["slot"])).read_text())
            rec["pid"] = dead_pid()
            Path(MS.slot_path(lock["slot"])).write_text(json.dumps(rec))
            old = time.time() - 120
            os.utime(MS.host_load_path(), (old, old))
            Path(MS.host_load_path()).write_text(json.dumps({"mem": 1, "cpu": 1, "at": old}))
            with mock.patch.object(D.H, "gh", return_value=(0, "[]")):
                ok, detail, items = D.check_machine(root, self.cfg("self-hosted"))
            by = {i["id"]: i for i in items}
            self.assertFalse(ok)
            self.assertEqual((by["machine.slots"]["status"], by["machine.hostload"]["status"], by["machine.runs_on"]["status"]),
                             ("fail", "fail", "fail"))
            self.assertIn("CI_RUNS_ON", by["machine.runs_on"]["detail"])

    def test_runner_hooks_both_required_and_warning_for_old_file_difference(self):
        with machine():
            MS.write_machine_config({"load_limits": {"memory_pct": 80, "cpu_pct": 60}})
            Path(os.environ["DELIVERY_MACHINE_CONFIG"]).write_text(json.dumps({"load_limits": {"memory_pct": 70}}))
            r = Path(tempfile.mkdtemp(prefix="actions-runner-"))
            (r / ".runner").write_text(json.dumps({"agentName": "host1-r1"}))
            (r / ".env").write_text("ACTIONS_RUNNER_HOOK_JOB_STARTED=/p/runner_load_gate.sh\n")
            with mock.patch.dict(os.environ, {"DELIVERY_RUNNER_DIRS": str(r)}), \
                    mock.patch.object(D.H, "gh", return_value=(0, "[]")):
                ok, detail, items = D.check_machine(make_root(), self.cfg())
            by = {i["id"]: i for i in items}
            self.assertEqual(by["machine.legacy"]["status"], "warn")
            self.assertIn("memory_pct", by["machine.legacy"]["detail"])
            self.assertEqual(by["machine.hooks:%s" % r]["status"], "fail")
            self.assertIn("runner_job_done", by["machine.hooks:%s" % r]["detail"])
            (r / ".env").write_text("ACTIONS_RUNNER_HOOK_JOB_STARTED=/p/runner_load_gate.sh\n"
                                    "ACTIONS_RUNNER_HOOK_JOB_COMPLETED=/p/runner_job_done.sh\n")
            with mock.patch.dict(os.environ, {"DELIVERY_RUNNER_DIRS": str(r)}), \
                    mock.patch.object(D.H, "gh", return_value=(0, "[]")):
                items = D.machine_items(make_root(), self.cfg())
            self.assertEqual({i["id"]: i for i in items}["machine.hooks:%s" % r]["status"], "ok")

    def test_pool_checks_are_called_when_the_module_imports(self):
        with machine(DELIVERY_RUNNER_DIRS=""):
            MS.write_machine_config({})
            fake = mock.Mock()
            fake.doctor_checks.return_value = [{"id": "pool.main", "status": "warn", "detail": "cap near the ceiling"},
                                               {"id": "pool.x", "status": "weird", "detail": "?"}]
            with mock.patch.dict(sys.modules, {"delivery_runner_pool": fake}), mock.patch.object(D.H, "gh", return_value=(0, "[]")):
                items = D.machine_items(make_root(), self.cfg())
            by = {i["id"]: i for i in items}
            self.assertEqual((by["pool.main"]["status"], by["pool.x"]["status"]), ("warn", "warn"))
            fake.doctor_checks.assert_called_once()

    def test_disk_warning_and_clean_work(self):
        with machine():
            MS.write_machine_config({})
            r = Path(tempfile.mkdtemp(prefix="actions-runner-"))
            (r / ".runner").write_text(json.dumps({"agentName": "host1-r1"}))
            (r / "_work" / "app1").mkdir(parents=True)
            (r / "_work" / "app1" / "big.bin").write_bytes(b"x" * 1000)
            with mock.patch.dict(os.environ, {"DELIVERY_RUNNER_DIRS": str(r)}), \
                    mock.patch.object(D.H, "gh", return_value=(0, "[]")), mock.patch.object(D, "WORK_WARN_GB", 0.0000001):
                items = D.machine_items(make_root(), self.cfg())
                disk = {i["id"]: i for i in items}["machine.disk"]
                self.assertEqual(disk["status"], "warn")
                lines = []
                D.clean_work(False, lines.append)                    # list only
                self.assertTrue((r / "_work" / "app1" / "big.bin").exists())
                MS.take_slot(ident("a", runner="host1-r1"))          # a job runs on this runner: not cleaned
                D.clean_work(True, lines.append)
                self.assertTrue((r / "_work" / "app1" / "big.bin").exists())
                self.assertTrue(any("job running" in l for l in lines))
                for s in MS.read_slots():
                    if s["holder"]:
                        MS.free_slot(dict(s["holder"], slot=s["slot"]))
                D.clean_work(True, lines.append)
                self.assertEqual(os.listdir(r / "_work"), [])


class Templates(unittest.TestCase):
    def test_every_ci_job_sets_delivery_shard(self):
        import re
        root = Path(SCRIPTS).parent / "templates"
        count = 0
        for path in sorted(root.glob("*/.github/workflows/*.yml")):
            if path.name == "ci-fallback.yml":
                continue
            text = path.read_text()
            for m in re.finditer(r"^  ([\w-]+):\n((?:(?!^  \S).*\n?)*)", text.split("\njobs:\n", 1)[-1], re.M):
                block = m.group(2)
                if "runs-on:" in block and "CI_RUNS_ON" in block:
                    count += 1
                    self.assertIn("DELIVERY_SHARD:", block, "%s job %s" % (path, m.group(1)))
        self.assertGreater(count, 20)


if __name__ == "__main__":
    unittest.main()
