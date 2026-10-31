import io
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

from _helpers import L, SCRIPTS, make_root
import hook_post_tool as H

GH = "gh"


def bash(cmd, out="", event="PostToolUse", cwd=None):
    d = {"hook_event_name": event, "tool_name": "Bash", "tool_input": {"command": cmd}}
    d["tool_response" if event == "PostToolUse" else "error"] = out
    if cwd:
        d["cwd"] = cwd
    return d


def seed(root, **train):
    def fn(led):
        t = L.new_train(led, train.pop("branch", "release/29"))
        t.update(train)
    L.update(root, fn)


def ghpr(*words):
    return " ".join([GH, "pr", *words])


class BashTests(unittest.TestCase):
    def setUp(self):
        self.root = make_root()
        seed(self.root, state="joined")

    def led(self):
        return L.load(self.root)

    def test_git_push_of_train_branch_marks_pushed(self):
        self.assertTrue(H.handle(bash("git push origin release/29"), self.root))
        t = self.led()["trains"][0]
        self.assertEqual(t["state"], "pushed")
        self.assertIsNotNone(t["pushed_at"])

    def test_git_push_refspec_and_force_flags(self):
        H.handle(bash("git push -u --force-with-lease origin HEAD:refs/heads/release/29"), self.root)
        self.assertEqual(self.led()["trains"][0]["state"], "pushed")

    def test_git_push_of_other_branch_ignored(self):
        H.handle(bash("git push origin DV148-fix"), self.root)
        self.assertEqual(self.led()["trains"][0]["state"], "joined")

    def test_failed_push_records_event_only(self):
        H.handle(bash("git push origin release/29", "Exit code 1\nrejected", event="PostToolUseFailure"), self.root)
        led = self.led()
        self.assertEqual(led["trains"][0]["state"], "joined")
        self.assertEqual(led["events"][-1]["kind"], "push.failed")

    def test_pr_create_parses_url_and_sets_ci(self):
        H.handle(bash("git push origin release/29 && " + ghpr("create", "--head", "release/29", "--title", "x"),
                      "https://github.com/o/r/pull/412\n"), self.root)
        t = self.led()["trains"][0]
        self.assertEqual((t["pr"], t["state"]), (412, "ci"))

    def test_pr_create_draft_does_not_start_ci(self):
        H.handle(bash(ghpr("create", "--draft", "--head", "release/29"), "https://github.com/o/r/pull/412"), self.root)
        t = self.led()["trains"][0]
        self.assertEqual((t["pr"], t["state"]), (412, "joined"))

    def test_pr_ready_by_number(self):
        seed(self.root, branch="release/30", pr=77, state="pushed")
        H.handle(bash(ghpr("ready", "77")), self.root)
        self.assertEqual(self.led()["trains"][1]["state"], "ci")

    def test_pr_merge_success_and_failure(self):
        seed(self.root, branch="release/31", pr=80, state="green")
        H.handle(bash(ghpr("merge", "80", "--merge"), "done"), self.root)
        t = self.led()["trains"][1]
        self.assertEqual(t["state"], "merged")
        self.assertIsNotNone(t["merged_at"])
        seed(self.root, branch="release/32", pr=81, state="green")
        H.handle(bash(ghpr("merge", "81", "--merge"), "Exit code 1\nnot mergeable", event="PostToolUseFailure"), self.root)
        self.assertEqual(self.led()["trains"][2]["state"], "green")

    def test_msiexec_and_schtasks(self):
        H.handle(bash('msiexec /i "C:\\build\\App-0.1.6212.msi" /qn'), self.root)
        H.handle(bash("schtasks /run /tn AppUpdateNow"), self.root)
        ins = self.led()["installs"]
        self.assertEqual(ins[0]["via"], "msiexec")
        self.assertEqual(ins[0]["state"], "done")
        self.assertEqual((ins[1]["product"], ins[1]["state"]), ("app", "installing"))

    def test_msiexec_failure_marks_failed(self):
        H.handle(bash("msiexec /i x.msi /qn", "Exit code 1603", event="PostToolUseFailure"), self.root)
        self.assertEqual(self.led()["installs"][0]["state"], "failed")

    def test_ci_watch_exit_codes(self):
        sha = "abcdef1234567"
        ci = lambda s: {"head_sha": s, "run_ids": [], "state": "running", "started_at": None}  # noqa: E731
        seed(self.root, branch="release/40", state="ci", ci=ci(sha))
        H.handle(bash("python scripts/delivery/ci_watch.py %s" % sha, "ci_watch: 1 ci.yml run(s) succeeded"), self.root)
        t = self.led()["trains"][1]
        self.assertEqual((t["state"], t["ci"]["state"]), ("ci", "running"))     # a pass never greens: the watcher does
        self.assertIn("ci_watch.passed", [e["kind"] for e in self.led()["events"]])
        seed(self.root, branch="release/41", state="ci", ci=ci("1111111"))
        H.handle(bash("python ci_watch.py 1111111", "Exit code 1\nfailed", event="PostToolUseFailure"), self.root)
        self.assertEqual(self.led()["trains"][2]["state"], "red")
        seed(self.root, branch="release/42", state="ci", ci=ci("2222222"))
        H.handle(bash("python ci_watch.py 2222222", "Exit code 4", event="PostToolUseFailure"), self.root)
        self.assertEqual(self.led()["trains"][3]["state"], "ci")
        H.handle(bash("python ci_watch.py 9999999", "ci_watch: ok"), self.root)    # unknown head: no train is guessed
        self.assertNotIn("green", [t["state"] for t in self.led()["trains"]])

    def test_ci_watch_started_in_background_records_nothing(self):
        sha = "abcdef1234567"
        seed(self.root, branch="release/47", state="ci", ci={"head_sha": sha, "run_ids": [], "state": "running", "started_at": None})
        d = bash("python ci_watch.py %s" % sha, "")
        d["tool_input"]["run_in_background"] = True
        H.handle(d, self.root)
        self.assertEqual(self.led()["trains"][-1]["ci"]["state"], "running")
        self.assertEqual([e for e in self.led()["events"] if e["kind"].startswith("ci_watch")], [])
        H.handle(bash("python ci_watch.py %s" % sha, ""), self.root)             # foreground but no all-green output
        self.assertEqual([e for e in self.led()["events"] if e["kind"].startswith("ci_watch")], [])

    def test_ci_watch_of_another_sha_or_repo_marks_no_train(self):
        ci = lambda s: {"head_sha": s, "run_ids": [], "state": "running", "started_at": None}  # noqa: E731
        seed(self.root, branch="release/45", state="ci", ci=ci("aaaaaaa1111"))
        H.handle(bash("python ci_watch.py 28cd8a0346bd --repo luis-mc/dev-standards --workflow spec-lint.yml",
                      "ci_watch: 1 spec-lint.yml run(s) succeeded"), self.root)
        t = self.led()["trains"][-1]
        self.assertEqual((t["state"], t["ci"]["state"], t["ci"]["head_sha"]), ("ci", "running", "aaaaaaa1111"))
        seed(self.root, branch="release/46", state="pushed", ci=ci(""))
        H.handle(bash("python ci_watch.py 9999999abc", "ci_watch: succeeded"), self.root)
        self.assertEqual(self.led()["trains"][-1]["state"], "pushed")

    def test_unrelated_command_adds_no_event(self):
        n = len(self.led()["events"])
        H.handle(bash("ls -la"), self.root)
        self.assertEqual(len(self.led()["events"]), n)

