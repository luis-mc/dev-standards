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
        H.handle(bash("git push origin CO148-fix"), self.root)
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
        H.handle(bash('msiexec /i "C:\\build\\Home-0.1.6212.msi" /qn'), self.root)
        H.handle(bash("schtasks /run /tn HomeUpdateNow"), self.root)
        ins = self.led()["installs"]
        self.assertEqual(ins[0]["via"], "msiexec")
        self.assertEqual(ins[0]["state"], "done")
        self.assertEqual((ins[1]["product"], ins[1]["state"]), ("home", "installing"))

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
        cmd = ("gh pr create --repo luis-mc/comics-organizer --base master --head release/40 "
               "--title \"R40\" --body-file C:/ComicsWork/briefs/r44-pr.md")
        with mock.patch.object(H, "rev_parse", return_value="a" * 40):
            H.handle(bash(cmd, "https://github.com/luis-mc/comics-organizer/pull/418\n"), self.root)
        trains = self.led()["trains"]
        self.assertEqual(len(trains), 1)
        t = trains[0]
        self.assertEqual((t["branch"], t["pr"], t["state"]), ("release/40", 418, "ci"))
        self.assertEqual(t["ci"]["head_sha"], "a" * 40)

    def test_pr_create_of_a_known_train_gets_head_sha(self):
        seed(self.root, state="pushed")
        with mock.patch.object(H, "rev_parse", return_value="b" * 40):
            H.handle(bash("gh pr create --head release/29 --body-file x.md", "https://github.com/o/r/pull/9"), self.root)
        t = self.led()["trains"][0]
        self.assertEqual((t["pr"], t["state"], t["ci"]["head_sha"]), (9, "ci", "b" * 40))

    def test_pr_create_of_a_non_release_branch_creates_no_train(self):
        H.handle(bash("gh pr create --repo o/r --head CO1-x --body-file x.md", "https://github.com/o/r/pull/5"), self.root)
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
task: CO152
branch: CO152-scripts
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
        self.assertEqual(b["task"], "CO152")
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
        self.assertEqual((a["task"], a["where"], a["id"], a["state"]), ("CO152", "local", "ag_1", "running"))
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
        self.assertEqual((agents[0]["where"], agents[0]["id"], agents[0]["task"]), ("cloud", "trig_abc", "CO152"))


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


if __name__ == "__main__":
    unittest.main()
