#!/usr/bin/env python3
"""DL23 (CIR10 S7): Option 4 core, ci_fallback.py. No network: a local bare git remote stands in for GitHub, a local
HTTP server records every commit status. Each 'machine' (main runner, fallback) is its own clone. Standard library."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "claude/plugins/delivery/templates/shared/scripts/delivery"))
import ci_fallback as F  # noqa: E402
import pass_records as PR  # noqa: E402

T0 = datetime(2026, 11, 3, 10, 0, tzinfo=timezone.utc)
SHA = "a" * 40
SHARD, CTX = "unit-linux", "unit (linux)"
ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}


class Api(BaseHTTPRequestHandler):
    posts: list = []

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        Api.posts.append((self.path, body))
        self.send_response(201)
        self.end_headers()
        self.wfile.write(b"{}")

    def log_message(self, *a):
        pass


def sh(cwd, *args):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, env={**os.environ, **ENV})
    assert r.returncode == 0, (args, r.stderr)
    return r.stdout.strip()


def result(state="success", sha=SHA):
    return {"sha": sha, "shard": SHARD, "context": CTX, "state": state, "summary": state}


def cfg(**fb):
    return {"ci": {"fallback": {"options": {"linux": "cloud", "windows": "github-hosted"}, "after_min": 10, **fb}}}


class Base(unittest.TestCase):
    def setUp(self):
        base = Path(tempfile.mkdtemp(prefix="fb-"))
        self.remote = str(base / "remote.git")
        subprocess.run(["git", "init", "-q", "--bare", self.remote], check=True)
        self.clones = {}
        for name in ("main", "fallback", "watcher"):
            d = base / name
            subprocess.run(["git", "init", "-q", str(d)], check=True)
            sh(d, "remote", "add", "origin", self.remote)
            self.clones[name] = str(d)
        Api.posts = []
        self.srv = HTTPServer(("127.0.0.1", 0), Api)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        patch = mock.patch.dict(os.environ, {"DELIVERY_GITHUB_API": "http://127.0.0.1:%d" % self.srv.server_port})
        patch.start()
        self.addCleanup(patch.stop)
        self.addCleanup(self.srv.server_close)
        self.addCleanup(self.srv.shutdown)

    def claim(self, who, attempt=1, now=T0):
        return F.claim(self.clones[who], "origin", SHA, SHARD, attempt, who, now)

    def post(self, who, attempt=1, state="success"):
        return F.post_checked(self.clones[who], "origin", "o/r", "tok", result(state), SHA, SHARD, attempt, who)

    def posted(self):
        return [(p, b["context"], b["state"]) for p, b in Api.posts]


class SettingsAndWaitTests(unittest.TestCase):
    def test_after_min_has_no_default(self):
        self.assertFalse(F.fallback_settings({"ci": {"fallback": {"options": {"linux": "cloud"}}}})["enabled"])
        self.assertFalse(F.fallback_settings({})["enabled"])
        s = F.fallback_settings(cfg())
        self.assertTrue(s["enabled"])
        self.assertEqual((s["only_for"], s["max_shards_per_day"], s["max_minutes_per_month"]), ("all", None, None))

    def test_bad_values_are_dropped(self):
        s = F.fallback_settings(cfg(after_min=True, max_shards_per_day=-1, max_minutes_per_month="x"))
        self.assertFalse(s["enabled"])
        self.assertIsNone(s["max_shards_per_day"])
        self.assertEqual(F.fallback_settings({"ci": {"fallback": {"options": {"linux": "bogus"}, "after_min": 5}}})["options"], {})

    def test_only_a_runner_wait_counts(self):
        q = {"status": "queued", "created_at": "2026-11-03T09:40:00Z", "started_at": None}
        self.assertEqual(F.shard_wait_minutes([q], T0), 20.0)
        self.assertIsNone(F.shard_wait_minutes([q], T0, run_status="pending"))      # CI_SERIAL queue
        self.assertIsNone(F.shard_wait_minutes([], T0))                              # no jobs yet
        self.assertIsNone(F.shard_wait_minutes([q, {"status": "in_progress", "started_at": "2026-11-03T09:50:00Z"}], T0))
        self.assertIsNone(F.shard_wait_minutes([{"status": "completed", "created_at": "2026-11-03T09:40:00Z"}], T0))
        old = dict(q, created_at="2026-11-03T09:30:00Z")
        self.assertEqual(F.shard_wait_minutes([q, old], T0), 30.0)

    def test_decision(self):
        s = F.fallback_settings(cfg(after_min_if_offline=2))
        self.assertFalse(F.fallback_decision(s, "linux", 9.9)["start"])
        d = F.fallback_decision(s, "linux", 10)
        self.assertEqual((d["start"], d["kind"]), (True, "cloud"))
        self.assertFalse(F.fallback_decision(s, "linux", 3)["start"])
        self.assertTrue(F.fallback_decision(s, "linux", 3, offline=True)["start"])
        self.assertFalse(F.fallback_decision(s, "macos", 99)["start"])
        self.assertFalse(F.fallback_decision(s, "linux", None)["start"])
        same = F.fallback_settings(cfg())
        self.assertFalse(F.fallback_decision(same, "linux", 3, offline=True)["start"])   # offline wait defaults to X
        self.assertEqual(F.fallback_decision(s, "windows", 10)["kind"], "github-hosted")
        self.assertFalse(F.fallback_decision(F.fallback_settings({}), "linux", 99)["start"])


class SimulationTests(Base):
    def test_main_first_fallback_loses_and_posts_nothing(self):
        self.assertTrue(self.claim("main"))
        self.assertFalse(self.claim("fallback"))
        self.assertFalse(self.post("fallback")["posted"])
        self.assertTrue(self.post("main")["posted"])
        self.assertEqual(self.posted(), [("/repos/o/r/statuses/" + SHA, CTX, "success")])

    def test_fallback_first_main_ends_in_seconds(self):
        self.assertTrue(self.claim("fallback"))
        self.assertFalse(self.claim("main"))           # no pre-emption, answer 9
        self.assertEqual(F.read_claim(self.clones["main"], "origin", SHA, SHARD, 1)["holder"], "fallback")
        self.assertFalse(self.post("main")["posted"])
        self.assertTrue(self.post("fallback", state="failure")["posted"])
        self.assertEqual([s for _, _, s in self.posted()], ["failure"])

    def test_a_tie_has_one_winner(self):
        for round_ in range(5):
            sha = ("%d" % round_) * 40
            wins, barrier = [], threading.Barrier(2)

            def go(who):
                barrier.wait()
                wins.append((who, F.claim(self.clones[who], "origin", sha, SHARD, 1, who, T0)))
            ts = [threading.Thread(target=go, args=(w,)) for w in ("main", "fallback")]
            [t.start() for t in ts]
            [t.join() for t in ts]
            self.assertEqual(sum(1 for _, ok in wins if ok), 1, wins)

    def test_main_frees_mid_fallback_the_fallback_finishes_alone(self):
        self.assertTrue(self.claim("fallback"))
        self.assertFalse(self.claim("main"))                      # the runner frees, sees the claim, ends
        self.assertEqual(F.next_attempt(self.clones["main"], "origin", SHA, SHARD), 1)   # live claim: attempt 1 stays
        self.assertTrue(self.post("fallback")["posted"])
        self.assertFalse(self.post("fallback")["posted"])         # a second post of the same attempt is refused
        self.assertEqual(len(self.posted()), 1)
        self.assertIsNone(F.next_attempt(self.clones["main"], "origin", SHA, SHARD))   # answered: nothing to claim

    def test_post_refuses_other_sha_non_holder_and_no_claim(self):
        self.assertFalse(self.post("main")["posted"])             # no claim at all
        self.claim("main")
        other = F.post_checked(self.clones["main"], "origin", "o/r", "tok", result(sha="b" * 40), SHA, SHARD, 1, "main")
        self.assertFalse(other["posted"])
        self.assertIn("not", other["reason"])
        self.assertFalse(self.post("fallback")["posted"])         # not the holder
        self.assertEqual(Api.posts, [])

    def test_dead_claim_is_reaped_then_attempt_two_answers(self):
        self.assertTrue(self.claim("main", now=T0))
        w = self.clones["watcher"]
        early = F.reap(w, "origin", "o/r", "tok", SHA, SHARD, CTX, 60, now=T0 + timedelta(minutes=59))
        self.assertEqual(early["action"], "none")
        self.assertEqual(Api.posts, [])
        late = F.reap(w, "origin", "o/r", "tok", SHA, SHARD, CTX, 60, now=T0 + timedelta(minutes=61))
        self.assertEqual((late["action"], late["attempt"], late["next_attempt"]), ("reaped", 1, 2))
        self.assertEqual(self.posted(), [("/repos/o/r/statuses/" + SHA, CTX, "error")])
        again = F.reap(w, "origin", "o/r", "tok", SHA, SHARD, CTX, 60, now=T0 + timedelta(minutes=70))
        self.assertEqual(again["action"], "none")                  # one error post only
        self.assertFalse(self.post("main")["posted"])              # the dead holder wakes up late: refused
        self.assertEqual(F.next_attempt(w, "origin", SHA, SHARD), 2)
        self.assertFalse(self.claim("main", attempt=3))            # no attempt beyond the cap
        self.assertTrue(self.claim("fallback", attempt=2, now=T0 + timedelta(minutes=62)))
        self.assertTrue(self.post("fallback", attempt=2)["posted"])
        self.assertEqual([s for _, _, s in self.posted()], ["error", "success"])
        self.assertFalse(self.post("main", attempt=1)["posted"])

    def test_attempt_two_dying_ends_at_the_cap(self):
        self.claim("main", now=T0)
        F.reap(self.clones["watcher"], "origin", "o/r", "tok", SHA, SHARD, CTX, 60, now=T0 + timedelta(minutes=61))
        self.claim("fallback", attempt=2, now=T0 + timedelta(minutes=62))
        fin = F.reap(self.clones["watcher"], "origin", "o/r", "tok", SHA, SHARD, CTX, 60, now=T0 + timedelta(minutes=125))
        self.assertEqual((fin["action"], fin["attempt"], fin["next_attempt"]), ("reaped-final", 2, None))
        self.assertIsNone(F.next_attempt(self.clones["watcher"], "origin", SHA, SHARD))
        self.assertEqual([s for _, _, s in self.posted()], ["error", "error"])

    def test_a_pushed_result_branch_is_not_reaped(self):
        self.claim("main", now=T0)
        w = self.clones["watcher"]
        sh(w, "commit", "-q", "--allow-empty", "-m", "r")
        sh(w, "push", "-q", "origin", "HEAD:refs/heads/ci-result/%s/%s" % (SHA, SHARD))
        r = F.reap(w, "origin", "o/r", "tok", SHA, SHARD, CTX, 60, now=T0 + timedelta(hours=5))
        self.assertEqual(r["action"], "none")
        self.assertEqual(Api.posts, [])

    def test_a_failed_api_call_frees_the_marker_for_a_retry(self):
        self.claim("main")
        with mock.patch.object(F.CS, "post_status", side_effect=OSError("down")):
            r = self.post("main")
        self.assertFalse(r["posted"])
        self.assertTrue(r.get("error"))
        self.assertTrue(self.post("main")["posted"])
        self.assertEqual(len(self.posted()), 1)

    def test_concurrent_posts_of_one_attempt_make_one_status(self):
        self.claim("main")
        barrier, out = threading.Barrier(2), []

        def go():
            barrier.wait()
            out.append(self.post("main")["posted"])
        ts = [threading.Thread(target=go) for _ in range(2)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        self.assertEqual(sorted(out), [False, True])
        self.assertEqual(len(Api.posts), 1)


class CapTests(Base):
    def gate(self, c, waited=15, os_name="linux", now=T0, who="watcher"):
        return F.fallback_gate(self.clones[who], "origin", c, os_name, waited, False, now, 60)

    def test_no_caps_means_no_limit_and_no_counter_use_beyond_counting(self):
        for _ in range(5):
            self.assertTrue(self.gate(cfg())["start"])

    def test_daily_cap_pauses_and_never_overruns(self):
        c = cfg(max_shards_per_day=2)
        self.assertTrue(self.gate(c)["start"])
        self.assertTrue(self.gate(c)["start"])
        g = self.gate(c)
        self.assertFalse(g["start"])
        self.assertEqual(g["warning"], "fallback paused: daily cap")
        self.assertTrue(self.gate(c, now=T0 + timedelta(days=1))["start"])    # a new day starts clean

    def test_monthly_minutes_cap_counts_hosted_only(self):
        c = cfg(max_minutes_per_month=100)
        self.assertTrue(self.gate(c, os_name="windows")["start"])             # reserves 60
        g = self.gate(c, os_name="windows")                                   # 60 + 60 > 100
        self.assertEqual((g["start"], g["warning"]), (False, "fallback paused: monthly cap"))
        self.assertTrue(self.gate(c, os_name="linux")["start"])               # cloud uses no hosted minutes
        s = F.fallback_settings(c)
        F.settle(self.clones["watcher"], "origin", s, T0, "github-hosted", 60, 12)   # it really took 12
        self.assertTrue(self.gate(c, os_name="windows")["start"])             # 12 + 60 <= 100

    def test_counter_keeps_the_pass_records_on_the_shared_branch(self):
        # DS180: DL20 pass records and the DL23 counter share one orphan branch; a counter write must not drop records
        w = self.clones["watcher"]
        rec = PR.make_record(SHARD, "f" * 64, "success", SHA, "feature")
        ok, msg = PR.write(w, "origin", F.DEFAULT_RECORDS_BRANCH, "feature", rec)
        self.assertTrue(ok, msg)
        self.assertTrue(self.gate(cfg(max_shards_per_day=5))["start"])         # writes the counter
        self.assertTrue(self.gate(cfg(max_shards_per_day=5))["start"])
        sh(w, "fetch", "-q", "origin", "+refs/heads/%s:refs/tmp/rb" % F.DEFAULT_RECORDS_BRANCH)
        files = sh(w, "ls-tree", "-r", "--name-only", "refs/tmp/rb").split("\n")
        self.assertIn(F.COUNTER_FILE, files)
        self.assertIn(PR.record_path("feature", SHARD, "f" * 64), files)

    def test_two_watchers_never_pass_the_cap(self):
        c = cfg(max_shards_per_day=3)
        barrier, out = threading.Barrier(4), []

        def go(who):
            barrier.wait()
            out.append(self.gate(c, who=who)["start"])
        ts = [threading.Thread(target=go, args=(w,)) for w in ("main", "fallback", "watcher", "watcher")]
        # two threads share one clone: give the extra one its own
        extra = Path(tempfile.mkdtemp(prefix="fb-x-"))
        subprocess.run(["git", "init", "-q", str(extra)], check=True)
        sh(extra, "remote", "add", "origin", self.remote)
        ts[3] = threading.Thread(target=lambda: (barrier.wait(), out.append(
            F.fallback_gate(str(extra), "origin", c, "linux", 15, False, T0, 60)["start"])))
        [t.start() for t in ts]
        [t.join() for t in ts]
        self.assertEqual(sum(out), 3, out)

    def test_not_waited_long_enough_reserves_nothing(self):
        c = cfg(max_shards_per_day=1)
        self.assertFalse(self.gate(c, waited=3)["start"])
        self.assertTrue(self.gate(c, waited=15)["start"])


class CliTests(Base):
    def run_cli(self, who, *argv):
        out = []
        with mock.patch("builtins.print", side_effect=lambda *a, **k: out.append(" ".join(map(str, a)))):
            code = F.main(["--root", self.clones[who], *argv])
        return code, "\n".join(out)

    def test_claim_cli_exit_codes(self):
        a = ("claim", "--sha", SHA, "--shard", SHARD)
        self.assertEqual(self.run_cli("main", *a, "--holder", "main")[0], 0)
        self.assertEqual(self.run_cli("fallback", *a, "--holder", "fallback")[0], 3)
        self.assertEqual(self.run_cli("fallback", "claim", "--sha", SHA)[0], 2)

    def test_post_cli_uses_the_token_variable_and_one_status(self):
        self.run_cli("main", "claim", "--sha", SHA, "--shard", SHARD, "--holder", "main")
        rf = Path(self.clones["main"]) / "r.json"
        rf.write_text(json.dumps(result()))
        with mock.patch.dict(os.environ, {"TOK": "secret"}):
            args = ("post", "--sha", SHA, "--shard", SHARD, "--attempt", "1", "--holder", "main",
                    "--result", str(rf), "--repo", "o/r", "--token-env", "TOK")
            self.assertEqual(self.run_cli("main", *args)[0], 0)
            code, out = self.run_cli("main", *args)
        self.assertEqual(code, 1)
        self.assertNotIn("secret", out)
        self.assertEqual(len(Api.posts), 1)


class SourceTests(unittest.TestCase):
    def test_no_actions_no_webhook_standard_library_only(self):
        src = (REPO / "claude/plugins/delivery/templates/shared/scripts/delivery/ci_fallback.py").read_text()
        for bad in ("requests", "webhook", "workflow_dispatch", "pip install"):
            self.assertNotIn(bad, src)


if __name__ == "__main__":
    unittest.main()
