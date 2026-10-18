#!/usr/bin/env python3
"""Keep only the newest GitHub Actions artifact of each name.

STACKSPEC 13.1 "Build artifacts": outputs a workflow uploads (an installer, a
bundle, a test report) are billed for storage, so the platform keeps only the
newest artifact of each name. This script lists the repository's Actions
artifacts (`repos/{repo}/actions/artifacts`), ignores the expired ones, groups
the rest by `name`, keeps the newest `--keep` of each name (by `created_at`, then
`id`, both descending) and deletes the others. It touches nothing else: not
releases, release assets, caches or branches.

Listing uses `gh api --paginate`, which prints one JSON document per page,
back to back. The output is read as a stream of JSON values (objects with an
`artifacts` list, or bare lists), so one page, many pages and the concatenated
form all parse the same way.

A deletion that answers 404 means the artifact is already gone (a concurrent
prune, or it expired meanwhile): not a failure. Any other failed deletion is
reported and makes the exit code 1; the remaining deletions are still tried.

Exit codes (shared by the delivery scripts): 0 done, 1 a deletion failed,
2 usage error or `gh` failed to list. It never exits 0 when it could not decide.

Python 3.11+, standard library only; `gh` is the one external tool.
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import argparse
import json
import os
import re
import shutil
import subprocess
import urllib.request
import urllib.error
from datetime import datetime, timezone

REPO_RE = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
NOT_FOUND_RE = re.compile(r"\b404\b|not found", re.IGNORECASE)


class GhError(Exception):
    pass


class GhResult:
    def __init__(self, returncode: int, stdout: str, stderr: str) -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def rest_call(args: list[str], timeout: int) -> GhResult:
    """The `gh` calls this script makes, over the REST API with GH_TOKEN, for a runner without gh:
    `api [--paginate] PATH` (pages printed one JSON document each, as gh does) and
    `api --method DELETE PATH`. Anything else (repo view) is not supported: pass --repo."""
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token or not args or args[0] != "api":
        return GhResult(1, "", "gh is not on PATH and the REST fallback needs GH_TOKEN and an api call")
    method = "DELETE" if "DELETE" in args else "GET"
    url = "https://api.github.com/" + args[-1]
    out: list[str] = []
    while url:
        req = urllib.request.Request(url, method=method, headers={
            "Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "artifact-prune"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                out.append(resp.read().decode("utf-8"))
                link = resp.headers.get("Link") or ""
        except urllib.error.HTTPError as exc:
            return GhResult(1, "", f"HTTP {exc.code} {exc.reason}")
        except (OSError, ValueError) as exc:
            return GhResult(1, "", f"could not call the GitHub API: {exc}")
        nxt = re.search(r'<([^>]+)>;\s*rel="next"', link)
        url = nxt.group(1) if nxt and "--paginate" in args else ""
    return GhResult(0, chr(10).join(out), "")


def run_gh(args: list[str], timeout: int = 300) -> GhResult:
    """Run `gh` with an argument list (never a shell string)."""
    # The resolved path, so Windows finds gh whatever its extension.
    if shutil.which("gh") is None:
        return rest_call(args, timeout)
    gh = shutil.which("gh") or "gh"
    try:
        proc = subprocess.run(
            [gh, *args], capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise GhError(f"could not run gh: {exc}") from exc
    return GhResult(proc.returncode, proc.stdout or "", proc.stderr or "")


def parse_json_stream(text: str) -> list[object]:
    """Every JSON value in `text`, however the pages are joined (none, spaces, newlines)."""
    decoder = json.JSONDecoder()
    values: list[object] = []
    pos, end = 0, len(text)
    while True:
        while pos < end and text[pos].isspace():
            pos += 1
        if pos >= end:
            return values
        try:
            value, pos = decoder.raw_decode(text, pos)
        except json.JSONDecodeError as exc:
            raise GhError(f"gh returned invalid JSON near offset {pos}: {exc.msg}") from exc
        values.append(value)


def extract_artifacts(values: list[object]) -> list[dict]:
    """Artifact objects from every page: `{"artifacts": [...]}` or a bare list."""
    found: list[dict] = []
    for value in values:
        if isinstance(value, dict):
            items = value.get("artifacts")
            if not isinstance(items, list):
                raise GhError("a page from gh has no `artifacts` list")
        elif isinstance(value, list):
            items = value
        else:
            raise GhError("a page from gh is neither an object nor a list")
        found.extend(a for a in items if isinstance(a, dict))
    return found


def list_artifacts(repo: str) -> list[dict]:
    res = run_gh(["api", "--paginate", f"repos/{repo}/actions/artifacts?per_page=100"])
    if res.returncode != 0:
        raise GhError(f"gh api (list artifacts) failed ({res.returncode}): "
                      f"{(res.stderr or res.stdout).strip()[:300]}")
    return extract_artifacts(parse_json_stream(res.stdout))


def resolve_repo(arg: str | None) -> str:
    repo = arg or os.environ.get("GITHUB_REPOSITORY")
    if not repo:
        res = run_gh(["repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"],
                     timeout=60)
        if res.returncode != 0:
            raise GhError("no repository: pass --repo OWNER/NAME or set GITHUB_REPOSITORY "
                          f"({(res.stderr or res.stdout).strip()[:200]})")
        repo = res.stdout.strip()
    if not REPO_RE.fullmatch(repo):
        raise GhError(f"{repo!r} is not OWNER/NAME")
    return repo


def parse_time(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def plan(artifacts: list[dict], keep: int) -> tuple[dict[str, dict], list[str]]:
    """Group live artifacts by name and split each group into keep and delete.

    Returns ({name: {"keep": [artifact], "delete": [artifact]}}, warnings).
    An artifact with no usable id, name or created_at is left alone: with any
    doubt about its age it is never a deletion candidate.
    """
    groups: dict[str, list[tuple[datetime, int, dict]]] = {}
    warnings: list[str] = []
    for art in artifacts:
        if art.get("expired") is True:
            continue
        name, ident, created = art.get("name"), art.get("id"), parse_time(art.get("created_at"))
        if (not isinstance(name, str) or not name or isinstance(ident, bool)
                or not isinstance(ident, int) or created is None):
            warnings.append(f"skipped an artifact without a usable name, id or created_at: "
                            f"{json.dumps(art, sort_keys=True)[:120]}")
            continue
        groups.setdefault(name, []).append((created, ident, art))
    result: dict[str, dict] = {}
    for name in sorted(groups):
        ordered = sorted(groups[name], key=lambda t: (t[0], t[1]), reverse=True)
        result[name] = {"keep": [t[2] for t in ordered[:keep]],
                        "delete": [t[2] for t in ordered[keep:]]}
    return result, warnings


def delete_artifact(repo: str, ident: int) -> str:
    """'deleted', 'gone' (404) or 'failed: <why>'."""
    try:
        res = run_gh(["api", "--method", "DELETE", f"repos/{repo}/actions/artifacts/{ident}"],
                     timeout=120)
    except GhError as exc:
        return f"failed: {exc}"
    if res.returncode == 0:
        return "deleted"
    text = (res.stderr or res.stdout).strip()
    if NOT_FOUND_RE.search(text):
        return "gone"
    return f"failed: {text[:200] or 'gh exited ' + str(res.returncode)}"


def size_of(art: dict) -> int:
    size = art.get("size_in_bytes")
    return size if isinstance(size, int) and not isinstance(size, bool) and size > 0 else 0


def human(n: int) -> str:
    value = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{n} B" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{n} B"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Keep only the newest GitHub Actions artifact of each name (STACKSPEC 13.1).")
    ap.add_argument("--repo", help="OWNER/NAME (default: GITHUB_REPOSITORY, then the current "
                                   "repository)")
    ap.add_argument("--keep", type=int, default=1,
                    help="how many of each name to keep, newest first (default 1)")
    ap.add_argument("--dry-run", action="store_true", help="delete nothing, print the plan")
    ap.add_argument("--json", action="store_true", dest="as_json",
                    help="print one JSON document instead of rows")
    args = ap.parse_args(argv)

    if args.keep < 1:
        print("artifact_prune: --keep must be at least 1 (keeping 0 would delete every "
              "artifact)", file=sys.stderr)
        return 2
    if shutil.which("gh") is None and not (os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")):
        print("artifact_prune: the GitHub CLI (gh) is not installed or not on PATH, and neither "
              "GH_TOKEN nor GITHUB_TOKEN is set (the REST fallback needs one of them)",
              file=sys.stderr)
        return 2
    try:
        repo = resolve_repo(args.repo)
        artifacts = list_artifacts(repo)
    except GhError as exc:
        print(f"artifact_prune: {exc}", file=sys.stderr)
        return 2

    groups, warnings = plan(artifacts, args.keep)
    for warning in warnings:
        print(f"artifact_prune: warning: {warning}", file=sys.stderr)

    report: list[dict] = []
    failures = 0
    for name, g in groups.items():
        row = {"name": name, "kept": [a["id"] for a in g["keep"]],
               "deleted": [], "already_gone": [], "failed": [], "errors": [],
               "would_delete": [a["id"] for a in g["delete"]] if args.dry_run else [],
               "bytes_freed": 0}
        if not args.dry_run:
            for art in g["delete"]:
                outcome = delete_artifact(repo, art["id"])
                if outcome == "deleted":
                    row["deleted"].append(art["id"])
                    row["bytes_freed"] += size_of(art)
                elif outcome == "gone":
                    row["already_gone"].append(art["id"])
                else:
                    row["failed"].append(art["id"])
                    row["errors"].append(f"{art['id']}: {outcome}")
                    failures += 1
        else:
            row["bytes_freed"] = sum(size_of(a) for a in g["delete"])
        report.append(row)

    if args.as_json:
        print(json.dumps({"repo": repo, "keep": args.keep, "dry_run": args.dry_run,
                          "failed": failures, "artifacts": report}, indent=2))
    else:
        verb = "would free" if args.dry_run else "freed"
        for row in report:
            n_del = len(row["would_delete"]) if args.dry_run else len(row["deleted"])
            label = "would delete" if args.dry_run else "deleted"
            extra = ""
            if row["already_gone"]:
                extra += f", {len(row['already_gone'])} already gone"
            if row["failed"]:
                extra += f", {len(row['failed'])} FAILED"
            kept = ", ".join(str(i) for i in row["kept"])
            print(f"{row['name']}: kept {kept}; {label} {n_del}{extra}; "
                  f"{verb} {human(row['bytes_freed'])}")
        if not report:
            print("artifact_prune: no live artifacts")
        for row in report:
            for err in row["errors"]:
                print(f"artifact_prune: could not delete {row['name']} {err}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