class LedgerGapTests(unittest.TestCase):
    """DS8: body-file PRs on a release branch with no train yet, fix-forward pushes, cd / -C directories."""

    def setUp(self):
        self.root = make_root()

    def led(self):
        return L.load(self.root)

    def test_pr_create_with_repo_and_body_file_creates_the_train(self):
        cmd = ("gh pr create --repo example/app --base master --head release/40 "
               "--title \"R40\" --body-file C:/Work/briefs/r44-pr.md")
        with mock.patch.object(H, "rev_parse", return_value="a" * 40):
            H.handle(bash(cmd, "https://github.com/example/app/pull/418\n"), self.root)
        trains = self.led()["trains"]
        self.assertEqual(len(trains), 1)
        t = trains[0]
        self.assertEqual((t["branch"], t["pr"], t["state"]), ("release/40", 418, "ci"))
        self.assertEqual(t["ci"]["head_sha"], "a" * 40)

    def test_pr_create_on_an_integration_branch_creates_the_train(self):
        # DS95: <id>-integration branches are trains by default, as hooklib.is_release_branch says
        with mock.patch.object(H, "rev_parse", return_value="a" * 40):
            H.handle(bash("gh pr create --base main --head DS90-integration --body-file x.md",
                          "https://github.com/example/app/pull/103\n"), self.root)
        t = self.led()["trains"][0]
        self.assertEqual((t["branch"], t["pr"], t["state"]), ("DS90-integration", 103, "ci"))

    def test_pr_create_of_a_known_train_gets_head_sha(self):
        seed(self.root, state="pushed")
        with mock.patch.object(H, "rev_parse", return_value="b" * 40):
            H.handle(bash("gh pr create --head release/29 --body-file x.md", "https://github.com/o/r/pull/9"), self.root)
        t = self.led()["trains"][0]
        self.assertEqual((t["pr"], t["state"], t["ci"]["head_sha"]), (9, "ci", "b" * 40))

    def test_pr_create_falls_back_to_the_origin_branch_for_head_sha(self):
        # DS97: a branch pushed from another worktree has no local ref here; head_sha stayed null
        seed(self.root, state="pushed")
        heads = {"origin/release/29": "c" * 40}
        with mock.patch.object(H, "rev_parse", side_effect=lambda ref, cwd: heads.get(ref)):
            H.handle(bash("gh pr create --head release/29 --body-file x.md", "https://github.com/o/r/pull/9"), self.root)
        self.assertEqual(self.led()["trains"][0]["ci"]["head_sha"], "c" * 40)

    def test_pr_create_of_a_non_release_branch_creates_no_train(self):
        H.handle(bash("gh pr create --repo o/r --head DV1-x --body-file x.md", "https://github.com/o/r/pull/5"), self.root)
        self.assertEqual(self.led()["trains"], [])

    def test_pr_create_failed_creates_no_train(self):
        H.handle(bash("gh pr create --head release/41 --body-file x.md", "Exit code 1", event="PostToolUseFailure"), self.root)
        self.assertEqual(self.led()["trains"], [])

    def test_push_with_existing_pr_resets_ci(self):
        seed(self.root, branch="release/41", pr=422, state="green", green_at="2026-10-17T10:00:00Z",
             ci={"head_sha": "old", "run_ids": [1], "state": "success", "started_at": "x"})
        with mock.patch.object(H, "rev_parse", return_value="c" * 40):
            H.handle(bash("git push origin release/41"), self.root)
        t = self.led()["trains"][0]
        self.assertEqual((t["state"], t["ci"]["state"], t["green_at"]), ("ci", "queued", None))
        self.assertEqual((t["ci"]["head_sha"], t["ci"]["run_ids"]), ("c" * 40, []))

    def test_push_without_pr_still_just_pushed(self):
        seed(self.root, branch="release/43", state="joined")
        H.handle(bash("git push origin release/43"), self.root)
        self.assertEqual(self.led()["trains"][0]["state"], "pushed")

    def test_cd_prefix_resolves_branch_in_that_directory(self):
        seed(self.root, branch="release/44", state="joined")
        seen = []
        with mock.patch.object(H, "current_branch", side_effect=lambda c: seen.append(c) or "release/44"):
            H.handle(bash("cd C:/work/wt && git push", cwd="C:/elsewhere"), self.root)
        self.assertEqual(seen, ["C:/work/wt"])
        self.assertEqual(self.led()["trains"][0]["state"], "pushed")

    def test_git_dash_c_resolves_branch_in_that_directory(self):
        seed(self.root, branch="release/44", state="joined")
        seen = []
        with mock.patch.object(H, "current_branch", side_effect=lambda c: seen.append(c) or "release/44"):
            H.handle(bash("git -C C:/work/wt push", cwd="C:/elsewhere"), self.root)
        self.assertEqual(seen, ["C:/work/wt"])
        self.assertEqual(self.led()["trains"][0]["state"], "pushed")

    def test_split_commands_cwd_relative_cd(self):
        out = H.split_commands_cwd("cd sub && git status", os.path.abspath("base"))
        self.assertEqual(out[0][1], os.path.normpath(os.path.join(os.path.abspath("base"), "sub")))


