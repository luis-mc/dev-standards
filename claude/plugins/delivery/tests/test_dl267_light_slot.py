"""DL267: a light job takes its own light slot and does not wait for a CI slot."""
import json
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
BUSY = lambda: {"mem": 95, "cpu": 10}  # noqa: E731


def gate(who, sample=QUIET, lines=None):
    now = [0.0]

    def sleep(s):
        now[0] += s
    marker = mock.Mock()
    marker.claim_lost.return_value = False
    lines = [] if lines is None else lines
    code, lock = R.queue_wait(LIM, CFG, who, sample=sample, sleep=sleep, clock=lambda: now[0], log=lines.append,
                              marker=marker, priority=1)
    return code, lock, lines


def hold_ci(n=2):
    return [MS.take_slot(ident("build%d" % i, run=100 + i)) for i in range(n)]


class LightSlot(unittest.TestCase):
    def test_light_job_takes_light_1_while_both_ci_slots_are_held(self):
        with machine():
            MS.write_machine_config({})
            hold_ci()
            code, lock, lines = gate(ident("smoke", run=5))
            self.assertEqual(code, 0, "\n".join(lines))
            self.assertEqual((lock["slot"], lock["kind"]), (1, "light"))
            self.assertTrue(Path(MS.slot_path(1, "light")).exists())
            self.assertTrue(any("slot light-1 taken after" in l for l in lines))
            self.assertEqual(MS.queue_list(), [])                    # no place in the CI queue

    def test_second_light_job_takes_a_free_ci_slot(self):
        with machine():
            MS.write_machine_config({})
            self.assertEqual(gate(ident("smoke", run=5))[0], 0)
            code, lock, lines = gate(ident("prune-old", run=6))
            self.assertEqual(code, 0, "\n".join(lines))
            self.assertNotEqual(lock.get("kind"), "light")
            self.assertTrue(Path(MS.slot_path(lock["slot"])).exists())

    def test_second_light_job_waits_when_no_slot_is_free(self):
        with machine():
            MS.write_machine_config({})
            hold_ci()
            self.assertEqual(gate(ident("smoke", run=5))[0], 0)
            code, lock, lines = gate(ident("cleanup", run=6))
            self.assertEqual((code, lock), (1, None), "\n".join(lines))
            self.assertTrue(any("every light slot is busy" in l for l in lines))
            self.assertEqual(MS.queue_list(), [])                    # its ticket is gone again

    def test_heavy_job_never_takes_a_light_slot(self):
        with machine():
            MS.write_machine_config({})
            hold_ci()
            code, lock, _ = gate(ident("unit", run=5))
            self.assertEqual((code, lock), (1, None))
            self.assertFalse(Path(MS.slot_path(1, "light")).exists())

    def test_light_slots_zero_is_todays_behaviour(self):
        with machine():
            MS.write_machine_config({"light_slots": 0})
            self.assertFalse(MS.is_light_job(ident("smoke")))
            hold_ci()
            code, lock, _ = gate(ident("smoke", run=5))
            self.assertEqual((code, lock), (1, None))
            self.assertEqual(MS.status()["light_slots"], [])
            self.assertEqual(MS.find_held(ident("smoke", run=5)), [])

    def test_load_over_the_limit_holds_a_light_job(self):
        with machine():
            MS.write_machine_config({})
            code, lock, lines = gate(ident("smoke", run=5), sample=BUSY)
            self.assertEqual((code, lock), (1, None), "\n".join(lines))
            self.assertTrue(any("memory" in l for l in lines))
            self.assertFalse(Path(MS.slot_path(1, "light")).exists())

    def test_job_completed_frees_light_1(self):
        with machine():
            MS.write_machine_config({})
            who = ident("smoke", run=5)
            code, lock, _ = gate(who)
            self.assertEqual(code, 0)
            env = {"GITHUB_REPOSITORY": who["repo"], "GITHUB_RUN_ID": "5", "GITHUB_RUN_ATTEMPT": "1",
                   "GITHUB_JOB": "smoke", "RUNNER_NAME": who["runner"]}
            res = RJD.done(env=env, log=lambda l: None, keep_work=True)
            self.assertEqual(res["freed"], [1])
            self.assertFalse(Path(MS.slot_path(1, "light")).exists())
            self.assertEqual(MS.free_light_count(), 1)
            self.assertTrue(any(e.get("slot_kind") == "light" and e.get("outcome") == "ran" for e in MS.read_log()))

    def test_stale_light_lock_is_freed_like_a_ci_lock(self):
        with machine():
            MS.write_machine_config({})
            lock = MS.take_slot(ident("smoke", run=7), kind="light")
            rec = json.loads(Path(MS.slot_path(1, "light")).read_text())
            rec["taken_ts"] -= 3 * 3600
            Path(MS.slot_path(1, "light")).write_text(json.dumps(rec))
            self.assertTrue(MS.status()["light_slots"][0]["stale"])
            freed = MS.free_stale()
            self.assertEqual([(f["slot"], f["kind"]) for f in freed], [(1, "light")])
            self.assertEqual(MS.free_light_count(), 1)
            self.assertIsNotNone(lock)

    def test_glob_match_on_delivery_shard(self):
        with machine():
            MS.write_machine_config({})
            self.assertTrue(MS.is_light_job(ident("job-x", shard="prune-images")))
            self.assertTrue(MS.is_light_job(ident("delete-branches")))
            self.assertFalse(MS.is_light_job(ident("unit", shard="unit-1")))
            MS.write_machine_config({"runner_gate": {"light_jobs": ["quick-*"]}})
            self.assertTrue(MS.is_light_job(ident("x", shard="quick-1")))
            self.assertFalse(MS.is_light_job(ident("smoke")))

    def test_config_validation(self):
        with machine():
            got = MS.write_machine_config({"light_slots": 0, "runner_gate": {"light_jobs": ["a", 3, ""]}})
            self.assertEqual((got["light_slots"], got["runner_gate"]["light_jobs"]), (0, ["a"]))
            Path(MS.config_path()).write_text(json.dumps({"light_slots": -1}))
            self.assertEqual(MS.machine_config()["light_slots"], 1)


if __name__ == "__main__":
    unittest.main()
