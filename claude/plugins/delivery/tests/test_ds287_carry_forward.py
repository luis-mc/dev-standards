"""DS287 (R5.88-R5.93): carry_plan.py planner, area_select valves, --carry, carry_replay.py. No network."""
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

DELIVERY = Path(__file__).resolve().parent.parent / "templates" / "shared" / "scripts" / "delivery"
sys.path.insert(0, str(DELIVERY))


def load(name):
    spec = importlib.util.spec_from_file_location(name, DELIVERY / (name + ".py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


AS = load("area_select")
CP = load("carry_plan")
CR = load("carry_replay")
CS = load("ci_scope")
CA = load("changed_areas")

WORKFLOW = """name: CI
on: pull_request
jobs:
  plan:
    runs-on: ubuntu-latest
    steps:
      - run: python scripts/delivery/carry_plan.py
  web:
    name: web tests
    runs-on: ubuntu-latest
    steps:
      - run: python scripts/ci/web_check.py
  api:
    name: api tests (${{ matrix.shard }})
    runs-on: ubuntu-latest
    steps:
      - run: go test ./...
  ci_tests:
    runs-on: ubuntu-latest
    steps:
      - run: pytest scripts
"""
KEYS = ["plan", "web", "api", "ci_tests"]
CMAP = {
    "jobs": ["web", "api", "ci_tests"],
    "always_jobs": [],
    "run_everything": [".github/**", "scripts/**/*.sh"],
    "docs": ["docs/**", "**/*.md"],
    "areas": {
        "web": {"paths": ["apps/web/**"], "jobs": ["web"]},
        "api": {"paths": ["apps/api/**"], "jobs": ["api"]},
        "ci_tests": {"paths": ["tests/ci/**"], "jobs": ["ci_tests"]},
    },
}
DEFS = AS.parse_workflow_jobs(WORKFLOW)


def git(repo, *args):
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    assert r.returncode == 0, (args, r.stderr)
    return r.stdout.strip()


class Repo:
    def __init__(self, test):
        self.dir = Path(tempfile.mkdtemp(prefix="ds287-"))
        test.addCleanup(shutil.rmtree, self.dir, True)
        git(self.dir, "init", "-q", "-b", "main")
        git(self.dir, "config", "user.email", "t@example.com")
        git(self.dir, "config", "user.name", "T")
        git(self.dir, "config", "commit.gpgsign", "false")
        self.n = 0
        self.commit({"README.md": "x", "apps/web/a.ts": "1", "apps/api/a.go": "1"}, "base")
        git(self.dir, "update-ref", "refs/remotes/origin/main", "HEAD")

    def commit(self, files, msg=None):
        for p, text in files.items():
            f = self.dir / p
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(text)
        git(self.dir, "add", "-A")
        self.n += 1
        git(self.dir, "commit", "-q", "-m", msg or f"c{self.n}")
        return git(self.dir, "rev-parse", "HEAD")

    def paths(self, head, proof):
        return CP.changed_paths_since(str(self.dir), "origin/main", head, proof)


class Planner(unittest.TestCase):
    def test_linear_fix_push_counts_only_new_commit(self):
        r = Repo(self)
        r.git = lambda *a: git(r.dir, *a)
        git(r.dir, "checkout", "-q", "-b", "pr")
        p = r.commit({"apps/web/a.ts": "2"})
        h = r.commit({"apps/api/a.go": "2"})
        self.assertEqual(r.paths(h, p), ["apps/api/a.go"])

    def test_rebase_keeps_proof_for_identical_commits(self):
        r = Repo(self)
        git(r.dir, "checkout", "-q", "-b", "pr")
        r.commit({"apps/web/a.ts": "2"})
        proof = r.commit({"apps/web/b.ts": "3"})
        git(r.dir, "checkout", "-q", "main")
        r.commit({"docs/new.md": "main moved"})
        git(r.dir, "update-ref", "refs/remotes/origin/main", "HEAD")
        git(r.dir, "checkout", "-q", "pr")
        git(r.dir, "rebase", "-q", "main")
        head = git(r.dir, "rev-parse", "HEAD")
        self.assertNotEqual(head, proof)
        self.assertEqual(r.paths(head, proof), [])  # patch-identical: nothing counts
        extra = r.commit({"apps/api/z.go": "9"})
        self.assertEqual(r.paths(extra, proof), ["apps/api/z.go"])

    def test_rebase_with_a_changed_commit_counts_it(self):
        r = Repo(self)
        git(r.dir, "checkout", "-q", "-b", "pr")
        proof = r.commit({"apps/web/a.ts": "2"})
        git(r.dir, "commit", "-q", "--amend", "-m", "again")  # same patch
        git(r.dir, "checkout", "-q", "-B", "pr", "HEAD")
        (r.dir / "apps/web/a.ts").write_text("changed")
        git(r.dir, "commit", "-qam", "edit")
        head = git(r.dir, "rev-parse", "HEAD")
        self.assertIn("apps/web/a.ts", r.paths(head, proof))

    def test_merge_from_main_counts_the_paths_it_brings(self):
        r = Repo(self)
        git(r.dir, "checkout", "-q", "-b", "pr")
        proof = r.commit({"apps/web/a.ts": "2"})
        git(r.dir, "checkout", "-q", "main")
        r.commit({"apps/api/main.go": "m"})
        git(r.dir, "update-ref", "refs/remotes/origin/main", "HEAD")
        git(r.dir, "checkout", "-q", "pr")
        git(r.dir, "merge", "-q", "--no-ff", "-m", "merge main", "main")
        head = git(r.dir, "rev-parse", "HEAD")
        self.assertEqual(r.paths(head, proof), ["apps/api/main.go"])

    def test_unfetchable_proof_head_raises(self):
        r = Repo(self)
        with self.assertRaises(CP.Undecided):
            r.paths("HEAD", "0" * 40)

    def test_decide_carries_untouched_job_and_runs_touched(self):
        proofs = {"web": {"sha": "p1", "run_url": "u1"}, "api": {"sha": "p1", "run_url": "u1"}}
        res = CP.decide(["web", "api"], proofs, lambda s: ["apps/api/x.go"], CMAP, None, None)
        self.assertEqual(res["run"], ["api"])
        self.assertEqual(res["carried"], {"web": {"sha": "p1", "run_url": "u1"}})

    def test_no_proof_runs(self):
        res = CP.decide(["web"], {}, lambda s: [], CMAP, None, None)
        self.assertEqual(res["run"], ["web"])

    def test_error_runs_the_job_and_says_why(self):
        def boom(sha):
            raise CP.Undecided("proof head gone")
        res = CP.decide(["web"], {"web": {"sha": "p1", "run_url": ""}}, boom, CMAP, None, None)
        self.assertEqual(res["run"], ["web"])
        self.assertIn("proof head gone", res["reason"])

    def test_empty_change_carries_everything_proven(self):
        res = CP.decide(["web"], {"web": {"sha": "p1", "run_url": "u"}}, lambda s: [], CMAP, None, None)
        self.assertEqual(res["run"], [])

    def test_job_the_map_does_not_list_is_not_carried(self):
        res = CP.decide(["plan"], {"plan": {"sha": "p1", "run_url": ""}}, lambda s: ["apps/web/a.ts"], CMAP, None, None)
        self.assertEqual(res["run"], ["plan"])


def run(i, sha, created, jobs):
    return {"id": i, "head_sha": sha, "created_at": created, "status": "completed",
            "html_url": f"https://x/runs/{i}", "jobs": jobs}


def J(name, concl, start="2026-01-01T00:00:00Z", end="2026-01-01T00:10:00Z"):
    return {"name": name, "conclusion": concl, "started_at": start, "completed_at": end}


GREEN = [J("plan", "success"), J("web tests", "success"), J("api tests (1)", "success"),
         J("api tests (2)", "success"), J("ci_tests", "success")]


class ProofsAndPlan(unittest.TestCase):
    def fetch(self, runs):
        by = {r["id"]: r["jobs"] for r in runs}
        return lambda rid: by[rid]

    def test_names_map_to_keys_incl_matrix(self):
        self.assertEqual(CP.api_job_key("api tests (2)", DEFS), "api")
        self.assertEqual(CP.api_job_key("web tests", DEFS), "web")
        self.assertEqual(CP.api_job_key("ci_tests", DEFS), "ci_tests")
        self.assertIsNone(CP.api_job_key("unknown", DEFS))

    def test_first_run_runs_everything(self):
        res = CP.plan(KEYS, DEFS, [], "h1", lambda i: [], lambda p: [], CMAP, WORKFLOW, None)
        self.assertEqual(res["run"], KEYS)
        self.assertEqual(res["carried"], {})

    def test_later_head_carries_proven_jobs(self):
        runs = [run(1, "p", "2026-01-01T01:00:00Z", GREEN)]
        res = CP.plan(KEYS, DEFS, runs, "h2", self.fetch(runs), lambda p: ["apps/web/a.ts"], CMAP, WORKFLOW, None)
        self.assertEqual(res["run"], ["plan", "web"])  # plan is not in the map: it runs
        self.assertEqual(sorted(res["carried"]), ["api", "ci_tests"])
        self.assertEqual(res["carried"]["api"], {"sha": "p", "run_url": "https://x/runs/1"})

    def test_failed_job_has_no_proof_there_and_looks_further_back(self):
        red = [J("web tests", "failure"), J("api tests (1)", "success"), J("api tests (2)", "failure")]
        runs = [run(1, "old", "2026-01-01T01:00:00Z", GREEN), run(2, "mid", "2026-01-01T02:00:00Z", red)]
        proofs = CP.find_proofs(CP.group_heads(runs, "h3"), ["web", "api"], DEFS, self.fetch(runs))
        self.assertEqual(proofs["web"]["sha"], "old")
        self.assertEqual(proofs["api"]["sha"], "old")  # one failed leg is not a success

    def test_skipped_job_is_not_a_proof(self):
        skipped = [J("web tests", "skipped"), J("api tests (1)", "success")]
        runs = [run(1, "old", "2026-01-01T01:00:00Z", GREEN), run(2, "new", "2026-01-01T02:00:00Z", skipped)]
        proofs = CP.find_proofs(CP.group_heads(runs, "h3"), ["web", "api"], DEFS, self.fetch(runs))
        self.assertEqual(proofs["web"]["sha"], "old")
        self.assertEqual(proofs["api"]["sha"], "new")

    def test_current_head_runs_are_not_earlier_heads(self):
        runs = [run(1, "h2", "2026-01-01T01:00:00Z", GREEN)]
        self.assertEqual(CP.group_heads(runs, "h2"), [])

    def test_lines_output(self):
        res = {"run": ["web"], "carried": {"api": {"sha": "p", "run_url": "u"}}, "reason": "r"}
        out = CP.lines(["web", "api"], res)
        self.assertEqual(out[0], "run=web")
        self.assertIn("run_web=true", out)
        self.assertIn("run_api=false", out)
        self.assertIn('carried={"api":{"run_url":"u","sha":"p"}}', out)

    def test_cli_falls_back_to_everything_on_error(self):
        d = Path(tempfile.mkdtemp(prefix="ds287-"))
        self.addCleanup(shutil.rmtree, d, True)
        wf = d / "ci.yml"
        wf.write_text(WORKFLOW)
        out = d / "out"
        import os
        os.environ["GITHUB_OUTPUT"] = str(out)
        self.addCleanup(os.environ.pop, "GITHUB_OUTPUT", None)
        rc = CP.main(["--repo", "o/r", "--workflow", "ci.yml", "--pr", "1", "--sha", "HEAD",
                      "--workflow-path", str(wf), "--map", str(d / "nomap.json"), "--github-output"])
        self.assertEqual(rc, 0)
        text = out.read_text()
        self.assertIn("run=plan,web,api,ci_tests", text)
        self.assertIn("run_web=true", text)


class Valves(unittest.TestCase):
    def test_existing_behaviour_unchanged_without_new_keys(self):
        r = AS.select(["package.json"], CMAP)
        self.assertEqual(r["mode"], "all")
        r = AS.select([".github/workflows/other.yml"], CMAP)
        self.assertEqual(r["mode"], "all")  # no workflow_path: still run_everything

    def test_lock_jobs_runs_only_listed_jobs(self):
        cm = dict(CMAP, lock_jobs={"pnpm-lock.yaml": ["web"], "go.*": ["api"]})
        r = AS.select(["pnpm-lock.yaml"], cm)
        self.assertEqual(r["mode"], "areas")
        self.assertTrue(r["jobs"]["web"])
        self.assertFalse(r["jobs"]["api"])
        r = AS.select(["go.sum"], cm)
        self.assertTrue(r["jobs"]["api"])
        self.assertFalse(r["jobs"]["web"])

    def test_lock_file_without_the_valve_runs_everything(self):
        cm = dict(CMAP, run_everything=["pnpm-lock.yaml"])
        self.assertEqual(AS.select(["pnpm-lock.yaml"], cm)["mode"], "all")

    def test_script_jobs_selects_naming_jobs_and_ci_tests(self):
        cm = dict(CMAP, script_jobs=True, run_everything=["scripts/**"])
        r = AS.select(["scripts/ci/web_check.py"], cm, workflow_text=WORKFLOW)
        self.assertEqual(r["mode"], "areas")
        self.assertTrue(r["jobs"]["web"])
        self.assertTrue(r["jobs"]["ci_tests"])
        self.assertFalse(r["jobs"]["api"])

    def test_script_jobs_off_or_no_workflow_text_runs_everything(self):
        base = dict(CMAP, run_everything=["scripts/**"])
        self.assertEqual(AS.select(["scripts/ci/web_check.py"], base, workflow_text=WORKFLOW)["mode"], "all")
        on = dict(base, script_jobs=True)
        self.assertEqual(AS.select(["scripts/ci/web_check.py"], on)["mode"], "all")

    def test_workflow_file_rules(self):
        wp = ".github/workflows/ci.yml"
        self.assertEqual(AS.select([wp], CMAP, workflow_path=wp)["mode"], "all")
        other = AS.select([".github/workflows/package.yml", "docs/a.md"], CMAP, workflow_path=wp)
        self.assertEqual(other["mode"], "none")
        self.assertFalse(any(other["jobs"].values()))
        self.assertEqual(AS.select([".github/actions/x/action.yml"], CMAP, workflow_path=wp)["mode"], "all")

    def test_parse_workflow_jobs(self):
        self.assertEqual(list(DEFS), KEYS)
        self.assertEqual(DEFS["web"]["name"], "web tests")
        self.assertIn("go test", DEFS["api"]["text"])
        self.assertNotIn("go test", DEFS["web"]["text"])
        self.assertEqual(AS.jobs_naming_script(WORKFLOW, "scripts/delivery/carry_plan.py"), ["plan"])


class CarryFlag(unittest.TestCase):
    def test_ci_scope_release_pr_full_only_without_carry(self):
        cfg = {"release_pr": {"base": "main", "head_re": "^release/.+"}, "docs": ["docs"]}
        args = (cfg, ["src/a.py"], "pull_request", "release/1", "main")
        self.assertEqual(CS.decide(*args)["scope"], "full")
        self.assertEqual(CS.decide(*args, carry=True)["scope"], "affected")

    def test_ci_scope_carry_keeps_full_files(self):
        cfg = {"full_files": ["package.json"], "release_pr": {"base": "main", "head_re": "^release/"}}
        r = CS.decide(cfg, ["package.json"], "pull_request", "release/1", "main", carry=True)
        self.assertEqual(r["scope"], "full")

    def test_changed_areas_release_full_only_without_carry(self):
        cmap = {"areas": {"code": ["src/**"], "web": ["web/**"]}, "all": [".github/**"]}
        self.assertTrue(CA.decide(["src/a.py"], cmap, release=True)["all"])
        r = CA.decide(["src/a.py"], cmap, release=True, carry=True)
        self.assertFalse(r["all"])
        self.assertEqual(r["areas"], ["code"])
        self.assertTrue(CA.decide([".github/x.yml"], cmap, release=True, carry=True)["all"])


MAP_TEXT = json.dumps(CMAP)


class Replay(unittest.TestCase):
    def files(self, sha, path):
        if path.endswith("ci.yml"):
            return WORKFLOW
        if path == CR.MAP_PATH:
            return MAP_TEXT
        return None

    def test_replay_counts_saved_minutes(self):
        runs = [
            run(1, "h1", "2026-01-01T01:00:00Z", GREEN),
            run(2, "h2", "2026-01-01T02:00:00Z", GREEN),
            run(3, "h3", "2026-01-01T03:00:00Z", GREEN),
        ]
        changes = {("h2", "h1"): ["apps/web/a.ts"], ("h3", "h1"): ["apps/web/a.ts", "apps/api/a.go"],
                   ("h3", "h2"): ["apps/api/a.go"]}
        rows = CR.replay_workflow(runs, self.files, lambda head, proof: changes[(head, proof)],
                                  ".github/workflows/ci.yml")
        self.assertEqual([r["head"] for r in rows], ["h1", "h2", "h3"])
        self.assertEqual(rows[0]["planned"], KEYS)
        self.assertEqual(rows[0]["saved_minutes"], 0)
        # h2: plan and web run; api (2 legs of 10 min) and ci_tests (10 min) carried = 30 min
        self.assertEqual(rows[1]["planned"], ["plan", "web"])
        self.assertEqual(rows[1]["saved_minutes"], 30.0)
        self.assertEqual(rows[1]["ran"], KEYS)
        # h3: proof for web/api/ci_tests is h2; api changed since: plan, api run; web 10 + ci_tests 10 carried
        self.assertEqual(rows[2]["planned"], ["plan", "api"])
        self.assertEqual(rows[2]["saved_minutes"], 20.0)
        self.assertEqual(CR.total(rows), 50.0)

    def test_replay_error_runs_everything_saves_nothing(self):
        runs = [run(1, "h1", "2026-01-01T01:00:00Z", GREEN), run(2, "h2", "2026-01-01T02:00:00Z", GREEN)]

        def gone(head, proof):
            raise CR.CP.Undecided("head not fetchable")
        rows = CR.replay_workflow(runs, self.files, gone, ".github/workflows/ci.yml")
        self.assertEqual(rows[1]["planned"], KEYS)
        self.assertEqual(rows[1]["saved_minutes"], 0)

    def test_replay_without_map_runs_everything(self):
        runs = [run(1, "h1", "2026-01-01T01:00:00Z", GREEN), run(2, "h2", "2026-01-01T02:00:00Z", GREEN)]
        rows = CR.replay_workflow(runs, lambda s, p: WORKFLOW if p.endswith("ci.yml") else None,
                                  lambda h, p: ["apps/web/a.ts"], ".github/workflows/ci.yml")
        self.assertEqual(rows[1]["planned"], KEYS)

    def test_render_has_total(self):
        out = CR.render([{"pr": 7, "workflows": {"ci.yml": [
            {"head": "abcdef123456", "ran": ["web"], "planned": [], "carried": ["web"], "saved_minutes": 4.5, "reason": ""}]}}])
        self.assertIn("PR #7 ci.yml", out)
        self.assertIn("total saved: 4.5 job-minutes", out)


if __name__ == "__main__":
    unittest.main()
