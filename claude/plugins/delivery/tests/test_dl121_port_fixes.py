"""DL121: five shared scripts gain opt-in behaviour (artifact groups and retry, other-repo guard,
package.json valve, Docker trim, delivery log off by default). Pure functions and fakes; no network, no Docker."""
import argparse
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

SHARED = Path(__file__).resolve().parents[1] / "templates" / "shared" / "scripts" / "delivery"
sys.path.insert(0, str(SHARED))

import artifact_prune as ap  # noqa: E402
import ci_scope as cs  # noqa: E402
import ci_watch as cw  # noqa: E402
import cleanup as cl  # noqa: E402
import session_guard as sg  # noqa: E402

NOW = datetime(2026, 1, 10, 12, 0, tzinfo=timezone.utc)


def art(ident, name, hours_old, run=None, sha=None):
    created = (NOW - timedelta(hours=hours_old)).isoformat()
    return {"id": ident, "name": name, "created_at": created,
            "workflow_run": {"id": run, "head_sha": sha}}


class ArtifactPrune(unittest.TestCase):
    PAT = r"(installer-[a-z]+)-[0-9a-f]{12}"

    def groups(self, **extra):
        import re
        return [{"regex": re.compile(self.PAT), "keep": 0, "protect_pr_heads": None,
                 "hold_workflow": None, **extra}]

    def items(self):
        return [art(1, "installer-home-aaaaaaaaaaaa", 5, run=10, sha="s1"),
                art(2, "installer-home-bbbbbbbbbbbb", 4, run=11, sha="s2"),
                art(3, "report", 3), art(4, "report", 2)]

    def test_unset_is_plain_rule(self):
        res, _ = ap.plan(self.items(), 1, now=NOW)
        self.assertEqual(sorted(res), ["installer-home-aaaaaaaaaaaa", "installer-home-bbbbbbbbbbbb", "report"])
        self.assertEqual([a["id"] for a in res["report"]["delete"]], [3])

    def test_group_by_kind_keep_zero(self):
        res, _ = ap.plan(self.items(), 1, groups=self.groups(), now=NOW)
        self.assertEqual(sorted(a["id"] for a in res["installer-home"]["delete"]), [1, 2])

    def test_protections(self):
        res, _ = ap.plan(self.items(), 1, groups=self.groups(), now=NOW, busy_runs={10}, pr_heads={self.PAT: {"s2"}})
        self.assertEqual(res["installer-home"]["delete"], [])
        res, _ = ap.plan(self.items(), 1, groups=self.groups(), now=NOW, held_runs={self.PAT: {99}})
        self.assertEqual(res["installer-home"]["delete"], [])
        res, _ = ap.plan(self.items(), 1, groups=self.groups(), now=NOW, min_age=5 * 3600 + 1)
        self.assertEqual(res["installer-home"]["delete"], [])

    def test_held_workflow_runs(self):
        runs = [{"id": 1, "head_sha": "a", "created_at": (NOW - timedelta(hours=2)).isoformat(), "conclusion": "failure"},
                {"id": 2, "head_sha": "a", "created_at": (NOW - timedelta(hours=1)).isoformat(), "conclusion": "success"},
                {"id": 3, "head_sha": "b", "created_at": (NOW - timedelta(hours=1)).isoformat(), "conclusion": "cancelled"}]
        self.assertEqual(ap.held_workflow_runs(runs, now=NOW), {3})

    def test_load_groups(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "c.json"
            self.assertEqual(ap.load_groups(str(p)), ([], ap.MIN_AGE_SECONDS))
            p.write_text(json.dumps({"artifact_prune": {"groups": [{"pattern": self.PAT, "keep": 0}]}}))
            groups, _ = ap.load_groups(str(p))
            self.assertEqual(ap.group_match("installer-x-0123456789ab", groups)[0], "installer-x")
            p.write_text(json.dumps({"artifact_prune": {"groups": [{"pattern": "a|b"}]}}))
            with self.assertRaises(ap.GhError):
                ap.load_groups(str(p))

    def test_retry_on_5xx(self):
        calls = []
        replies = [ap.GhResult(1, "", "HTTP 503 Service Unavailable"), ap.GhResult(0, "ok", "")]
        saved, env = ap.run_gh, ap.os.environ.get("ARTIFACT_PRUNE_BACKOFF")
        ap.os.environ["ARTIFACT_PRUNE_BACKOFF"] = "0"
        ap.run_gh = lambda args, timeout=300: calls.append(args) or replies.pop(0)
        try:
            self.assertEqual(ap.run_gh_retry(["api", "x"]).stdout, "ok")
            self.assertEqual(len(calls), 2)
            replies[:] = [ap.GhResult(1, "", "HTTP 404 Not Found")]
            self.assertEqual(ap.run_gh_retry(["api", "x"]).returncode, 1)
            self.assertEqual(len(calls), 3)  # a 404 is not retried
        finally:
            ap.run_gh = saved
            if env is None:
                ap.os.environ.pop("ARTIFACT_PRUNE_BACKOFF", None)
            else:
                ap.os.environ["ARTIFACT_PRUNE_BACKOFF"] = env


class SessionGuard(unittest.TestCase):
    def test_slug(self):
        for v in ("owner/example-app", "https://github.com/Owner/Example-App.git", "git@host1:owner/example-app.git",
                  "host1/owner/example-app"):
            self.assertEqual(sg.repo_slug(v), "owner/example-app")

    def test_targets(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            subprocess.run(["git", "remote", "add", "origin", "https://github.com/owner/example-app.git"], cwd=root, check=True)
            self.assertTrue(sg.targets_this_repo(root, None))
            self.assertTrue(sg.targets_this_repo(root, "owner/example-app"))
            self.assertFalse(sg.targets_this_repo(root, "other/repo"))
            # a ready pull request aimed at another repository is not this repo's business
            self.assertIsNone(sg.check_pr(root, ["gh", "pr", "ready", "5", "-R", "other/repo"]))
            self.assertIsNone(sg.check_pr(root, ["gh", "pr", "create", "--repo", "other/repo", "--head", "x"]))

    def test_cannot_tell_keeps_guard(self):
        with tempfile.TemporaryDirectory() as d:
            subprocess.run(["git", "init", "-q"], cwd=d, check=True)
            self.assertTrue(sg.targets_this_repo(Path(d), "other/repo"))


class CiScope(unittest.TestCase):
    CFG = {"full_files": ["package.json", "pnpm-lock.yaml", ".github/dependabot.yml"],
           "no_test_reads": [".github/dependabot.yml"],
           "package_json": {"file": "package.json", "scripts": ["test*", "build*"]},
           "docs": ["docs/**"]}

    def pair(self, old, new):
        return lambda f: (json.dumps(old), json.dumps(new))

    def test_no_test_reads(self):
        res = cs.decide(self.CFG, [".github/dependabot.yml"], "pull_request")
        self.assertNotEqual(res["scope"], "full")
        self.assertEqual(cs.decide(self.CFG, ["pnpm-lock.yaml"], "pull_request")["scope"], "full")

    def test_package_json_valve(self):
        base = {"name": "a", "scripts": {"lint": "x", "test": "y"}, "version": "1"}
        same = lambda **k: {**base, **k}  # noqa: E731
        d = lambda new: cs.decide(self.CFG, ["package.json"], "pull_request", read_pair=self.pair(base, new))["scope"]  # noqa: E731
        self.assertNotEqual(d(same(version="2")), "full")
        self.assertNotEqual(d(same(scripts={"lint": "z", "test": "y"})), "full")
        self.assertEqual(d(same(scripts={"lint": "x", "test": "q"})), "full")
        self.assertEqual(d(same(dependencies={"x": "1"})), "full")  # a default key
        # no reader: any doubt is full
        self.assertEqual(cs.decide(self.CFG, ["package.json"], "pull_request")["scope"], "full")

    def test_without_rule_package_json_is_plain(self):
        cfg = {"full_files": ["package.json"]}
        self.assertEqual(cs.decide(cfg, ["package.json"], "pull_request")["scope"], "full")

    def test_git_pair(self):
        with tempfile.TemporaryDirectory() as d:
            def git(*a):
                subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *a], cwd=d, check=True,
                               capture_output=True)
            git("init", "-q", "-b", "main")
            Path(d, "package.json").write_text('{"a":1}')
            git("add", "."); git("commit", "-qm", "one")
            git("checkout", "-qb", "topic")
            Path(d, "package.json").write_text('{"a":2}')
            git("commit", "-qam", "two")
            import os
            cwd = os.getcwd()
            os.chdir(d)
            try:
                old, new = cs.git_pair("main")("package.json")
            finally:
                os.chdir(cwd)
            self.assertEqual((old, new), ('{"a":1}', '{"a":2}'))


