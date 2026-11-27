"""DS287 R5.95: a push of a merge commit carries what the merged pull request proved."""
import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

DELIVERY = Path(__file__).resolve().parent.parent / "templates" / "shared" / "scripts" / "delivery"
TEMPLATES = Path(__file__).resolve().parent.parent / "templates"
sys.path.insert(0, str(DELIVERY))
spec = importlib.util.spec_from_file_location("carry_plan", DELIVERY / "carry_plan.py")
CP = importlib.util.module_from_spec(spec)
spec.loader.exec_module(CP)

DEFS = {"unit": {"name": "unit"}, "e2e": {"name": "e2e"}, "release": {"name": "release"}}
KEYS = list(DEFS)
CMAP = {"areas": {"web": {"paths": ["web/**"], "jobs": ["e2e"]}, "core": {"paths": ["core/**"], "jobs": ["unit"]}},
        "docs": ["docs/**"]}
RUNS = [{"id": 1, "head_sha": "prhead", "status": "completed", "created_at": "2026-11-27T10:00:00Z", "html_url": "u1"}]


def jobs(_rid):
    return [{"name": "unit", "conclusion": "success"}, {"name": "e2e", "conclusion": "success"},
            {"name": "release", "conclusion": "skipped"}]


def plan(paths, always=(), runs=RUNS):
    return CP.push_plan(KEYS, DEFS, runs, "merge", jobs, lambda _p: paths, CMAP, None, None, list(always))


class PushPlan(unittest.TestCase):
    def test_same_tree_carries_every_proven_job(self):
        r = plan([])
        self.assertEqual(sorted(r["carried"]), ["e2e", "unit"])
        self.assertEqual(r["run"], ["release"])  # no proof on the PR: it runs

    def test_differing_tree_runs_only_reached_jobs(self):
        r = plan(["web/app.ts"])
        self.assertIn("e2e", r["run"])
        self.assertIn("unit", r["carried"])

    def test_always_runs(self):
        r = plan([], always=["unit"])
        self.assertIn("unit", r["run"])
        self.assertNotIn("unit", r["carried"])

    def test_no_pr_run_runs_everything(self):
        self.assertEqual(plan([], runs=[])["run"], KEYS)

    def test_tree_diff_on_git(self):
        with tempfile.TemporaryDirectory() as d:
            g = lambda *a: subprocess.run(["git", "-C", d, *a], check=True, capture_output=True, text=True).stdout.strip()
            g("init", "-q"); g("config", "user.email", "t@e"); g("config", "user.name", "t")
            Path(d, "a.txt").write_text("1"); g("add", "."); g("commit", "-qm", "a"); head = g("rev-parse", "HEAD")
            g("commit", "-q", "--allow-empty", "-m", "merge-like"); same = g("rev-parse", "HEAD")
            self.assertEqual(CP.tree_diff(d, head, same), [])
            Path(d, "b.txt").write_text("2"); g("add", "."); g("commit", "-qm", "b")
            self.assertEqual(CP.tree_diff(d, head, g("rev-parse", "HEAD")), ["b.txt"])


class Wiring(unittest.TestCase):
    def test_action_plans_default_branch_push(self):
        a = (TEMPLATES / "shared/.github/actions/carry-plan/action.yml").read_text(encoding="utf-8")
        self.assertIn('[ "$EVENT" = push ] && [ "$REF_NAME" = "$DEFAULT_BRANCH" ]', a)
        self.assertIn("--push --sha \"$PUSH_SHA\"", a)

    def test_carry_jobs_may_read_pull_requests(self):
        for f in TEMPLATES.rglob("*.yml"):
            s = f.read_text(encoding="utf-8")
            if "actions/carry-plan" in s:
                self.assertIn("pull-requests: read", s, f)


if __name__ == "__main__":
    unittest.main()
