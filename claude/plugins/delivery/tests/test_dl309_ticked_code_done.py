"""DL309: the default agent_ci marker accepts a bullet and a ticked box before CODE DONE."""
import re
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "templates" / "shared" / "scripts" / "delivery"))

import agent_ci as ac  # noqa: E402


def hit(text: str) -> bool:
    return re.search(ac.DEFAULTS["marker"], text, re.MULTILINE) is not None


class TickedCodeDone(unittest.TestCase):
    def test_matches(self):
        for line in ("CODE DONE", "  CODE DONE", "- CODE DONE", "* CODE DONE", "+ CODE DONE", "1. CODE DONE",
                     "- [x] CODE DONE", "- [X] CODE DONE", "* [x] CODE DONE", "1. [x] CODE DONE"):
            with self.subTest(line=line):
                self.assertTrue(hit("# Report\n" + line + "\nREADY"))

    def test_no_match(self):
        for line in ("- [ ] CODE DONE", "* [ ] CODE DONE", "not CODE DONE yet", "when CODE DONE is written",
                     "- [x] CODE DONEX", "CODE  DONE"):
            with self.subTest(line=line):
                self.assertFalse(hit("# Report\n" + line + "\n"))


if __name__ == "__main__":
    unittest.main()
