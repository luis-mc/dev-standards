"""DL327: a heavy job takes a heavy slot first, holds no CI slot while it waits, and two never run at once."""
import os
import unittest
from pathlib import Path
from unittest import mock

from test_machine import machine, ident
import machine_slots as MS
import runner_job_done as RJD
import runner_load_gate as R

LIM = {"memory_pct": 85.0, "cpu_pct": 60.0}
CFG = {"max_wait_min": 1, "poll_sec": 15, "on_timeout": "fail"}
QUIET = lambda: {"mem": 10, "cpu": 10}  # noqa: E731
CONF = {"runner_gate": {"heavy_jobs": ["integration", "e2e-*", "owner/example-app:full"], "light_jobs": ["integration", "smoke"]}}


def gate(who, cfg=CFG, on_sleep=None, lines=None):
    now = [0.0]

    def sleep(s):
        now[0] += s
        if on_sleep:
            on_sleep()
    marker = mock.Mock()
    marker.claim_lost.return_value = False
    lines = [] if lines is None else lines
    code, lock = R.queue_wait(LIM, cfg, who, sample=QUIET, sleep=sleep, clock=lambda: now[0], log=lines.append,
                              marker=marker, priority=1)
    return code, lock, lines


class Matching(unittest.TestCase):
    def test_exact_glob_and_repo_prefix(self):
        with machine():
            MS.write_machine_config(CONF)
            c = MS.machine_config()
            self.assertTrue(MS.is_heavy_job(ident("integration"), c))
            self.assertTrue(MS.is_heavy_job(ident("x", shard="e2e-chrome"), c))
            self.assertTrue(MS.is_heavy_job(ident("full"), c))
            self.assertFalse(MS.is_heavy_job(ident("full", repo="owner/other"), c))
            self.assertFalse(MS.is_heavy_job(ident("unit"), c))

    def test_zero_heavy_slots_means_no_limit(self):
        with machine():
            MS.write_machine_config(dict(CONF, heavy_slots=0))
            self.assertFalse(MS.is_heavy_job(ident("integration")))

    def test_heavy_beats_light(self):
        with machine():
            MS.write_machine_config(CONF)
            self.assertFalse(MS.is_light_job(ident("integration")))
            self.assertTrue(MS.is_light_job(ident("smoke")))
            code, lock, _ = gate(ident("integration", run=3))
            self.assertEqual(code, 0)
            self.assertNotEqual(lock.get("kind"), "light")
            self.assertFalse(Path(MS.slot_path(1, "light")).exists())

    def test_config_round_trip(self):
        with machine():
            MS.write_machine_config(dict(CONF, heavy_slots=2))
            c = MS.machine_config()
            self.assertEqual(c["heavy_slots"], 2)
            self.assertEqual(c["runner_gate"]["heavy_jobs"], CONF["runner_gate"]["heavy_jobs"])
            self.assertEqual(MS.DEFAULT_CONFIG["heavy_slots"], 1)
            self.assertEqual(MS.DEFAULT_CONFIG["runner_gate"]["heavy_jobs"], [])
            self.assertEqual(MS.normalise_config({"heavy_slots": "x"})["heavy_slots"], 1)


class Gate(unittest.TestCase):
    def test_heavy_takes_both_slots_and_release_frees_both(self):
        with machine():
            MS.write_machine_config(CONF)
            who = ident("integration", run=3)
            code, lock, lines = gate(who)
            self.assertEqual(code, 0, lines)
            self.assertTrue(Path(MS.slot_path(1, "heavy")).exists())
            self.assertTrue(Path(MS.slot_path(lock["slot"])).exists())
            freed = RJD.done(env={"GITHUB_REPOSITORY": who["repo"], "GITHUB_RUN_ID": "3", "GITHUB_JOB": "integration",
                                  "GITHUB_RUN_ATTEMPT": "1"}, log=lambda *_: None)
            self.assertEqual(len(freed["freed"]), 2)
            self.assertFalse(Path(MS.slot_path(1, "heavy")).exists())
            self.assertEqual(MS.free_count(), 2)

    def test_second_heavy_waits_and_holds_no_ci_slot(self):
        with machine():
            MS.write_machine_config(CONF)
            self.assertEqual(gate(ident("integration", run=3))[0], 0)    # holds heavy-1 and one CI slot
            seen = []
            code, lock, lines = gate(ident("e2e-a", run=4), on_sleep=lambda: seen.append(MS.free_count()))
            self.assertEqual(code, 1, lines)
            self.assertTrue(seen and all(n == 1 for n in seen))           # only the first heavy job's CI slot is busy
            self.assertEqual(MS.queue_list(), [])
            self.assertTrue(any("heavy job e2e-a waits for the heavy slot (held by" in l for l in lines))
            self.assertEqual(len([h for h in MS.read_slots(kind="heavy") if h["holder"]]), 1)

    def test_normal_job_flows_while_heavy_waits(self):
        with machine():
            MS.write_machine_config(CONF)
            gate(ident("integration", run=3))
            result = []

            def normal():
                if not result:
                    result.append(gate(ident("unit", run=9)))
            gate(ident("e2e-a", run=4), on_sleep=normal)
            self.assertEqual(result[0][0], 0)

    def test_waiting_heavy_runs_after_release(self):
        with machine():
            MS.write_machine_config(CONF)
            first = gate(ident("integration", run=3))[1]
            held = [first]

            def release():
                if held:
                    MS.free_slot(MS.read_slots(kind="heavy")[0]["holder"] | {"slot": 1, "kind": "heavy"})
                    held.clear()
            code, lock, lines = gate(ident("e2e-a", run=4), on_sleep=release)
            self.assertEqual(code, 0, lines)
            self.assertTrue(any("heavy slot heavy-1 taken after" in l for l in lines))

    def test_dead_holder_is_freed(self):
        from test_machine import dead_pid
        with machine():
            MS.write_machine_config(CONF)
            MS.take_slot(dict(ident("integration", run=3), pid=0), kind="heavy")
            path = MS.slot_path(1, "heavy")
            rec = MS._read_json(path)
            rec["pid"] = dead_pid()
            import json
            Path(path).write_text(json.dumps(rec))
            code, lock, lines = gate(ident("e2e-a", run=4))
            self.assertEqual(code, 0, lines)
            self.assertEqual(MS._read_json(MS.slot_path(1, "heavy"))["run_id"], 4)

    def test_heavy_slot_freed_when_ci_wait_times_out(self):
        with machine():
            MS.write_machine_config(dict(CONF, ci_slots=1))
            MS.take_slot(ident("build", run=1))                          # the only CI slot is busy
            code, lock, lines = gate(ident("integration", run=3))
            self.assertEqual(code, 1, lines)
            self.assertFalse(Path(MS.slot_path(1, "heavy")).exists())


if __name__ == "__main__":
    unittest.main()
