"""DL118: an old watcher that cannot be stopped is reported; dead watcher rows are pruned after 24 h."""
import io
import json
import unittest
from contextlib import redirect_stdout
from datetime import timedelta
from unittest import mock

from _helpers import L, make_root
import hook_session_start as SS
import hooklib as H


def row(pid, version, age_h=0.0, kind="delivery_watch"):
    beat = L.iso(L.utcnow() - timedelta(hours=age_h))
    return {"pid": pid, "kind": kind, "started": beat, "heartbeat_at": beat, "version": version}


def denied(*_a):
    raise PermissionError(5, "Access is denied")


class UnstoppableTests(unittest.TestCase):
    def rearm(self, rows, kill=denied, alive=True, installed="1.12.0"):
        root = make_root()
        L.update(root, lambda led: led["watchers"].extend(rows))
        with mock.patch("os.kill", side_effect=kill), mock.patch("machine_slots.pid_alive", return_value=alive), \
                mock.patch.object(SS, "_cmdline_ok", return_value=True), \
                mock.patch.object(SS, "spawn_watcher", return_value=True) as spawn:
            msgs, gone = SS.rearm_old_watchers(str(root), H.load_ledger(str(root)), installed, L.utcnow(), 10)
        return spawn, msgs, gone

    def test_access_denied_warns_and_still_starts_watcher(self):
        spawn, msgs, gone = self.rearm([row(4242, None)])
        spawn.assert_called_once()
        self.assertEqual(list(gone), [])
        self.assertEqual(gone.failed, [4242])
        text = " ".join(gone.warnings)
        self.assertIn("delivery_watch pid 4242 (plugin unstamped) could not be stopped", text)
        self.assertIn("Access is denied", text)
        self.assertIn("Stop-Process -Id 4242" if SS.os.name == "nt" else "kill 4242", text)

    def test_admin_command_text(self):
        with mock.patch.object(SS.os, "name", "nt"):
            self.assertIn("Administrator shell on Windows: Stop-Process -Id 9", SS.stop_hint(9))
        with mock.patch.object(SS.os, "name", "posix"):
            self.assertIn("kill 9", SS.stop_hint(9))

    def test_dead_unstamped_row_is_not_warned_about(self):
        spawn, msgs, gone = self.rearm([row(4242, None)], alive=False)
        self.assertEqual(gone.failed, [])
        self.assertEqual(gone.warnings, [])
        spawn.assert_not_called()

    def test_stale_failed_row_is_not_warned_about(self):
        _, _, gone = self.rearm([row(4242, None, age_h=3)])
        self.assertEqual(gone.warnings, [])

    def test_stoppable_row_still_stopped(self):
        spawn, msgs, gone = self.rearm([row(4242, "1.0.0")], kill=lambda *a: None)
        self.assertEqual(list(gone), [4242])
        self.assertEqual(gone.failed, [])
        spawn.assert_called_once()

    def test_main_prints_warning_each_session(self):
        root = make_root()
        L.update(root, lambda led: led["watchers"].append(row(4242, None)))
        for _ in range(2):
            buf = io.StringIO()
            with mock.patch("os.kill", side_effect=denied), mock.patch("machine_slots.pid_alive", return_value=True), \
                    mock.patch.object(SS, "_cmdline_ok", return_value=True), \
                    mock.patch.object(SS, "spawn_watcher", return_value=True), \
                    mock.patch.object(SS.H, "read_input", return_value={"cwd": str(root)}), \
                    mock.patch.object(SS.H, "find_root", return_value=str(root)), \
                    mock.patch.object(L, "plugin_version", return_value="9.0.0"), redirect_stdout(buf):
                SS.main()
            ctx = json.loads(buf.getvalue())["hookSpecificOutput"]["additionalContext"]
            self.assertIn("pid 4242 (plugin unstamped) could not be stopped", ctx)

    def test_main_prunes_dead_old_row(self):
        root = make_root()
        L.update(root, lambda led: led["watchers"].extend([row(11, None, age_h=48), row(12, "9.0.0")]))
        buf = io.StringIO()
        with mock.patch("machine_slots.pid_alive", return_value=False), \
                mock.patch.object(SS.H, "read_input", return_value={"cwd": str(root)}), \
                mock.patch.object(SS.H, "find_root", return_value=str(root)), \
                mock.patch.object(L, "plugin_version", return_value="9.0.0"), redirect_stdout(buf):
            SS.main()
        self.assertEqual([w["pid"] for w in H.load_ledger(str(root))["watchers"]], [12])
        self.assertNotIn("could not be stopped", buf.getvalue())


class PruneTests(unittest.TestCase):
    def test_prune_rule(self):
        led = {"watchers": [row(1, None, 30), row(2, None, 30), row(3, None, 1), row(4, None, 30, kind="ci_watch")]}
        n = L.prune_watchers(led, L.utcnow(), lambda pid: pid == 2)
        self.assertEqual(n, 1)
        self.assertEqual([w["pid"] for w in led["watchers"]], [2, 3, 4])

    def test_fresh_row_never_pruned_even_if_dead(self):
        led = {"watchers": [row(3, None, 0.5)]}
        self.assertEqual(L.prune_watchers(led, L.utcnow(), lambda pid: False), 0)

    def test_heartbeat_prunes_old_dead_rows(self):
        import delivery_watch as W
        root = make_root()
        L.update(root, lambda led: led["watchers"].extend([row(11, None, 30), row(12, "1.0.0", 0.1)]))
        w = W.Watcher(root) if hasattr(W, "Watcher") else None
        self.assertIsNotNone(w)
        with mock.patch("machine_slots.pid_alive", return_value=False):
            w.heartbeat(L.iso())
        pids = [x["pid"] for x in L.load(root)["watchers"]]
        self.assertNotIn(11, pids)
        self.assertIn(12, pids)


if __name__ == "__main__":
    unittest.main()
