import json
import multiprocessing
import os
import subprocess
import sys
import unittest
from datetime import datetime, timedelta, timezone

from _helpers import L, SCRIPTS, make_root


def _bump(args):
    root, n = args
    for _ in range(n):
        L.update(root, lambda led: led["events"].append({"at": L.iso(), "kind": "x", "ref": "", "by": "t"}))


class LedgerTests(unittest.TestCase):
    def test_update_creates_file_with_schema_and_no_temp_left(self):
        root = make_root()
        L.update(root, lambda led: L.new_train(led, "release/1"))
        data = json.loads(L.ledger_path(root).read_text())
        self.assertEqual(data["schema"], 1)
        self.assertEqual(data["trains"][0]["branch"], "release/1")
        left = [p.name for p in (root / ".delivery").iterdir()]
        self.assertEqual(left, ["ledger.json"])  # no .tmp, no .lock

    def test_failed_update_leaves_old_file_intact(self):
        root = make_root()
        L.update(root, lambda led: L.new_train(led, "release/1"))
        before = L.ledger_path(root).read_text()

        def boom(led):
            led["trains"].clear()
            raise RuntimeError("x")
        with self.assertRaises(RuntimeError):
            L.update(root, boom)
        self.assertEqual(L.ledger_path(root).read_text(), before)
        self.assertFalse(any(p.suffix in (".tmp", ".lock") for p in (root / ".delivery").iterdir()))

    def test_concurrent_writers_lose_nothing(self):
        root = make_root()
        with multiprocessing.get_context("spawn").Pool(4) as pool:
            pool.map(_bump, [(str(root), 15)] * 4)
        self.assertEqual(len(L.load(root)["events"]), 60)

    def test_lock_busy_raises_and_stale_lock_is_broken(self):
        root = make_root()
        lock = L.ledger_path(root).with_suffix(".json.lock")
        lock.write_text("1")
        with self.assertRaises(L.LedgerError):
            with L.locked(root, wait=0.1):
                pass
        old = os.stat(lock).st_mtime - 120
        os.utime(lock, (old, old))
        with L.locked(root, wait=1):
            pass

    def test_events_capped_at_500(self):
        root = make_root()

        def fn(led):
            for i in range(520):
                L.add_event(led, "k", str(i))
        led = L.update(root, fn)
        self.assertEqual(len(led["events"]), 500)
        self.assertEqual(led["events"][-1]["ref"], "519")

    def test_phases_derived_from_timestamps_with_gaps_implied(self):
        t = {"created_at": "2026-10-14T10:00:00Z", "joined_at": "2026-10-14T10:10:00Z",
             "pushed_at": "2026-10-14T10:30:00Z", "green_at": "2026-10-14T10:50:00Z",
             "merged_at": "2026-10-14T10:55:00Z", "live_at": None, "smoke": {}}
        actual = L.derive_phases(t)
        self.assertEqual([p["name"] for p in actual], ["join", "ci", "merge"])
        self.assertEqual(actual[1], {"name": "ci", "start": "2026-10-14T10:30:00Z", "end": "2026-10-14T10:50:00Z"})
        # the 10:10-10:30 gap is not a phase
        self.assertNotIn("gap", [p["name"] for p in actual])

    def test_phase_with_end_before_start_is_dropped_and_actual_is_rewritten(self):
        t = {"pushed_at": "2026-10-14T11:00:00Z", "green_at": "2026-10-14T10:00:00Z",
             "phases": {"planned": [], "actual": [{"name": "typed", "start": "a", "end": "b"}]}}
        self.assertEqual(L.derive_phases(t), [])
        self.assertEqual(t["phases"]["actual"], [])

    def test_update_derives_phases(self):
        root = make_root()

        def fn(led):
            t = L.new_train(led, "release/2")
            t["pushed_at"], t["green_at"] = "2026-10-14T10:00:00Z", "2026-10-14T10:20:00Z"
        led = L.update(root, fn)
        self.assertEqual(led["trains"][0]["phases"]["actual"][0]["name"], "ci")

    def test_train_id_uses_owner_timezone_day(self):
        cfg = {"tz": "Europe/Lisbon"}
        led = L.empty_ledger()
        late = datetime(2026, 10, 14, 23, 30, tzinfo=timezone.utc)  # 00:30 on the 15th in Lisbon (WEST, UTC+1)
        t = L.new_train(led, "release/3", cfg=cfg, now=late)
        self.assertEqual(t["id"], "T-2026-10-15-01")
        t2 = L.new_train(led, "release/4", cfg=cfg, now=late)
        self.assertEqual(t2["id"], "T-2026-10-15-02")

    def test_record_is_best_effort(self):
        self.assertFalse(L.record(None, "event", kind="x"))
        self.assertFalse(L.record("/nonexistent/path", "event", kind="x"))
        root = make_root()
        self.assertTrue(L.record(root, "event", kind="hello", ref="r", by="t"))
        self.assertEqual(L.load(root)["events"][-1]["kind"], "hello")

    def test_record_ci_matches_by_sha_and_moves_state(self):
        root = make_root()
        L.update(root, lambda led: L.new_train(led, "release/5").update(state="ci", ci={"head_sha": "abcdef1234", "run_ids": [], "state": "running", "started_at": None}))
        self.assertTrue(L.record(root, "ci", sha="abcdef1", state="success"))
        t = L.load(root)["trains"][0]
        self.assertEqual((t["state"], t["ci"]["state"]), ("green", "success"))
        self.assertIsNotNone(t["green_at"])

    def test_hold_active_respects_until(self):
        now = datetime(2026, 10, 14, 12, tzinfo=timezone.utc)
        self.assertFalse(L.hold_active({"hold": None}, now))
        self.assertTrue(L.hold_active({"hold": {"reason": "r", "by": "owner"}}, now))
        self.assertTrue(L.hold_active({"hold": {"reason": "r", "by": "owner", "until": "2026-10-14T13:00:00Z"}}, now))
        self.assertFalse(L.hold_active({"hold": {"reason": "r", "by": "owner", "until": "2026-10-14T11:00:00Z"}}, now))


