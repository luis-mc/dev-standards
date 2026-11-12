"""DL270: `delivery_ci.py slots` and the doctor machine.slots check cover light slots."""
import contextlib
import io
import json
import unittest
from pathlib import Path
from unittest import mock

from _helpers import make_root
from test_machine import machine, ident, dead_pid
import machine_slots as MS
import delivery_ci as CI
import delivery_doctor as D
import load as L


def listing():
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        CI.print_slots(False)
    return buf.getvalue()


class Listing(unittest.TestCase):
    def test_free_and_held_light_slot(self):
        with machine():
            MS.write_machine_config({})
            self.assertIn("light 1  free", listing())
            MS.take_slot(ident("smoke", run=77), kind="light")
            out = [l for l in listing().splitlines() if l.startswith("light 1")]
            self.assertEqual(len(out), 1)
            self.assertIn("owner/example-app run 77 job smoke", out[0])
            self.assertIn("runner host1-pool-app1", out[0])
            self.assertIn("held", out[0])

    def test_light_slots_after_ci_slots(self):
        with machine():
            MS.write_machine_config({})
            lines = listing().splitlines()
            idx = [i for i, l in enumerate(lines) if l.startswith(("slot ", "light "))]
            self.assertTrue(lines[idx[-1]].startswith("light 1"))

    def test_zero_light_slots_prints_no_light_line(self):
        with machine():
            MS.write_machine_config({"light_slots": 0})
            self.assertNotIn("light", listing())

    def test_json_keeps_light_slots(self):
        with machine():
            MS.write_machine_config({})
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                CI.print_slots(True)
            self.assertEqual(len(json.loads(buf.getvalue())["light_slots"]), 1)


class Doctor(unittest.TestCase):
    def test_stale_light_lock_is_flagged_and_ok_line_counts_both(self):
        cfg = {"ci": {"options": {"linux": "self-hosted"}}}
        with machine(DELIVERY_RUNNER_DIRS=""):
            MS.write_machine_config({})
            L.write_host_load({"mem": 10, "cpu": 10})
            root = make_root()
            with mock.patch.object(D.H, "gh", return_value=(0, "[]")):
                _, _, items = D.check_machine(root, cfg)
            ok = {i["id"]: i for i in items}["machine.slots"]
            self.assertEqual(ok["status"], "ok")
            self.assertIn("2 CI, 1 light", ok["detail"])
            lock = MS.take_slot(ident("smoke"), kind="light")
            p = Path(MS.slot_path(lock["slot"], "light"))
            rec = json.loads(p.read_text())
            rec["pid"] = dead_pid()
            p.write_text(json.dumps(rec))
            with mock.patch.object(D.H, "gh", return_value=(0, "[]")):
                _, _, items = D.check_machine(root, cfg)
            bad = {i["id"]: i for i in items}["machine.slots"]
            self.assertEqual(bad["status"], "fail")
            self.assertIn("slot light-1 held by", bad["detail"])


if __name__ == "__main__":
    unittest.main()
