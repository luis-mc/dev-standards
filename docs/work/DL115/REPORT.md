# DL115 report: CI tool cache

## What changed
- New `claude/plugins/delivery/templates/shared/scripts/delivery/ci_tool.py` (stdlib, Python 3.10+).
- The gitleaks step in the ts, go, rust and dotnet `ci.yml` templates and in `.github/workflows/secret-scan.yml` now calls it, then runs the printed binary. Flags, config and `--redact` are unchanged. The templates keep the `::error::` when tools.json has no linux_x64 pin. The repo workflow now reads the version and pin from the shipped tools.json (the inline copy is gone).
- `templates/runner-pool/compose.yaml`: named volume `ci-tools` mounted at `/ci-tools`, `CI_TOOLS_DIR=/ci-tools`. The agents volume holds `/agents` only; job home folders are not persistent, so the cache needed its own volume.
- Change note `docs/architecture/changes/DL115-ci-tool-cache.md`.
- Test `claude/plugins/delivery/tests/test_dl115_ci_tool.py` (9 tests, local http.server).

## Exact behaviour (for the spec)
- `ci_tool.py fetch <url> --sha256 <hex> --name <tool>/<version>/<file>`: prints only the absolute path of the verified file.
- `ci_tool.py gitleaks [--platform linux_x64|linux_arm64|darwin_x64|darwin_arm64|windows_x64]`: reads `tools.json` next to the script (default platform: the current one), fetches `gitleaks_<version>_<platform>.tar.gz` (`.zip` for windows) from the GitHub release through the same cache, extracts the binary once to `<dir>/gitleaks/<version>/<platform>-gitleaks[.exe]`, prints its path.
- Cache dir: `CI_TOOLS_DIR`, else `C:/ci-tools` on Windows, `~/.cache/ci-tools` elsewhere. Layout `<dir>/<tool>/<version>/<file>`. If `CI_TOOLS_DIR` is not writable, one stderr warning and the default dir is used.
- A cached file is used only if its sha256 matches; otherwise deleted and fetched again.
- 5 attempts, wait 10 s, 20 s, 30 s, 40 s (`CI_TOOL_RETRY_DELAY` sets the base seconds), 20 s timeout, any error retried. Download to `<file>.<pid>.partial`, verify, `os.replace`. The partial file is always removed.
- Exit 0 path printed; 1 failure; 2 usage error (bad args, `--name` not three parts).
- Stderr on failure: `ci_tool: cannot fetch <url> after 5 attempts: <ErrorType>: <message>`; a wrong checksum ends the same way with `checksum mismatch: expected <hex>, got <hex>` as the last error (checked after every download, so it is also retried 5 times).
- No pin: `ci_tool: <tools.json> has no pinned SHA-256 for gitleaks on <platform>. Run: python3 scripts/delivery/tools_pin.py gitleaks <version>`.

## Needs follow-up (not my files)
- The pool Dockerfile does not create `/ci-tools`. Jobs run as per-agent users, and a new named volume is root-owned, so they cannot write it; ci_tool then warns and falls back to `~/.cache/ci-tools`. Add `mkdir -p /ci-tools && chmod 1777 /ci-tools` to the Dockerfile to make the volume usable.
- `docs_check.py` M1 errors for `features/delivery` and `features/delivery-speed`: expected until the orchestrator writes the spec text. G1 (decisions.md stale) is a generated file I did not touch. `.github/workflows/secret-scan.yml` is unmapped (warning).
- `ci_areas.py --branch-advice` answered "unreadable diff" (no gh here): all areas advised. I ran the delivery ci and pool tests instead.
- Not tested live: the real download from GitHub and the Windows zip path.

## Tests
- `python3 -m unittest claude/plugins/delivery/tests/test_dl115_ci_tool.py`: 9 OK.
- `python3 -m unittest discover -s claude/plugins/delivery/tests -p "test_ci_*.py"`: 75 OK.
- `... -p test_runner_pool.py`: 149 OK.
- YAML parse of the 5 edited workflows: OK.
- `tools/test_delivery_ci.py`, `tools/test_ci_speedups.py`: no unittest tests found (need pytest, not installed).
- `python3 claude/plugins/docs/scripts/docs_check.py`: 3 errors, 1 warning, explained above.