BLOCK = """Do the work.

```delivery
task: DV152
branch: DV152-scripts
owns: scripts/delivery/**, docs/specs/x.md
setup: 5
work: 12
checks: 8
basis: 2 small scripts
model: sonnet
effort: medium
```
"""


class AgentTests(unittest.TestCase):
    def test_parse_block(self):
        b = H.parse_delivery_block(BLOCK)
        self.assertEqual(b["task"], "DV152")
        self.assertEqual(b["owns"], ["scripts/delivery/**", "docs/specs/x.md"])
        self.assertEqual(b["breakdown"], {"setup": 5.0, "work": 12.0, "checks": 8.0})
        self.assertEqual(b["total_min"], 25.0)
        self.assertEqual(H.parse_delivery_block("no block"), {})

    def test_agent_row_from_background_call(self):
        root = make_root()
        H.handle({"hook_event_name": "PostToolUse", "tool_name": "Agent",
                  "tool_input": {"prompt": BLOCK, "run_in_background": True, "model": "sonnet"},
                  "tool_response": {"agentId": "ag_1"}}, root)
        a = L.load(root)["agents"][0]
        self.assertEqual((a["task"], a["where"], a["id"], a["state"]), ("DV152", "local", "ag_1", "running"))
        self.assertEqual(a["eta"]["total_min"], 25.0)
        self.assertEqual(a["eta"]["breakdown"]["work"], 12.0)
        self.assertTrue(a["eta"]["due"])
        self.assertEqual(a["owns"][0], "scripts/delivery/**")

    def test_agent_without_block_records_missing_eta_event(self):
        root = make_root()
        H.handle({"hook_event_name": "PostToolUse", "tool_name": "Agent", "tool_input": {"prompt": "just do it"},
                  "tool_response": "ok"}, root)
        led = L.load(root)
        self.assertIsNone(led["agents"][0]["eta"])
        self.assertIn("agent.no_eta", [e["kind"] for e in led["events"]])

    def test_remote_trigger_create_and_run_only(self):
        root = make_root()
        body = {"action": "create", "body": {"events": [{"data": {"message": {"content": BLOCK}}}]}}
        H.handle({"hook_event_name": "PostToolUse", "tool_name": "RemoteTrigger", "tool_input": body,
                  "tool_response": {"id": "trig_abc"}}, root)
        H.handle({"hook_event_name": "PostToolUse", "tool_name": "RemoteTrigger",
                  "tool_input": {"action": "list"}, "tool_response": "[]"}, root)
        agents = L.load(root)["agents"]
        self.assertEqual(len(agents), 1)
        self.assertEqual((agents[0]["where"], agents[0]["id"], agents[0]["task"]), ("cloud", "trig_abc", "DV152"))


