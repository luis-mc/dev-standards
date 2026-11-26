import unittest
from _helpers import *  # noqa
import docs_check as C
import docs_index as I
from test_check import GOOD


def make(extra):
    d = project({"docs/features/import/spec.md": GOOD, "docs/architecture/sec.md": "# Top\n", **extra})
    I.build(d)
    return d


def r1(d):
    return [x for x in C.run_checks(d, None, reference=True) if x["code"] == "R1"]


class RemovedIdTests(unittest.TestCase):
    def test_cited_id_fails_in_a_delivery_project(self):
        d = make({".delivery/config.json": "{}", "src/a.py": "x = 1  # DL-77 guard\n"})
        found = r1(d)
        self.assertEqual(len(found), 1)
        self.assertIn("DL-77", found[0]["message"])
        self.assertIn("removed, delete the citation", found[0]["message"])
        self.assertIn("removed-delivery-ids.md", found[0]["message"])

    def test_project_without_delivery_is_not_checked(self):
        d = make({"src/a.py": "# DL-77\n"})
        self.assertEqual(r1(d), [])

    def test_task_ids_and_other_rules_pass(self):
        d = make({".delivery/config.json": "{}", "src/a.py": "# DL77 and DL-770 and DL-50\n"})
        self.assertEqual(r1(d), [])

    def test_version_rows_are_history(self):
        d = make({".delivery/config.json": "{}", "docs/guides/g.md": "| 0.31.2 | 2026-11-11 | R | DL-91 freed | DL253 |\n"})
        self.assertEqual(r1(d), [])

    def test_tool_checkouts_worktrees_and_state_are_not_scanned(self):
        """DL430: a pinned tool checkout, an agent worktree and the delivery state are not the project's files."""
        cite = "# DL-77\n"
        d = make({".delivery/config.json": "{}", ".delivery/ledger.json": "DL-77", ".dev-standards-tools/x/a.py": cite,
                  ".claude/worktrees/agent-1/a.py": cite})
        self.assertEqual(r1(d), [])


if __name__ == "__main__":
    unittest.main()
