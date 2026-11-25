#!/usr/bin/env python3
"""DP6: after a PR merge the watcher runs the project's cleanup and smoke commands; a failure stops the next push.

Run:  python3 tools/test_delivery_watch_post_merge.py
"""
from __future__ import annotations

import sys
import tempfile
import traceback
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "claude/plugins/delivery/scripts"
sys.path.insert(0, str(SCRIPTS))
import delivery_watch as W  # noqa: E402

TESTS: list = []


def test(fn):
    TESTS.append(fn)
    return fn


class Sh:
    def __init__(self, fail=()):
        self.fail, self.calls = fail, []

    def run(self, argv, cwd=None, timeout=120):
        self.calls.append(argv)
        return (1, "", "boom") if any(f in " ".join(argv) for f in self.fail) else (0, "ok", "")


def watcher(cfg, fail=()):
    d = tempfile.mkdtemp()
    (Path(d) / ".delivery").mkdir()
    w = W.Watcher(d, sh=Sh(fail))
    w.cfg = cfg
    w.events = []
    led = {"events": []}
    w.mut = lambda fn: (fn(led), w.events.extend(e.get("kind") for e in led["events"]))
    return w


TRAIN = {"id": "T1", "pr": 42}


@test
def both_run_in_order_with_pr_number():
    w = watcher({"cleanup_command": "python cleanup.py --pr {pr}", "smoke_command": "python smoke.py {pr}"})
    assert w.after_merge(TRAIN) is True
    assert [c[1:] for c in w.sh.calls] == [["cleanup.py", "--pr", "42"], ["smoke.py", "42"]], w.sh.calls


@test
def unset_commands_are_skipped():
    w = watcher({})
    assert w.after_merge(TRAIN) is True and not w.sh.calls


@test
def cleanup_failure_stops_before_smoke():
    w = watcher({"cleanup_command": "python cleanup.py", "smoke_command": "python smoke.py"}, fail=("cleanup.py",))
    assert w.after_merge(TRAIN) is False
    assert len(w.sh.calls) == 1 and "post_merge.failed" in w.events, (w.sh.calls, w.events)


@test
def smoke_failure_stops():
    w = watcher({"cleanup_command": "python cleanup.py", "smoke_command": "python smoke.py"}, fail=("smoke.py",))
    assert w.after_merge(TRAIN) is False and len(w.sh.calls) == 2


def main():
    bad = 0
    for fn in TESTS:
        try:
            fn()
        except Exception:
            bad += 1
            print("FAIL", fn.__name__)
            traceback.print_exc()
    print("%d passed, %d failed" % (len(TESTS) - bad, bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
