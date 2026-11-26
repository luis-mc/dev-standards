"""DL421: `docs_fold.py note` sets last_verified to today. DL422: `design_system.py visuals` prints missing Proof lines."""
import unittest

from _helpers import *  # noqa
import docs_fold as F
import design_system as DS


def spec_text(body="# T\n", lv="2026-01-01"):
    return f"---\nid: import\ntitle: Import\nversion: 1.3.1\nlast_verified: {lv}\n---\n{body}"


class NoteVerifies(unittest.TestCase):
    def test_note_sets_last_verified_to_today(self):
        d = project({"docs/features/import/spec.md": spec_text()})
        self.assertEqual(F.main(["note", "--root", str(d), "--doc", "features/import", "--task", "X1",
                                 "--change", "minor", "--text", "Changed."]), 0)
        self.assertIn("last_verified: 2026-10-31", r(d, "docs/features/import/spec.md"))
        self.assertIn("version: 1.3.1", r(d, "docs/features/import/spec.md"))

    def test_note_adds_the_key_when_missing(self):
        d = project({"docs/features/import/spec.md": spec_text().replace("last_verified: 2026-01-01\n", "")})
        F.main(["note", "--root", str(d), "--doc", "features/import", "--task", "X1", "--change", "minor", "--text", "C."])
        self.assertIn("last_verified: 2026-10-31", r(d, "docs/features/import/spec.md"))


class ProofHint(unittest.TestCase):
    def test_cited_rule_without_proof_is_named(self):
        d = project({"docs/features/a/spec.md": spec_text("Follows UX-4.\n")})
        self.assertEqual(DS.missing_proofs(d), [("docs/features/a/spec.md", "UX-4")])
        self.assertIn("Proof: UX-4 `", DS.proof_hint(d))

    def test_proof_line_with_existing_test_is_enough(self):
        d = project({"docs/features/a/spec.md": spec_text("Follows UX-4.\n\nProof: UX-4 `tests/ux.test.ts`\n"),
                     "tests/ux.test.ts": ""})
        self.assertEqual(DS.missing_proofs(d), [])
        self.assertEqual(DS.proof_hint(d), "")

    def test_missing_test_file_still_counts(self):
        d = project({"docs/features/a/spec.md": spec_text("Follows CORE-1, proof `tests/none.test.ts`.\n")})
        self.assertEqual(DS.missing_proofs(d), [("docs/features/a/spec.md", "CORE-1")])


if __name__ == "__main__":
    unittest.main()
