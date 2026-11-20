"""DL378: ci_watch does not cancel a red run while jobs still run (D105, DL-97). Stubbed gh."""
import sys
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "templates" / "shared" / "scripts" / "delivery"))

import test_dl306_red_run_cancel as base  # noqa: E402

cw = base.cw
run, FakeGh, watch = base.run, base.FakeGh, base.watch


def two_phase(fake, final):
    """gh stub: first run list shows the live runs; later lists show the finished runs."""
    polls = {"n": 0}

    def handler(args):
        if args[:2] == ["run", "list"]:
            polls["n"] += 1
            if polls["n"] >= 3:
                return final
        return fake(args)
    return mock.Mock(side_effect=handler), polls


def cancels(stub):
    return [c for c in stub.call_args_list if c.args[0][:2] == ["run", "cancel"]]


FINAL = [run(1, "completed", "failure"), run(2, "completed", "failure", "lint")]


def jobs_with(name, step=None):
    failed = {"name": name, "status": "completed", "conclusion": "failure",
              "steps": [{"name": step, "conclusion": "failure"}] if step else []}
    return {1: [failed, {"name": "web", "status": "in_progress", "conclusion": None}],
            2: [{"name": "lint", "status": "in_progress", "conclusion": None}]}


class RedFinishes(unittest.TestCase):
    def test_default_does_not_cancel_and_waits(self):
        fake = FakeGh("release/1.2", jobs=jobs_with("setup"))
        stub, polls = two_phase(fake, FINAL)
        code, out = watch(stub, config=cw.load_cancel_config("/nonexistent.json", Path("/nonexistent")))
        self.assertEqual(code, 1)
        self.assertEqual(cancels(stub), [])
        self.assertGreaterEqual(polls["n"], 3)
        self.assertIn("FAILED job: setup", out)
        self.assertIn("waiting for the other jobs", out)

    def test_all_failed_jobs_reported_at_end(self):
        fake = FakeGh("release/1.2", jobs=jobs_with("rust"))
        stub, _ = two_phase(fake, FINAL)
        code, out = watch(stub, config=(False, r"^release/"))
        self.assertEqual(code, 1)
        self.assertIn("run 1 (ci", out)
        self.assertIn("run 2 (lint", out)

    def test_non_blocking_failure_warns_and_waits(self):
        fake = FakeGh("release/1.2", jobs=jobs_with("rust", "Run tests"))
        stub, polls = two_phase(fake, FINAL)
        code, out = watch(stub, config=(True, r"^release/"))
        self.assertEqual(code, 1)
        self.assertEqual(cancels(stub), [])
        self.assertIn("D105", out)
        self.assertGreaterEqual(polls["n"], 3)

    def test_blocking_job_name_cancels(self):
        fake = FakeGh("release/1.2", jobs=jobs_with("setup"))
        code, out = watch(fake, config=(True, r"^release/"))
        self.assertEqual(code, 1)
        self.assertEqual(sorted(fake.cancelled()), ["1", "2"])
        self.assertIn("push freeze lifted", out)

    def test_blocking_step_cancels(self):
        fake = FakeGh("release/1.2", jobs=jobs_with("rust", "Install dependencies"))
        code, _ = watch(fake, config=(True, r"^release/"))
        self.assertEqual(code, 1)
        self.assertEqual(sorted(fake.cancelled()), ["1", "2"])

    def test_cancel_flag_cancels_blocking(self):
        fake = FakeGh("release/1.2", jobs=jobs_with("checkout"))
        code, _ = watch(fake, ["--cancel-on-red"], config=(False, r"^release/"))
        self.assertEqual(code, 1)
        self.assertEqual(sorted(fake.cancelled()), ["1", "2"])

    def test_agent_branch_blocking_not_cancelled(self):
        fake = FakeGh("DL1-task", jobs=jobs_with("setup"))
        stub, _ = two_phase(fake, FINAL)
        code, _ = watch(stub, ["--cancel-on-red"], config=(True, r"^release/"))
        self.assertEqual(code, 1)
        self.assertEqual(cancels(stub), [])

    def test_blocking_re_from_config(self):
        import json
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "c.json"
            self.assertEqual(cw.load_blocking_re(str(p), Path(d)), cw.BLOCKING_JOB_RE)
            p.write_text(json.dumps({"ci_watch": {"blocking_job_re": "^boot"}}), encoding="utf-8")
            self.assertEqual(cw.load_blocking_re(str(p), Path(d)), "^boot")
        self.assertTrue(cw.is_blocking([{"name": "boot x"}], "^boot"))
        self.assertFalse(cw.is_blocking([{"name": "rust"}], cw.BLOCKING_JOB_RE))


if __name__ == "__main__":
    unittest.main()
