#!/usr/bin/env python3
"""Decide how much of the suite a CI run covers (DELIVERYSPEC DL-80; CI speed-ups, DS26).

    ci_scope.py [--config FILE] [--event E] [--head-ref R] [--base-ref B]
                [--base REF | --changed-file FILE|- | PATH...] [--github-output] [--json]

Four scopes, from the changed paths and the event:

  full       a release pull request (ready, from a head branch matching `release_pr.head_re` into
             `release_pr.base`), or a change to a `full_files` path (what every workspace reads: the lockfile,
             root manifests and configs): every job runs. Two valves are narrower, both off unless configured:
             `no_test_reads` (globs of files no test reads, e.g. .github/dependabot.yml) never trip it, and
             `package_json` ({"file", "keys", "scripts"}) trips it only when a listed key or a script named by a
             `scripts` glob changed in that file.
  ci-smoke   a change only to `ci_files` (the CI's own scripts and workflows; `docs` may ride along): the CI
             tests, the guard tests and a fixed, named `smoke` set, even on a release pull request.
  rust-release  a release pull request whose code files are all Rust (`rust_release.rust_only` matches each and
             `rust_release.node_inputs` matches none). Optional: it needs a `rust_release` block. Node suites do not
             run for it; the project's CI plan runs only the tests that call Rust builds (how is the project's
             choice). A docs-only release has no code files and stays full.
  affected   everything else (agent branches, fix pushes, the default branch after a merge): only what the
             change reaches. Pick the jobs and areas with area_select.py (`mode`, `areas`).

Order: no diff -> full; a `full_files` match -> full; every non-doc file in `ci_files` -> ci-smoke;
release PR -> rust-release when Rust-only, else full; else affected. Any doubt (no diff) is full.

The project's committed config (default `scripts/delivery/ci-scope.json`; all keys optional):

    {
      "default_branch": "main",
      "release_pr": {"base": "main", "head_re": "^release/.+"},
      "full_files": ["package.json", "pnpm-lock.yaml", ".github", "!.github/workflows"],
      "ci_files": ["scripts/ci", "scripts/delivery", ".github/workflows"],
      "docs": ["docs", "**/*.md", ".claude"],
      "smoke": {"tests": ["scripts/**/*.test.ts"], "e2e": ["apps/web/e2e/smoke.spec.ts"]},
      "rust_release": {"why": "release PR, Rust-only: Node suites skipped",
                       "rust_only": ["crates", "Cargo.toml", "Cargo.lock"], "node_inputs": ["apps", "package.json"]}
    }

Globs are area_select.py's (`**/`, `*`, `?`; a plain path matches everything under it). In `full_files` an entry
that starts with `!` is an exception: a file matching it is not a full file for that rule. With no config the
script exits 2 and a workflow must treat empty outputs as full.

Manual runs (`workflow_dispatch`) on an agent branch plan what the branch brings since the default branch: with no
--base the diff is `origin/<default_branch>...HEAD`, never `HEAD~1` (the branch holds many commits). On the default
branch itself that diff is empty, which is full.

Output (JSON with --json, else key=value lines; --github-output appends them to $GITHUB_OUTPUT): `scope`, `why`,
`ci_changed` (true when a changed file is one of the CI's own, so a mixed change also carries the smoke set),
`smoke_tests`, `smoke_e2e` (space separated).
Exit: 0; 2 unreadable config or git failure. Python 3.8+, standard library only.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from area_select import any_match  # noqa: E402

DEFAULT_CONFIG = "scripts/delivery/ci-scope.json"
EXIT_USAGE = 2


def norm(path: str) -> str:
    return re.sub(r"^\./", "", path.strip().replace("\\", "/"))


def is_full_file(path: str, patterns: list[str], no_reads: list[str] | None = None) -> bool:
    keep = [p for p in patterns if not p.startswith("!")]
    skip = [p[1:] for p in patterns if p.startswith("!")] + list(no_reads or [])
    return any_match(path, keep) and not any_match(path, skip)


# Root package.json fields a build or test can read. Used when `package_json.keys` is not set.
DEFAULT_PACKAGE_KEYS = ["name", "type", "main", "module", "exports", "bin", "engines", "packageManager",
                        "workspaces", "dependencies", "devDependencies", "peerDependencies", "overrides",
                        "resolutions", "pnpm"]


def _scripts(manifest: dict) -> dict:
    s = manifest.get("scripts")
    return s if isinstance(s, dict) else {}


def package_json_counts(old: str | None, new: str | None, rule: dict) -> bool:
    """Does a change of the root package.json make a run full? Only a changed key in `rule["keys"]` (default
    DEFAULT_PACKAGE_KEYS) or an added, removed or changed script whose name matches `rule["scripts"]` (globs;
    default: every script). A side that is missing or not JSON counts: any doubt is full."""
    try:
        a, b = json.loads(old or ""), json.loads(new or "")
    except ValueError:
        return True
    if not isinstance(a, dict) or not isinstance(b, dict):
        return True
    keys = rule["keys"] if "keys" in rule else DEFAULT_PACKAGE_KEYS
    if any(a.get(k) != b.get(k) for k in keys or []):
        return True
    sa, sb = _scripts(a), _scripts(b)
    names = [n for n in set(sa) | set(sb) if sa.get(n) != sb.get(n)]
    patterns = rule["scripts"] if "scripts" in rule else ["*"]
    return any(any_match(n, patterns or []) for n in names)


def is_rust_only(rule: dict, code: list[str]) -> bool:
    only = rule.get("rust_only") or []
    if not only or not code:
        return False
    return all(any_match(f, only) and not any_match(f, rule.get("node_inputs") or []) for f in code)


def is_release_pr(cfg: dict, event: str | None, head_ref: str, base_ref: str) -> bool:
    rel = cfg.get("release_pr") or {}
    if not rel.get("head_re"):
        return False
    return (event == "pull_request" and base_ref == rel.get("base", cfg.get("default_branch", "main"))
            and re.search(rel["head_re"], head_ref or "") is not None)


def decide(cfg: dict, changed: list[str] | None, event: str | None = None,
           head_ref: str = "", base_ref: str = "", read_pair=None) -> dict:
    """`read_pair(path)` -> (old text, new text) of a changed file, for the package.json rule. Without it, or with
    a missing side, a changed package.json counts."""
    smoke = cfg.get("smoke") or {}

    def out(scope: str, why: str, ci_changed: bool = False) -> dict:
        return {"scope": scope, "why": why, "ci_changed": ci_changed,
                "smoke_tests": list(smoke.get("tests") or []), "smoke_e2e": list(smoke.get("e2e") or [])}

    if not changed:
        return out("full", "no diff available")
    files = [norm(f) for f in changed if f.strip()]
    ci = cfg.get("ci_files") or []
    ci_changed = any(any_match(f, ci) for f in files)
    no_reads = cfg.get("no_test_reads") or []
    pkg = cfg.get("package_json") or {}

    def counts(f: str) -> bool:
        # With a `package_json` rule, that file is a valve only for the keys and scripts tests use.
        if pkg.get("file") and f == pkg["file"]:
            old, new = read_pair(f) if read_pair else (None, None)
            return package_json_counts(old, new, pkg)
        return is_full_file(f, cfg.get("full_files") or [], no_reads)

    root = next((f for f in files if counts(f)), None)
    if root:
        return out("full", f"root configuration changed ({root})", ci_changed)
    # Docs, files no test reads, and a package.json change the rule does not count are not code.
    code = [f for f in files if not any_match(f, cfg.get("docs") or []) and not any_match(f, no_reads)
            and f != pkg.get("file")]
    # A change of CI files alone touches no product code: the CI tests and the smoke set prove it, even on a release PR.
    if code and all(any_match(f, ci) for f in code):
        return out("ci-smoke", "only CI scripts and workflows changed", True)
    if is_release_pr(cfg, event, head_ref, base_ref):
        rule = cfg.get("rust_release") or {}
        if is_rust_only(rule, code):
            return out("rust-release", rule.get("why") or "release PR, Rust-only: Node suites skipped", ci_changed)
        return out("full", "release pull request", ci_changed)
    return out("affected", "what the change reaches", ci_changed)


def changed_from_git(base: str) -> list[str]:
    # --no-renames: a moved file counts at its old and its new path. -z: real names, no quoting.
    flags = ["git", "diff", "--name-only", "--no-renames", "-z"]
    r = subprocess.run([*flags, f"{base}...HEAD"], capture_output=True)
    if r.returncode != 0:
        r = subprocess.run([*flags, base, "HEAD"], capture_output=True)
    if r.returncode != 0:
        raise OSError(f"git diff {base} failed: {r.stderr.decode('utf-8', 'replace').strip()}")
    return [p for p in r.stdout.decode("utf-8", "replace").split("\0") if p.strip()]


def git_pair(base: str):
    """read_pair for a diff against `base`: the file at the merge base and at HEAD (None when git cannot say)."""
    mb = subprocess.run(["git", "merge-base", base, "HEAD"], capture_output=True, text=True)
    old_ref = mb.stdout.strip() if mb.returncode == 0 and mb.stdout.strip() else base

    def show(ref: str, path: str):
        r = subprocess.run(["git", "show", f"{ref}:{path}"], capture_output=True, text=True)
        return r.stdout if r.returncode == 0 else None

    return lambda path: (show(old_ref, path), show("HEAD", path))


def lines(res: dict) -> list[str]:
    return [f"scope={res['scope']}", f"why={res['why']}", f"ci_changed={'true' if res['ci_changed'] else 'false'}",
            f"smoke_tests={' '.join(res['smoke_tests'])}", f"smoke_e2e={' '.join(res['smoke_e2e'])}"]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="how much of the suite does this CI run cover")
    p.add_argument("--config", default=DEFAULT_CONFIG)
    p.add_argument("--event", default=os.environ.get("GITHUB_EVENT_NAME"))
    p.add_argument("--head-ref", default=os.environ.get("GITHUB_HEAD_REF", ""))
    p.add_argument("--base-ref", default=os.environ.get("GITHUB_BASE_REF", ""))
    p.add_argument("--base")
    p.add_argument("--changed-file")
    p.add_argument("--github-output", action="store_true")
    p.add_argument("--json", action="store_true")
    p.add_argument("paths", nargs="*")
    a = p.parse_args(argv)
    try:
        cfg = json.loads(Path(a.config).read_text(encoding="utf-8"))
        if not isinstance(cfg, dict):
            raise ValueError(f"{a.config}: expected an object")
        changed = list(a.paths)
        if a.changed_file:
            text = sys.stdin.read() if a.changed_file == "-" else Path(a.changed_file).read_text(encoding="utf-8")
            changed += text.splitlines()
        base = a.base
        if not base and not changed and a.event == "workflow_dispatch":
            base = f"origin/{cfg.get('default_branch', 'main')}"  # the plan-diff rule for manual runs
        if base:
            changed += changed_from_git(base)
    except (OSError, ValueError) as e:
        print(f"ci_scope: {e}", file=sys.stderr)
        return EXIT_USAGE
    res = decide(cfg, changed, a.event, a.head_ref, a.base_ref, git_pair(base) if base else None)
    print(json.dumps(res, indent=1) if a.json else "\n".join(lines(res)))
    target = os.environ.get("GITHUB_OUTPUT")
    if a.github_output and target:
        with open(target, "a", encoding="utf-8") as fh:
            fh.write("\n".join(lines(res)) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
