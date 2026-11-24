"""DL410 (R5.68): rerun_tests.py reads failed Cypress specs and reruns them with one `--spec a,b`."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "templates" / "shared" / "scripts" / "delivery"))
import rerun_tests as rt  # noqa: E402

LOG = """\
  Running:  cypress/e2e/a.cy.js                                                         (1 of 3)
    1 passing (1s)
  Running:  cypress/e2e/b.cy.js                                                         (2 of 3)
    1 passing
    2 failing
  Running:  cypress/e2e/c.cy.js                                                         (3 of 3)
    1 failing

====================================================================================================
  (Run Finished)

       Spec                                              Tests  Passing  Failing  Pending  Skipped
  ┌────────────────────────────────────────────────────────────────────────────────────────────────┐
  │ ✔  cypress/e2e/a.cy.js                      00:01        1        1        -        -        - │
  ├────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ ✖  cypress/e2e/b.cy.js                      00:03        3        1        2        -        - │
  ├────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ ✖  cypress/e2e/c.cy.js                      00:02        1        -        1        -        - │
  └────────────────────────────────────────────────────────────────────────────────────────────────┘
    ✖  2 of 3 failed (67%)
"""
GREEN = LOG.split("Running:  cypress/e2e/b")[0] + "\n  │ ✔  All specs passed!   00:01  1  1  -  -  - │\n"
WANT = ["cypress/e2e/b.cy.js", "cypress/e2e/c.cy.js"]


def files(text):
    return [f["file"] for f in rt.parse_failures("cypress", text)]


class Cypress(unittest.TestCase):
    def test_two_failing_in_order(self):
        self.assertEqual(files(LOG), WANT)

    def test_ansi(self):
        col = LOG.replace("✖", "\x1b[31m✖\x1b[0m").replace("cypress/e2e/b.cy.js  ", "\x1b[31mcypress/e2e/b.cy.js\x1b[0m  ")
        self.assertEqual(files(col), WANT)

    def test_running_headers_without_table(self):
        self.assertEqual(files(LOG.split("(Run Finished)")[0]), WANT)

    def test_all_passing(self):
        with self.assertRaises(rt.Unreadable):
            rt.parse_failures("cypress", GREEN)

    def test_junit(self):
        xml = ('<testsuites><testsuite name="Root" file="cypress/e2e/b.cy.js"><testcase name="x"><failure/></testcase></testsuite>'
               '<testsuite name="Root" file="cypress/e2e/a.cy.js"><testcase name="y"/></testsuite></testsuites>')
        self.assertEqual(files(xml), ["cypress/e2e/b.cy.js"])

    def test_args_one_spec(self):
        self.assertEqual(rt.build_invocations("cypress", rt.parse_failures("cypress", LOG)),
                         [["--spec", "cypress/e2e/b.cy.js,cypress/e2e/c.cy.js"]])

    def test_decide_narrow(self):
        res = rt.decide("cypress", "e2e", {"conclusion": "failure", "log": LOG})
        self.assertEqual((res["mode"], res["invocations"]), ("narrow", [["--spec", ",".join(WANT)]]))


if __name__ == "__main__":
    unittest.main()
