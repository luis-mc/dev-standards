#!/usr/bin/env python3
"""DL19 (CIR10 L3): the shard-table guard, the timings balance for every suite, and shard sizing in cloud_shard.py.

Proves: a test file in no shard fails the guard; a test file in two shards fails the guard; a sample project's
shards fit their limits; every suite is cut by recorded timings; a size over the limits is an error; the peak
memory limit fails a shard; a mutant guard with one rule broken fails a scenario. Standard library only.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = REPO / "claude/plugins/delivery/templates/shared/scripts/delivery"
sys.path.insert(0, str(SCRIPTS))

import cloud_shard as CS  # noqa: E402
import shard_guard as G  # noqa: E402
import shard_table as ST  # noqa: E402

PY = sys.executable


def write(root: Path, rel: str, text: str = "") -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def sample_table() -> dict:
    return {
        "schema": 1,
        "limits": {"cpus": 4, "memory_gib": 8, "timeout_min": 15},
        "discover": ["**/*.test.ts", "**/*.spec.ts", "**/*.budget.ts"],
        "suites": {
            "unit": {"globs": ["packages/**/*.test.ts"]},
            "e2e": {"globs": ["e2e/**/*.spec.ts"]},
            "budget": {"globs": ["budgets/*.budget.ts"]},
        },
        "shards": [
            {"id": "unit-1", "os": "linux", "suite": "unit", "part": "1/2", "size": {"workers": 4},
             "commands": ["echo {files}"]},
            {"id": "unit-2", "os": "linux", "suite": "unit", "part": "2/2", "size": {"workers": 4},
             "commands": ["echo {files}"]},
            {"id": "e2e-1", "os": "linux", "suite": "e2e", "part": "1/2", "size": {"workers": 2}, "commands": ["x"]},
            {"id": "e2e-2", "os": "linux", "suite": "e2e", "part": "2/2", "size": {"workers": 2}, "commands": ["x"]},
            {"id": "budget", "os": "linux", "suite": "budget", "members": ["budgets/*.budget.ts"], "commands": ["x"]},
            {"id": "static", "os": "linux", "commands": ["x"]},
        ],
    }


def sample_project(root: Path, table: dict | None = None) -> dict:
    timings = {}
    for i, sec in enumerate([30, 25, 20, 15, 10, 5]):
        write(root, "packages/p%d/a.test.ts" % i)
        timings["packages/p%d/a.test.ts" % i] = sec
    for i, sec in enumerate([120, 100, 80, 40]):
        write(root, "e2e/f%d.spec.ts" % i)
        timings["e2e/f%d.spec.ts" % i] = sec
    for i in range(2):
        write(root, "budgets/b%d.budget.ts" % i)
        timings["budgets/b%d.budget.ts" % i] = 60
    write(root, "scripts/delivery/ci-timings.json", json.dumps({"seconds": timings}))
    table = table or sample_table()
    write(root, "scripts/delivery/ci-shards.json", json.dumps(table))
    return table


def guard(root: Path, table: dict):
    return G.check(table, root)


class GuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="shard-guard-"))
        self.table = sample_project(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_a_sample_project_passes_and_its_shards_fit_their_limits(self):
        problems, rows = guard(self.tmp, self.table)
        self.assertEqual(problems, [])
        by = {r["id"]: r for r in rows}
        for sid in ("unit-1", "unit-2", "e2e-1", "e2e-2", "budget"):
            self.assertLessEqual(by[sid]["estimate_s"], 15 * 60, sid)
        self.assertEqual(by["unit-1"]["files"] + by["unit-2"]["files"], 6)
        self.assertIsNone(by["static"]["files"])

    def test_a_file_in_no_shard_fails(self):
        write(self.tmp, "tools/new/b.test.ts")
        problems, _ = guard(self.tmp, self.table)
        self.assertTrue(any("tools/new/b.test.ts is in no shard" in p for p in problems), problems)

    def test_an_unclaimed_file_of_an_explicit_only_suite_is_in_no_shard(self):
        write(self.tmp, "budgets/c.budget.ts")
        self.table["shards"][4]["members"] = ["budgets/b*.budget.ts"]
        problems, _ = guard(self.tmp, self.table)
        self.assertTrue(any("budgets/c.budget.ts is in no shard" in p for p in problems), problems)

    def test_a_file_that_two_suites_take_is_in_two_shards(self):
        self.table["suites"]["slow"] = {"globs": ["e2e/f0.spec.ts"]}
        self.table["shards"].append({"id": "slow-1", "os": "linux", "suite": "slow", "part": "1/1", "commands": ["x"]})
        problems, _ = guard(self.tmp, self.table)
        self.assertTrue(any("e2e/f0.spec.ts is in 2 shards" in p and "slow-1" in p for p in problems), problems)

    def test_a_file_in_two_shards_fails(self):
        self.table["shards"].append({"id": "extra", "os": "linux", "suite": "e2e", "members": ["e2e/f0.spec.ts"],
                                     "commands": ["x"]})
        problems, _ = guard(self.tmp, self.table)
        self.assertEqual([p for p in problems if "is in 2 shards" in p], [])  # explicit claim leaves the pool
        self.table["shards"].append({"id": "extra2", "os": "linux", "suite": "e2e", "members": ["e2e/f*.spec.ts"],
                                     "commands": ["x"]})
        problems, _ = guard(self.tmp, self.table)
        self.assertTrue(any("e2e/f0.spec.ts is in 2 shards (extra, extra2)" in p for p in problems), problems)

    def test_the_same_part_twice_puts_files_in_two_shards(self):
        self.table["shards"].append({"id": "unit-1b", "os": "linux", "suite": "unit", "part": "1/2",
                                     "commands": ["x"]})
        problems, _ = guard(self.tmp, self.table)
        self.assertTrue(any("is in 2 shards (unit-1, unit-1b)" in p for p in problems), problems)

    def test_a_missing_part_leaves_files_in_no_shard(self):
        self.table["shards"] = [s for s in self.table["shards"] if s["id"] != "unit-2"]
        problems, _ = guard(self.tmp, self.table)
        self.assertTrue(any("part 2/2 has no shard" in p for p in problems), problems)
        self.assertTrue(any("is in no shard" in p for p in problems), problems)

    def test_a_suite_with_no_shard_and_a_stale_members_glob_fail(self):
        self.table["suites"]["extra"] = {"globs": ["packages/**/*.test.ts"]}
        self.table["shards"][4]["members"].append("budgets/gone/*.ts")
        problems, _ = guard(self.tmp, self.table)
        self.assertTrue(any("suite extra has no shard" in p for p in problems), problems)
        self.assertTrue(any("budgets/gone/*.ts" in p and "matches no file" in p for p in problems), problems)

    def test_each_os_is_cut_on_its_own(self):
        self.table["shards"] += [
            {"id": "unit-win", "os": "windows", "suite": "unit", "part": "1/1", "commands": ["x"]}]
        problems, _ = guard(self.tmp, self.table)
        self.assertEqual(problems, [])

    def test_sizes_over_the_limits_fail(self):
        self.table["shards"][0]["size"] = {"workers": 4, "memory_gib": 12}
        self.table["shards"][1]["size"] = {"workers": 8}
        self.table["shards"][2]["size"] = {"cpus": 2, "workers": 4}
        problems, _ = guard(self.tmp, self.table)
        self.assertTrue(any("shard unit-1" in p and "memory_gib 12 is over the limit 8" in p for p in problems))
        self.assertTrue(any("shard unit-2: 8 workers on 4 cpus" in p for p in problems), problems)
        self.assertTrue(any("shard e2e-1: 4 workers on 2 cpus" in p for p in problems), problems)

    def test_a_shard_too_slow_for_its_timeout_fails(self):
        self.table["shards"][2]["size"] = {"workers": 1, "timeout_min": 2}
        problems, _ = guard(self.tmp, self.table)
        self.assertTrue(any("shard e2e-1" in p and "over its timeout of 2 min" in p for p in problems), problems)

    def test_cli_exit_codes(self):
        def run(*a):
            return subprocess.run([PY, "-I", str(SCRIPTS / "shard_guard.py"), "check", "--root", str(self.tmp), *a],
                                  capture_output=True, text=True)
        self.assertEqual(run().returncode, 0)
        write(self.tmp, "tools/new/b.test.ts")
        r = run()
        self.assertEqual(r.returncode, 1)
        self.assertIn("FAIL", r.stderr)
        self.assertEqual(json.loads(run("--json").stdout)["ok"], False)
        self.assertEqual(run("--table", "missing.json").returncode, 2)

    def test_a_guard_with_one_rule_broken_fails_a_scenario(self):
        src = (SCRIPTS / "shard_table.py").read_text(encoding="utf-8")
        two = lambda root, t: (write(root, "e2e/f9.spec.ts"), t["shards"].extend([
            {"id": "x1", "os": "linux", "suite": "e2e", "members": ["e2e/f9*"], "commands": ["x"]},
            {"id": "x2", "os": "linux", "suite": "e2e", "members": ["e2e/f9*"], "commands": ["x"]}]))
        unclaimed = lambda root, t: (write(root, "budgets/c.budget.ts"),
                                     t["shards"][4].update(members=["budgets/b*.budget.ts"]), t.pop("discover"))
        outside = lambda root, t: write(root, "tools/new/b.test.ts")
        mutants = [
            ("two shards", "elif len(who) > 1:", "elif len(who) > 99:", two),
            ("unclaimed file", "if not who and (name, os_name) in groups and groups[(name, os_name)]:", "if False:",
             unclaimed),
            ("file no suite takes", 'out.append("%s is in no shard (no suite takes it)" % f)', "pass", outside),
        ]
        for label, old, new, break_project in mutants:
            self.assertIn(old, src, label)
            d = Path(tempfile.mkdtemp(prefix="shard-mutant-"))
            try:
                for f in ("shard_table.py", "shard_balance.py", "shard_guard.py"):
                    shutil.copy(SCRIPTS / f, d / f)
                (d / "shard_table.py").write_text(src.replace(old, new), encoding="utf-8")
                root = d / "proj"
                table = sample_project(root)
                break_project(root, table)
                write(root, "scripts/delivery/ci-shards.json", json.dumps(table))
                args = ["check", "--root", str(root)]
                real = subprocess.run([PY, "-I", str(SCRIPTS / "shard_guard.py"), *args], capture_output=True, text=True)
                mutant = subprocess.run([PY, "-I", str(d / "shard_guard.py"), *args], capture_output=True, text=True)
                self.assertEqual(real.returncode, 1, "the real guard must fail the %r project" % label)
                self.assertEqual(mutant.returncode, 0, "mutant %r was not detected" % label)
            finally:
                shutil.rmtree(d, ignore_errors=True)


class BalanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="shard-bal-"))
        self.table = sample_project(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_every_suite_is_cut_by_recorded_timings_and_nothing_is_lost(self):
        assignment, problems = ST.resolve(self.table, self.tmp)
        self.assertEqual(problems, [])
        self.assertEqual(sorted(assignment["unit-1"] + assignment["unit-2"]),
                         sorted("packages/p%d/a.test.ts" % i for i in range(6)))
        # e2e: 120,100,80,40 over two shards -> 120+40 and 100+80 (greedy, longest first)
        self.assertEqual(assignment["e2e-1"], ["e2e/f0.spec.ts", "e2e/f3.spec.ts"])
        self.assertEqual(assignment["e2e-2"], ["e2e/f1.spec.ts", "e2e/f2.spec.ts"])
        # unit: 30,25,20,15,10,5 -> 30+15+5=50 and 25+20+10=55 differ by less than the longest file
        t = json.loads((self.tmp / "scripts/delivery/ci-timings.json").read_text())["seconds"]
        a, b = (sum(t[f] for f in assignment[s]) for s in ("unit-1", "unit-2"))
        self.assertLessEqual(abs(a - b), 30)

    def test_shard_balance_prints_the_files_of_a_table_shard(self):
        r = subprocess.run([PY, "-I", str(SCRIPTS / "shard_balance.py"), "--table", "scripts/delivery/ci-shards.json",
                            "--shard-id", "e2e-2", "--root", str(self.tmp)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.split(), ["e2e/f1.spec.ts", "e2e/f2.spec.ts"])
        r = subprocess.run([PY, "-I", str(SCRIPTS / "shard_balance.py"), "--table", "x.json"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)

    def test_a_per_suite_timings_file_wins(self):
        write(self.tmp, "t-e2e.json", json.dumps({"e2e/f0.spec.ts": 1, "e2e/f1.spec.ts": 1, "e2e/f2.spec.ts": 1,
                                                  "e2e/f3.spec.ts": 500}))
        self.table["suites"]["e2e"]["timings"] = "t-e2e.json"
        assignment, _ = ST.resolve(self.table, self.tmp)
        self.assertEqual(assignment["e2e-1"], ["e2e/f3.spec.ts"])


class CloudShardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="shard-cloud-"))
        self.table = sample_project(self.tmp)
        subprocess.run(["git", "init", "-q"], cwd=self.tmp, check=True)
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "i"],
                       cwd=self.tmp, check=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, shard_id):
        return CS.run_shard(self.table, shard_id, str(self.tmp), None, None)

    def test_files_and_sizing_reach_the_commands(self):
        py = PY.replace("\\", "/")
        self.table["shards"][0]["commands"] = [
            '"%s" -c "import os,sys;print(os.environ[\'CI_SHARD_WORKERS\'],os.environ[\'CI_SHARD_MEMORY_GIB\'],'
            'len(sys.argv)-1)" {files}' % py]
        r = self._run("unit-1")
        self.assertEqual(r["state"], "success", r)
        n = len(ST.resolve(self.table, self.tmp)[0]["unit-1"])
        self.assertEqual(r["commands"][0]["tail"].split(), ["4", "8", str(n)])
        self.assertEqual(r["size"]["cpus"], 4)

    def test_a_size_over_the_limits_is_an_error_not_a_run(self):
        self.table["shards"][0]["size"] = {"workers": 4, "cpus": 16}
        r = self._run("unit-1")
        self.assertEqual(r["state"], "error")
        self.assertEqual(r["commands"], [])
        self.assertIn("cpus 16 is over the limit 4", r["summary"])

    @unittest.skipIf(CS.resource is None, "no peak memory on this OS")
    def test_a_peak_above_the_memory_limit_fails_the_shard(self):
        py = PY.replace("\\", "/")
        self.table["limits"]["memory_gib"] = 0.02
        self.table["shards"][0]["size"] = {"workers": 1}
        self.table["shards"][0]["commands"] = ['"%s" -c "b=bytearray(100*1024*1024);print(len(b))"' % py]
        r = self._run("unit-1")
        self.assertEqual(r["state"], "failure", r)
        self.assertIn("over the limit of 0.02 GiB", r["summary"])
        self.assertGreater(r["peak_memory_gib"], 0.02)
        self.table["limits"]["memory_gib"] = 8
        ok = self._run("unit-1")
        self.assertEqual(ok["state"], "success", ok)
        self.assertLess(ok["peak_memory_gib"], 8)


if __name__ == "__main__":
    unittest.main()
