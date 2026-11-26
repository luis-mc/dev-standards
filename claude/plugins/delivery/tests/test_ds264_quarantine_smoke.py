"""DS264: the flake quarantine (quarantine_check.py, session hook line) and the smoke local gate (gate.json local_gate)."""
import contextlib
import importlib.util
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN = Path(__file__).resolve().parent.parent
DELIVERY = PLUGIN / "templates" / "shared" / "scripts" / "delivery"
sys.path.insert(0, str(DELIVERY))
sys.path.insert(0, str(PLUGIN / "scripts"))


def load(name):
    spec = importlib.util.spec_from_file_location(name, DELIVERY / (name + ".py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


Q = load("quarantine_check")
import delivery_common as dc  # noqa: E402

GOOD = {"test": "TestJoinsItsOwnAgent", "task": "DS300", "review": "2026-12-05", "reason": "temp dir race"}
TODAY = "2026-11-26"


def run(argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = Q.main(argv)
    return code, out.getvalue()


class QuarantineTests(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp(prefix="ds264-"))
        self.addCleanup(shutil.rmtree, self.d, True)
        self.f = self.d / "quarantine.json"

    def write(self, *entries):
        self.f.write_text(json.dumps({"tests": list(entries)}), encoding="utf-8")

    def test_valid_entry_passes_and_says_what_it_loses(self):
        self.write(GOOD)
        code, out = run(["check", "--file", str(self.f), "--today", TODAY])
        self.assertEqual(code, 0)
        self.assertEqual(len(out.strip().splitlines()), 1)
        self.assertIn("TestJoinsItsOwnAgent quarantined loses", out)
        self.assertIn("non-blocking", out)

    def test_no_task_id_fails(self):
        self.write({**GOOD, "task": ""})
        code, out = run(["check", "--file", str(self.f), "--today", TODAY])
        self.assertEqual(code, 1)
        self.assertIn("FAIL TestJoinsItsOwnAgent: quarantine has no task ID", out)

    def test_past_review_date_fails_and_today_passes(self):
        self.write({**GOOD, "review": "2026-11-25"})
        code, out = run(["check", "--file", str(self.f), "--today", TODAY])
        self.assertEqual(code, 1)
        self.assertIn("review date 2026-11-25 is past", out)
        self.write({**GOOD, "review": TODAY})
        self.assertEqual(run(["check", "--file", str(self.f), "--today", TODAY])[0], 0)

    def test_missing_or_bad_review_date_fails(self):
        for bad in (None, "soon"):
            self.write({k: v for k, v in {**GOOD, "review": bad}.items() if v is not None})
            code, out = run(["check", "--file", str(self.f), "--today", TODAY])
            self.assertEqual(code, 1)
            self.assertIn("no review date", out)

    def test_no_file_is_fine_and_prints_nothing(self):
        code, out = run(["check", "--file", str(self.d / "none.json"), "--today", TODAY])
        self.assertEqual((code, out), (0, ""))
        self.assertEqual(run(["line", "--file", str(self.d / "none.json")]), (0, "\n"))

    def test_line_and_names(self):
        self.write(GOOD, {**GOOD, "test": "TestMirror"})
        code, out = run(["line", "--file", str(self.f)])
        self.assertEqual(out.strip(), "Quarantined tests (2): TestJoinsItsOwnAgent, TestMirror")
        code, out = run(["names", "--file", str(self.f)])
        self.assertEqual(out.split(), ["TestJoinsItsOwnAgent", "TestMirror"])

    def test_session_hook_adds_one_line_only_while_an_entry_exists(self):
        import hook_session_start as S
        self.assertEqual(S._quarantine_line(self.d), "")
        (self.d / ".delivery").mkdir()
        (self.d / ".delivery" / "quarantine.json").write_text(json.dumps({"tests": [GOOD]}), encoding="utf-8")
        self.assertEqual(S._quarantine_line(self.d), "Quarantined tests (1): TestJoinsItsOwnAgent")
        (self.d / ".delivery" / "quarantine.json").write_text(json.dumps({"tests": []}), encoding="utf-8")
        self.assertEqual(S._quarantine_line(self.d), "")


E2E_STEP = {"name": "e2e", "scope": "ui-changed", "run": "e2e {e2e_specs}", "run_full": "e2e FULL"}


def ctx_for(files, local_gate=None, e2e_map=None, full=False):
    cfg = {"ui_paths": ["apps/web", "packages/ui"], "packages": {"kind": "go-modules"},
           "e2e_spec_paths": list(dc.DEFAULT_E2E_SPEC_PATHS), "widen_on": []}
    if local_gate:
        cfg["local_gate"] = local_gate
    if e2e_map:
        cfg["e2e_map"] = dc._check_e2e_map(e2e_map, "t")
    return dc.Context(root=Path("."), cfg=cfg, base_ref="origin/main", base="b", head="h", files=files,
                      packages=[], changed_dirs=[], affected_dirs=[], widened=False, full=full)


MAP = {"specs": [{"spec": "e2e/web.spec.txt", "paths": ["apps/web/"]}], "full_on": []}


class SmokeGateTests(unittest.TestCase):
    def test_default_gate_is_unchanged(self):
        go, cmd, why = dc.plan_step(E2E_STEP, ctx_for(["apps/other/a.txt", "packages/ui/a.txt"]))
        self.assertTrue(go)
        self.assertEqual(cmd, "e2e ")      # specs not derived: the whole suite, as before
        self.assertFalse(dc.smoke_gate(ctx_for([])))

    def test_smoke_runs_the_touched_specs(self):
        go, cmd, why = dc.plan_step(E2E_STEP, ctx_for(["apps/web/a.txt"], "smoke", MAP))
        self.assertEqual((go, cmd), (True, "e2e e2e/web.spec.txt"))

    def test_smoke_leaves_an_underivable_suite_to_ci(self):
        go, cmd, why = dc.plan_step(E2E_STEP, ctx_for(["packages/ui/a.txt"], "smoke"))
        self.assertFalse(go)
        self.assertIn("CI is the one full run", why)

    def test_smoke_with_a_map_that_falls_back_to_full_skips(self):
        go, cmd, why = dc.plan_step(E2E_STEP, ctx_for(["packages/ui/a.txt"], "smoke", MAP))
        self.assertFalse(go)

    def test_explicit_full_still_runs_everything(self):
        go, cmd, why = dc.plan_step(E2E_STEP, ctx_for(["packages/ui/a.txt"], "smoke", full=True))
        self.assertEqual((go, cmd), (True, "e2e FULL"))

    def test_other_steps_are_unchanged(self):
        step = {"name": "lint", "scope": "always", "run": "lint"}
        self.assertEqual(dc.plan_step(step, ctx_for(["x"], "smoke"))[:2], (True, "lint"))

    def test_branch_gate_prints_one_line(self):
        self.assertIn("CI is the one full run", dc.SMOKE_LINE)
        self.assertEqual(len(dc.SMOKE_LINE.splitlines()), 1)

    def test_load_gate_accepts_only_full_or_smoke(self):
        root = Path(tempfile.mkdtemp(prefix="ds264g-"))
        self.addCleanup(shutil.rmtree, root, True)
        gate = json.loads((PLUGIN / "templates" / "ts" / "scripts" / "delivery" / "gate.json").read_text(encoding="utf-8"))
        (root / "scripts" / "delivery").mkdir(parents=True)
        path = root / "scripts" / "delivery" / "gate.json"
        path.write_text(json.dumps(gate), encoding="utf-8")
        self.assertEqual(dc.load_gate(root)["local_gate"], "full")
        path.write_text(json.dumps({**gate, "local_gate": "smoke"}), encoding="utf-8")
        self.assertEqual(dc.load_gate(root)["local_gate"], "smoke")
        path.write_text(json.dumps({**gate, "local_gate": "half"}), encoding="utf-8")
        with self.assertRaises(dc.DeliveryError):
            dc.load_gate(root)


if __name__ == "__main__":
    unittest.main()
