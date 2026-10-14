#!/usr/bin/env python3
"""Prove runner_plan.py does what its docstring says (DELIVERYSPEC DL-50, DL-51, D6).

The unit scenarios inject the OS and gh calls (fake clock, gh, memory, service control, process
table); two end-to-end scenarios run the real script as a subprocess with a stub `gh` on PATH and
send it a real SIGTERM. Nothing here touches a real runner or GitHub.

Run:  python3 tools/test_delivery_runner.py [-k SUBSTRING]
Exit: 0 all passed, 1 otherwise.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import traceback
import contextlib
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DS = REPO / "claude/plugins/project-setup/skills/tech-stack-setup/assets/tooling/shared/scripts/delivery"
sys.path.insert(0, str(DS))
import runner_plan as rp  # noqa: E402

TMP = Path(tempfile.mkdtemp(prefix="runner-plan-test-"))
SCENARIOS = []


def scenario(fn):
    SCENARIOS.append(fn)
    return fn


class Clock:
    """Fake time: sleep() advances it."""
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, s):
        self.now += s


class FakeChild:
    def __init__(self, code=0, on_wait=None):
        self.pid, self.code, self.on_wait = 4242, code, on_wait

    def wait(self, timeout=None):
        if self.on_wait:
            self.on_wait()
        return self.code

    def poll(self):
        return self.code

    def terminate(self):
        pass

    def kill(self):
        pass


class Spy:
    def __init__(self):
        self.events = []

    def record(self, kind, data, root=None):
        self.events.append((kind, dict(data)))

    def states(self, kind="job"):
        return [d.get("state") if kind == "job" else d.get("paused_by") for k, d in self.events if k == kind]


def new_root():
    d = Path(tempfile.mkdtemp(dir=TMP))
    return str(d)


def cfg(**kw):
    c = dict(rp.DEFAULTS)
    c.update(kw)
    return c


def make_plan(root, cmd=("x",), config=None, runs=None, free=None, svc=None, alive=None, child=None,
              ledger=None, label="build"):
    clock = Clock()
    spy = ledger or Spy()
    svc_calls = svc if svc is not None else []

    def gh(_args):
        r = runs(clock) if callable(runs) else runs
        return r

    def service(action, name):
        svc_calls.append((action, name))
        return True

    plan = rp.Plan(root, config or cfg(poll_seconds=20), label, list(cmd), ledger=rp.Ledger(root, spy),
                   gh=gh, free_mb=(free or (lambda: None)), service=service,
                   alive=(alive or (lambda pid: False)), sleep=clock.sleep, clock=clock,
                   popen=lambda c, **k: (child or FakeChild()), limits=lambda *a: None)
    return plan, spy, clock, svc_calls


def run_logged(plan):
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        code = plan.run()
    return code, err.getvalue()


def run_obj(branch="release/29", status="in_progress"):
    return [{"databaseId": 777, "status": status, "headBranch": branch, "workflowName": "ci", "event": "pull_request"}]


@scenario
def waits_for_train_ci_and_logs_every_minute():
    root = new_root()
    # CI is running for 150 seconds, then done
    plan, spy, clock, _ = make_plan(root, runs=lambda c: run_obj() if c.now < 150 else [])
    code, err = run_logged(plan)
    lines = [l for l in err.splitlines() if "waiting for CI 777" in l]
    assert code == 0, (code, err)
    assert len(lines) == 3, lines                       # at 0, 60 and 120 seconds
    assert "release/29" in lines[0] and "in_progress" in lines[0], lines[0]
    assert "waiting-ci" in spy.states() and spy.states()[-1] == "done", spy.states()


@scenario
def other_branches_and_finished_runs_do_not_block():
    root = new_root()
    runs = run_obj("dependabot/npm/x") + run_obj("release/30", "completed") + run_obj("main", "queued")
    plan, spy, clock, _ = make_plan(root, runs=runs)
    code, err = run_logged(plan)
    assert code == 0 and "waiting for CI" not in err and clock.now == 0, (code, err, clock.now)


@scenario
def gh_failure_warns_and_does_not_block():
    root = new_root()
    plan, _, _, _ = make_plan(root, runs=None)
    code, err = run_logged(plan)
    assert code == 0 and "not waiting for CI" in err, (code, err)


@scenario
def gives_up_after_max_wait():
    root = new_root()
    plan, spy, _, svc = make_plan(root, config=cfg(poll_seconds=30, max_wait_minutes=3, pause_service="runner"),
                                  runs=run_obj())
    code, err = run_logged(plan)
    assert code == rp.EXIT_TIMEOUT and "gave up waiting" in err, (code, err)
    assert svc == [], "nothing was paused before the wait ended"
    assert not os.path.exists(plan.lock_path)


@scenario
def one_heavy_job_at_a_time():
    root = new_root()
    lock = Path(root, ".delivery", rp.LOCK_NAME)
    lock.parent.mkdir(parents=True)
    lock.write_text(json.dumps({"pid": 99, "label": "other", "job": "other-1"}))
    alive = {"yes": True}
    plan, spy, clock, _ = make_plan(root, alive=lambda pid: alive["yes"] and clock.now < 90)
    code, err = run_logged(plan)
    assert code == 0 and "another heavy job (other, pid 99)" in err and clock.now >= 90, (code, err)
    assert not lock.exists(), "released at the end"


@scenario
def a_dead_owners_lock_is_taken_over():
    root = new_root()
    lock = Path(root, ".delivery", rp.LOCK_NAME)
    lock.parent.mkdir(parents=True)
    lock.write_text(json.dumps({"pid": 99, "label": "ghost", "job": "ghost-1"}))
    plan, _, clock, _ = make_plan(root, alive=lambda pid: False)
    code, err = run_logged(plan)
    assert code == 0 and clock.now == 0 and "another heavy job" not in err, (code, err)


@scenario
def memory_floor_is_enforced():
    root = new_root()
    readings = iter([1000, 1500, 3000, 3000])
    plan, _, clock, _ = make_plan(root, config=cfg(poll_seconds=30, min_free_mb=2048), free=lambda: next(readings))
    code, err = run_logged(plan)
    assert code == 0 and "1000 MB free, need 2048 MB" in err and clock.now >= 60, (code, err, clock.now)
    # unknown free memory never blocks
    plan, _, clock, _ = make_plan(new_root(), config=cfg(min_free_mb=2048), free=lambda: None)
    assert run_logged(plan)[0] == 0 and clock.now == 0


@scenario
def runner_is_paused_and_always_resumed():
    for child, boom in ((FakeChild(0), False), (FakeChild(7), False), (None, True)):
        root = new_root()
        spy = Spy()

        class Boom(FakeChild):
            def wait(self, timeout=None):
                raise RuntimeError("boom")
        plan, spy, _, svc = make_plan(root, config=cfg(pause_service="runner-svc"), child=(Boom() if boom else child),
                                      ledger=spy)
        try:
            code, err = run_logged(plan)
        except RuntimeError:
            code = None
        assert svc == [("stop", "runner-svc"), ("start", "runner-svc")], (child, svc)
        assert spy.states("runner")[-1] is None, spy.events
        assert [d["paused_by"] for k, d in spy.events if k == "runner"][0].startswith("build-"), spy.events
        assert not os.path.exists(plan.lock_path)
        if not boom:
            assert code == (0 if child.code == 0 else 7), code


@scenario
def interrupt_stops_the_child_and_resumes():
    root = new_root()
    holder = {}

    def interrupt():
        holder["plan"].on_signal(signal.SIGTERM, None)
    child = FakeChild(0, on_wait=interrupt)
    plan, spy, _, svc = make_plan(root, config=cfg(pause_service="svc"), child=child)
    holder["plan"] = plan
    code, err = run_logged(plan)
    assert code == rp.EXIT_INTERRUPTED and svc[-1] == ("start", "svc"), (code, svc)
    assert spy.states()[-1] == "failed"


@scenario
def ledger_records_job_and_is_a_noop_when_absent():
    root = new_root()
    plan, spy, _, _ = make_plan(root, cmd=("echo", "hi"), label="B14-build")
    run_logged(plan)
    jobs = [d for k, d in spy.events if k == "job"]
    last = jobs[-1]
    assert last["state"] == "done" and last["heavy"] is True and last["cmd"] == "echo hi", last
    assert last["id"].startswith("B14-build-") and last["exit_code"] == 0
    # no ledger module: nothing raised, no file made
    assert rp.Ledger(root, None).record("job", {"id": "x"}) is None
    # a ledger module that raises must not stop the job
    class Bad:
        def record(self, *a, **k):
            raise ValueError("nope")
    plan, _, _, _ = make_plan(new_root())
    plan.ledger = rp.Ledger(root, Bad())
    code, err = run_logged(plan)
    assert code == 0 and "ledger not updated" in err


@scenario
def ledger_module_found_through_env():
    root = new_root()
    mod = Path(root, "led.py")
    out = Path(root, "calls.jsonl")
    mod.write_text("import json\ndef record(kind, data, root=None):\n    open(%r,'a').write(json.dumps([kind, data['state'] if kind=='job' else data['paused_by']])+'\\n')\n" % str(out))
    os.environ["DELIVERY_LEDGER"] = str(mod)
    try:
        found = rp.find_ledger_module(root)
        assert found is not None
        rp.Ledger(root, found).record("job", {"state": "running"})
    finally:
        del os.environ["DELIVERY_LEDGER"]
    assert json.loads(out.read_text().splitlines()[0]) == ["job", "running"]


@scenario
def config_file_and_options():
    root = new_root()
    Path(root, ".delivery").mkdir()
    Path(root, ".delivery", "config.json").write_text(json.dumps(
        {"runner_plan": {"min_free_mb": 1234, "pause_service": "svc", "bogus": 1}}))
    c = rp.load_config(root)
    assert c["min_free_mb"] == 1234 and c["pause_service"] == "svc" and "bogus" not in c
    assert rp.load_config(new_root())["min_free_mb"] == 0
    assert rp.main(["run", "--label", "x"]) == rp.EXIT_USAGE            # no command
    assert rp.main(["run", "--label", "x", "--train-branch-regex", "(", "--", "true"]) == rp.EXIT_USAGE


def real_run(root, extra_args, cmd, env_extra=None, wait=True):
    env = dict(os.environ)
    env.update(env_extra or {})
    p = subprocess.Popen([sys.executable, str(DS / "runner_plan.py"), "run", "--label", "e2e", "--root", root,
                          "--poll-seconds", "1", *extra_args, "--", *cmd],
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
    return p


def stub_gh(bin_dir, runs):
    Path(bin_dir).mkdir(parents=True, exist_ok=True)
    gh = Path(bin_dir, "gh")
    gh.write_text("#!%s\nimport json, os, sys\nprint(open(os.environ['STUB_RUNS']).read())\n" % sys.executable)
    gh.chmod(0o755)
    return gh


@scenario
def end_to_end_waits_for_ci_then_runs_and_exit_code_passes_through():
    if os.name == "nt":
        return
    root = new_root()
    bin_dir = Path(root, "bin")
    stub_gh(bin_dir, None)
    runs = Path(root, "runs.json")
    runs.write_text(json.dumps(run_obj()))
    env = {"PATH": str(bin_dir) + os.pathsep + os.environ["PATH"], "STUB_RUNS": str(runs)}
    marker = Path(root, "ran")
    p = real_run(root, [], [sys.executable, "-c", "import sys; open(%r,'w').write('x'); sys.exit(3)" % str(marker)], env)
    time.sleep(2.5)
    assert p.poll() is None and not marker.exists(), "must still be waiting for CI"
    runs.write_text("[]")
    out, err = p.communicate(timeout=30)
    assert p.returncode == 3 and marker.exists(), (p.returncode, err)
    assert "waiting for CI 777" in err, err
    assert not Path(root, ".delivery", rp.LOCK_NAME).exists()


@scenario
def end_to_end_sigterm_stops_the_child_and_restarts_the_service():
    if os.name == "nt":
        return
    root = new_root()
    bin_dir = Path(root, "bin")
    stub_gh(bin_dir, None)
    runs = Path(root, "runs.json")
    runs.write_text("[]")
    log = Path(root, "svc.log")
    systemctl = Path(bin_dir, "systemctl")
    systemctl.write_text("#!/bin/sh\necho \"$1 $2\" >> %s\n" % log)
    systemctl.chmod(0o755)
    env = {"PATH": str(bin_dir) + os.pathsep + os.environ["PATH"], "STUB_RUNS": str(runs)}
    started = Path(root, "started")
    p = real_run(root, ["--pause-service", "gh-runner"],
                 [sys.executable, "-c", "import time; open(%r,'w').write('x'); time.sleep(60)" % str(started)], env)
    for _ in range(100):
        if started.exists():
            break
        time.sleep(0.1)
    assert started.exists(), "child never started"
    p.send_signal(signal.SIGTERM)
    out, err = p.communicate(timeout=30)
    assert p.returncode == rp.EXIT_INTERRUPTED, (p.returncode, err)
    assert log.read_text().split("\n")[:2] == ["stop gh-runner", "start gh-runner"], log.read_text()
    assert not Path(root, ".delivery", rp.LOCK_NAME).exists()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("-k", default="")
    args = ap.parse_args()
    failed = 0
    for fn in SCENARIOS:
        if args.k and args.k not in fn.__name__:
            continue
        try:
            fn()
            print("PASS  " + fn.__name__)
        except Exception:
            failed += 1
            print("FAIL  " + fn.__name__)
            traceback.print_exc()
    shutil.rmtree(TMP, ignore_errors=True)
    print("%d failed" % failed if failed else "all passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
