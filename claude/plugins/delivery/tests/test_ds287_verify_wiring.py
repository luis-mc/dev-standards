"""DS287 (R5.88, R5.91): carry_verify.py, the carry-plan action, and the wiring in the shipped workflow templates."""
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

PLUGIN = Path(__file__).resolve().parent.parent
TPL = PLUGIN / "templates"
VERIFY = TPL / "shared" / "scripts" / "delivery" / "carry_verify.py"
ACTION = TPL / "shared" / ".github" / "actions" / "carry-plan" / "action.yml"

# workflow file -> jobs that must be gated by the plan
WORKFLOWS = {
    "ts/.github/workflows/ci.yml": ["verify", "integration", "integration-pool", "e2e-shard"],
    "go/.github/workflows/ci.yml": ["verify", "integration"],
    "rust/.github/workflows/ci.yml": ["verify", "integration", "integration-pool"],
    "dotnet/.github/workflows/ci.yml": ["verify", "integration"],
    "ts/.github/workflows/package.yml": ["package"],
    "go/.github/workflows/package.yml": ["package"],
    "rust/.github/workflows/package.yml": ["package"],
    "dotnet/.github/workflows/package.yml": ["package"],
    "shared/.github/workflows/package-windows.yml": ["build"],
    "shared/.github/workflows/windows-msi-check.yml": ["msi"],
}
# the job that calls carry_verify.py (workflow -> job)
VERIFY_JOB = {k: ("e2e" if k == "ts/.github/workflows/ci.yml" else "carry-ok") for k in WORKFLOWS}


def run_verify(needs, carried, summary=None):
    args = [sys.executable, str(VERIFY), "--needs", json.dumps(needs), "--carried", json.dumps(carried)]
    if summary:
        args += ["--summary", summary]
    return subprocess.run(args, capture_output=True, text=True)


def res(**kw):
    return {k: {"result": v} for k, v in kw.items()}


class CarryVerify(unittest.TestCase):
    def test_all_success_passes(self):
        self.assertEqual(run_verify(res(a="success", b="success"), {}).returncode, 0)

    def test_carried_skip_passes(self):
        carried = {"b": {"sha": "abcdef1234", "run_url": "https://x/runs/1"}}
        self.assertEqual(run_verify(res(a="success", b="skipped"), carried).returncode, 0)

    def test_uncarried_skip_fails(self):
        p = run_verify(res(a="success", b="skipped"), {"c": {"sha": "1", "run_url": "u"}})
        self.assertEqual(p.returncode, 1)
        self.assertIn("b", p.stdout)

    def test_failure_fails_even_when_carried(self):
        carried = {"b": {"sha": "1", "run_url": "u"}}
        self.assertEqual(run_verify(res(a="success", b="failure"), carried).returncode, 1)
        self.assertEqual(run_verify(res(a="cancelled"), {}).returncode, 1)

    def test_ignore_leaves_a_job_out(self):
        p = subprocess.run([sys.executable, str(VERIFY), "--needs", json.dumps(res(a="success", plan="skipped")),
                            "--carried", "{}", "--ignore", "plan"], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0)

    def test_summary_table(self):
        carried = {"b": {"sha": "abcdef1234", "run_url": "https://x/runs/1"}}
        with tempfile.TemporaryDirectory() as d:
            f = str(Path(d) / "s.md")
            run_verify(res(a="success", b="skipped", c="failure"), carried, f)
            text = Path(f).read_text()
        self.assertIn("| job | result | proved by |", text)
        self.assertIn("| a | success |", text)
        self.assertIn("[abcdef1](https://x/runs/1)", text)  # carried job links to the proof run
        self.assertRegex(text, r"\| c \| failure \(not passed\)")


class Templates(unittest.TestCase):
    def doc(self, rel):
        return yaml.safe_load((TPL / rel).read_text(encoding="utf-8"))

    def test_each_template_parses(self):
        for rel in WORKFLOWS:
            self.assertIsInstance(self.doc(rel).get("jobs"), dict, rel)
        self.assertIn("runs", self.doc("shared/.github/actions/carry-plan/action.yml"))

    def test_gated_jobs_name_the_plan(self):
        for rel, jobs in WORKFLOWS.items():
            doc = self.doc(rel)
            for job in jobs:
                cond = str(doc["jobs"][job].get("if", ""))
                self.assertIn("carry_plan", cond, f"{rel}:{job} if does not read the carry plan")
                self.assertIn(f"run_{job}", cond, f"{rel}:{job} if does not name run_{job}")
                self.assertIn("'false'", cond, f"{rel}:{job}")

    def test_plan_job_runs_the_action_with_full_history(self):
        for rel in WORKFLOWS:
            doc = self.doc(rel)
            jobs = [j for j in doc["jobs"].values()
                    if any(str(s.get("uses", "")).endswith(".github/actions/carry-plan") for s in j.get("steps", []))]
            self.assertEqual(len(jobs), 1, rel)
            checkout = jobs[0]["steps"][0]
            self.assertEqual(checkout["with"]["fetch-depth"], 0, rel)

    def test_verify_job_calls_carry_verify(self):
        for rel, job in VERIFY_JOB.items():
            body = json.dumps(self.doc(rel)["jobs"][job])
            self.assertIn("carry_verify.py", body, f"{rel}:{job}")
            self.assertIn("toJSON(needs)", body, f"{rel}:{job}")
            self.assertIn("carried", body, f"{rel}:{job}")

    def test_verify_job_always_runs(self):
        for rel, job in VERIFY_JOB.items():
            cond = str(self.doc(rel)["jobs"][job].get("if", ""))
            self.assertTrue("always()" in cond or "!cancelled()" in cond, f"{rel}:{job}")

    def test_action_falls_back_to_everything_runs(self):
        text = ACTION.read_text(encoding="utf-8")
        for name in ("workflow", "map", "github-token"):
            self.assertRegex(text, rf"(?m)^  {name}:")
        for name in ("run", "carried", "reason", "plan"):
            self.assertRegex(text, rf"(?m)^  {name}:")
        self.assertIn("carry_plan.py", text)
        self.assertIn("::warning::", text)
        self.assertIn("pull_request", text)

    def test_snippet_shows_the_pattern(self):
        text = (TPL / "ci-snippets" / "ci-areas-pattern.yml").read_text(encoding="utf-8")
        self.assertIn("carry_plan", text)
        self.assertIn("carry_verify.py", text)
        yaml.safe_load(text)


if __name__ == "__main__":
    unittest.main()
