#!/usr/bin/env python3
"""Prove shard_balance.py, area_select.py and the nightly-full template do what CONTRACT.md says (DS9).

  * shard_balance.py: greedy longest-first split, deterministic, unknown files get the median, every
    file in exactly one shard, the greedy result beats a round-robin split, `update` from vitest and
    Playwright reports, the usage errors.
  * area_select.py: area, union of areas, shared path, unknown path, docs-only, empty diff, `--all`,
    `--base` against a throwaway git repository, `$GITHUB_OUTPUT`, the starter map shipped for ts.
  * nightly-full.yml: structure (schedule + dispatch, runner variables, jobs gated on the first one)
    and the compare step itself, run with bash against a stub `gh`.
  * mutants: copies of the scripts with one rule broken must each fail at least one scenario.

Run:  python3 tools/test_ci_speedups.py
"""
from __future__ import annotations

import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TOOLING = REPO / "claude/plugins/project-setup/skills/tech-stack-setup/assets/tooling"
DELIVERY = TOOLING / "shared/scripts/delivery"
NIGHTLY = TOOLING / "ts/.github/workflows/nightly-full.yml"
TS_MAP = TOOLING / "ts/scripts/delivery/ci-areas.json"
TS_TIMINGS = TOOLING / "ts/scripts/delivery/ci-timings.json"

TESTS: list = []


def test(fn):
    TESTS.append(fn)
    return fn


