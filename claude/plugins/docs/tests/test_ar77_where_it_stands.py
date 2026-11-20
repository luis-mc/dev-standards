"""AR77: Full Progress section 1 'Where it stands' is built from the record (ARTIFACTSPEC R5.53, R5.54, R5.37a)."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "claude" / "plugins" / "docs" / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import render_artifacts as R  # noqa: E402
import test_render_artifacts as T  # noqa: E402
from test_dl228_record_messages import RecordCase  # noqa: E402


def mk(tid, status, expected="23 Nov", basis=None, rides=None, owner="artifacts", **extra):
    t = T.task(tid, owner, status, "Item %s" % tid, expected, "2026-11-19T10:00+00:00", "luismc-docs")
    if basis:
        t["expected_basis"] = basis
    if rides:
        t["rides"] = rides
    t.update(extra)
    return t


def release(n, status="Live", item="luismc-docs 1.2.0", **extra):
    t = mk("DL%d" % (900 + n), status, item="x", release=n, **extra)
    t["item"] = item
    t["changed"] = "2026-11-19T10:00+00:00"
    return t


class Stands(unittest.TestCase):
    def stands(self, tasks, lede="Old lede. More."):
        return R.feature_stands("artifacts", tasks, lede)

    def test_live_release_and_waiting_tasks_show_both_parts(self):
        rel = release(154)
        tasks = [rel, mk("DL10", "Built", rides=rel["id"]),
                 mk("DL346", "Waiting", basis="the new pool"), mk("DL347", "Waiting", basis="the new pool"),
                 mk("DL348", "Waiting", basis="the new pool"), mk("DL349", "To do", expected="")]
        text = self.stands(tasks)
        self.assertIn("Live: RELEASE-154 (19 Nov) luismc-docs 1.2.0", text)
        self.assertIn("Waiting: DL346-DL348 on the new pool (~23 Nov)", text)
        self.assertIn("To do: DL349", text)
        self.assertNotIn("Old lede", text)

    def test_no_version_gives_number_and_date_only(self):
        rel = release(7, item="Plain release")
        text = self.stands([rel, mk("DL10", "Built", rides=rel["id"]), mk("DL11", "To do")])
        self.assertTrue(text.startswith("Live: RELEASE-7 (19 Nov);"), text)

    def test_gaps_split_ranges(self):
        text = self.stands([mk("DL1", "To do"), mk("DL2", "To do"), mk("DL4", "To do")])
        self.assertIn("To do: DL1-DL2, DL4", text)

    def test_running_names_its_release(self):
        rel = release(155, status="Waiting", expected="24 Nov")
        text = self.stands([rel, mk("DL20", "Running", rides=rel["id"])])
        self.assertIn("Running: DL20 in RELEASE-155 (~24 Nov)", text)

    def test_final_statuses_are_never_listed(self):
        text = self.stands([mk("DL1", "Dropped"), mk("DL2", "Live"), mk("DL3", "Built"), mk("DL4", "To do")])
        self.assertNotIn("DL1", text)
        self.assertNotIn("DL2", text)
        self.assertNotIn("DL3", text)

    def test_no_tasks_falls_back_to_the_lede(self):
        self.assertEqual(self.stands([mk("DL1", "To do", owner="other")]), "Old lede.")

    def test_cell_stays_short_and_keeps_whole_ids(self):
        rel = release(9)
        tasks = [rel, mk("DL10", "Built", rides=rel["id"])]
        for i, status in enumerate(("Running", "Needs you", "Waiting", "To do")):
            for j in range(3):
                tasks.append(mk("DL%d" % (100 + i * 10 + j * 2), status, basis="a long basis number %d" % i * 2))
        text = self.stands(tasks)
        self.assertLessEqual(len(text), R.STANDS_MAX + 1, text)
        self.assertNotIn("Live:", text)               # the oldest detail went first
        for clause in text.rstrip(".").split("; "):
            self.assertRegex(clause, r"^(Running|Needs you|Waiting|To do): DL\d+")

    def test_section_one_cell_in_the_page_and_structure_check(self):
        fx = T.Fixture()
        self.addCleanup(fx.close)
        rel = release(12)
        reg = T.base_registry()
        reg["tasks"] += [rel, mk("DL9", "Built", rides=rel["id"], owner="models"),
                         mk("DL5", "Waiting", basis="the pool", owner="models")]
        out = fx.render("full-progress", registry=reg)
        self.assertIn("Live: RELEASE-12 (19 Nov) luismc-docs 1.2.0; ", out)
        self.assertEqual(fx.check(out, "full-progress", registry=reg), [])


class Fingerprint(RecordCase):
    def test_basis_change_changes_the_fingerprint(self):
        sys.path.insert(0, str(ROOT / "claude" / "plugins" / "docs" / "scripts"))
        import project_artifacts as P
        self.ok("task-add", "--owner", "alpha", "--item", "First", "--detail", "d", "--expected", "13 Oct",
                "--status", "Waiting", "--basis", "the new pool")
        rec_dir = self.root / "docs" / "artifacts"
        before = P.publish_fingerprint(P.Record.load(rec_dir))
        self.ok("set-task-status", "AL1", "Waiting", "--basis", "the other pool", "--expected", "13 Oct")
        after = P.publish_fingerprint(P.Record.load(rec_dir))
        self.assertNotEqual(before, after)


class StaleLede(RecordCase):
    def warn(self, lede):
        import project_artifacts as P
        d = self.root / "export"
        if not d.exists():
            d = self.export()
        import json
        meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
        meta["lede"] = lede
        (d / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
        self.ok("edit-content", "alpha", "--from", str(d))
        return P.stale_lede_warnings(P.Record.load(self.root / "docs" / "artifacts"))

    def test_train_label_and_pr_number_warn(self):
        sys.path.insert(0, str(ROOT / "claude" / "plugins" / "docs" / "scripts"))
        self.assertEqual(self.warn("Plain note."), [])
        self.assertEqual(len(self.warn("It shipped on train-2026-10-11-47.")), 1)
        self.assertEqual(len(self.warn("It shipped in #47.")), 1)
        self.assertEqual(self.warn("Item A#1 is fine."), [])


if __name__ == "__main__":
    unittest.main()
