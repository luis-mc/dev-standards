"""ci_runs.py on recorded GitHub JSON and a fixture slot log. No network, no gh."""
import json
import re
import unittest
from datetime import datetime, timezone
from pathlib import Path

from _helpers import make_root

import ci_runs as R

FIX = Path(__file__).resolve().parent / "fixtures" / "ci_runs"
REPO = "owner/example-app"
NOW = datetime(2026, 11, 4, 14, 33, tzinfo=timezone.utc)


def load(name):
    return json.loads((FIX / name).read_text())


class FakeShell:
    def __init__(self, fail=False):
        self.calls = []
        self.jobs = load("jobs.json")
        self.fail = fail

    def run(self, argv, cwd=None, timeout=60):
        self.calls.append(list(argv))
        if self.fail:
            return 1, "", "no"
        ep = argv[-1]
        if argv[:2] == ["gh", "api"]:
            if ep.endswith("/actions/runs?per_page=%d" % R.RUNS_PER_PAGE):
                return 0, (FIX / "runs.json").read_text(), ""
            m = re.search(r"/runs/(\d+)/jobs", ep)
            if m:
                return 0, json.dumps(self.jobs.get(m.group(1), {"jobs": []})), ""
            if ep == "repos/%s" % REPO:
                return 0, (FIX / "repo.json").read_text(), ""
        return 1, "", "unrouted"


def collect(root=None, sh=None, claims=None):
    root = root or make_root({"ci": {"fallback": {"after_min": 10}}})
    col = R.Collector(root, repo=REPO, sh=sh or FakeShell(), now=lambda: NOW,
                      slot_log=str(FIX / "slot-log.jsonl"), claims=claims or (lambda sha: []))
    return col, col.collect()