def check(cond, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def run(script: Path, args: list[str], *, cwd: Path | None = None, env: dict | None = None,
        stdin: str | None = None) -> tuple[int, str, str]:
    e = {k: v for k, v in os.environ.items() if k != "GITHUB_OUTPUT"}
    e.update(env or {})
    p = subprocess.run([sys.executable, "-I", str(script), *args], cwd=cwd, env=e, input=stdin,
                       capture_output=True, text=True, encoding="utf-8", timeout=60)
    return p.returncode, p.stdout, p.stderr


def kv(out: str) -> dict[str, str]:
    return dict(ln.split("=", 1) for ln in out.splitlines() if "=" in ln)


# --------------------------------------------------------------------------- shard_balance

SB = DELIVERY / "shard_balance.py"


def shards(script: Path, files: dict[str, float] | list[str], n: int, timings: dict | None = None,
           flat: bool = False) -> list[list[str]]:
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        names = list(files)
        t = timings if timings is not None else (files if isinstance(files, dict) else {})
        tf = d / "t.json"
        tf.write_text(json.dumps(t if flat else {"seconds": t}), encoding="utf-8")
        out = []
        for k in range(1, n + 1):
            rc, so, se = run(script, ["--shard", f"{k}/{n}", "--timings", str(tf), *names])
            check(rc == 0, f"shard {k}/{n} exited {rc}: {se}")
            out.append(so.split())
        return out


def load_sb(script: Path):
    import importlib.util
    spec = importlib.util.spec_from_file_location("sb_" + script.parent.name.replace("-", "_"), script)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def scenario_split(script: Path) -> None:
    times = {"a": 10, "b": 9, "c": 5, "d": 4, "e": 3, "f": 1}
    got = shards(script, times, 2)
    flat = sorted(f for s in got for f in s)
    check(flat == sorted(times), f"every file exactly once: {got}")
    sums = [sum(times[f] for f in s) for s in got]
    check(max(sums) - min(sums) <= 2, f"greedy longest-first should balance {times}: {sums}")
    # greedy: a->1, b->2, c->2 (9+5=14 vs 10), d->1 (14), e->1 or 2 ... same input, same output
    check(got == shards(script, times, 2), "deterministic")
    check(shards(script, times, 2, flat=True) == got, "a flat timings map reads the same as {seconds: ...}")
    # round-robin would be a,c,e / b,d,f = 18 / 14; the longest shard must be shorter than that
    check(max(sums) <= 17, f"worse than round-robin: {sums}")


def scenario_unknown_gets_median(script: Path) -> None:
    # known: 2, 4, 100 -> median 4. new1/new2 weigh 4 each: with 3 shards the 100 s file sits alone.
    timings = {"x": 2, "y": 4, "z": 100}
    got = shards(script, ["x", "y", "z", "new1", "new2"], 3, timings)
    check(["z"] in got, f"the 100 s file should be alone on a shard: {got}")
    check(sorted(f for s in got for f in s) == ["new1", "new2", "x", "y", "z"], f"all files placed: {got}")
    # at the median (4 s) the unknowns land beside y and x; at 0 s they would all stack onto x
    check(got == [["z"], ["new1", "y"], ["new2", "x"]], f"unknown files weigh the median: {got}")
    # nothing measured among the given files: the median of the whole timings file
    got = shards(script, ["n1", "n2", "n3"], 3, {"other": 7})
    check(sorted(len(s) for s in got) == [1, 1, 1], f"three equal unknowns on three shards: {got}")
    # no timings at all: still a split by count
    got = shards(script, ["n1", "n2", "n3", "n4"], 2, {})
    check(sorted(len(s) for s in got) == [2, 2], f"no timings: equal weights: {got}")


def scenario_glob_files_from_and_errors(script: Path) -> None:
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        for name in ("tests/a.spec.ts", "tests/sub/b.spec.ts", "tests/c.test.ts", "node_modules/tests/z.spec.ts"):
            (d / name).parent.mkdir(parents=True, exist_ok=True)
            (d / name).write_text("", encoding="utf-8")
        rc, out, _ = run(script, ["--shard", "1/1", "--root", str(d), "--timings", str(d / "none.json"),
                                  "--glob", "tests/**/*.spec.ts", "--join", " "])
        check(rc == 0 and out.split() == ["tests/a.spec.ts", "tests/sub/b.spec.ts"],
              f"`**/` matches no or many directories, node_modules is skipped: {out!r}")
        rc, out, _ = run(script, ["--shard", "1/2", "--timings", str(d / "none.json"), "--files-from", "-"],
                         stdin="p.test\nq.test\n")
        check(rc == 0 and out.split() == ["p.test"], f"--files-from -: {out!r}")
        rc, _, _ = run(script, ["--shard", "1/1", "--root", str(d), "--glob", "nope/**/*.ts"])
        check(rc == 3, f"a glob that matches nothing exits 3, got {rc}")
        for bad in ("0/2", "3/2", "x", "1/0"):
            rc, _, err = run(script, ["--shard", bad, "f"])
            check(rc == 2 and "--shard" in err, f"--shard {bad}: exit {rc}, {err!r}")
        (d / "bad.json").write_text("[1,2]", encoding="utf-8")
        rc, _, _ = run(script, ["--shard", "1/1", "--timings", str(d / "bad.json"), "f"])
        check(rc == 2, f"an unreadable timings file exits 2, got {rc}")


def scenario_update(script: Path) -> None:
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        (d / "src").mkdir()
        for n in ("a.test.ts", "b.test.ts"):
            (d / "src" / n).write_text("", encoding="utf-8")
        tf = d / "ci-timings.json"
        tf.write_text(json.dumps({"seconds": {"src/a.test.ts": 100.0, "src/old.test.ts": 5.0, "src/keep.test.ts": 9.0}}),
                      encoding="utf-8")
        r1 = d / "r1.json"
        r2 = d / "r2.json"
        r1.write_text(json.dumps({"testResults": [
            {"name": str(d / "src/a.test.ts"), "startTime": 1000, "endTime": 3000},
            {"name": str(d / "src/b.test.ts"), "startTime": 0, "endTime": 1500},
            {"name": str(d / "src/nostamp.test.ts")}]}), encoding="utf-8")
        r2.write_text(json.dumps({"testResults": [
            {"name": str(d / "src/a.test.ts"), "startTime": 0, "endTime": 4000}]}), encoding="utf-8")
        rc, out, err = run(script, ["update", "--report", str(r1), str(r2), "--timings", str(tf), "--root", str(d),
                                    "--prune-missing"])
        check(rc == 0, f"update exited {rc}: {err}")
        sec = json.loads(tf.read_text(encoding="utf-8"))["seconds"]
        check(sec.get("src/a.test.ts") == 3.0, f"a file in two reports is averaged (2 s and 4 s): {sec}")
        check(sec.get("src/b.test.ts") == 1.5, f"a new file is added: {sec}")
        check("src/old.test.ts" not in sec and "src/keep.test.ts" not in sec,
              f"--prune-missing drops files that no longer exist: {sec}")
        check("src/nostamp.test.ts" not in sec, f"a result without times is ignored: {sec}")
        # without --prune-missing an unmeasured file keeps its old figure
        tf.write_text(json.dumps({"seconds": {"src/keep.test.ts": 9.0}}), encoding="utf-8")
        run(script, ["update", "--report", str(r2), "--timings", str(tf), "--root", str(d)])
        sec = json.loads(tf.read_text(encoding="utf-8"))["seconds"]
        check(sec.get("src/keep.test.ts") == 9.0 and sec.get("src/a.test.ts") == 4.0, f"old figures kept: {sec}")
        # Playwright's JSON reporter: durations per test result, summed per file
        pw = d / "pw.json"
        pw.write_text(json.dumps({"config": {"rootDir": str(d / "tests")}, "suites": [
            {"file": "login.spec.ts", "suites": [], "specs": [
                {"tests": [{"results": [{"duration": 1500}]}, {"results": [{"duration": 2500}]}]}]}]}),
            encoding="utf-8")
        rc, _, err = run(script, ["update", "--report", str(pw), "--timings", str(tf), "--root", str(d)])
        sec = json.loads(tf.read_text(encoding="utf-8"))["seconds"]
        check(rc == 0 and sec.get("tests/login.spec.ts") == 4.0, f"playwright report: rc={rc} {sec} {err}")
        (d / "junk.json").write_text("{", encoding="utf-8")
        rc, _, _ = run(script, ["update", "--report", str(d / "junk.json"), "--timings", str(tf)])
        check(rc == 2, f"an unreadable report exits 2, got {rc}")


SB_SCENARIOS = [scenario_split, scenario_unknown_gets_median, scenario_glob_files_from_and_errors, scenario_update]


@test
def shard_balance_scenarios():
    for sc in SB_SCENARIOS:
        sc(SB)


def mutant_dir(script: Path, extra: list[Path], old: str, new: str) -> Path:
    d = Path(tempfile.mkdtemp())
    for f in [script, *extra]:
        shutil.copy(f, d / f.name)
    p = d / script.name
    text = p.read_text(encoding="utf-8")
    if old not in text:
        raise AssertionError(f"mutation target not found in {script.name}: {old!r}")
    p.write_text(text.replace(old, new, 1), encoding="utf-8")
    return d


@test
def shard_balance_mutants_are_detected():
    mutants = [
        ("shortest first", "sorted(w, key=lambda f: (-w[f], f))", "sorted(w, key=lambda f: (w[f], f))"),
        ("heaviest shard", "k = min(range(shards), key=lambda i: (totals[i], i))",
         "k = max(range(shards), key=lambda i: (totals[i], -i))"),
        ("unknown weighs zero", "fill = statistics.median(known)", "fill = 0.0"),
        ("unknown weighs the max", "fill = statistics.median(known)", "fill = max(known)"),
        ("round robin", "k = min(range(shards), key=lambda i: (totals[i], i))",
         "k = sum(len(s) for s in out) % shards"),
        ("no pruning", "dict(sorted((f, s) for f, s in merged.items() if keep(f)))", "dict(sorted(merged.items()))"),
    ]
    for sc in SB_SCENARIOS:
        sc(SB)  # the real script must pass first, or every mutant would look detected
    for label, old, new in mutants:
        d = mutant_dir(SB, [], old, new)
        try:
            caught = False
            for sc in SB_SCENARIOS:
                try:
                    sc(d / "shard_balance.py")
                except Exception:  # noqa: BLE001 - any failing scenario is a detection
                    caught = True
                    break
            check(caught, f"shard_balance mutant '{label}' was not detected")
        finally:
            shutil.rmtree(d, ignore_errors=True)


# --------------------------------------------------------------------------- area_select

AS = DELIVERY / "area_select.py"
MAP = {
    "jobs": ["verify", "integration", "e2e"],
    "always_jobs": ["verify"],
    "run_everything": ["package.json", ".github/**", "scripts/delivery"],
    "docs": ["docs/**", "**/*.md"],
    "areas": {
        "api": {"paths": ["apps/api/**"], "jobs": ["integration"], "tests": ["apps/api/**/*.test.ts"]},
        "web": {"paths": ["apps/web"], "jobs": ["integration", "e2e"], "tests": ["apps/web/**/*.test.ts"]},
        "ui": {"paths": ["packages/ui"], "jobs": ["e2e"], "tests": ["packages/ui/**/*.test.ts"]},
    },
}


def select(script: Path, paths: list[str], *extra: str, cmap: dict = MAP) -> dict[str, str]:
    with tempfile.TemporaryDirectory() as d:
        mp = Path(d) / "map.json"
        mp.write_text(json.dumps(cmap), encoding="utf-8")
        rc, out, err = run(script, ["--map", str(mp), *extra, *paths])
        check(rc == 0, f"area_select exited {rc}: {err}")
        return kv(out)


def scenario_select(script: Path) -> None:
    r = select(script, ["apps/api/src/x.ts"])
    check((r["mode"], r["areas"], r["integration"], r["e2e"], r["verify"]) == ("areas", "api", "true", "false", "true"),
          f"one area: {r}")
    check(r["tests"] == "apps/api/**/*.test.ts", f"the area's test globs: {r}")
    r = select(script, ["apps/api/a.ts", "packages/ui/b.ts"])
    check((r["areas"], r["integration"], r["e2e"]) == ("api,ui", "true", "true"), f"areas are united: {r}")
    check(r["tests"] == "apps/api/**/*.test.ts packages/ui/**/*.test.ts", f"united test globs: {r}")
    for shared in ("package.json", ".github/workflows/ci.yml", "scripts/delivery/area_select.py"):
        r = select(script, ["apps/api/a.ts", shared])
        check((r["mode"], r["integration"], r["e2e"]) == ("all", "true", "true"), f"shared path {shared}: {r}")
    r = select(script, ["apps/api/a.ts", "tools/new-thing.sh"])
    check(r["mode"] == "all" and "tools/new-thing.sh" in r["reason"], f"an unknown path runs everything: {r}")
    r = select(script, ["docs/a/b.txt", "README.md", "apps/api/NOTES.md"])
    check((r["mode"], r["integration"], r["e2e"], r["verify"]) == ("none", "false", "false", "true"),
          f"docs only runs no test, the static gates stay: {r}")
    r = select(script, ["docs/x.md", "apps/web/a.ts"])
    check((r["areas"], r["e2e"]) == ("web", "true"), f"docs next to code: the code decides: {r}")
    check(select(script, [])["mode"] == "all", "no changed path runs everything")
    check(select(script, ["apps/api/a.ts"], "--all")["mode"] == "all", "--all runs everything")
    # a plain path matches the folder and what is under it, not a sibling with the same prefix
    r = select(script, ["apps/webby/a.ts"])
    check(r["mode"] == "all", f"apps/webby is not under apps/web: {r}")
    r = select(script, ["apps\\api\\a.ts", "./apps/web/b.ts"])
    check(r["areas"] == "api,web", f"backslashes and a leading ./ are normalised: {r}")
    # a longer map: `**/` matches no directory too
    r = select(script, ["a.md"], cmap={**MAP, "docs": ["**/*.md"]})
    check(r["mode"] == "none", f"**/ matches the repository root: {r}")


def scenario_select_git_and_output(script: Path) -> None:
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        g = lambda *a: subprocess.run(["git", *a], cwd=d, check=True, capture_output=True, text=True)  # noqa: E731
        g("init", "-q", "-b", "main")
        g("config", "user.email", "t@example.com")
        g("config", "user.name", "t")
        (d / "apps/api").mkdir(parents=True)
        (d / "apps/api/a.ts").write_text("1", encoding="utf-8")
        g("add", "-A")
        g("commit", "-qm", "base")
        g("checkout", "-q", "-b", "feature")
        (d / "apps/api/a.ts").write_text("2", encoding="utf-8")
        (d / "docs").mkdir()
        (d / "docs/n.md").write_text("n", encoding="utf-8")
        g("add", "-A")
        g("commit", "-qm", "change")
        mp = d / "map.json"
        mp.write_text(json.dumps(MAP), encoding="utf-8")
        out_file = d / "github_output"
        rc, out, err = run(script, ["--map", str(mp), "--base", "main", "--github-output"], cwd=d,
                           env={"GITHUB_OUTPUT": str(out_file)})
        check(rc == 0 and kv(out)["areas"] == "api", f"--base reads git diff base...HEAD: rc={rc} {out} {err}")
        written = kv(out_file.read_text(encoding="utf-8"))
        check(written["integration"] == "true" and written["e2e"] == "false" and written["mode"] == "areas",
              f"--github-output appends the same lines: {written}")
        rc, out, _ = run(script, ["--map", str(mp), "--json", "apps/web/x"], cwd=d)
        check(rc == 0 and json.loads(out)["jobs"] == {"verify": True, "integration": True, "e2e": True}, f"--json: {out}")
        rc, _, err = run(script, ["--map", str(mp), "--base", "no-such-ref"], cwd=d)
        check(rc == 2 and "git diff" in err, f"a bad base exits 2: {rc} {err}")
        rc, _, _ = run(script, ["--map", str(d / "missing.json"), "x"], cwd=d)
        check(rc == 2, f"a missing map exits 2, got {rc}")
        (d / "bad.json").write_text('{"areas": {"a": {}}}', encoding="utf-8")
        rc, _, _ = run(script, ["--map", str(d / "bad.json"), "x"], cwd=d)
        check(rc == 2, f"an area without paths exits 2, got {rc}")


AS_SCENARIOS = [scenario_select, scenario_select_git_and_output]


@test
def area_select_scenarios():
    for sc in AS_SCENARIOS:
        sc(AS)


@test
def area_select_mutants_are_detected():
    mutants = [
        ("unknown path is skipped", 'return result("all", [], f"{p} is in no area: run everything")', "continue"),
        ("shared path ignored", 'return result("all", [], f"{p} is shared: run everything")', "continue"),
        ("docs run everything", "        if any_match(p, cmap.get(\"docs\") or []):\n            continue\n",
         "        if False:\n            continue\n"),
        ("docs-only runs all", 'return result("none", [], "documentation only: no tests")',
         'return result("all", [], "documentation only: no tests")'),
        ("empty diff runs none", 'return result("all", [], "no changed paths: run everything")',
         'return result("none", [], "no changed paths")'),
        ("static gates skipped", "on = set(always)", "on = set()"),
        ("area jobs ignored", "on |= set(cmap[\"areas\"][a].get(\"jobs\") or [])", "pass"),
        ("prefix match", 'return path == pattern or path.startswith(pattern + "/")', "return path.startswith(pattern)"),
        ("--all ignored", "    if force_all:\n", "    if False:\n"),
        ("first area only", "areas += [n for n in hit if n not in areas]", "areas += [n for n in hit[:1] if n not in areas] if not areas else []"),
    ]
    for sc in AS_SCENARIOS:
        sc(AS)
    for label, old, new in mutants:
        d = mutant_dir(AS, [SB], old, new)
        try:
            caught = False
            for sc in AS_SCENARIOS:
                try:
                    sc(d / "area_select.py")
                except Exception:  # noqa: BLE001
                    caught = True
                    break
            check(caught, f"area_select mutant '{label}' was not detected")
        finally:
            shutil.rmtree(d, ignore_errors=True)


@test
def ts_starter_files_are_valid():
    cmap = json.loads(TS_MAP.read_text(encoding="utf-8"))
    r = select(AS, ["docs/readme.txt"], cmap=cmap)
    check(r["mode"] == "none", f"the starter map: docs-only runs none: {r}")
    check(select(AS, ["pnpm-lock.yaml"], cmap=cmap)["mode"] == "all", "the starter map: the lockfile runs everything")
    check(select(AS, ["somewhere/else.ts"], cmap=cmap)["mode"] == "all", "the starter map: unknown runs everything")
    check(kv(select_raw(["apps/api/x.ts"], cmap))["integration"] == "true", "the starter map has an api area")
    data = json.loads(TS_TIMINGS.read_text(encoding="utf-8"))
    check(data.get("seconds") == {}, "the starter timings file is empty")
    rc, _, err = run(SB, ["--shard", "1/2", "--timings", str(TS_TIMINGS), "a", "b"])
    check(rc == 0, f"shard_balance reads the starter timings file: {err}")


def select_raw(paths: list[str], cmap: dict) -> str:
    with tempfile.TemporaryDirectory() as d:
        mp = Path(d) / "m.json"
        mp.write_text(json.dumps(cmap), encoding="utf-8")
        return run(AS, ["--map", str(mp), *paths])[1]


# --------------------------------------------------------------------------- nightly-full.yml


def jobs_of(text: str) -> dict[str, str]:
    body = text[text.index("\njobs:\n") + 7:]
    marks = list(re.finditer(r"^  ([A-Za-z0-9_-]+):[ \t]*$", body, re.M))
    return {m.group(1): body[m.start(): marks[i + 1].start() if i + 1 < len(marks) else len(body)]
            for i, m in enumerate(marks)}


def nightly_problems(text: str) -> list[str]:
    p: list[str] = []
    if not re.search(r"^  schedule:\n    - cron: ", text, re.M):
        p.append("no schedule")
    if not re.search(r"^  workflow_dispatch:", text, re.M):
        p.append("no workflow_dispatch")
    jobs = jobs_of(text)
    first = jobs.get("changed")
    if first is None or list(jobs)[0] != "changed":
        return p + ["`changed` must be the first job"]
    if "actions/workflows/nightly-full.yml/runs?status=success&per_page=1" not in first:
        p.append("changed must read the last SUCCESSFUL run of this workflow")
    if '[ "$head" = "$last" ]' not in first or 'echo "run=false"' not in first or 'echo "run=true"' not in first:
        p.append("changed must compare the heads and output run")
    for name, block in jobs.items():
        if "runs-on:" not in block or not re.search(r"^    runs-on: \$\{\{ fromJSON\(vars\.NIGHTLY_RUNS_ON \|\| vars\.CI_RUNS_ON \|\| '\"ubuntu-latest\"'\) \}\}\s*$", block, re.M):
            p.append(f"job {name}: runner must come from the NIGHTLY_RUNS_ON / CI_RUNS_ON variables")
        if name != "changed":
            if not re.search(r"^    needs: changed\s*$", block, re.M):
                p.append(f"job {name}: must need changed")
            if "if: ${{ needs.changed.outputs.run == 'true' }}" not in block:
                p.append(f"job {name}: must run only when changed said run=true")
            if "ref: ${{ needs.changed.outputs.sha }}" not in block:
                p.append(f"job {name}: must test the commit that was compared")
    return p


@test
def nightly_template_structure():
    text = NIGHTLY.read_text(encoding="utf-8").replace("\r\n", "\n")
    check(not nightly_problems(text), "\n".join(nightly_problems(text)))
    cases = [
        ("no schedule", "    - cron: '30 2 * * *'\n", ""),
        ("workflow_dispatch", "  workflow_dispatch:\n", ""),
        ("SUCCESSFUL run", "status=success", "status=completed"),
        ("compare the heads", '[ "$head" = "$last" ]', '[ "$head" != "$last" ]'),
        ("variables", "vars.NIGHTLY_RUNS_ON || ", ""),
        ("must need changed", "    needs: changed\n", ""),
        ("run=true", "if: ${{ needs.changed.outputs.run == 'true' }}", "if: ${{ true }}"),
        ("commit that was compared", "ref: ${{ needs.changed.outputs.sha }}", "ref: main"),
    ]
    for want, old, new in cases:
        if old not in text:
            raise AssertionError(f"mutation target not found: {old!r}")
        probs = nightly_problems(text.replace(old, new))
        check(any(want in x for x in probs), f"nightly mutation '{want}' not detected: {probs}")


def run_compare(head: str, last: str | None) -> dict[str, str]:
    """Run the `changed` job's compare step with bash against a stub gh."""
    text = NIGHTLY.read_text(encoding="utf-8")
    step = jobs_of(text.replace("\r\n", "\n"))["changed"]
    m = re.search(r"        run: \|\n((?:          .*\n|\n)+)", step)
    script = "\n".join(ln[10:] for ln in m.group(1).splitlines())
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        (d / "bin").mkdir()
        gh = d / "bin/gh"
        gh.write_text(
            "#!/bin/sh\n"
            'case "$2" in\n'
            '  repos/o/r/commits/main) echo "$HEAD_SHA" ;;\n'
            '  repos/o/r/actions/workflows/nightly-full.yml/runs*) echo "$LAST_SHA" ;;\n'
            '  *) echo "unexpected gh call: $*" >&2; exit 1 ;;\n'
            "esac\n", encoding="utf-8")
        gh.chmod(gh.stat().st_mode | stat.S_IEXEC)
        out = d / "out"
        out.write_text("", encoding="utf-8")
        env = {**os.environ, "PATH": f"{d / 'bin'}{os.pathsep}{os.environ['PATH']}", "GITHUB_OUTPUT": str(out),
               "REPO": "o/r", "BRANCH": "main", "GH_TOKEN": "x", "HEAD_SHA": head, "LAST_SHA": last or ""}
        p = subprocess.run(["bash", "-c", script], env=env, capture_output=True, text=True, timeout=30)
        check(p.returncode == 0, f"compare step failed: {p.stderr}")
        return kv(out.read_text(encoding="utf-8"))


@test
def nightly_compare_step_skips_an_unchanged_head():
    r = run_compare("abc123", "abc123")
    check(r == {"sha": "abc123", "run": "false"}, f"equal heads must skip: {r}")
    r = run_compare("def456", "abc123")
    check(r == {"sha": "def456", "run": "true"}, f"a moved head must run: {r}")
    r = run_compare("def456", None)
    check(r == {"sha": "def456", "run": "true"}, f"no earlier successful run must run: {r}")


@test
def ts_ci_plan_job_is_in_the_template():
    text = (TOOLING / "ts/.github/workflows/ci.yml").read_text(encoding="utf-8")
    plan = jobs_of(text.replace("\r\n", "\n"))["plan"]
    check("area_select.py --base" in plan and "area_select.py --all" in plan,
          "the plan job runs area_select.py for pull requests and --all otherwise")
    check("|| echo" in plan, "a failed plan step must not fail the job (every job then runs)")


# --------------------------------------------------------------------------- main


def main() -> int:
    failed = 0
    for fn in TESTS:
        try:
            fn()
        except Exception:  # noqa: BLE001 - report every failing test
            failed += 1
            print(f"FAIL  {fn.__name__}")
            print("      " + traceback.format_exc().strip().replace("\n", "\n      "))
        else:
            print(f"ok    {fn.__name__}")
    print(f"\n{len(TESTS) - failed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
