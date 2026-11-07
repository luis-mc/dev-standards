"""DL105: the setup failure text names the memory kill first for exit code 137, the lockfile first otherwise."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "templates" / "shared" / "scripts" / "delivery"))
import branch_gate as G  # noqa: E402


class GateTextTests(unittest.TestCase):
    def test_exit_137_prints_memory_sentence_first(self):
        lines = G.setup_failure_lines(137)
        self.assertIn("killed for memory", lines[1])
        self.assertIn("lockfile", lines[2])
        self.assertIn("Never install unfrozen", "\n".join(lines))

    def test_other_exit_code_prints_lockfile_sentence_first(self):
        for code in (1, 2, None):
            lines = G.setup_failure_lines(code)
            self.assertIn("lockfile", lines[1])
            self.assertIn("killed for memory", lines[2])
            self.assertIn("Never install unfrozen", "\n".join(lines))


if __name__ == "__main__":
    unittest.main()
