---
name: feature-spec-new
description: Write a new feature spec to the documentation standard, or revise one. Use when the user wants to document, spec or describe a feature in docs/features, add a feature folder, or turn a feature artifact's decided work into a lasting spec. Creates docs/features/<feature>/spec.md from the template with front matter, requirement IDs, a Mermaid flow and the test table.
model: opus
effort: medium
---

# Feature spec — new

Produces `docs/features/<feature>/spec.md` from `templates/feature-spec.md` (DOCSPEC §4). Read the template and §4 before writing.

## Loop

1. Read the code the feature touches, and the feature's artifact in the record (`record_dir`) if there is one. Findings and decided choices are promoted into the spec (R4.10); copy decided entries of its `decisions.json` into section 10.
2. Pick `apps` and `topics` from `docs/docs.json`. Ask the owner only when the lists do not cover the feature.
3. Copy the template into `docs/features/<feature>/spec.md` (folder name: lower-case words with hyphens). Set `id` to the folder name, `status: proposed` (or `building`), `version: 0.1.0`, `code:` globs, `last_verified:` today.
4. Write sections 1 to 4 for every reader: one paragraph, why, a Mermaid flow and the steps in words, screens and states (images in `images/` with alt text, rules cited by design-system ID, never written here). Then 5 to 12 for engineers. Delete a section that does not apply.
5. Every requirement gets an ID and a test in section 9. Mark unbuilt parts `NOT YET IMPLEMENTED`.
6. Run `docs_index.py build` then `docs_check.py`; fix every error.

Never write `version` or the Versions table: the release fold does. For later changes use `docs-note`.