class OtherToolTests(unittest.TestCase):
    def test_artifact_publish(self):
        root = make_root()
        for v in (1, 2):
            H.handle({"hook_event_name": "PostToolUse", "tool_name": "Artifact",
                      "tool_input": {"file_path": "/x/full-progress.html"},
                      "tool_response": "Published https://claude.ai/artifact/abc-123 version %d" % (500 + v)}, root)
        H.handle({"hook_event_name": "PostToolUse", "tool_name": "Artifact",
                  "tool_input": {"action": "read", "url": "https://claude.ai/artifact/abc-123"}, "tool_response": "x"}, root)
        pubs = L.load(root)["publishes"]
        self.assertEqual(len(pubs), 1)
        self.assertEqual((pubs[0]["artifact"], pubs[0]["url"], pubs[0]["last_version"]),
                         ("full-progress", "https://claude.ai/artifact/abc-123", 502))

    def test_question_asked_then_answered(self):
        root = make_root()
        H.handle({"hook_event_name": "PostToolUse", "tool_name": "AskUserQuestion",
                  "tool_input": {"questions": [{"question": "Merge now?"}, {"question": "Which colour?"}]},
                  "tool_response": "waiting"}, root)
        qs = L.load(root)["owner_questions"]
        self.assertEqual([q["id"] for q in qs], ["Q1", "Q2"])
        self.assertTrue(all(q["answered_at"] is None for q in qs))
        self.assertTrue(H.handle({"hook_event_name": "UserPromptSubmit", "prompt": "yes"}, root))
        self.assertTrue(all(q["answered_at"] for q in L.load(root)["owner_questions"]))
        answered = [q["answered_at"] for q in L.load(root)["owner_questions"]]
        H.handle({"hook_event_name": "UserPromptSubmit", "prompt": "again"}, root)     # records owner_prompt only
        self.assertEqual([q["answered_at"] for q in L.load(root)["owner_questions"]], answered)
        H.handle({"hook_event_name": "PostToolUse", "tool_name": "AskUserQuestion",
                  "tool_input": {"questions": [{"question": "More?"}]}, "tool_response": ""}, root)
        self.assertEqual(L.load(root)["owner_questions"][-1]["id"], "Q3")

    def test_no_delivery_folder_is_a_noop(self):
        d = tempfile.mkdtemp()
        self.assertFalse(H.handle(bash("git push origin release/1"), d))
        self.assertFalse(os.path.exists(os.path.join(d, ".delivery")))

    def test_failed_non_bash_tool_only_logs(self):
        root = make_root()
        H.handle({"hook_event_name": "PostToolUseFailure", "tool_name": "Agent", "tool_input": {"prompt": BLOCK}, "error": "x"}, root)
        led = L.load(root)
        self.assertEqual(led["agents"], [])
        self.assertEqual(led["events"][-1]["kind"], "tool.failed")


