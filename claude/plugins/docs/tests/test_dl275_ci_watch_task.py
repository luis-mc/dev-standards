"""DL275: a ci_watch / gh run watch result speaks for the watched head's task, never for the checkout."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
HOOK = SCRIPTS / "hook_after_command.py"

GH_STUB = """import json, os, sys
d = os.path.dirname(os.path.abspath(__file__))
print(json.dumps(json.load(open(os.path.join(d, "run.json")))))
"""


def git(cwd, *a):
    p = subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", *a],
                       cwd=str(cwd), capture_output=True, text=True)
    if p.returncode:
        raise RuntimeError(p.stderr)
    return p.stdout.strip()


class Case(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "work"
        self.root.mkdir()
        git(self.root, "init", "-q", "-b", "main")
        rec = self.root / "docs" / "artifacts"
        rec.mkdir(parents=True)
        (self.root / ".claude").mkdir()
        (self.root / ".claude" / "artifacts.json").write_text("{}\n", encoding="utf-8")
        (rec / "manifest.json").write_text(json.dumps({"merged_status": "Live"}), encoding="utf-8")
        self.set_registry({"AB12": "Running", "AB38": "Running", "AB82": "Running"})
        (self.root / "README.md").write_text("x\n", encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "base")
        self.stub = Path(self.tmp.name) / "gh.py"
        self.stub.write_text(GH_STUB, encoding="utf-8")

    def set_registry(self, statuses):
        tasks = [{"id": k, "owner": "project", "status": v, "item": "x"} for k, v in statuses.items()]
        (self.root / "docs" / "artifacts" / "registry.json").write_text(
            json.dumps({"tasks": tasks}), encoding="utf-8")

    def branch_with_commit(self, name):
        git(self.root, "checkout", "-q", "-b", name, "main")
        (self.root / (name + ".txt")).write_text(name, encoding="utf-8")
        git(self.root, "add", name + ".txt")
        git(self.root, "commit", "-q", "-m", name)
        return git(self.root, "rev-parse", "HEAD")

    def fire(self, command, error=None, env=None):
        data = {"session_id": "s1", "cwd": str(self.root), "tool_name": "Bash",
                "tool_input": {"command": command}}
        if error:
            data.update(hook_event_name="PostToolUseFailure", error=error)
        else:
            data.update(hook_event_name="PostToolUse",
                        tool_response={"stdout": "ok", "stderr": "", "interrupted": False})
        full = {k: v for k, v in os.environ.items() if not k.startswith("CLAUDE_ARTIFACTS_")}
        full.update(env or {})
        p = subprocess.run([sys.executable, str(HOOK)], cwd=str(self.root), input=json.dumps(data).encode(),
                           capture_output=True, env=full)
        self.assertEqual(p.returncode, 0, p.stderr)
        qf = self.root / ".claude" / "artifacts-queue.json"
        if not qf.exists():
            return []
        return [(e["id"], e["suggested_status"]) for e in json.loads(qf.read_text())["events"]]


class CiWatch(Case):
    def test_other_branch_head_names_that_task(self):
        sha82 = self.branch_with_commit("AB82-y")
        self.branch_with_commit("AB38-x")
        self.assertEqual(self.fire("python ci_watch.py " + sha82), [("AB82", "Waiting")])

    def test_remote_branch_head_names_that_task(self):
        sha82 = self.branch_with_commit("AB82-y")
        git(self.root, "update-ref", "refs/remotes/origin/AB82-y", sha82)
        git(self.root, "checkout", "-q", "main")
        git(self.root, "branch", "-q", "-D", "AB82-y")
        self.branch_with_commit("AB38-x")
        self.assertEqual(self.fire("python ci_watch.py " + sha82[:10]), [("AB82", "Waiting")])

    def test_head_on_no_task_branch_queues_nothing(self):
        git(self.root, "checkout", "-q", "-b", "AB38-x")
        sha = self.branch_with_commit("plain-topic")
        git(self.root, "checkout", "-q", "AB38-x")
        self.assertEqual(self.fire("python ci_watch.py " + sha), [])
        self.assertEqual(self.fire("python ci_watch.py deadbeef"), [])

    def test_current_head_keeps_the_current_task(self):
        sha = self.branch_with_commit("AB38-x")
        self.assertEqual(self.fire("python ci_watch.py " + sha), [("AB38", "Waiting")])
        self.assertEqual(self.fire("python ci_watch.py " + sha, "Exit code 1\nred"), [("AB38", "Waiting"),
                                                                                    ("AB38", "Failed")])

    def test_live_task_queues_nothing(self):
        sha82 = self.branch_with_commit("AB82-y")
        self.branch_with_commit("AB38-x")
        self.set_registry({"AB38": "Running", "AB82": "Live"})
        self.assertEqual(self.fire("python ci_watch.py " + sha82), [])
        self.set_registry({"AB38": "Live", "AB82": "Running"})
        sha38 = git(self.root, "rev-parse", "HEAD")
        self.assertEqual(self.fire("python ci_watch.py " + sha38), [])

    def test_failed_or_unknown_code_never_passes(self):
        sha = self.branch_with_commit("AB38-x")
        for cmd in ("python ci_watch.py %s | tail -3", "python ci_watch.py %s; echo done",
                    "python ci_watch.py %s || true"):
            self.assertEqual(self.fire(cmd % sha, "Exit code 1\nred"), [], cmd)
            self.assertEqual(self.fire(cmd % sha), [], cmd)   # exit code of the last command only
        events = self.fire("python ci_watch.py " + sha, "Exit code 1\nred")
        self.assertNotIn(("AB38", "Waiting"), events)
        self.assertEqual(events, [("AB38", "Failed")])


class RunWatch(Case):
    def view(self, sha, branch):
        (self.stub.parent / "run.json").write_text(json.dumps({"headBranch": branch, "headSha": sha}))
        return {"CLAUDE_ARTIFACTS_GH": str(self.stub)}

    def test_run_of_other_task_branch(self):
        sha82 = self.branch_with_commit("AB82-y")
        self.branch_with_commit("AB38-x")
        env = self.view(sha82, "AB82-y")
        self.assertEqual(self.fire("gh run watch 77 --exit-status", env=env), [("AB82", "Waiting")])

    def test_run_failed_is_failed(self):
        sha82 = self.branch_with_commit("AB82-y")
        self.branch_with_commit("AB38-x")
        env = self.view(sha82, "AB82-y")
        self.assertEqual(self.fire("gh run watch 77", "Exit code 1\nred", env=env), [("AB82", "Failed")])

    def test_run_of_unknown_branch_or_unreadable_queues_nothing(self):
        self.branch_with_commit("AB38-x")
        git(self.root, "checkout", "-q", "-b", "plain", "main")
        sha = self.branch_with_commit("other-topic")
        git(self.root, "checkout", "-q", "AB38-x")
        self.assertEqual(self.fire("gh run watch 77", env=self.view(sha, "other-topic")), [])
        self.assertEqual(self.fire("gh run watch 77"), [])   # no gh answer: no event


if __name__ == "__main__":
    unittest.main()