class CliTests(unittest.TestCase):
    def run_cli(self, root, *args):
        return subprocess.run([sys.executable, str(SCRIPTS / "delivery_ledger.py"), "--root", str(root), *args],
                              capture_output=True, text=True)

    def test_plan_hold_measure_show(self):
        root = make_root({"tz": "Europe/Lisbon"})
        p = self.run_cli(root, "plan", "--branch", "release/29", "--release-no", "29", "--cargo", "DV148:DV148-fix:409")
        self.assertEqual(p.returncode, 0, p.stderr)
        tid = p.stdout.strip()
        self.assertTrue(tid.startswith("T-"))
        self.assertEqual(self.run_cli(root, "hold", "--train", tid).returncode, 1)  # reason required
        self.assertEqual(self.run_cli(root, "hold", "--train", tid, "--reason", "owner says wait").returncode, 0)
        self.assertEqual(L.load(root)["trains"][0]["hold"]["reason"], "owner says wait")
        self.assertEqual(self.run_cli(root, "hold", "--train", tid, "--release").returncode, 0)
        self.assertIsNone(L.load(root)["trains"][0]["hold"])
        self.assertEqual(self.run_cli(root, "measure", "--train", tid, "--state", "clean", "--report", "r.json").returncode, 0)
        self.assertEqual(L.load(root)["trains"][0]["measure"]["state"], "clean")
        s = self.run_cli(root, "show")
        self.assertIn(tid, s.stdout)
        self.assertEqual(json.loads(self.run_cli(root, "show", "--json").stdout)["trains"][0]["cargo"][0]["pr"], 409)

    def test_unknown_train_is_an_error(self):
        root = make_root()
        self.assertEqual(self.run_cli(root, "measure", "--train", "nope", "--state", "clean").returncode, 1)


class SchemaTests(unittest.TestCase):
    def test_schema_loads_and_lists_every_top_level_section(self):
        schema = json.load(open(SCRIPTS.parent / "references" / "ledger-schema.json"))
        for key in L.empty_ledger():
            if key not in ("updated_at", "config_ref", "schema"):
                self.assertIn(key, schema["properties"])
        self.assertEqual(schema["properties"]["events"]["maxItems"], 500)
        self.assertEqual(set(schema["properties"]["trains"]["items"]["properties"]["state"]["enum"]), set(L.TRAIN_STATES))


if __name__ == "__main__":
    unittest.main()
