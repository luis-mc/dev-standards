"""DL98: SessionStart stops a watcher from an older plugin version (by pid) and starts the newest."""
import io
import json
import unittest
from contextlib import redirect_stdout
from unittest import mock

from _helpers import L, make_root
import hook_session_start as SS
import hooklib as H


def watcher(pid, version, kind="delivery_watch"):
    return {"pid": pid, "kind": kind, "started": L.iso(), "heartbeat_at": L.iso(), "version": version}


class RearmTests(unittest.TestCase):
    def go(self, rows, installed="1.12.0"):
        root = make_root()
        L.update(root, lambda led: led["watchers"].extend(rows))
        with mock.patch.object(SS, "stop_pid", return_value=True) as stop, \
                mock.patch.object(SS, "spawn_watcher", return_value=True) as spawn, \
                mock.patch.object(L, "plugin_version", return_value=installed):
            msgs, gone = SS.rearm_old_watchers(str(root), H.load_ledger(str(root)), installed)
        return stop, spawn, msgs, gone

    def test_older_version_is_stopped_and_replaced(self):
        stop, spawn, msgs, gone = self.go([watcher(4242, "1.11.0")])
        stop.assert_called_once_with(4242)
        spawn.assert_called_once()
        self.assertEqual(gone, [4242])

    def test_unstamped_watcher_is_older(self):
        stop, spawn, _, _ = self.go([watcher(7, None)])
        stop.assert_called_once_with(7)

    def test_same_or_newer_version_left_alone(self):
        stop, spawn, msgs, gone = self.go([watcher(1, "1.12.0"), watcher(2, "1.13.0")])
        stop.assert_not_called()
        spawn.assert_not_called()
        self.assertEqual(msgs, [])

    def test_other_kinds_ignored(self):
        stop, _, _, _ = self.go([watcher(9, "0.1.0", kind="ci_watch")])
        stop.assert_not_called()

    def test_stop_pid_refuses_own_and_bad_pids(self):
        import os
        self.assertFalse(SS.stop_pid(os.getpid()))
        self.assertFalse(SS.stop_pid(None))
        self.assertFalse(SS.stop_pid(1))

    def test_stop_pid_refuses_process_that_is_not_a_watcher(self):
        with mock.patch.object(SS, "_cmdline_ok", return_value=False), mock.patch("os.kill") as kill:
            self.assertFalse(SS.stop_pid(5555))
            kill.assert_not_called()

    def test_main_reports_and_suppresses_no_heartbeat_prompt(self):
        root = make_root()
        L.update(root, lambda led: led["watchers"].append(watcher(4242, "1.0.0")))
        buf = io.StringIO()
        with mock.patch.object(SS, "stop_pid", return_value=True), mock.patch.object(SS, "spawn_watcher", return_value=True), \
                mock.patch.object(SS.H, "read_input", return_value={"cwd": str(root)}), \
                mock.patch.object(SS.H, "find_root", return_value=str(root)), \
                mock.patch.object(L, "plugin_version", return_value="9.0.0"), redirect_stdout(buf):
            SS.main()
        ctx = json.loads(buf.getvalue())["hookSpecificOutput"]["additionalContext"]
        self.assertIn("Watcher re-armed (DL98)", ctx)
        self.assertNotIn("No watcher heartbeat", ctx)

    def test_heartbeat_stamps_version(self):
        import delivery_watch as W
        self.assertEqual(W.WATCHER_VERSION, L.plugin_version())
        self.assertTrue(L.version_key("1.12.0") > L.version_key("1.11.9") > L.version_key(None))


if __name__ == "__main__":
    unittest.main()
