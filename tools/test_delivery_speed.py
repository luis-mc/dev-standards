#!/usr/bin/env python3
"""Prove the speed probe, scaled(ms), ci.limits and the database-per-worker template (CIR10 L7, L8).

  * speed_probe.py: the median of the runs, scale never below 1, a probe above 3 refuses (exit 2, state
    error, never success), a budget at scale 1 equals the unscaled one, the env variable wins and a bad
    value refuses, calibrate writes the reference file.
  * scaled.mjs: the same rules in JavaScript (skipped when node is missing).
  * ci.limits: schema accepts it, rejects a bad value, ci_limits() gives measured defaults.
  * db_per_worker.py: names, the SQL, the worker id from the environment, a name cannot carry SQL.
  * mutants: copies with one rule broken must each fail a scenario.

Run:  python3 tools/test_delivery_speed.py
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DELIVERY = REPO / "claude/plugins/delivery"
DS = DELIVERY / "templates/shared/scripts/delivery"
sys.path.insert(0, str(DELIVERY / "scripts"))

TESTS: list = []


def test(fn):
    TESTS.append(fn)
    return fn


def check(cond, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run(script: Path, args: list, env: dict | None = None):
    p = subprocess.run([sys.executable, "-I", str(script), *args], capture_output=True, text=True,
                       encoding="utf-8", timeout=120, env=env)
    return p.returncode, p.stdout, p.stderr


class Clock:
    """A fake clock: each workload call advances it by the next duration (seconds)."""

    def __init__(self, durations):
        self.d, self.t, self.i, self.pending = list(durations), 0.0, 0, False

    def work(self):
        self.pending = True

    def now(self):
        if self.pending:
            self.t += self.d[self.i]
            self.i += 1
            self.pending = False
        return self.t


def probe_with(mod, durations_ms):
    c = Clock([x / 1000.0 for x in durations_ms])
    return mod.probe(len(durations_ms), work=c.work, clock=c.now)


@test
def probe_is_the_median():
    m = load(DS / "speed_probe.py", "sp1")
    check(abs(probe_with(m, [10, 90, 20, 30, 1000]) - 30) < 1e-6, "median of 5 runs")
    check(abs(probe_with(m, [10, 20]) - 15) < 1e-6, "median of 2 runs")
    check(m.DEFAULT_RUNS == 5, "default is 5 runs")


@test
def scale_never_below_one():
    m = load(DS / "speed_probe.py", "sp2")
    check(m.scale_from(25, 50) == 1.0, "a faster machine does not tighten budgets")
    check(m.scale_from(100, 50) == 2.0, "2x slower is scale 2")


@test
def scale_above_three_refuses():
    m = load(DS / "speed_probe.py", "sp3")
    check(m.check_scale(3.0) == 3.0, "exactly 3 is allowed")
    try:
        m.check_scale(3.01)
    except m.SpeedRefused:
        pass
    else:
        raise AssertionError("3.01 must refuse")
    try:
        m.get_scale(env={"DELIVERY_SPEED_SCALE": "3.5"})
    except m.SpeedRefused:
        pass
    else:
        raise AssertionError("env scale 3.5 must refuse")


@test
def bad_env_scale_refuses_not_scale_one():
    m = load(DS / "speed_probe.py", "sp4")
    for bad in ("abc", "0", "-2", "nan", "inf"):
        try:
            m.get_scale(env={"DELIVERY_SPEED_SCALE": bad})
        except m.SpeedRefused:
            continue
        raise AssertionError("%r must refuse" % bad)


@test
def budget_at_scale_one_equals_unscaled():
    m = load(DS / "speed_probe.py", "sp5")
    for ms in (1, 7, 200, 1500, 2.5):
        check(m.scaled(ms, 1.0) == ms and type(m.scaled(ms, 1.0)) is type(ms), "scaled(%s, 1) must be %s" % (ms, ms))
    check(m.get_scale(env={"DELIVERY_SPEED_SCALE": "1"}) == 1.0, "env 1 gives 1")
    check(m.scaled(200, 1.5) == 300 and m.scaled(101, 1.5) == 152, "above 1 it multiplies and rounds up")
    check(m.get_scale(env={"DELIVERY_SPEED_SCALE": "0.4"}) == 1.0, "a scale below 1 is raised to 1")


@test
def cli_refuses_with_error_state():
    d = Path(tempfile.mkdtemp())
    try:
        res = d / "r.json"
        # a reference far below the real time forces a scale above 3
        code, out, err = run(DS / "speed_probe.py", ["--runs", "1", "--reference-ms", "0.001", "--result", str(res)])
        check(code == 2, "refusal exits 2, got %s" % code)
        r = json.loads(res.read_text())
        check(r["state"] == "error" and r["state"] != "success", "state is error: %s" % r)
        check("REFUSED" in err, "stderr says refused: %s" % err)
        # a huge reference gives scale 1 and exit 0
        code, out, err = run(DS / "speed_probe.py", ["--runs", "1", "--reference-ms", "100000", "--json", "--result", str(res)])
        check(code == 0 and json.loads(out)["scale"] == 1.0, "slow reference -> scale 1, got %s %s" % (code, out))
        check(json.loads(res.read_text())["state"] == "ok", "ok state written")
        code, out, _ = run(DS / "speed_probe.py", ["--runs", "1", "--reference-ms", "100000", "--export-env"])
        check(out.strip() == "DELIVERY_SPEED_SCALE=1.0", "export-env line: %r" % out)
        code, _, _ = run(DS / "speed_probe.py", ["--runs", "0"])
        check(code == 64, "usage error exits 64, got %s" % code)
    finally:
        shutil.rmtree(d, ignore_errors=True)


@test
def calibrate_writes_reference():
    d = Path(tempfile.mkdtemp())
    try:
        f = d / "sub" / "speed-probe.json"
        code, out, _ = run(DS / "speed_probe.py", ["calibrate", "--runs", "1", "--file", str(f)])
        check(code == 0 and json.loads(f.read_text())["reference_ms"] > 0, "reference written")
        m = load(DS / "speed_probe.py", "sp6")
        ref, ok = m.read_reference(str(f))
        check(ok and ref > 0, "read back")
        check(m.read_reference(str(d / "none.json")) == (m.DEFAULT_REFERENCE_MS, False), "missing file -> built-in")
    finally:
        shutil.rmtree(d, ignore_errors=True)


@test
def scaled_mjs_matches():
    node = shutil.which("node")
    if not node:
        print("  (node missing: scaled.mjs not run)")
        return
    js = ("import {scaled,scaleFromEnv} from %s; const out=[scaled(200),scaled(101,1.5)];"
          "try{scaleFromEnv({DELIVERY_SPEED_SCALE:'3.5'});out.push('no throw')}catch(e){out.push('throws')}"
          "try{scaleFromEnv({DELIVERY_SPEED_SCALE:'x'});out.push('no throw')}catch(e){out.push('throws')}"
          "out.push(scaleFromEnv({DELIVERY_SPEED_SCALE:'0.5'}));console.log(JSON.stringify(out))"
          % json.dumps((DS / "scaled.mjs").as_uri()))
    p = subprocess.run([node, "--input-type=module", "-e", js], capture_output=True, text=True, timeout=30)
    check(p.returncode == 0 and json.loads(p.stdout) == [200, 152, "throws", "throws", 1], "mjs: %s %s" % (p.stdout, p.stderr))


@test
def ci_limits_config():
    C = load(DELIVERY / "scripts/delivery_config.py", "cfg")
    d = C.ci_limits({})
    check(d["cloud"] == {"browser_workers": 2, "memory_gib": 8.5}, "measured defaults: %s" % d)
    cfg = {"ci": {"limits": {"cloud": {"browser_workers": 4, "integration_workers": 3, "memory_gib": 16},
                             "self-hosted": {"browser_workers": 0, "memory_gib": True}}}}
    d = C.ci_limits(cfg)
    check(d["cloud"] == {"browser_workers": 4, "memory_gib": 16, "integration_workers": 3}, "set values: %s" % d["cloud"])
    check(d["self-hosted"] == {"browser_workers": 2, "memory_gib": 8.5}, "bad values fall back: %s" % d["self-hosted"])
    errs, _ = C.validate_config({"ci": {"limits": cfg["ci"]["limits"]["cloud"] and {"cloud": cfg["ci"]["limits"]["cloud"]}}})
    check(not errs, "valid config: %s" % errs)
    errs, _ = C.validate_config({"ci": {"limits": {"cloud": {"browser_workers": 0}}}})
    check(errs, "browser_workers 0 must be rejected")
    errs, _ = C.validate_config({"ci": {"limits": {"cloud": {"browser_workers": "2"}}}})
    check(errs, "a string worker count must be rejected")


@test
def db_per_worker():
    m = load(DS / "db_per_worker.py", "db")
    check(m.worker_db("app_test", 3) == "app_test_w3" and m.template_name("app_test") == "app_test_tpl", "names")
    check(m.this_worker({"VITEST_POOL_ID": "4"}) == 4 and m.this_worker({}) == 1, "worker id from env")
    sql = m.workers_sql("app_test", 2)
    check(sql[1] == 'CREATE DATABASE "app_test_w1" TEMPLATE "app_test_tpl";' and len(sql) == 4, "workers sql: %s" % sql)
    check(m.template_sql("app_test")[1] == 'CREATE DATABASE "app_test_tpl";', "template sql")
    check(m.teardown_sql("x", 2)[-1] == 'DROP DATABASE IF EXISTS "x_tpl" WITH (FORCE);', "teardown drops the template last")
    for bad in ('a"; DROP DATABASE b; --', "a b", "1abc", "", "x" * 60):
        try:
            m.check_name(bad)
        except ValueError:
            continue
        raise AssertionError("%r must be refused" % bad)
    calls = []

    class R:
        def __init__(self, rc):
            self.returncode = rc

    code = m.main(["setup", "--base", "t", "--workers", "2", "--run"], runner=lambda cmd, **k: calls.append(cmd) or R(0))
    check(code == 0 and len(calls) == 6 and calls[0][0] == "psql", "run sends 6 statements: %d" % len(calls))
    calls.clear()
    code = m.main(["setup", "--base", "t", "--workers", "2", "--run"], runner=lambda cmd, **k: calls.append(cmd) or R(1))
    check(code == 1 and len(calls) == 1, "stops at the first psql failure")
    check(m.main(["setup", "--base", "bad name"]) == 2, "bad name is a usage error")
    code, out, _ = run(DS / "db_per_worker.py", ["name", "--base", "app", "--worker", "2"])
    check(code == 0 and out.strip() == "app_w2", "name command: %r" % out)


@test
def mutants_fail():
    d = Path(tempfile.mkdtemp())
    try:
        src = (DS / "speed_probe.py").read_text()
        muts = {
            "limit 3 -> 30": ("DEFAULT_MAX_SCALE = 3.0", "DEFAULT_MAX_SCALE = 30.0"),
            "refusal -> ok": ('out["state"], out["summary"], code = "error", str(exc), EXIT_REFUSED',
                              'out["state"], out["summary"], code = "ok", str(exc), EXIT_OK'),
            "scale may go below 1": ("return max(1.0, median_ms / reference_ms)", "return median_ms / reference_ms"),
            "scale 1 changes budget": ("    if s == 1:\n        return ms\n", "    if s == 1:\n        return ms + 1\n"),
            "bad env -> 1": ("raise SpeedRefused(\"%s=%r is not a number\" % (ENV_SCALE, raw))", "return 1.0"),
        }
        for name, (old, new) in muts.items():
            check(old in src, "mutant anchor missing: %s" % name)
            f = d / ("m_%d.py" % abs(hash(name)))
            f.write_text(src.replace(old, new, 1))
            failed = False
            for fn in (scale_above_three_refuses, scale_never_below_one, budget_at_scale_one_equals_unscaled,
                       bad_env_scale_refuses_not_scale_one, cli_refuses_with_error_state):
                orig = globals()["DS"]
                try:
                    globals()["DS"] = d
                    shutil.copy(f, d / "speed_probe.py")
                    fn()
                except Exception:
                    failed = True
                finally:
                    globals()["DS"] = orig
                if failed:
                    break
            check(failed, "mutant survived: %s" % name)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def main() -> int:
    bad = 0
    for t in TESTS:
        try:
            t()
            print("ok   %s" % t.__name__)
        except Exception:  # noqa: BLE001
            bad += 1
            print("FAIL %s" % t.__name__)
            traceback.print_exc()
    print("%d/%d passed" % (len(TESTS) - bad, len(TESTS)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
