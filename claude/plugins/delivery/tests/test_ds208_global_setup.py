"""DS208: the Rust global-setup template exists, and the ts unit job sets up cargo only on the Rust track."""
import unittest
from pathlib import Path

TEMPLATES = Path(__file__).resolve().parents[1] / "templates"
SETUP = TEMPLATES / "rust" / "test" / "rust-binaries.global-setup.ts"
CI = TEMPLATES / "ts" / ".github" / "workflows" / "ci.yml"


class GlobalSetup(unittest.TestCase):
    def test_template_builds_with_cargo(self):
        text = SETUP.read_text(encoding="utf-8")
        self.assertIn("'build', '--locked', '-p'", text)
        for word in ("RUST_TEST_CRATES", "CARGO_TARGET_DIR", ".exe", "_BIN"):
            self.assertIn(word, text)

    def test_unit_job_sets_up_cargo_on_rust_track_only(self):
        lines = CI.read_text(encoding="utf-8").splitlines()
        idx = [i for i, l in enumerate(lines) if "Install the pinned Rust toolchain" in l]
        self.assertEqual(len(idx), 1)
        self.assertIn("hashFiles('scripts/delivery/rust_ci.py') != ''", lines[idx[0] + 1])
        unit = next(i for i, l in enumerate(lines) if l.strip() == "- name: Unit tests")
        self.assertLess(idx[0], unit)
        job = max(i for i, l in enumerate(lines[:idx[0]]) if l.startswith("  verify:"))
        self.assertTrue(job < idx[0])

    def test_path_filters_unchanged(self):
        self.assertIn("'**/*.rs'", CI.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