class MainProcessTests(unittest.TestCase):
    def run_hook(self, payload, env=None):
        e = dict(os.environ, **(env or {}))
        return subprocess.run([sys.executable, str(SCRIPTS / "hook_post_tool.py")], input=payload,
                              capture_output=True, text=True, env=e, timeout=10)

    def test_exits_zero_silently_on_garbage_and_empty_input(self):
        for payload in ("", "not json", "[1,2]", "{}"):
            p = self.run_hook(payload)
            self.assertEqual((p.returncode, p.stdout), (0, ""))

    def test_records_through_process_and_is_fast(self):
        root = make_root()
        seed(root, state="joined")
        payload = json.dumps(bash("git push origin release/29", cwd=str(root)))
        t0 = time.monotonic()
        p = self.run_hook(payload)
        self.assertEqual((p.returncode, p.stdout), (0, ""))
        self.assertLess(time.monotonic() - t0, 1.0)
        self.assertEqual(L.load(root)["trains"][0]["state"], "pushed")

    def test_switch_off(self):
        root = make_root()
        seed(root, state="joined")
        self.run_hook(json.dumps(bash("git push origin release/29", cwd=str(root))), {"CLAUDE_DELIVERY_HOOKS": "off"})
        self.assertEqual(L.load(root)["trains"][0]["state"], "joined")

    def test_internal_error_still_exits_zero(self):
        with mock.patch.object(H, "handle", side_effect=RuntimeError("boom")), \
                mock.patch.object(sys, "stdin", io.TextIOWrapper(io.BytesIO(b"{}"))):
            with mock.patch("sys.stderr", new_callable=io.StringIO) as err:
                self.assertEqual(H.main(), 0)
            self.assertIn("boom", err.getvalue())


# --- CO688: the delivery hook missed PR and push records ------------------------------------------------------

import shutil as _shutil  # noqa: E402
import threading  # noqa: E402


def _git(cwd, *a):
    return subprocess.run(["git", "-C", str(cwd), "-c", "user.email=t@t", "-c", "user.name=t", *a],
                          capture_output=True, text=True, check=True).stdout.strip()


def make_git_repo(*branches):
    """A temporary repository with one commit and the named branches at it."""
    d = tempfile.mkdtemp(prefix="repo-")
    _git(d, "init", "-q", "-b", "main")
    open(os.path.join(d, "f"), "w").write("x")
    _git(d, "add", "-A")
    _git(d, "commit", "-q", "-m", "i")
    for b in branches:
        _git(d, "branch", b)
    return d


BACKGROUNDED = "Command did not complete within its 120s timeout and was moved to the background"
CO688_A = ("cd {cwd} && git push -q -u origin release/132 2>&1 | tail -3; "
           "git push -q origin CO682-nightly-no-gh:claude/CO682-nightly-no-gh 2>&1 | tail -1; "
           "cat > {tmp}/pr132.md <<'EOF'\n## Release 132\nbody\nEOF\n"
           "gh pr create --base master --head release/132 --title 'RELEASE-132' --body-file {tmp}/pr132.md 2>&1 | tail -1; "
           "git rev-parse HEAD")


