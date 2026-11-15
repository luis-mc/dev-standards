"""DL365 (R5.63): a stop reaches the agent's whole process group; no second listener while one survives."""
import json
import os
import signal
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

POOL = Path(__file__).resolve().parent.parent / "templates" / "runner-pool"
sys.path.insert(0, str(POOL))
import pool_supervisor as SUP  # noqa: E402


class FakeProc:
    def __init__(self):
        self.code = None

    def poll(self):
        return self.code


class SpawnTest(unittest.TestCase):
    def test_popen_starts_own_session(self):
        with mock.patch.object(subprocess, "Popen") as popen:
            SUP.popen_spawn({"slug": "app1", "user": "r-app1"}, "/agents", {})
        self.assertTrue(popen.call_args.kwargs["start_new_session"])


class SignalTest(unittest.TestCase):
    def test_real_popen_signals_group(self):
        proc = mock.Mock(spec=subprocess.Popen)
        proc.pid = 4242
        with mock.patch.object(os, "killpg", create=True) as killpg:
            SUP.signal_group(proc, signal.SIGTERM)
        killpg.assert_called_once_with(4242, signal.SIGTERM)

    def test_fake_proc_falls_back(self):
        proc = mock.Mock()
        SUP.signal_group(proc, signal.SIGTERM)
        proc.terminate.assert_called_once()


class ListenerTest(unittest.TestCase):
    def procs(self, table):
        return dict(listdir=lambda d: list(table) + ["self"], read=lambda p: table[p.split("/")[-2]])

    def test_finds_listener(self):
        table = {"7": b"/agents/app1/bin/Runner.Listener\0run\0", "8": b"bash\0"}
        self.assertTrue(SUP.proc_listener_alive("app1", **self.procs(table)))

    def test_other_slug_does_not_match(self):
        table = {"7": b"/agents/app10/bin/Runner.Listener\0run\0"}
        self.assertFalse(SUP.proc_listener_alive("app1", **self.procs(table)))

    def test_no_proc_dir(self):
        def boom(d):
            raise FileNotFoundError(d)
        self.assertFalse(SUP.proc_listener_alive("app1", listdir=boom))


class TickTest(unittest.TestCase):
    def make(self, alive, signals):
        d = tempfile.mkdtemp()
        f = os.path.join(d, "agents.json")
        with open(f, "w") as fh:
            json.dump({"agents": [{"slug": "app1", "user": "r-app1"}]}, fh)
        self.spawned = []

        def spawn(agent):
            p = FakeProc()
            self.spawned.append(p)
            return p

        sup = SUP.Supervisor(f, base=d, spawn=spawn, clock=lambda: 1000.0, drain_dir=d,
                             busy=lambda s: False, listener_alive=lambda s: alive[0],
                             signal=lambda p, sig: signals.append(sig))
        return sup, d

    def test_orphan_blocks_spawn_until_gone(self):
        alive, sigs = [True], []
        sup, _ = self.make(alive, sigs)
        with mock.patch.object(SUP, "_log") as log:
            sup.tick()
            sup.tick()
        self.assertEqual(self.spawned, [])
        self.assertEqual(log.call_count, 1)
        alive[0] = False
        sup.tick()
        self.assertEqual(len(self.spawned), 1)

    def test_drain_signals_group_with_sigterm(self):
        alive, sigs = [False], []
        sup, d = self.make(alive, sigs)
        sup.tick()
        Path(d, "drain").write_text("x")
        sup.tick()
        self.assertEqual(sigs, [signal.SIGTERM])

    def test_stop_escalates_to_sigkill(self):
        alive, sigs = [False], []
        sup, _ = self.make(alive, sigs)
        sup.tick()
        sup.stop(grace_sec=0, sleep=lambda s: None)
        self.assertEqual(sigs, [signal.SIGTERM, SUP._SIGKILL])


if __name__ == "__main__":
    unittest.main()
