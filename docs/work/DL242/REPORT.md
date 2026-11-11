DL242 report

Base check: `--sync-workflow` exists. The brief's path claude/plugins/delivery/scripts/artifact_prune.py does not exist; the script is claude/plugins/delivery/templates/shared/scripts/delivery/artifact_prune.py and that file was changed. The brief's `owns` list has the wrong path; the real path is in the diff.

What changed
- artifact_prune.py: `--sync-workflow` picks the list from the config (`artifact_prune.workflows`, wins), else the workflow file's own list, else the default. It prints `workflow list from: config|existing file|default` before `synced`/`unchanged`. A missing file is created from the shipped template (only when the script runs from the plugin; in a project it errors).
- tests/test_dl242_prune_keep_list.py (new, 5 tests); tests/test_dl122_prune_workflow_list.py updated for the new source line.
- Spec R5.33, feature note docs/features/delivery/changes/DL242.md, change note docs/architecture/changes/DL242-prune-keep-workflow-list.md.

Tests
- python3 -m unittest on test_dl242_prune_keep_list, test_dl122_prune_workflow_list, test_dl121_port_fixes, test_dl150_install_sync, test_dl227_install_peer_fixes: all OK.
- python3 tools/test_delivery_ci.py --no-mutants: 78 passed, 0 failed.
- docs_check: only G1 (decisions.md stale, generated, not mine) and W1 (this report) remain.
- spec-lint.yml areas=delivery, three dispatches, all ended `cancelled`, none by a test failure:
  - run 43086403829, 43086822820: setup preflight, runner plan, area mapping, train cleanup, change notes ok; branch gate, CI scripts, artifact pruning, packaged smoke, ledger jobs cancelled mid-run (after ~1 min); docs check failed on G1/W1 only; aggregate job failed because of the cancels.
  - run 43087238318: docs check failed (G1/W1), every other job cancelled.
  - Sibling branches' dispatches were cancelled in the same window. The cancel is not from this change and not from the workflow's concurrency rule (cancel-in-progress is for pull requests only). No job was left running.

Follow-ups
- Re-run `gh workflow run spec-lint.yml --ref DL242-prune-keep-workflow-list -f areas=delivery` when no sibling runs are active.
- The installer rewrites the workflow from the template before it syncs; the project's list then survives only through the installer's 3-way merge. If that merge takes the template line, "existing file" yields the default. Check this in a later task.

Branch head SHA: see `git rev-parse origin/DL242-prune-keep-workflow-list`.

NOT READY
