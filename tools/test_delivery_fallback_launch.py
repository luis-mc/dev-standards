#!/usr/bin/env python3
"""CIR10 S8: the fallback launchers and the ci_watch hook, proved with fakes (no network, no real session,
no GitHub run). A local bare git remote stands in for GitHub where git is the thing under test."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = REPO / "claude/plugins/delivery/templates/shared/scripts/delivery"
sys.path.insert(0, str(SCRIPTS))

import ci_watch as W  # noqa: E402
import fallback_launch as F  # noqa: E402
import fallback_run as R  # noqa: E402

SHA = "a" * 40
NOW = datetime(2026, 11, 3, 12, 0, tzinfo=timezone.utc).timestamp()
GIT_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
SHARDS = [
    {"id": "unit-linux", "os": "linux", "context": "unit (linux)", "commands": ["x"]},
    {"id": "int-linux", "os": "linux", "context": "int (linux)", "commands": ["x"]},
    {"id": "real-windows", "os": "windows", "context": "real (windows)", "commands": ["x"]},
]


def iso(minutes_ago: float) -> str:
    return (datetime.fromtimestamp(NOW, timezone.utc) - timedelta(minutes=minutes_ago)).isoformat().replace("+00:00", "Z")


def jobs_answer(spec):
    """gh_json fake: spec = [(job name, status, minutes queued, labels)]."""
    def gh(args):
        assert args[0] == "api" and "/jobs" in args[1]
        return {"jobs": [{"id": i, "name": n, "status": s, "created_at": iso(m), "labels": lab}
                         for i, (n, s, m, lab) in enumerate(spec)]}
    return gh


def config(kind="cloud", after=10):
    return {"ci": {"fallback": {"options": {"linux": kind, "windows": "github-hosted"}, "after_min": after,
                                "cloud": {"fire_url": "https://x/fire", "token_env": "T"}},
                   "cloud": {"repo": "o/r", "status_token_env": "S"}}}


def settings(kind="cloud", after=10):
    return F.settings_from(config(kind, after))


class Rec:
    """Fake launchers, reservation and caps gate that record what was asked."""

    def __init__(self, caps_ok=True, ready=True, settled=False):
        self.cloud, self.hosted, self.out, self.reserved, self.released, self.gated = [], [], [], [], [], []
        self.caps_ok, self.ready, self.settled = caps_ok, ready, settled
        self.cloud_busy, self.markers, self.claims = 0, {}, set()   # DL-90, DL-91

    def gate(self, st, os_name, waited):
        self.gated.append(os_name)
        return {"start": True} if self.caps_ok else {"start": False, "warning": "fallback paused: monthly cap"}

    def deps(self, gh_json, **over):
        kw = dict(gh_json=gh_json, now=lambda: NOW, out=self.out.append,
                  cloud=lambda st, sha, sh: self.cloud.append(sh["id"]),
                  hosted=lambda st, sha, sh: self.hosted.append(sh["id"]),
                  reserve=lambda sha, sh: self.reserved.append(sh) or True,
                  release=lambda sha, sh: self.released.append(sh),
                  settled=lambda sha, sh, prefix: self.settled,
                  ready_pr=lambda sha: self.ready, gate=self.gate, is_hosted=lambda l: "ubuntu-latest" in l,
                  cloud_sessions=lambda: self.cloud_busy, wait_marker=lambda sha, sh: self.markers.get(sh),
                  claimed=lambda sha, sh: sh in self.claims)
        kw.update(over)
        return F.Deps("/nowhere", "origin", "o/r", **kw)


RUNS = [{"databaseId": 7}]
SPEC_TWO_LATE = [("unit (linux)", "queued", 12, ["self-hosted", "linux"]),
                 ("int (linux)", "queued", 15, ["self-hosted", "linux"])]


class Hook(unittest.TestCase):
    def go(self, rec, spec, st=None, **over):
        return F.check_and_launch(SHA, RUNS, rec.deps(jobs_answer(spec), **over), st or settings(), SHARDS)

    def test_wait_under_x_starts_nothing(self):
        rec = Rec()
        got = self.go(rec, [("unit (linux)", "queued", 9.9, ["self-hosted"]), ("int (linux)", "queued", 1, ["self-hosted"])])
        self.assertEqual(got, [])
        self.assertEqual((rec.cloud, rec.hosted, rec.out), ([], [], []))

    def test_over_x_one_launch_per_waiting_shard_and_only_once(self):
        rec = Rec()
        deps = rec.deps(jobs_answer(SPEC_TWO_LATE))
        for _ in range(3):  # three polls of the same watch
            F.check_and_launch(SHA, RUNS, deps, settings(), SHARDS)
        self.assertEqual(sorted(rec.cloud), ["int-linux", "unit-linux"])
        self.assertEqual(rec.hosted, [])
        self.assertEqual(len(rec.reserved), 2)
        self.assertEqual(len(rec.gated), 2)  # caps are counted once per started shard
        self.assertEqual(len([l for l in rec.out if "started" in l]), 2)

    def test_cloud_limit_never_starts_an_extra_session(self):    # DL-91: 10 cloud CI sessions at most
        rec = Rec()
        rec.cloud_busy = 9
        got = self.go(rec, SPEC_TWO_LATE)
        self.assertEqual(rec.cloud, ["int-linux"])      # one place left: the first shard (sorted) starts, the second waits
        self.assertEqual(len(got), 1)
        self.assertTrue(any("limit 10" in l for l in rec.out))
        rec.cloud_busy = 10
        self.assertEqual(self.go(Rec(), SPEC_TWO_LATE, cloud_sessions=lambda: 10), [])

    def test_cloud_limit_does_not_hold_hosted_fallback(self):
        rec = Rec()
        rec.cloud_busy = 10
        self.go(rec, SPEC_TWO_LATE, settings("github-hosted"))
        self.assertEqual(sorted(rec.hosted), ["int-linux", "unit-linux"])

    def test_held_job_with_a_wait_marker_counts_as_waiting(self):     # DL-90, G6
        rec = Rec()
        started = [("unit (linux)", "in_progress", 12, ["self-hosted", "linux"])]
        self.assertEqual(self.go(rec, started), [])                     # started on GitHub, no marker: not waiting
        rec.markers["unit-linux"] = {"at": iso(12)}
        got = self.go(rec, started)
        self.assertEqual([g["shard"] for g in got], ["unit-linux"])
        rec2 = Rec()
        rec2.markers["unit-linux"] = {"at": iso(12)}
        rec2.claims.add("unit-linux")                                   # claimed: the marker no longer counts
        self.assertEqual(self.go(rec2, started), [])

    def test_only_shards_over_x_launch(self):
        rec = Rec()
        self.go(rec, [("unit (linux)", "queued", 12, ["self-hosted"]), ("int (linux)", "queued", 3, ["self-hosted"])])
        self.assertEqual(rec.cloud, ["unit-linux"])

    def test_hosted_kind_uses_the_hosted_launcher(self):
        rec = Rec()
        self.go(rec, SPEC_TWO_LATE, settings("github-hosted"))
        self.assertEqual((sorted(rec.hosted), rec.cloud), (["int-linux", "unit-linux"], []))

    def test_caps_paused_no_launch_and_one_warning(self):
        rec = Rec(caps_ok=False)
        deps = rec.deps(jobs_answer(SPEC_TWO_LATE))
        for _ in range(4):
            F.check_and_launch(SHA, RUNS, deps, settings(), SHARDS)
        self.assertEqual((rec.cloud, rec.hosted), ([], []))
        self.assertEqual(rec.out, ["ci_watch: fallback paused: monthly cap"])
        self.assertEqual(sorted(rec.released), sorted(rec.reserved))  # the launch stays possible later

    def test_only_runner_waits_count(self):
        rec = Rec()
        self.go(rec, [("unit (linux)", "in_progress", 30, ["self-hosted"]),   # already running
                      ("int (linux)", "queued", 30, ["ubuntu-latest"]),       # hosted: the platform's wait
                      ("other job", "queued", 30, ["self-hosted"]),           # not a shard
                      ("unit (linux)", "waiting", 30, ["self-hosted"])])      # approval, not a runner
        self.assertEqual((rec.cloud, rec.hosted), ([], []))

    def test_claimed_or_finished_shard_is_not_launched(self):
        rec = Rec(settled=True)
        self.go(rec, SPEC_TWO_LATE)
        self.assertEqual((rec.cloud, rec.reserved), ([], []))

    def test_second_watcher_loses_the_reservation(self):
        rec = Rec()
        self.go(rec, SPEC_TWO_LATE, reserve=lambda sha, sh: False)
        self.assertEqual(rec.cloud, [])

    def test_windows_goes_hosted_and_needs_a_ready_pr(self):
        spec = [("real (windows)", "queued", 20, ["self-hosted", "windows"])]
        rec = Rec(ready=True)
        self.go(rec, spec, settings("cloud"))
        self.assertEqual((rec.hosted, rec.cloud), (["real-windows"], []))
        rec = Rec(ready=False)
        self.go(rec, spec, settings("cloud"))
        self.assertEqual((rec.hosted, rec.cloud), ([], []))

    def test_windows_set_to_cloud_is_refused_with_one_warning(self):
        cfg = config()
        cfg["ci"]["fallback"]["options"]["windows"] = "cloud"
        rec = Rec()
        deps = rec.deps(jobs_answer([("real (windows)", "queued", 20, ["self-hosted"])]))
        for _ in range(3):
            F.check_and_launch(SHA, RUNS, deps, F.settings_from(cfg), SHARDS)
        self.assertEqual((rec.cloud, rec.hosted, len(rec.out)), ([], [], 1))

    def test_every_run_may_use_the_fallback_even_a_draft(self):  # answer 6
        rec = Rec(ready=False)
        self.go(rec, SPEC_TWO_LATE, settings("cloud"))
        self.assertEqual(len(rec.cloud), 2)

    def test_os_without_a_fallback_is_left_alone(self):
        cfg = config()
        del cfg["ci"]["fallback"]["options"]["linux"]
        rec = Rec()
        self.go(rec, SPEC_TWO_LATE, F.settings_from(cfg))
        self.assertEqual((rec.cloud, rec.hosted), ([], []))

    def test_launch_failure_warns_and_stops_after_three(self):
        rec = Rec()

        def boom(st, sha, sh):
            raise RuntimeError("503")
        deps = rec.deps(jobs_answer(SPEC_TWO_LATE[:1]), cloud=boom)
        for _ in range(6):
            F.check_and_launch(SHA, RUNS, deps, settings(), SHARDS)
        self.assertEqual(len(rec.out), 3)
        self.assertIn("503", rec.out[0])
        self.assertEqual(len(rec.released), 3)

    def test_no_config_no_launch_and_never_raises(self):
        rec = Rec()
        with tempfile.TemporaryDirectory() as empty:  # no ci.fallback in the config: nothing launches
            deps = rec.deps(jobs_answer(SPEC_TWO_LATE))
            deps.root = empty
            self.assertEqual(F.check_and_launch(SHA, RUNS, deps, None, SHARDS), [])
        self.assertEqual(rec.cloud, [])
        deps = rec.deps(lambda a: (_ for _ in ()).throw(RuntimeError("gh down")))
        self.assertEqual(F.check_and_launch(SHA, RUNS, deps, settings(), SHARDS), [])

    def test_settings_need_kind_and_x(self):
        self.assertIsNone(F.settings_from({}))
        self.assertIsNone(F.settings_from({"ci": {"fallback": {"options": {"linux": "cloud"}}}}))  # no X, no default
        self.assertIsNone(F.settings_from({"ci": {"fallback": {"options": {"linux": "other"}, "after_min": 5}}}))
        self.assertEqual(settings(after=10)["core"]["after_min"], 10)

    def test_job_shard_prefers_the_longest_name(self):
        shards = [{"id": "unit", "context": "unit"}, {"id": "unit-windows", "context": "unit (windows)"}]
        self.assertEqual(F.job_shard("Unit (windows) / run", shards)["id"], "unit-windows")


class Launchers(unittest.TestCase):
    def test_cloud_launch_posts_one_request_per_shard(self):
        calls = []
        st = settings()
        F.launch_cloud(st, SHA, SHARDS[0], post=lambda u, h, b: calls.append((u, h, b)) or 200, env={"T": "tok"})
        (url, headers, body), = calls
        self.assertEqual(url, "https://x/fire")
        self.assertEqual(headers["Authorization"], "Bearer tok")
        self.assertIn("--shard unit-linux", body["text"])
        self.assertIn(SHA, body["text"])
        self.assertNotIn("tok", body["text"])

    def test_cloud_launch_failures_raise(self):
        st = settings()
        with self.assertRaises(ValueError):
            F.launch_cloud(st, SHA, SHARDS[0], post=lambda *a: 200, env={})
        with self.assertRaises(RuntimeError):
            F.launch_cloud(st, SHA, SHARDS[0], post=lambda *a: 500, env={"T": "tok"})
        with self.assertRaises(ValueError):
            F.http_post("http://example.com/x", {}, {})

    def test_hosted_launch_dispatches_the_workflow(self):
        seen = []

        def run(args):
            seen.append(args)
            return subprocess.CompletedProcess(args, 0, "", "")
        F.launch_hosted(settings("github-hosted"), SHA, SHARDS[2], "o/r", run=run)
        args = seen[0]
        self.assertEqual(args[:3], ["workflow", "run", "ci-fallback.yml"])
        for want in ("sha=" + SHA, "shard=real-windows", "os=windows"):
            self.assertIn(want, args)
        with self.assertRaises(RuntimeError):
            F.launch_hosted(settings("github-hosted"), SHA, SHARDS[2], None, run=lambda a: subprocess.CompletedProcess(a, 1, "", "no"))

    def test_reserve_is_once_only_on_a_real_remote(self):
        base = Path(tempfile.mkdtemp(prefix="fb-"))
        subprocess.run(["git", "init", "-q", "--bare", str(base / "r.git")], check=True)
        subprocess.run(["git", "init", "-q", str(base / "w")], check=True)
        subprocess.run(["git", "remote", "add", "origin", str(base / "r.git")], cwd=base / "w", check=True)
        self.assertTrue(F.reserve_launch(str(base / "w"), "origin", SHA, "unit-linux"))
        self.assertFalse(F.reserve_launch(str(base / "w"), "origin", SHA, "unit-linux"))
        F.release_launch(str(base / "w"), "origin", SHA, "unit-linux")
        self.assertTrue(F.reserve_launch(str(base / "w"), "origin", SHA, "unit-linux"))  # free again
        self.assertTrue(F.reserve_launch(str(base / "w"), "origin", SHA, "int-linux"))
        self.assertTrue(F.remote_has(str(base / "w"), "origin", "ci-fallback/%s/*" % SHA))
        self.assertFalse(F.remote_has(str(base / "w"), "origin", "ci-claim/%s/*" % SHA))


class Sweep(unittest.TestCase):
    def test_sweep_groups_runs_by_commit_and_launches_over_x(self):
        rec = Rec()
        root = tempfile.mkdtemp(prefix="fbs-")
        os.makedirs(os.path.join(root, ".delivery"))
        os.makedirs(os.path.join(root, "scripts/delivery"))
        Path(root, ".delivery/config.json").write_text(json.dumps({"ci": {"fallback": {
            "options": {"linux": "cloud"}, "after_min": 10, "cloud": {"fire_url": "https://x", "token_env": "T"}}}}))
        Path(root, "scripts/delivery/ci-shards.json").write_text(json.dumps({"shards": SHARDS}))

        def gh(args):
            if args[0] == "run":
                return [{"databaseId": 7, "headSha": SHA}] if "queued" in args else []
            return jobs_answer(SPEC_TWO_LATE)(args)
        deps = rec.deps(gh)
        deps.root = root
        self.assertEqual(F.sweep(deps), 0)
        self.assertEqual(sorted(rec.cloud), ["int-linux", "unit-linux"])

    def test_routine_template_is_hourly_and_says_so(self):
        t = json.loads((SCRIPTS.parent.parent / "routines/ci-fallback-watch.json").read_text())
        self.assertIn("fallback_launch.py sweep", t["prompt"])
        self.assertIn("hour", t["_comment"])
        self.assertEqual(t["cron_expression"].split()[-5], "17")


class Run(unittest.TestCase):
    def project(self):
        base = Path(tempfile.mkdtemp(prefix="fbr-"))
        w = base / "w"
        subprocess.run(["git", "init", "-q", str(w)], check=True)
        (w / "scripts/delivery").mkdir(parents=True)
        (w / "scripts/delivery/ci-shards.json").write_text(json.dumps({"shards": [
            {"id": "s", "os": "linux", "context": "s (linux)", "commands": ["x"]}]}))
        env = {**os.environ, **GIT_ENV}
        subprocess.run(["git", "add", "-A"], cwd=w, check=True, env=env)
        subprocess.run(["git", "commit", "-qm", "c"], cwd=w, check=True, env=env)
        sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=w, capture_output=True, text=True).stdout.strip()
        return str(w), sha

    def test_lost_claim_runs_nothing_and_posts_nothing(self):
        root, sha = self.project()
        ran, posted = [], []

        class Core:
            def next_attempt(self, *a):
                return 1

            def claim(self, *a):
                return False

            def post_checked(self, *a):
                posted.append(a)
        code = R.main(["--sha", sha, "--shard", "s", "--who", "cloud", "--root", root], core=Core(),
                      shard_runner=lambda *a: ran.append(a))
        self.assertEqual((code, ran, posted), (0, [], []))

    def test_answered_shard_runs_nothing(self):
        root, sha = self.project()

        class Core:
            def next_attempt(self, *a):
                return None

            def claim(self, *a):
                raise AssertionError("claimed an answered shard")
        self.assertEqual(R.main(["--sha", sha, "--shard", "s", "--who", "cloud", "--root", root], core=Core(),
                                shard_runner=lambda *a: self.fail("ran")), 0)

    def test_claim_is_taken_before_the_tests_and_one_status_follows(self):
        root, sha = self.project()
        order = []

        class Core:
            def next_attempt(self, *a):
                return 1

            def claim(self, root_, remote, sha_, shard, attempt, holder):
                order.append("claim:%d:%s" % (attempt, holder))
                return True

            def post_checked(self, root_, remote, repo, token, result, sha_, shard, attempt, holder):
                order.append("post:" + result["state"])
                return {"posted": True}

        def runner(table, shard, cwd, sha_, timeout):
            order.append("tests")
            return {"schema": 1, "shard": shard, "context": "s (linux)", "os": "linux", "sha": sha_,
                    "state": "success", "summary": "ok", "commands": []}
        with mock.patch.object(R.cloud_shard, "push_result", return_value=(True, "b")), \
                mock.patch.dict(os.environ, {"GITHUB_TOKEN": "t", "GITHUB_REPOSITORY": "o/r"}):
            code = R.main(["--sha", sha, "--shard", "s", "--who", "hosted", "--root", root], core=Core(), shard_runner=runner)
        self.assertEqual((code, order), (0, ["claim:1:fallback-hosted", "tests", "post:success"]))

    def test_hosted_run_settles_its_reserved_minutes_and_cloud_does_not(self):
        # DS180: DL23 reserves the full shard timeout for a hosted shard; the run must settle it (DL23 open point)
        for who, settled in (("hosted", 1), ("cloud", 0)):
            root, sha = self.project()
            calls = []

            class Core:
                def next_attempt(self, *a):
                    return 1

                def claim(self, *a):
                    return True

                def post_checked(self, *a):
                    return {"posted": True}

                def fallback_settings(self, cfg):
                    return {"settings": True}

                def settle(self, root_, remote, settings, now, kind, reserved, actual):
                    calls.append((kind, reserved, actual >= 0))

            def runner(table, shard, cwd, sha_, timeout):
                return {"schema": 1, "shard": shard, "context": "s (linux)", "os": "linux", "sha": sha_,
                        "state": "success", "summary": "ok", "commands": []}
            with mock.patch.object(R.cloud_shard, "push_result", return_value=(True, "b")), \
                    mock.patch.dict(os.environ, {"GITHUB_TOKEN": "t", "GITHUB_REPOSITORY": "o/r", "CLOUD_TOKEN": "t"}):
                R.main(["--sha", sha, "--shard", "s", "--who", who, "--root", root], core=Core(), shard_runner=runner)
            self.assertEqual(len(calls), settled, who)
            if settled:
                self.assertEqual(calls[0], ("github-hosted", 60, True))

    def test_wrong_head_fails_closed(self):
        root, sha = self.project()
        self.assertEqual(R.main(["--sha", "b" * 40, "--shard", "s", "--who", "cloud", "--root", root],
                                shard_runner=lambda *a: self.fail("ran")), 2)


class WatchHook(unittest.TestCase):
    def test_ci_watch_calls_the_hook_on_a_pending_poll_and_not_with_the_flag(self):
        pending = [{"databaseId": 7, "workflowName": "ci", "status": "queued", "headSha": SHA}]
        base = ["--timeout", "0.01", "--interval", "0", "--no-post-run", SHA]
        for extra, calls in (([], 1), (["--no-fallback"], 0)):
            with mock.patch.object(W, "list_runs", return_value=pending), \
                    mock.patch.object(W, "warn_queued_jobs"), \
                    mock.patch.object(W.shutil, "which", return_value="/bin/gh"), \
                    mock.patch.object(W.fallback_launch, "check_and_launch") as hook, \
                    mock.patch.object(W, "fallback_deps", return_value=object()):
                code = W.main(extra + base)
            self.assertEqual(code, 4)
            self.assertEqual(hook.call_count > 0, bool(calls))
            if calls:
                self.assertEqual(hook.call_args.args[0], SHA)
                self.assertEqual(hook.call_args.args[1], pending)


if __name__ == "__main__":
    unittest.main()
