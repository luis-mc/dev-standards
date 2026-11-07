"""DL109: the watcher opens no console windows on Windows, and a second watcher for the same root exits."""
import subprocess
import unittest
from datetime import timedelta
from unittest import mock

from _helpers import L, make_root  # noqa: F401  (sets sys.path to the scripts folder)
import delivery_watch as W
import hook_session_start as SS


def row(pid, beat, version=None):
    return {"pid": pid, "kind": "delivery_watch", "heartbeat_at": L.iso(beat), "version": version or W.WATCHER_VERSION}


class NoWindowTests(unittest.TestCase):
    def test_run_and_spawn_pass_the_hidden_window_flag(self):
        flags = {"creationflags": 0x08000000}
        with mock.patch.object(W, "NO_WINDOW", flags), \
                mock.patch.object(W.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "", "")) as run, \
                mock.patch.object(W.subprocess, "Popen") as popen:
            W.Shell().run(["gh", "version"])
            W.Shell().spawn(["git", "status"])
        self.assertEqual(run.call_args.kwargs["creationflags"], 0x08000000)
        self.assertEqual(popen.call_args.kwargs["creationflags"], 0x08000000)

    def test_flag_only_on_windows(self):
        self.assertEqual(bool(W.NO_WINDOW), W.os.name == "nt")

    def test_hook_starts_the_watcher_on_a_hidden_console(self):
        with mock.patch.object(SS.os, "name", "nt"), mock.patch("subprocess.Popen") as popen:
            self.assertTrue(SS.spawn_watcher("."))
        flags = popen.call_args.kwargs["creationflags"]
        self.assertTrue(flags & 0x08000000)
        self.assertFalse(flags & 0x00000008)  # not DETACHED_PROCESS: its children would each open a window


class LivePeerTests(unittest.TestCase):
    def setUp(self):
        self.now = L.utcnow()

    def peer(self, rows, alive=lambda pid: True):
        return W.live_peer({"watchers": rows}, 60, now=self.now, pid=100, alive=alive)

    def test_a_fresh_live_peer_is_found(self):
        self.assertEqual(self.peer([row(200, self.now)])["pid"], 200)

    def test_own_row_is_ignored(self):
        self.assertIsNone(self.peer([row(100, self.now)]))

    def test_stale_heartbeat_is_ignored(self):
        self.assertIsNone(self.peer([row(200, self.now - timedelta(minutes=10))]))

    def test_dead_pid_is_ignored(self):
        self.assertIsNone(self.peer([row(200, self.now)], alive=lambda pid: False))

    def test_older_version_is_ignored(self):
        if not L.version_key(W.WATCHER_VERSION):
            self.skipTest("no plugin version in this checkout")
        self.assertIsNone(self.peer([row(200, self.now, version="0.0.1")]))

    def test_other_kinds_are_ignored(self):
        self.assertIsNone(self.peer([dict(row(200, self.now), kind="other")]))


if __name__ == "__main__":
    unittest.main()
