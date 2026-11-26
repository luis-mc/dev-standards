"""DS260 (DL-120): the watcher re-runs the failed jobs once after an infrastructure failure, never a test failure."""
import json
import unittest
from pathlib import Path

import test_watch as T
from _helpers import L
import delivery_config as C

ON = {"watcher": {"infra_retry": True}}


def job(steps, conclusion="failure"):
    return {"name": "build", "status": "completed", "conclusion": conclusion,
            "steps": [{"name": n, "conclusion": c} for n, c in steps]}


def routes(run_conclusion="failure", jobs=None, log=""):
    r = T.routes_for_green()
    r[("gh", "run", "list", "--commit")] = (0, T.runs((1, "completed", run_conclusion, T.SHA, "release/29")))
    r[("gh", "run", "view", "1", "--json")] = (0, json.dumps({"jobs": jobs or []}))
    r[("gh", "run", "view", "1", "--log-failed")] = (0, log)
    r[("gh", "run", "rerun")] = (0, "")
    return r


def go(cfg, r, root=None):
    root = root or T.make_root(cfg)
    if not L.load(root)["trains"]:
        T.seed(root, [{"branch": "release/29", "pr": 10, "state": "ci"}])
    sh = T.FakeShell(r)
    lines = []
    T.W.Watcher(root, sh=sh, now=lambda: T.NOW, out=lines.append, ci_runs=False).run_once()
    return root, sh, lines


def reruns(sh):
    return [c for c in sh.calls if c[:3] == ["gh", "run", "rerun"]]


def retry_events(root):
    return [e for e in L.load(root)["events"] if e["kind"] == "ci.retry"]


class InfraRetryTests(unittest.TestCase):
    def assert_retried(self, r, cls):
        root, sh, lines = go(ON, r)
        self.assertEqual(reruns(sh), [["gh", "run", "rerun", "1", "--failed"]])
        ev = retry_events(root)
        self.assertEqual(len(ev), 1)
        self.assertIn("class=" + cls, ev[0]["ref"])
        self.assertNotEqual(L.load(root)["trains"][0]["state"], "red")
        self.assertEqual(sh.writes() and [c for c in sh.writes() if c[:3] == ["gh", "pr", "merge"]], [])
        return root

    def test_startup_failure_run(self):
        self.assert_retried(routes("startup_failure"), "startup_failure")

    def test_runner_lost_job_with_no_steps(self):
        self.assert_retried(routes(jobs=[job([])]), "runner_lost")

    def test_runner_lost_log(self):
        r = routes(jobs=[job([("Set up job", "success"), ("Build", "failure")])],
                   log="The runner has received a shutdown signal.")
        self.assert_retried(r, "runner_lost")

    def test_failure_before_any_project_step(self):
        self.assert_retried(routes(jobs=[job([("Set up job", "failure")])]), "before_project_step")

    def test_log_patterns(self):
        for pat, log in (("Hash Sum mismatch", "E: Failed to fetch  Hash Sum mismatch"),
                         ("Could not resolve host", "curl: Could not resolve host: x.org"),
                         ("TLS handshake timeout", "net/http: TLS handshake timeout"),
                         ("502 Bad Gateway", "error: 502 Bad Gateway"),
                         ("The operation was canceled", "docker pull base: The operation was canceled")):
            r = routes(jobs=[job([("Set up job", "success"), ("Build image", "failure")])], log=log)
            root = self.assert_retried(r, "log:" + pat)
            self.assertTrue(retry_events(root), pat)

    def test_canceled_without_docker_or_apt_is_not_infra(self):
        r = routes(jobs=[job([("Set up job", "success"), ("Run tests", "failure")])],
                   log="--- FAIL: TestX\nThe operation was canceled")
        root, sh, _ = go(ON, r)
        self.assertEqual(reruns(sh), [])
        self.assertEqual(L.load(root)["trains"][0]["state"], "red")

    def test_test_failure_is_not_retried(self):
        r = routes(jobs=[job([("Set up job", "success"), ("Run tests", "failure")])],
                   log="--- FAIL: TestJoin (0.01s)\nFAIL")
        root, sh, _ = go(ON, r)
        self.assertEqual(reruns(sh), [])
        self.assertEqual(retry_events(root), [])
        self.assertEqual(L.load(root)["trains"][0]["state"], "red")

    def test_one_test_failure_among_infra_failures_is_not_retried(self):
        jobs = [job([("Set up job", "failure")]), job([("Set up job", "success"), ("Run tests", "failure")])]
        root, sh, _ = go(ON, routes(jobs=jobs, log="--- FAIL: TestX"))
        self.assertEqual(reruns(sh), [])

    def test_second_failure_is_not_retried(self):
        r = routes("startup_failure")
        root, sh, _ = go(ON, r)
        self.assertEqual(len(reruns(sh)), 1)
        # the re-run failed again on the same head
        root, sh2, _ = go(ON, r, root=root)
        self.assertEqual(reruns(sh2), [])
        self.assertEqual(len(retry_events(root)), 1)
        self.assertEqual(L.load(root)["trains"][0]["state"], "red")

    def test_off_by_default(self):
        root, sh, _ = go({}, routes("startup_failure"))
        self.assertEqual(reruns(sh), [])
        self.assertEqual(L.load(root)["trains"][0]["state"], "red")

    def test_failed_rerun_goes_red(self):
        r = routes("startup_failure")
        r[("gh", "run", "rerun")] = (1, "")
        root, sh, _ = go(ON, r)
        self.assertEqual(L.load(root)["trains"][0]["state"], "red")
        self.assertIn("ci.retry_failed", [e["kind"] for e in L.load(root)["events"]])


class ConfigTests(unittest.TestCase):
    def test_accessors(self):
        self.assertFalse(C.infra_retry({}))
        self.assertTrue(C.infra_retry(ON))
        self.assertFalse(C.infra_retry({"watcher": {"infra_retry": "yes"}}))
        self.assertIn("Hash Sum mismatch", C.infra_retry_patterns({}))
        self.assertEqual(C.infra_retry_patterns({"watcher": {"infra_retry_patterns": ["boom"]}}), ["boom"])
        self.assertEqual(len(C.infra_retry_patterns({"watcher": {"infra_retry_patterns": []}})), 5)

    def test_schema_lists_the_keys(self):
        schema = json.loads(Path(C.SCHEMA_PATH).read_text(encoding="utf-8"))
        props = schema["properties"]["watcher"]["properties"]
        self.assertEqual(props["infra_retry"]["default"], False)
        self.assertEqual(props["infra_retry_patterns"]["type"], "array")


if __name__ == "__main__":
    unittest.main()