class Co688Tests(unittest.TestCase):
    def led(self, root):
        return L.load(root)

    def test_pr_create_in_backgrounded_bash_is_reconciled(self):
        # (a) the hook's only PostToolUse for the call is the "moved to the background" answer
        root = make_root()
        repo = make_git_repo("release/132")
        cmd = CO688_A.format(cwd=repo, tmp=repo)
        self.assertTrue(H.handle(bash(cmd, BACKGROUNDED, cwd=repo), root))
        led = self.led(root)
        self.assertEqual(led["trains"], [], "nothing done is recorded for a backgrounded push or PR")
        ev = [e for e in led["events"] if e["kind"] == "bash.backgrounded"]
        self.assertEqual(len(ev), 1, led["events"])
        self.assertIn("release/132", ev[0]["ref"])
        self.assertIn("pr create", ev[0]["ref"])
        self.assertIn("push", ev[0]["ref"])

    def test_run_in_background_flag_also_counts(self):
        root = make_root()
        seed(root, state="joined")
        d = bash("git push origin release/29", "started")
        d["tool_input"]["run_in_background"] = True
        H.handle(d, root)
        led = self.led(root)
        self.assertEqual(led["trains"][0]["state"], "joined")
        kinds = [e["kind"] for e in led["events"]]
        self.assertEqual(kinds.count("bash.backgrounded"), 1)
        self.assertNotIn("train.pushed", kinds)

    def test_other_backgrounded_commands_leave_no_event(self):
        root = make_root()
        H.handle(bash("npm test", BACKGROUNDED), root)
        self.assertEqual(self.led(root)["events"], [])

    def test_pr_create_after_heredoc_newline_records_pr(self):
        # (b) PR #849: the "pr None" the orchestrator saw came from the python -c in the same call
        repo = make_git_repo("release/134")
        root = make_root()
        seed(root, branch="release/134", state="joined")
        cmd = ("cd {r} && cat > {r}/pr134.md <<'EOF'\nbody line\nEOF\n"
               "gh pr create --base master --head release/134 --title 'RELEASE-134' --body-file {r}/pr134.md 2>&1 | tail -1; "
               "python -c \"print('pr', None)\"; date +%H:%M").format(r=repo)
        H.handle(bash(cmd, "https://github.com/luis-mc/comics-organizer/pull/849", cwd=str(root)), root)
        t = self.led(root)["trains"][0]
        self.assertEqual(t["pr"], 849)
        self.assertEqual(t["ci"]["head_sha"], _git(repo, "rev-parse", "release/134"))
        self.assertEqual(t["state"], "ci")

    def test_repush_in_worktree_resets_ci(self):
        # (c) a foreground re-push from a worktree to a train that has a PR and is red
        repo = make_git_repo("release/134")
        root = make_root()
        old = "2d5594da6"
        seed(root, branch="release/134", pr=849, state="red", green_at=None,
             ci={"head_sha": old, "run_ids": [41181589467], "state": "failure", "started_at": None})
        cmd = ("cat /tmp/task-output; cd {r} && git push -q origin release/134 2>&1 | tail -3; "
               "git ls-remote origin release/134; date +%H:%M").format(r=repo)
        H.handle(bash(cmd, "ok", cwd=str(root)), root)
        led = self.led(root)
        t = led["trains"][0]
        self.assertEqual(t["ci"]["head_sha"], _git(repo, "rev-parse", "release/134"))
        self.assertEqual(t["ci"]["run_ids"], [])
        self.assertEqual((t["state"], t["ci"]["state"]), ("ci", "queued"))
        self.assertIn("train.repushed", [e["kind"] for e in led["events"]])

    def test_repush_lands_when_another_process_holds_the_lock_for_five_seconds(self):
        repo = make_git_repo("release/134")
        root = make_root()
        seed(root, branch="release/134", pr=849, state="red",
             ci={"head_sha": "old", "run_ids": [1], "state": "failure", "started_at": None})
        lock = L.ledger_path(root).with_suffix(".json.lock")
        lock.write_text("123")
        threading.Timer(5.0, lambda: lock.unlink()).start()
        t0 = time.monotonic()
        try:
            H.handle(bash("cd %s && git push -q origin release/134 2>&1 | tail -3" % repo, "ok", cwd=str(root)), root)
        except Exception:  # noqa: BLE001 - a hook failure must at least be visible
            pass
        landed = L.load(root)["trains"][0]["ci"]["head_sha"] != "old"
        logged = (root / ".delivery" / "blocks.log").exists()
        self.assertTrue(landed or logged, "the record landed, or a blocks.log line says it did not")
        self.assertTrue(landed, "the longer second wait lets the record land")
        self.assertGreater(time.monotonic() - t0, 4.0)

    def test_failed_hook_writes_a_blocks_log_line(self):
        root = make_root()
        seed(root, state="joined")
        payload = json.dumps(bash("git push origin release/29  # " + "x" * 300, "ok", cwd=str(root)))
        with mock.patch.object(L, "update", side_effect=L.LedgerError("ledger lock busy: x")), \
                mock.patch.object(sys, "stdin", io.TextIOWrapper(io.BytesIO(payload.encode()))), \
                mock.patch("sys.stderr", new_callable=io.StringIO):
            self.assertEqual(H.main(), 0)
        line = (root / ".delivery" / "blocks.log").read_text().strip().split("\n")[-1].split("\t")
        self.assertEqual(line[1], "post-tool")
        self.assertIn("git push origin release/29", line[3])
        self.assertIn("ledger lock busy", line[3])
        self.assertLess(len(line[3]), 120 + 80, "only the first 120 characters of the command")

    def test_gh_pr_ready_after_cd_uses_worktree_branch(self):
        # (d) the hook looks the branch up in the cd target, not in the session cwd
        repo = make_git_repo()
        wt = tempfile.mkdtemp(prefix="wt-")
        _shutil.rmtree(wt)
        _git(repo, "worktree", "add", "-q", "-b", "release/132", wt)
        root = make_root()
        seed(root, branch="release/132", state="pushed")
        cmd = ("cd %s && git branch --show-current && gh pr ready 847 2>&1 | tail -1; "
               "cd %s && python -c \"print('pr', None)\"" % (wt, repo))
        H.handle(bash(cmd, "Pull request #847 is already ready for review", cwd=repo), root)
        led = self.led(root)
        self.assertEqual(led["trains"][0]["pr"], 847)
        self.assertIn("pr.ready", [e["kind"] for e in led["events"]])

    def test_gh_pr_ready_without_a_number_reads_the_worktree_branch(self):
        repo = make_git_repo()
        wt = tempfile.mkdtemp(prefix="wt-")
        _shutil.rmtree(wt)
        _git(repo, "worktree", "add", "-q", "-b", "release/132", wt)
        root = make_root()
        seed(root, branch="release/132", state="pushed")
        H.handle(bash("cd %s && gh pr ready 2>&1 | tail -1" % wt, "https://github.com/o/r/pull/847", cwd=repo), root)
        self.assertEqual(self.led(root)["trains"][0]["pr"], 847)

    def test_quoted_semicolon_keeps_head_flag(self):
        cmd = 'gh pr create --base master --title "RELEASE-9: a; b" --head release/9 --body "x"'
        parts = H.split_commands(cmd)
        self.assertEqual(len(parts), 1, parts)
        self.assertEqual(H.opt_value(parts[0], "--head", "-H"), "release/9")
        root = make_root()
        H.handle(bash(cmd, "https://github.com/o/r/pull/9", cwd=str(root)), root)
        t = self.led(root)["trains"][0]
        self.assertEqual((t["branch"], t["pr"]), ("release/9", 9))

    def test_quotes_with_operators_and_escapes(self):
        self.assertEqual(len(H.split_commands("echo 'a && b' && echo \"c | d\"; echo e\\;f")), 3)
        self.assertEqual(H.split_commands("git commit -m \"fix: a || b\"")[0][-1], "fix: a || b")

    def test_heredoc_body_is_not_a_command(self):
        root = make_root()
        seed(root, branch="release/77", state="joined")
        cmd = ("cat > pr.md <<'EOF'\nRelease notes\ngit push origin release/77\n"
               "gh pr merge 5 --merge\nEOF\ngh pr create --draft --head release/77 --title x")
        self.assertEqual([a[0] for a in H.split_commands(cmd)], ["cat", "gh"])
        H.handle(bash("git status\n" + cmd, "https://github.com/o/r/pull/5"), root)
        t = self.led(root)["trains"][0]
        self.assertEqual(t["state"], "joined", "the body line did not record a push")
        self.assertNotIn("train.pushed", [e["kind"] for e in self.led(root)["events"]])

    def test_heredoc_variants(self):
        for opener, close in (("<<EOF", "EOF"), ("<<'EOF'", "EOF"), ('<<"EOF"', "EOF"), ("<<-EOF", "\tEOF"), ("<< EOF", "EOF")):
            cmd = "cat %s\ngit push origin release/77\n%s\necho done" % (opener, close)
            self.assertEqual([a[0] for a in H.split_commands(cmd)], ["cat", "echo"], opener)
        self.assertEqual([a[0] for a in H.split_commands("cat <<EOF | tail -1\nx; rm -rf y\nEOF\nls")], ["cat", "tail", "ls"])

    def test_redirection_is_not_a_branch(self):
        argv, _cwd = H.split_commands_cwd("git push -q origin release/134 2>&1", None)[0]
        self.assertEqual(argv, ["git", "push", "-q", "origin", "release/134"])
        for cmd, want in (("git push origin release/134 >out.log 2>&1", ["git", "push", "origin", "release/134"]),
                          ("git push origin release/134 > /dev/null", ["git", "push", "origin", "release/134"]),
                          ("git push origin release/134 &> all.log", ["git", "push", "origin", "release/134"]),
                          ("cat < in.txt >> out.txt", ["cat"]),
                          ("echo 'a > b' 2>&1", ["echo", "a > b"])):
            self.assertEqual(H.split_commands(cmd)[0], want, cmd)

    def test_cd_tracking_survives_the_tokenizer(self):
        got = H.split_commands_cwd("cd /w/one && git push origin release/1; cd ../two\ngit push origin release/2", "/w/zero")
        self.assertEqual([(a[-1], c) for a, c in got], [("release/1", "/w/one"), ("release/2", os.path.normpath("/w/two"))])

    def test_windows_command_shapes(self):
        P = ["git", "push", "origin", "release/135"]
        for cmd, argv_head, where in (
            (r"cd C:/GitHub/comics-organizer && gh pr create --draft --head release/135", ["gh", "pr", "create"], "C:/GitHub/comics-organizer"),
            (r'cd "C:\Users\Luis\x y" && git push origin release/135', P, r"C:\Users\Luis\x y"),
            (r"cd C:\Users\tmp\new && git push origin release/135", P, r"C:\Users\tmp\new"),
            (r"cd 'C:\Users\Luis\x y'; git push origin release/135", P, r"C:\Users\Luis\x y"),
            (r"git -C C:\path\new push origin release/135", P, r"C:\path\new"),
            (r'git -C "C:\Users\Luis\x y" push origin release/135', P, r"C:\Users\Luis\x y"),
            (r"Set-Location C:\GitHub\x; git push origin release/135", P, r"C:\GitHub\x"),
            (r'Set-Location -Path "C:\a b"; git push', ["git", "push"], r"C:\a b"),
            (r'& "C:\Program Files\Git\bin\git.exe" push origin release/135', [r"C:\Program Files\Git\bin\git.exe", "push", "origin", "release/135"], "C:/start"),
            (r'cd C:/ComicsWork/worktrees/rec134; gh pr create --draft --title "a; b"', ["gh", "pr", "create", "--draft", "--title", "a; b"], "C:/ComicsWork/worktrees/rec134"),
            (r"cd C:\Users\Luis\n && git push origin release/135 &", P, r"C:\Users\Luis\n"),
        ):
            argv, cwd = H.split_commands_cwd(cmd, "C:/start")[-1]
            self.assertEqual(argv[:len(argv_head)], argv_head, cmd)
            self.assertEqual(cwd, where, cmd)


