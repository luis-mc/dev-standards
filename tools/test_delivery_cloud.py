#!/usr/bin/env python3
"""DL15: the cloud-session CI starter scripts: cloud_shard.py (runs one shard, writes the result JSON, pushes it)
and cloud_status.py (finds the commits that need shards, posts commit statuses). No network: a local bare git
remote and a local HTTP server stand in for GitHub. Standard library only."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = REPO / "claude/plugins/delivery/templates/shared/scripts/delivery"
sys.path.insert(0, str(SCRIPTS))

import cloud_shard as S  # noqa: E402
import cloud_status as T  # noqa: E402

PY = sys.executable.replace("\\", "/")
THIS = S.this_os()
GIT_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}


def git(cwd, *args):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, env={**os.environ, **GIT_ENV})
    assert r.returncode == 0, (args, r.stderr)
    return r.stdout.strip()


def make_project(table=None, config=None):
    """A work clone with one commit, wired to a bare remote."""
    base = Path(tempfile.mkdtemp(prefix="cloud-"))
    remote, work = base / "remote.git", base / "work"
    subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True)
    subprocess.run(["git", "init", "-q", str(work)], check=True)
    git(work, "checkout", "-q", "-b", "release/1")
    (work / "scripts/delivery").mkdir(parents=True)
    table = table or {"tests": {"ok": f'"{PY}" -c "print(1)"'}, "shards": [
        {"id": "unit", "os": THIS, "context": "unit (%s)" % THIS, "commands": ["@ok", f'"{PY}" -c "print(2)"']},
        {"id": "fails", "os": THIS, "commands": [f'"{PY}" -c "import sys; sys.exit(3)"', f'"{PY}" -c "print(9)"']},
        {"id": "other", "os": "beos", "commands": ["x"]}]}
    (work / "scripts/delivery/ci-shards.json").write_text(json.dumps(table))
    (work / ".delivery").mkdir()
    cfg = config if config is not None else {"ci": {"options": {THIS: "cloud"}, "cloud": {
        "repo": "o/r", "status_token_env": "STATUS_TOK", "branches": ["release/*"]}}}
    (work / ".delivery/config.json").write_text(json.dumps(cfg))
    (work / ".gitignore").write_text(".delivery/\n")
    git(work, "add", "-A")
    git(work, "commit", "-q", "-m", "c1")
    git(work, "remote", "add", "origin", str(remote))
    git(work, "push", "-q", "origin", "release/1")
    return work, remote, git(work, "rev-parse", "HEAD")


class ShardTests(unittest.TestCase):
    def test_success_runs_every_command_and_writes_the_result(self):
        work, _r, sha = make_project()
        table = S.load_table(str(work / "scripts/delivery/ci-shards.json"))
        res = S.run_shard(table, "unit", str(work), sha, None)
        self.assertEqual(res["state"], "success")
        self.assertEqual(res["sha"], sha)
        self.assertEqual(res["context"], "unit (%s)" % THIS)
        self.assertEqual([c["exit"] for c in res["commands"]], [0, 0])
        self.assertEqual(res["commands"][0]["tail"].strip(), "1")      # @ok expanded to the named test

    def test_first_failure_stops_the_shard(self):
        work, _r, sha = make_project()
        res = S.run_shard(S.load_table(str(work / "scripts/delivery/ci-shards.json")), "fails", str(work), sha, None)
        self.assertEqual(res["state"], "failure")
        self.assertEqual(len(res["commands"]), 1)
        self.assertEqual(res["commands"][0]["exit"], 3)
        self.assertEqual(res["context"], "fails")                      # context falls back to the id

    def test_errors_are_not_failures(self):
        work, _r, sha = make_project()
        table = S.load_table(str(work / "scripts/delivery/ci-shards.json"))
        self.assertEqual(S.run_shard(table, "nope", str(work), sha, None)["state"], "error")
        self.assertIn("this machine is", S.run_shard(table, "other", str(work), sha, None)["summary"])
        wrong = S.run_shard(table, "unit", str(work), "f" * 40, None)
        self.assertEqual(wrong["state"], "error")
        self.assertIn("HEAD is", wrong["summary"])
        table["tests"] = {}
        self.assertIn("names a test", S.run_shard(table, "unit", str(work), sha, None)["summary"])

    def test_timeout_is_a_failure(self):
        work, _r, sha = make_project({"shards": [{"id": "slow", "os": THIS, "commands": [f'"{PY}" -c "import time; time.sleep(30)"']}]})
        table = S.load_table(str(work / "scripts/delivery/ci-shards.json"))
        res = S.run_shard(table, "slow", str(work), sha, 0.01)
        self.assertEqual(res["state"], "failure")
        self.assertEqual(res["commands"][0]["exit"], 124)

    def test_cli_exit_codes_and_default_result_file(self):
        work, _r, sha = make_project()
        run = lambda *a: subprocess.run([PY, str(SCRIPTS / "cloud_shard.py"), "run", "--root", str(work), *a], capture_output=True, text=True)
        self.assertEqual(run("--shard", "unit", "--sha", sha).returncode, 0)
        self.assertEqual(json.loads((work / ".delivery/ci-results" / sha / "unit.json").read_text())["state"], "success")
        self.assertEqual(run("--shard", "fails").returncode, 1)
        self.assertEqual(run("--shard", "nope").returncode, 2)
        self.assertEqual(run("--shard", "unit", "--table", "missing.json").returncode, 2)

    def test_push_publishes_one_branch_per_sha_and_shard_with_plain_git(self):
        work, remote, sha = make_project()
        r = subprocess.run([PY, str(SCRIPTS / "cloud_shard.py"), "run", "--root", str(work), "--shard", "unit", "--sha", sha, "--push"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        branch = "ci-result/%s/unit" % sha
        self.assertEqual(git(remote, "ls-tree", "--name-only", branch), "result.json")
        self.assertEqual(json.loads(git(remote, "show", branch + ":result.json"))["state"], "success")
        self.assertEqual(git(work, "status", "--porcelain"), "")        # the work tree is untouched


class Api(BaseHTTPRequestHandler):
    seen: list = []
    status = 201

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        Api.seen.append((self.path, self.headers.get("Authorization"), json.loads(body)))
        self.send_response(Api.status)
        self.end_headers()
        self.wfile.write(b"{}")

    def log_message(self, *a):
        pass


class StatusTests(unittest.TestCase):
    def setUp(self):
        Api.seen, Api.status = [], 201
        self.srv = HTTPServer(("127.0.0.1", 0), Api)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.env = mock.patch.dict(os.environ, {"DELIVERY_GITHUB_API": "http://127.0.0.1:%d" % self.srv.server_port,
                                                "STATUS_TOK": "s3cret"})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.srv.shutdown()
        self.srv.server_close()

    def result(self, sha, state="success", **kw):
        return {"schema": 1, "shard": "unit", "context": "unit (linux)", "os": "linux", "sha": sha, "state": state,
                "summary": "2 command(s) passed", **kw}

    def test_payload_uses_the_context_and_only_the_shards_sha(self):
        sha = "a" * 40
        got_sha, body = T.status_payload(self.result(sha), sha)
        self.assertEqual((got_sha, body["context"], body["state"]), (sha, "unit (linux)", "success"))
        with self.assertRaises(ValueError):
            T.status_payload(self.result(sha), "b" * 40)             # not the sha the shard ran on
        with self.assertRaises(ValueError):
            T.status_payload(self.result("abc"), None)               # not a full sha
        with self.assertRaises(ValueError):
            T.status_payload(self.result(sha, state="running"), None)
        self.assertEqual(len(T.status_payload(self.result(sha, summary="x" * 500), None)[1]["description"]), 140)

    def test_post_sends_one_status_with_the_token_and_prints_no_token(self):
        sha = "a" * 40
        f = Path(tempfile.mkdtemp()) / "r.json"
        f.write_text(json.dumps(self.result(sha, state="failure")))
        r = subprocess.run([PY, str(SCRIPTS / "cloud_status.py"), "post", "--result", str(f), "--sha", sha, "--repo", "o/r", "--token-env", "STATUS_TOK"],
                           capture_output=True, text=True, env=os.environ.copy())
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("s3cret", r.stdout + r.stderr)
        self.assertEqual(Api.seen, [("/repos/o/r/statuses/" + sha, "Bearer s3cret",
                                     {"state": "failure", "context": "unit (linux)", "description": "2 command(s) passed"})])

    def test_post_refuses_a_wrong_sha_without_calling_the_api(self):
        f = Path(tempfile.mkdtemp()) / "r.json"
        f.write_text(json.dumps(self.result("a" * 40)))
        code = T.main(["post", "--result", str(f), "--sha", "c" * 40, "--repo", "o/r", "--token-env", "STATUS_TOK"])
        self.assertEqual(code, 1)
        self.assertEqual(Api.seen, [])

    def test_missing_token_or_bad_base_is_an_error(self):
        f = Path(tempfile.mkdtemp()) / "r.json"
        f.write_text(json.dumps(self.result("a" * 40)))
        with mock.patch.dict(os.environ, {"STATUS_TOK": ""}):
            self.assertEqual(T.main(["post", "--result", str(f), "--repo", "o/r", "--token-env", "STATUS_TOK"]), 2)
        with mock.patch.dict(os.environ, {"DELIVERY_GITHUB_API": "http://example.com"}):
            self.assertEqual(T.main(["post", "--result", str(f), "--repo", "o/r", "--token-env", "STATUS_TOK"]), 2)
        self.assertEqual(Api.seen, [])

    def test_pending_lists_heads_without_results_then_post_ready_posts_them(self):
        work, _remote, sha = make_project()
        git(work, "push", "-q", "origin", "release/1:refs/heads/feature/x")   # not in ci.cloud.branches
        pend = T.pending(str(work), "origin")
        self.assertEqual(pend, [{"branch": "release/1", "sha": sha, "missing": ["unit", "fails"]}])
        for shard in ("unit", "fails"):
            subprocess.run([PY, str(SCRIPTS / "cloud_shard.py"), "run", "--root", str(work), "--shard", shard, "--sha", sha, "--push"],
                           capture_output=True, text=True)
        self.assertEqual(T.pending(str(work), "origin"), [])
        code = T.main(["post-ready", "--sha", sha, "--root", str(work)])
        self.assertEqual(code, 0)
        posted = sorted((p[2]["context"], p[2]["state"]) for p in Api.seen)
        self.assertEqual(posted, [("fails", "failure"), ("unit (%s)" % THIS, "success")])
        self.assertTrue(all(p[0] == "/repos/o/r/statuses/" + sha for p in Api.seen))

    def test_a_new_head_needs_new_results(self):
        work, _remote, sha = make_project()
        subprocess.run([PY, str(SCRIPTS / "cloud_shard.py"), "run", "--root", str(work), "--shard", "unit", "--sha", sha, "--push"], capture_output=True)
        (work / "f.txt").write_text("x")
        git(work, "add", "-A")
        git(work, "commit", "-q", "-m", "c2")
        git(work, "push", "-q", "origin", "release/1")
        new = git(work, "rev-parse", "HEAD")
        self.assertEqual(T.pending(str(work), "origin"), [{"branch": "release/1", "sha": new, "missing": ["unit", "fails"]}])

    def test_pending_is_empty_when_no_os_is_cloud_and_errors_without_branches(self):
        work, _r, _s = make_project(config={"ci": {"options": {THIS: "github-hosted"}}})
        self.assertEqual(T.pending(str(work), "origin"), [])
        work2, _r2, _s2 = make_project(config={"ci": {"options": {THIS: "cloud"}}})
        with self.assertRaises(ValueError):
            T.pending(str(work2), "origin")

    def test_the_scripts_use_no_actions_and_no_webhook(self):
        for name in ("cloud_shard.py", "cloud_status.py"):
            text = (SCRIPTS / name).read_text(encoding="utf-8")
            self.assertNotIn("workflow_dispatch", text)
            self.assertNotIn("gh run", text)
            self.assertNotIn("/hooks", text)


if __name__ == "__main__":
    unittest.main()
