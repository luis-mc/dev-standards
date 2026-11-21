"""DS235d: lifecycle release check (LC-32) and opt-out report (LC-27), with the session hook line."""
import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path

DELIVERY = Path(__file__).resolve().parent.parent / "templates" / "shared" / "scripts" / "delivery"


def load(name):
    spec = importlib.util.spec_from_file_location(name, DELIVERY / (name + ".py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


R = load("lifecycle_release_check")
O = load("lifecycle_optout")

TARGETS = [{"os": "windows", "distro": None, "arch": "x64", "package": "msi"},
           {"os": "linux", "distro": "fedora", "arch": "x64", "package": "rpm"}]


class Release(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp(prefix="ds235d-"))
        self.addCleanup(shutil.rmtree, self.d, True)
        self.lc = self.d / "lifecycle.json"
        self.lc.write_text(json.dumps({"product": "Demo", "targets": TARGETS}))
        self.res = self.d / "results"
        self.res.mkdir()

    def result(self, lane, arch, pkg, status="pass"):
        (self.res / (lane + ".json")).write_text(json.dumps(
            {"lane": lane, "arch": arch, "package": pkg, "status": status, "failed": [] if status == "pass" else ["LC-9"]}))

    def check(self, *extra):
        return R.main(["check", "--lifecycle", str(self.lc), "--results", str(self.res), *extra])

    def test_all_green_passes(self):
        self.result("windows", "x64", "msi")
        self.result("fedora", "x64", "rpm")
        self.assertEqual(self.check("--release"), 0)

    def test_missing_lane_fails(self):
        self.result("windows", "x64", "msi")
        self.assertEqual(self.check("--release"), 1)

    def test_red_lane_fails(self):
        self.result("windows", "x64", "msi")
        self.result("fedora", "x64", "rpm", "fail")
        self.assertEqual(self.check("--release"), 1)

    def test_unlisted_target_not_required(self):
        self.lc.write_text(json.dumps({"product": "Demo", "targets": TARGETS[:1]}))
        self.result("windows", "x64", "msi")
        self.assertEqual(self.check("--release"), 0)

    def test_not_a_release_pr_needs_nothing(self):
        self.assertEqual(self.check(), 0)

    def test_write_result(self):
        steps = self.d / "steps.txt"
        steps.write_text("LC-9 PASS ok\nLC-8 PASS ok\n")
        out = self.d / "r.json"
        R.main(["write-result", "--lane", "fedora", "--arch", "x64", "--package", "rpm", "--steps", str(steps), "--out", str(out)])
        self.assertEqual(json.loads(out.read_text())["status"], "pass")
        steps.write_text("LC-9 PASS ok\nLC-8 FAIL no\n")
        R.main(["write-result", "--lane", "fedora", "--arch", "x64", "--package", "rpm", "--steps", str(steps), "--out", str(out)])
        r = json.loads(out.read_text())
        self.assertEqual((r["status"], r["failed"]), ("fail", ["LC-8"]))
        steps.write_text("")
        R.main(["write-result", "--lane", "fedora", "--arch", "x64", "--package", "rpm", "--steps", str(steps), "--out", str(out)])
        self.assertEqual(json.loads(out.read_text())["status"], "fail")

    def test_artifact_names(self):
        ok = ["Demo-1.2.0-win-x64.msi", "Demo-1.2.0-linux-x64.rpm"]
        self.assertEqual(R.check_names("Demo", TARGETS, ok), [])
        self.assertTrue(R.check_names("Demo", TARGETS, ["Demo-1.2.0-x64.msi", "Demo-1.2.0-linux-x64.rpm"]))
        self.assertTrue(R.check_names("Demo", TARGETS, ok + ["Demo-1.2.0-linux-x64.deb"]))

    def test_stores_separate(self):
        self.assertTrue(R.check_stores({}))
        s = {"lifecycle": {"stores": {"public_packages": "a", "private_data": "a"}}}
        self.assertTrue(R.check_stores(s))
        s["lifecycle"]["stores"]["private_data"] = "b"
        self.assertEqual(R.check_stores(s), [])


class Optout(unittest.TestCase):
    def cfg(self, **entry):
        return {"lifecycle": {"off": {"LC-16": entry}}}

    GOOD = {"decision": "D9", "reason": "no tray yet", "review": "2027-06-01"}

    def test_complete_optout_passes(self):
        self.assertEqual(O.problems(self.cfg(**self.GOOD), O.parse_day("2027-01-01")), [])

    def test_missing_decision_fails(self):
        e = dict(self.GOOD)
        del e["decision"]
        self.assertTrue(any("decision" in p for p in O.problems(self.cfg(**e), O.parse_day("2027-01-01"))))

    def test_past_review_fails(self):
        self.assertTrue(any("past" in p for p in O.problems(self.cfg(**self.GOOD), O.parse_day("2027-07-01"))))

    def test_missing_review_or_reason_fails(self):
        e = {"decision": "D9"}
        text = " ".join(O.problems(self.cfg(**e), O.parse_day("2027-01-01")))
        self.assertIn("reason", text)
        self.assertIn("review date", text)

    def test_impact_text_for_every_check(self):
        for n in list(range(8, 22)) + [29, 32, 33]:
            self.assertIn("LC-%d" % n, O.IMPACT)
            self.assertTrue(O.IMPACT["LC-%d" % n].strip())
        lines = O.impact_lines({"lifecycle": {"off": {"LC-9": self.GOOD, "LC-15": self.GOOD}}})
        self.assertEqual(len(lines), 2)
        self.assertIn("LC-15 off loses: purge", lines[1])

    def test_cli_exit_codes(self):
        d = Path(tempfile.mkdtemp(prefix="ds235d-"))
        self.addCleanup(shutil.rmtree, d, True)
        c = d / "config.json"
        c.write_text(json.dumps(self.cfg(**self.GOOD)))
        self.assertEqual(O.main(["check", "--config", str(c), "--today", "2027-01-01"]), 0)
        self.assertEqual(O.main(["check", "--config", str(c), "--today", "2028-01-01"]), 1)
        self.assertEqual(O.main(["check", "--config", str(d / "none.json")]), 0)

    def test_hook_line(self):
        self.assertEqual(O.hook_line({}), "")
        self.assertEqual(O.hook_line({"lifecycle": {"off": {"LC-9": {}, "LC-16": {}}}}), "Lifecycle checks off: LC-9, LC-16")

    def test_session_hook_adds_line(self):
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
        import hook_session_start as S
        d = Path(tempfile.mkdtemp(prefix="ds235d-"))
        self.addCleanup(shutil.rmtree, d, True)
        self.assertEqual(S._lifecycle_off_line({}, d), "")
        (d / ".delivery").mkdir()
        (d / ".delivery" / "config.json").write_text(json.dumps(self.cfg(**self.GOOD)))
        self.assertEqual(S._lifecycle_off_line({}, d), "Lifecycle checks off: LC-16")


if __name__ == "__main__":
    unittest.main()
