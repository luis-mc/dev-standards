import unittest

from _helpers import L, make_root  # noqa: F401  (puts scripts/ on sys.path)
import hook_stop as S

FLAG = [
    "ready in about 5 minutes after the CI run starts.",
    "The agent takes about 1 hour to finish, once it is merged.",
    "Done in about 20 minutes.",
]
NO_FLAG = [
    "That saves two full checks of about 50 min each.",
    "UI coding takes about 1 h, a full check 35-50 min, and CI about 20 min.",
    "Each try took about 4 minutes.",
    "- Smoke ready 16:40. The CI run takes about 25 minutes from the push.",
    "- The check ends about 16:40 (CI run started 16:15)\n  and it takes about 25 minutes.",
]


def keys(text):
    return [k for k, _ in S.check_eta_text(text) if k.startswith("DL-31:eta")]


class EtaTests(unittest.TestCase):
    def test_real_etas_are_flagged(self):
        self.assertTrue(keys("It will be ready in about 5 minutes."))
        self.assertTrue(keys("The rewrite takes about 1 hour."))
        self.assertTrue(keys("Done in about 20 minutes."))

    def test_measured_durations_savings_and_costs_are_not_flagged(self):
        for text in NO_FLAG[:3]:
            self.assertEqual(keys(text), [], text)

    def test_clock_time_elsewhere_in_the_same_bullet_covers_the_sentence(self):
        self.assertEqual(keys(NO_FLAG[3]), [])
        self.assertEqual(keys("- Ready 16:40. The CI run takes about 25 minutes."), [])
        self.assertTrue(keys("- Ready soon.\n- The rewrite takes about 25 minutes."))

    def test_tomorrow_is_still_flagged(self):
        self.assertTrue([k for k, _ in S.check_eta_text("The rest lands tomorrow.")])


FALSE_ALARM_TRAINS = "| `trains` | the releases, with their PR and state |"
FALSE_ALARM_ETA = "- **I** add the rows the hooks miss, like the ETA for DV395."


def label_keys(text, ledger=None):
    return [k for k, _ in S.check_label_text(text, S.H.DEFAULTS, ledger or {"trains": []})]


class FalseAlarmTests(unittest.TestCase):
    def test_eta_as_a_field_name_is_not_a_promise(self):
        for text in (FALSE_ALARM_ETA, "The ETA field holds it.", "It records its ETA and its state.",
                     "`eta` is set by agent-eta.", "```\n\"eta\": 20 min\n```"):
            self.assertEqual(keys(text), [], text)

    def test_real_eta_promises_still_fail(self):
        for text in ("ETA ~20 min", "ETA 16:40.", "The ETA is about 1 h.", "It will be ready soon.",
                     "Should be done in 30 min.", "ETA: tomorrow"):
            self.assertTrue(keys(text) or [k for k, _ in S.check_eta_text(text)], text)

    def test_train_word_in_code_is_ignored_in_prose_is_flagged(self):
        self.assertEqual(label_keys(FALSE_ALARM_TRAINS), [])
        self.assertEqual(label_keys("The `trains` key.\n```\ntrains: []\n```"), [])
        self.assertTrue(label_keys("The trains are green."))
        self.assertTrue(label_keys("train 12 is green."))

    def test_branch_names_are_flagged_even_in_code_spans(self):
        ledger = {"trains": [{"id": "T-1", "branch": "claude/foo-bar"}]}
        self.assertTrue(label_keys("Pushed `claude/foo-bar`.", ledger))
        self.assertTrue(label_keys("Pushed claude/foo-bar.", ledger))
        self.assertTrue(label_keys("Pushed `release/29`."))


class OneCiPerReleaseTests(unittest.TestCase):
    def ledger(self, **kw):
        t = {"id": "T-1", "release_no": 41, "pr": 399, "merged_at": "2026-10-16T22:00:00Z", "state": "merged"}
        t.update(kw)
        return {"trains": [t]}

    def gh(self, trees=("t1", "t1"), jobs=("Windows tests", "Publish"), merge="m" * 40, conclusion=None):
        def run(argv, root):
            if argv[:2] == ["pr", "view"]:
                return {"mergeCommit": {"oid": merge}, "baseRefName": "main", "headRefOid": "h" * 40}
            if argv[0] == "api":
                return {"tree": trees[0] if argv[1].endswith(merge) else trees[1]}
            if argv[:2] == ["run", "list"]:
                return [{"databaseId": 7, "workflowName": "main"}]
            if argv[:2] == ["run", "view"]:
                return {"jobs": [{"name": n, "conclusion": (conclusion or {}).get(n, "success")} for n in jobs]}
        return run

    def cfg(self, *names):
        return {"pr_proven_jobs": list(names)}

    def test_repeated_pr_proven_job_on_same_tree_is_flagged(self):
        out = S.check_one_ci_per_release("/x", self.ledger(), self.cfg("Windows tests"), gh=self.gh())
        self.assertEqual(len(out), 1)
        self.assertIn("DL-76", out[0][1])
        self.assertIn("RELEASE-41", out[0][1])
        self.assertIn("main / Windows tests", out[0][1])
        self.assertNotIn("Publish", out[0][1])

    def test_nothing_configured_means_no_check_and_no_gh_call(self):
        def boom(argv, root):
            raise AssertionError("gh called")
        self.assertEqual(S.check_one_ci_per_release("/x", self.ledger(), {}, gh=boom), [])

    def test_different_tree_skipped_job_and_unmerged_train_pass(self):
        c = self.cfg("Windows tests")
        self.assertEqual(S.check_one_ci_per_release("/x", self.ledger(), c, gh=self.gh(trees=("t2", "t1"))), [])
        self.assertEqual(S.check_one_ci_per_release("/x", self.ledger(), c,
                                                    gh=self.gh(conclusion={"Windows tests": "skipped"})), [])
        self.assertEqual(S.check_one_ci_per_release("/x", self.ledger(merged_at=None), c, gh=self.gh()), [])
        self.assertEqual(S.check_one_ci_per_release("/x", self.ledger(state="cleaned"), c, gh=self.gh()), [])

    def test_glob_and_gh_failure(self):
        self.assertEqual(len(S.check_one_ci_per_release("/x", self.ledger(), self.cfg("windows *"), gh=self.gh())), 1)
        self.assertEqual(S.check_one_ci_per_release("/x", self.ledger(), self.cfg("Publish"), gh=lambda a, r: None), [])


if __name__ == "__main__":
    unittest.main()
