"""DL200: the runner gate never waits on an empty queue when its own ticket vanished."""
import os
import unittest
from unittest import mock

from test_machine import machine, ident
import machine_slots as MS
import runner_load_gate as R


class VanishedTicket(unittest.TestCase):
    LIM = {"memory_pct": 85.0, "cpu_pct": 60.0}
    CFG = {"max_wait_min": 1, "poll_sec": 15, "on_timeout": "fail"}

    def test_dropped_ticket_is_queued_again_and_the_job_gets_a_slot(self):
        sleeps, lines = [], []
        now = [0.0]

        def sleep(s):
            sleeps.append(s)
            now[0] += s
        real = MS.queue_list
        calls = [0]

        def flaky(*a, **k):
            calls[0] += 1
            return [] if calls[0] <= 2 else real(*a, **k)
        marker = mock.Mock()
        marker.claim_lost.return_value = False
        with machine():
            MS.write_machine_config({})
            with mock.patch.object(MS, "queue_list", flaky):
                code, lock = R.queue_wait(self.LIM, self.CFG, ident("unit"), sample=lambda: {"mem": 10, "cpu": 10},
                                          sleep=sleep, clock=lambda: now[0], log=lines.append, marker=marker, priority=1)
            self.assertEqual(code, 0, "\n".join(lines))
            self.assertIsNotNone(lock)
            self.assertTrue(any("own ticket was gone; queued again" in l for l in lines))
            self.assertLessEqual(len(sleeps), 2)
            self.assertEqual(real(), [])


if __name__ == "__main__":
    unittest.main()
