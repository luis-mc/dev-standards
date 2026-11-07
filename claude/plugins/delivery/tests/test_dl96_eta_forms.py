"""DL97: DL-31 accepts an assumed start named as such and ignores past durations."""
import unittest

from _helpers import make_root  # noqa: F401
import hook_stop as S


def keys(text):
    return [k for k, _ in S.check_eta_text(text) if k.startswith("DL-31:eta")]


class EtaFormTests(unittest.TestCase):
    def test_assumed_start_form_accepted(self):
        self.assertEqual(keys("ETA ~16:40 if you approve the plan by 15:00."), [])
        self.assertEqual(keys("Ready ~16:40 if the owner pushes by 15:30"), [])

    def test_plain_clock_without_dependency_still_refused(self):
        self.assertTrue(keys("ETA 16:40."))

    def test_past_durations_are_facts(self):
        self.assertEqual(keys("The import ran at 512 MiB for about 10 hours."), [])
        self.assertEqual(keys("The first build took 3 hours."), [])
        self.assertEqual(keys("It used about 2 hours of CI."), [])

    def test_forecast_still_flagged(self):
        self.assertTrue(keys("It will be ready in about 5 minutes."))

    def test_message_shows_forms(self):
        msg = S.check_eta_text("ETA 16:40.")[0][1]
        self.assertIn("if you approve the plan by 15:00", msg)
        self.assertIn("took 3 hours", msg)


if __name__ == "__main__":
    unittest.main()