class CiRuns(unittest.TestCase):
    def test_finished_rows_newest_first_and_skipped_left_out(self):
        _, doc = collect()
        ids = [e["run_id"] for e in doc["finished"]]
        self.assertEqual(ids, [102, 101, 103, 104, 105])
        self.assertEqual(doc["repo"], REPO)

    def test_why(self):
        _, doc = collect()
        why = {e["run_id"]: e["why"] for e in doc["finished"]}
        self.assertEqual(why[101], "ready PR #141")
        self.assertEqual(why[102], "push to main")
        self.assertEqual(why[103], "re-run #2 by the owner")
        self.assertEqual(why[104], "schedule")
        self.assertEqual(why[105], "fallback to cloud after 12 min")

    def test_agent_branch(self):
        run = {"event": "push", "head_branch": "DL40-example"}
        self.assertEqual(R.why_of(run, "main"), "agent branch DL40-example")
        self.assertEqual(R.why_of({"event": "push", "head_branch": "topic"}, "main"), "push to topic")

    def test_where_kinds(self):
        _, doc = collect()
        where = {e["run_id"]: e["where"] for e in doc["finished"]}
        self.assertEqual(where[101], {"kind": "pool", "name": "host1-pool-app1"})
        self.assertEqual(where[102]["kind"], "windows")
        self.assertEqual(where[103]["kind"], "hosted")
        self.assertEqual(where[105]["kind"], "cloud")

    def test_cloud_name_is_the_claim_holder(self):
        _, doc = collect(claims=lambda sha: [{"holder": "cloud-session-1", "shard": "unit-1"}])
        run105 = [e for e in doc["finished"] if e["run_id"] == 105][0]
        self.assertEqual(run105["where"], {"kind": "cloud", "name": "cloud-session-1"})

    def test_waterfall_times(self):
        _, doc = collect()
        e = [x for x in doc["finished"] if x["run_id"] == 101][0]
        self.assertEqual((e["queued_s"], e["slot_wait_s"], e["total_s"]), (12, 70, 600))
        self.assertEqual(e["slot_start_s"], 12)
        names = [s["name"] for s in e["steps"]]
        self.assertEqual(names, ["Set up job", "Checkout", "Unit tests"])       # the skipped step is left out
        setup = e["steps"][0]
        self.assertEqual((setup["start_s"], setup["duration_s"]), (82, 0))       # the slot wait was drawn already
        self.assertEqual(e["steps"][2], {"job": "unit", "name": "Unit tests", "start_s": 90, "duration_s": 500, "conclusion": "success"})
        self.assertEqual(e["completed_at"], "2026-11-04T14:10:00Z")

    def test_failed_step_and_conclusion(self):
        _, doc = collect()
        e = [x for x in doc["finished"] if x["run_id"] == 102][0]
        self.assertEqual(e["conclusion"], "failure")
        self.assertEqual(e["steps"][-1]["conclusion"], "failure")
        self.assertEqual(e["slot_wait_s"], 0)

    def test_rerun_uses_the_attempt_start(self):
        _, doc = collect()
        e = [x for x in doc["finished"] if x["run_id"] == 103][0]
        self.assertEqual(e["queued_s"], 10)
        self.assertEqual(e["total_s"], 60)

    def test_other_repo_rows_in_the_slot_log_are_ignored(self):
        slots = R.read_slot_log(FIX / "slot-log.jsonl")
        self.assertEqual(len(R.slot_rows(slots, REPO, 101, 1)), 1)
        self.assertEqual(R.slot_rows(slots, REPO, 101, 1)[0]["released_at"], "2026-11-04T14:10:00Z")
        self.assertEqual(R.read_slot_log(FIX / "missing.jsonl"), {})

    def test_fallback_row(self):
        _, doc = collect()
        e = [x for x in doc["finished"] if x["run_id"] == 105][0]
        self.assertTrue(e["fallback"])
        self.assertEqual(e["slot_wait_s"], 710)

    def test_active(self):
        _, doc = collect()
        act = {a["run_id"]: a for a in doc["active"]}
        self.assertEqual(set(act), {201, 202})
        self.assertEqual(act[201]["now"], {"step": "Unit tests", "since": "2026-11-04T14:30:20Z"})
        self.assertEqual(act[201]["why"], "ready PR #143")
        self.assertIsNone(act[201].get("slot_wait"))
        self.assertEqual(act[202]["slot_wait"], {"since": "2026-11-04T14:28:05Z", "fallback_in_min": 5})
        self.assertIsNone(act[202]["now"])

    def test_fallback_in_min_is_unknown_without_a_setting(self):
        _, doc = collect(root=make_root({}))
        act = {a["run_id"]: a for a in doc["active"]}
        self.assertIsNone(act[202]["slot_wait"]["fallback_in_min"])

    def test_cache_reuses_finished_runs_and_skips_job_calls(self):
        root = make_root({})
        col, doc = collect(root=root)
        col.write(doc)
        sh = FakeShell()
        col2, doc2 = collect(root=root, sh=sh)
        self.assertEqual(doc2["finished"], doc["finished"])
        asked = [c[-1] for c in sh.calls if "/jobs" in c[-1]]
        self.assertEqual(len(asked), 2)                                          # only the two active runs

    def test_gh_failure_returns_none_and_keeps_the_file(self):
        root = make_root({})
        col, doc = collect(root=root)
        col.write(doc)
        before = (Path(root) / R.OUT_REL).read_text()
        col2 = R.Collector(root, repo=REPO, sh=FakeShell(fail=True), now=lambda: NOW, slot_log=str(FIX / "slot-log.jsonl"))
        self.assertIsNone(col2.collect())
        self.assertEqual((Path(root) / R.OUT_REL).read_text(), before)

    def test_main_writes_the_file(self):
        root = make_root({})
        col, doc = collect(root=root)
        col.write(doc)
        data = json.loads((Path(root) / R.OUT_REL).read_text())
        self.assertEqual(sorted(data), ["active", "finished", "generated_at", "repo"])


if __name__ == "__main__":
    unittest.main()