def block(*lines):
    return "```delivery\n" + "\n".join(lines) + "\n```"


class ParseDeliveryBlockTests(unittest.TestCase):
    def test_one_line_eta(self):
        b = H.parse_delivery_block(block("task: T1", "eta: setup 5 + work 60 + checks 10 = 75 min"))
        self.assertEqual(b["breakdown"], {"setup": 5.0, "work": 60.0, "checks": 10.0})
        self.assertEqual(b["total_min"], 75.0)

    def test_one_line_eta_tolerant(self):
        for line in ("eta: setup 5 + work 60 + checks 10", "eta: setup 5m + work 60m + checks 10m = 75m",
                     "eta: Setup 5 min + Work 60 min + Checks 10 min"):
            b = H.parse_delivery_block(block(line))
            self.assertEqual(b["breakdown"]["work"], 60.0, line)
        self.assertEqual(H.parse_delivery_block(block("eta: setup 5 + work 60 + checks 10"))["total_min"], 75.0)

    def test_unfilled_template_line_gives_no_eta(self):
        b = H.parse_delivery_block(block("eta: setup <m> + work <m> + checks <m> = <total> min"))
        self.assertNotIn("breakdown", b)

    def test_separate_lines_win(self):
        b = H.parse_delivery_block(block("eta: setup 1 + work 2 + checks 3 = 6 min", "setup: 5", "work: 40",
                                         "checks: 15"))
        self.assertEqual(b["breakdown"], {"setup": 5.0, "work": 40.0, "checks": 15.0})
        self.assertEqual(b["total_min"], 60.0)

    def test_owns_split_on_commas_only(self):
        b = H.parse_delivery_block(block("owns: a.py, skills/x/ (SKILL.md, assets/) , docs/b c.md"))
        self.assertEqual(b["owns"], ["a.py", "skills/x/ (SKILL.md", "assets/)", "docs/b c.md"])
        b = H.parse_delivery_block(block("owns: skills/x/ (SKILL.md assets/), b.py"))
        self.assertEqual(b["owns"], ["skills/x/ (SKILL.md assets/)", "b.py"])


if __name__ == "__main__":
    unittest.main()