class CiWatch(unittest.TestCase):
    class Proc:
        def __init__(self, rc=0, out=""):
            self.returncode, self.stdout = rc, out

    def test_trim_runs_with_no_window_flag(self):
        calls = []

        def run(argv, **kw):
            calls.append((argv, kw))
            return self.Proc(0, "/mnt/x: 2 GiB (1 bytes) trimmed on /dev/a\n")

        line = cw.trim_docker_disk(True, run, lambda n: "docker", ("img:1",))
        self.assertIn("2 GiB", line)
        self.assertTrue(all(kw.get("creationflags") == 0x08000000 for _, kw in calls))
        self.assertIn("fstrim", calls[-1][0])

    def test_trim_skips(self):
        self.assertEqual(cw.trim_docker_disk(False, None, lambda n: "docker"), "")
        self.assertEqual(cw.trim_docker_disk(True, None, lambda n: None), "")
        self.assertIn("no image", cw.trim_docker_disk(True, lambda *a, **k: self.Proc(1), lambda n: "d", ("i",)))
        self.assertIn("not trimmed", cw.trim_docker_disk(True, lambda *a, **k: 1 / 0, lambda n: "d", ("i",)))

    def test_config_off_by_default(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "c.json"
            self.assertEqual(cw.load_docker_trim(str(p), Path(d)), (False, cw.TRIM_IMAGES))
            p.write_text(json.dumps({"ci": {"docker_trim": True, "docker_trim_images": ["a:1"]}}))
            self.assertEqual(cw.load_docker_trim(str(p), Path(d)), (True, ("a:1",)))
            p.write_text(json.dumps({"ci": {}}))
            self.assertFalse(cw.load_docker_trim(str(p), Path(d))[0])

    def test_finish_trims_first_and_keeps_code(self):
        order = []
        saved = (cw.load_docker_trim, cw.trim_docker_disk, cw.load_post_run, cw.config_root)
        cw.config_root = lambda: Path(".")
        cw.load_docker_trim = lambda c, r: (True, ("i",))
        cw.trim_docker_disk = lambda **k: order.append("trim") or "trimmed"
        cw.load_post_run = lambda c, r: (order.append("hooks") or [], 1.0)
        try:
            ns = argparse.Namespace(no_trim=False, no_post_run=False, config=None)
            self.assertEqual(cw.finish(3, [], "sha", ns), 3)
            self.assertEqual(order, ["trim", "hooks"])
            order.clear()
            ns.no_trim = True
            cw.finish(0, [], "sha", ns)
            self.assertEqual(order, ["hooks"])
        finally:
            cw.load_docker_trim, cw.trim_docker_disk, cw.load_post_run, cw.config_root = saved


class Cleanup(unittest.TestCase):
    def args(self, *a):
        return cl.build_parser().parse_args(list(a))

    def test_log_off_by_default(self):
        self.assertFalse(cl.delivery_log_wanted(self.args("--pr", "5")))
        self.assertTrue(cl.delivery_log_wanted(self.args("--pr", "5", "--delivery-log")))
        self.assertFalse(cl.delivery_log_wanted(self.args("--delivery-log")))  # needs --pr
        self.assertFalse(cl.delivery_log_wanted(self.args("--pr", "5", "--delivery-log", "--dry-run")))

    def test_config_turns_it_on(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / ".delivery").mkdir()
            (Path(d) / ".delivery" / "config.json").write_text(json.dumps({"cleanup": {"delivery_log": True}}))
            self.assertTrue(cl.delivery_log_wanted(self.args("--pr", "5"), Path(d)))
            self.assertFalse(cl.delivery_log_wanted(self.args("--pr", "5", "--no-delivery-log"), Path(d)))

    def test_pre_merge_base(self):
        with tempfile.TemporaryDirectory() as d:
            def git(*a):
                return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *a], cwd=d,
                                      check=True, capture_output=True, text=True).stdout.strip()
            git("init", "-q", "-b", "main")
            Path(d, "a").write_text("1"); git("add", "."); git("commit", "-qm", "base")
            base = git("rev-parse", "HEAD")
            git("checkout", "-qb", "topic")
            Path(d, "b").write_text("1"); git("add", "."); git("commit", "-qm", "work")
            head = git("rev-parse", "HEAD")
            git("checkout", "-q", "main")
            git("merge", "--no-ff", "-qm", "merge", "topic")

            class Ctx:
                root = Path(d)
            self.assertEqual(cl.pre_merge_base(Ctx, head, "main"), base)
            self.assertIsNone(cl.pre_merge_base(Ctx, base, "main"))


if __name__ == "__main__":
    unittest.main()
