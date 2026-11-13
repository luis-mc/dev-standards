"""DL292: queue tickets carry a heartbeat; a ticket with no beat is dropped, from any host."""
import json
import os
import unittest
from unittest import mock

from test_machine import machine, ident
import machine_slots as MS
import runner_load_gate as R

T0 = 1_000_000.0


def other_host(path_name, **fields):
    p = os.path.join(MS.queue_dir(), path_name)
    rec = _read(p)
    rec.update(fields)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(rec, f)


def _read(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


class Prune(unittest.TestCase):
    def setUp(self):
        self.m = machine()
        self.m.__enter__()
        MS.write_machine_config({})
        self.addCleanup(self.m.__exit__, None, None, None)

    def test_enqueue_sets_beat_ts(self):
        t = MS.enqueue(ident("a"), 1, now=T0)
        self.assertEqual(t["beat_ts"], T0)

    def test_other_host_fresh_beat_stays(self):
        t = MS.enqueue(ident("a"), 1, now=T0)
        other_host(t["file"], host="elsewhere", beat_ts=T0 + 500)
        self.assertEqual(len(MS.queue_list(now=T0 + 500 + 100)), 1)

    def test_other_host_old_beat_dropped_and_logged(self):
        t = MS.enqueue(ident("a"), 1, now=T0)
        other_host(t["file"], host="elsewhere")
        self.assertEqual(MS.queue_list(now=T0 + 121), [])
        self.assertFalse(os.path.exists(os.path.join(MS.queue_dir(), t["file"])))
        entries = [e for e in MS.read_log() if e.get("reason") == "no heartbeat"]
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["host"], "elsewhere")
        self.assertEqual(entries[0]["job"], "a")
        self.assertTrue(entries[0]["repo"])

    def test_limit_follows_poll_sec(self):
        MS.write_machine_config({"runner_gate": {"poll_sec": 60}})
        t = MS.enqueue(ident("a"), 1, now=T0)
        other_host(t["file"], host="elsewhere")
        self.assertEqual(len(MS.queue_list(now=T0 + 200)), 1)
        self.assertEqual(MS.queue_list(now=T0 + 241), [])

    def test_old_ticket_without_beat_ts_uses_queued_ts(self):
        t = MS.enqueue(ident("a"), 1, now=T0)
        p = os.path.join(MS.queue_dir(), t["file"])
        rec = _read(p)
        del rec["beat_ts"]
        rec["host"] = "elsewhere"
        with open(p, "w", encoding="utf-8") as f:
            json.dump(rec, f)
        self.assertEqual(len(MS.queue_list(now=T0 + 60)), 1)
        self.assertEqual(MS.queue_list(now=T0 + 121), [])

    def test_same_host_dead_pid_still_dropped(self):
        t = MS.enqueue(ident("a"), 1, now=T0)
        other_host(t["file"], gate_pid=2 ** 22 + 7)
        with mock.patch.object(MS, "pid_alive", return_value=False):
            self.assertEqual(MS.queue_list(now=T0 + 1), [])

    def test_beat_keeps_the_file_name(self):
        t = MS.enqueue(ident("a"), 1, now=T0)
        before = sorted(os.listdir(MS.queue_dir()))
        self.assertTrue(MS.beat(t, now=T0 + 50))
        self.assertEqual(sorted(os.listdir(MS.queue_dir())), before)
        self.assertEqual(_read(os.path.join(MS.queue_dir(), t["file"]))["beat_ts"], T0 + 50)

    def test_beat_does_not_recreate_a_missing_ticket(self):
        t = MS.enqueue(ident("a"), 1, now=T0)
        MS.dequeue(t)
        self.assertFalse(MS.beat(t))
        self.assertEqual(os.listdir(MS.queue_dir()), [])


class Gate(unittest.TestCase):
    LIM = {"memory_pct": 85.0, "cpu_pct": 60.0}
    CFG = {"max_wait_min": 10, "poll_sec": 15, "on_timeout": "fail"}

    def test_poll_loop_beats_each_poll_without_renaming(self):
        seen, now = [], [0.0]
        marker = mock.Mock()
        marker.claim_lost.return_value = False
        with machine():
            MS.write_machine_config({"ci_slots": 1})
            blocker = MS.take_slot(ident("blocker"), MS.machine_config())
            self.assertIsNotNone(blocker)
            beats = []
            real = MS.beat

            def spy(ticket, now=None):
                ok = real(ticket)
                beats.append((ticket["file"], sorted(os.listdir(MS.queue_dir()))))
                return ok

            def sleep(s):
                now[0] += s
                if len(beats) == 3:
                    MS.free_slot(blocker, "released")

            with mock.patch.object(MS, "beat", spy), mock.patch.object(MS, "queue_list", wraps=MS.queue_list):
                code, _ = R.queue_wait(self.LIM, self.CFG, ident("w"), sample=lambda: {"memory_pct": 1, "cpu_pct": 1},
                                       sleep=sleep, clock=lambda: now[0], log=lambda l: None, marker=marker, priority=1)
            self.assertEqual(code, 0)
            self.assertGreaterEqual(len(beats), 3)
            self.assertEqual(len({b[0] for b in beats}), 1)
            self.assertTrue(all(len(b[1]) == 1 for b in beats))

    def test_dropped_ticket_is_queued_again_with_its_old_queued_ts(self):
        marker = mock.Mock()
        marker.claim_lost.return_value = False
        now = [0.0]
        with machine():
            MS.write_machine_config({"ci_slots": 1})
            blocker = MS.take_slot(ident("blocker"), MS.machine_config())
            enq = []
            real = MS.enqueue

            def spy(i, prio=None, now=None, beat_now=None):
                t = real(i, prio, now=now, beat_now=beat_now)
                enq.append(t)
                return t

            def sleep(s):
                now[0] += s
                if len(enq) == 1:                      # another host's pool gate drops the ticket
                    MS.dequeue(enq[0])
                elif len(enq) == 2:
                    MS.free_slot(blocker, "released")

            with mock.patch.object(MS, "enqueue", spy):
                code, _ = R.queue_wait(self.LIM, self.CFG, ident("w"), sample=lambda: {"memory_pct": 1, "cpu_pct": 1},
                                       sleep=sleep, clock=lambda: now[0], log=lambda l: None, marker=marker, priority=1)
            self.assertEqual(code, 0)
            self.assertEqual(len(enq), 2)
            self.assertEqual(enq[1]["queued_ts"], enq[0]["queued_ts"])
            self.assertTrue(enq[1]["file"].split("-")[1] == enq[0]["file"].split("-")[1])
            self.assertGreater(enq[1]["beat_ts"], enq[0]["beat_ts"] - 1)


if __name__ == "__main__":
    unittest.main()
