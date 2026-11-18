# DU13 report

Default install and update windows added to the design-system starter.

## Files
- `claude/plugins/docs/templates/design-system/next-version/ux-rules.md`: UX-62 to UX-65.
- `.../next-version/components.md`: components 35 (Update window) and 36 (Installer artwork).
- `.../next-version/CHANGES.md`: C14.
- `.../components/windows-installer/`: `make-installer-art.ts`, `installer-art.wxs`, `update-window.ps1` (with `-LayoutCheck`), `README.md`.
- `claude/plugins/docs/skills/design-system-setup/SKILL.md`: names the new default.
- `claude/plugins/docs/scripts/gallery_draw.py`: two drawings (outside the owns list). The existing gallery test needs a drawing per starter component, so it failed without them.
- `claude/plugins/docs/tests/test_du13_install_update.py`.
- `docs/features/docs/spec.md`: R5.20 and a test-table row. Change notes: `docs/features/docs/changes/DU13.md`, `docs/architecture/changes/DU13-install-update-windows.md`.

## Tests
- `python3 -I -m unittest discover -s claude/plugins/docs/tests -p "test_du13*.py"`: 9 tests OK (node ran the bitmap script; BMP sizes and colours checked).
- `test_design_system.py`: 38 OK. `test_components.py`: 20 OK. `test_du4.py`: 15 OK.
- `python3 claude/plugins/docs/scripts/docs_check.py`: 0 errors, 0 warnings.

Not run: the PowerShell script on Windows (static checks only).

## Branch head
Written in the final push; see `git rev-parse origin/DU13-install-update-windows`.

READY
