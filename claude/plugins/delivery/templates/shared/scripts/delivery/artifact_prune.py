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

Held names (CIR10 W5): `--hold NAME --hold-workflow FILE` keeps EVERY live artifact of NAME
while the newest run of that workflow (for example `package.yml`) has not succeeded: it
failed, was cancelled, is still running, or its state could not be read. A failed publish
then still finds its installers when "re-run failed jobs" is used. Once the newest run
succeeds, the hold ends and the normal keep-the-newest rule applies again.

Groups (opt-in): `.delivery/config.json` (or `--config FILE`) may hold an `artifact_prune` section.
Without it, nothing below applies and the behaviour is the one above.

    {"artifact_prune": {"groups": [{
        "pattern": "(installer-[a-z]+)-[0-9a-f]{12}",   one regex, one capture group: the group name
        "keep": 0,                                      newest to keep per group (default: --keep)
        "protect_pr_heads": {"head_prefix": "release/", "base": "main"},
        "hold_workflow": "installers.yml"}],
      "min_age_seconds": 3600}}

An artifact whose name matches `pattern` (a full match) is grouped by the captured text instead of its
own name, so builds named by a hash are pruned by kind. Of such an artifact beyond `keep`, these stay:
one of a run still queued or running; one younger than `min_age_seconds` (default 3600); one built from
the head commit of an open pull request whose head branch starts with `head_prefix` and whose base is
`base` (`protect_pr_heads`); and every artifact of the group while the newest run of `hold_workflow`
for any head commit failed, was cancelled or timed out in the last 24 hours (a re-run reuses them).
The extra API calls are made only for the options a group sets. Any failure to read them stops the
prune with exit 2, so it never decides without knowing.

Workflow list (DL122): GitHub Actions reads `on.workflow_run.workflows` before any step runs, so it cannot
be dynamic. The list is project-owned instead, in the same section:

    {"artifact_prune": {"workflows": ["CI", "Package", "Installers"]}}

Default when unset: `["CI", "Package"]`, the template's own list. `--print-workflows` prints the list, one name
per line. `--sync-workflow [FILE]` (default `.github/workflows/artifact-prune.yml`) rewrites the `workflows:`
line of that file and prints the source of the list (`config`, `existing file` or `default`), then `synced` or
`unchanged`. With no `artifact_prune.workflows` in the config, the file's own list stays; the default is written
only when the file is new or has no list; `--check-workflow [FILE]` changes nothing and
exits 1 when the line differs. Run `--sync-workflow` after `delivery_ci_install update`, which restores the
template's line. The daily sweep prunes any workflow's artifacts meanwhile. The config file is in
`.delivery/`, which a project tracks like its other delivery config; it is the file this script already reads.

Retries: transient failures (HTTP 5xx, 429, rate limits, timeouts, dropped connections) are retried
with exponential backoff and jitter, for every listing and deletion; deletions are paced apart.
`ARTIFACT_PRUNE_BACKOFF` (seconds, default 2) scales the backoff and `ARTIFACT_PRUNE_PAUSE` (seconds,
default 0.3) the pause between deletions; tests set both to 0.

A deletion that answers 404 (or 410) means the artifact is already gone (a concurrent
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
import random
import subprocess
import time
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timezone

REPO_RE = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
NOT_FOUND_RE = re.compile(r"\b404\b|\b410\b|not found|\bgone\b", re.IGNORECASE)
TRANSIENT_RE = re.compile(
    r"\b(429|500|502|503|504)\b|rate limit|abuse detection|secondary rate|try again|"
    r"timed out|timeout|connection (reset|refused)|\bEOF\b|temporar|unavailable|"
    r"bad gateway|internal server error|TLS handshake|no such host",
    re.IGNORECASE)
MIN_AGE_SECONDS = 3600
BUSY_STATUSES = ("queued", "in_progress", "waiting", "requested", "pending")
HOLD_CONCLUSIONS = ("failure", "cancelled", "timed_out")
HOLD_WINDOW_SECONDS = 24 * 3600
ATTEMPTS = 5
BACKOFF_CAP = 60.0
DEFAULT_CONFIG = ".delivery/config.json"
DEFAULT_WORKFLOWS = ["CI", "Package"]
DEFAULT_WORKFLOW_FILE = ".github/workflows/artifact-prune.yml"
WORKFLOWS_LINE_RE = re.compile(r"^(?P<indent>[ \t]*)workflows:[ \t]*\[[^\]\r\n]*\][ \t]*(?:#[^\r\n]*)?(?=\r?$)", re.MULTILINE)


def _env_float(name: str, default: float) -> float:
    try:
        return max(0.0, float(os.environ.get(name, default)))
    except ValueError:
        return default


class GhError(Exception):
    pass


class GhResult:
    def __init__(self, returncode: int, stdout: str, stderr: str) -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def allowed_api_host() -> str:
    """The one host the REST fallback may send the token to: api.github.com, or the host of
    GITHUB_API_URL (GitHub Enterprise)."""
    custom = os.environ.get("GITHUB_API_URL")
    if custom:
        host = urllib.parse.urlparse(custom).hostname
        if host:
            return host.lower()
    return "api.github.com"


def next_url_ok(url: str) -> bool:
    """True when a `Link: next` URL is https and on the allowed API host."""
    parts = urllib.parse.urlparse(url)
    return parts.scheme == "https" and (parts.hostname or "").lower() == allowed_api_host()


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
        if url and not next_url_ok(url):
            print(f"warning: refused the next-page URL (not https on {allowed_api_host()}); "
                  "stopped paging so the token is not sent there", file=sys.stderr)
            url = ""
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


def run_gh_retry(args: list[str], timeout: int = 300, attempts: int = ATTEMPTS) -> GhResult:
    """`run_gh`, retried with backoff while the failure looks transient.

    A non-transient failure (404, 403 without a rate limit, bad arguments) is returned at once;
    the last result is returned when the attempts run out."""
    base = _env_float("ARTIFACT_PRUNE_BACKOFF", 2.0)
    res = GhResult(1, "", "")
    for attempt in range(1, attempts + 1):
        try:
            res = run_gh(args, timeout=timeout)
        except GhError as exc:
            if attempt == attempts:
                raise
            res = GhResult(1, "", f"timed out or could not run: {exc}")
        if res.returncode == 0:
            return res
        text = f"{res.stderr}\n{res.stdout}"
        if attempt == attempts or not TRANSIENT_RE.search(text) or NOT_FOUND_RE.search(text):
            return res
        delay = min(BACKOFF_CAP, base * (2 ** (attempt - 1))) * (0.5 + random.random())
        print(f"artifact_prune: transient gh failure (attempt {attempt}/{attempts}), "
              f"retrying in {delay:.1f}s: {text.strip()[:120]}", file=sys.stderr)
        time.sleep(delay)
    return res


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
    res = run_gh_retry(["api", "--paginate", f"repos/{repo}/actions/artifacts?per_page=100"])
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


def newest_run_succeeded(repo: str, workflow: str) -> bool:
    """True only when the newest run of `workflow` finished with `success`.

    No run, a run in progress, any other conclusion, or any error reading it: False (hold)."""
    try:
        res = run_gh_retry(["api", f"repos/{repo}/actions/workflows/{urllib.parse.quote(workflow)}"
                            "/runs?per_page=1"], timeout=60)
        if res.returncode != 0:
            return False
        values = parse_json_stream(res.stdout)
        runs = values[0].get("workflow_runs") if values and isinstance(values[0], dict) else None
    except GhError:
        return False
    if not isinstance(runs, list) or not runs or not isinstance(runs[0], dict):
        return False
    return runs[0].get("status") == "completed" and runs[0].get("conclusion") == "success"


def load_groups(path: str) -> tuple[list[dict], float]:
    """The `artifact_prune` groups of the project config and their min age; ([], default) when unset.

    A missing file or section means no groups. A malformed section raises GhError."""
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.loads(fh.read())
    except FileNotFoundError:
        return [], MIN_AGE_SECONDS
    except (OSError, ValueError) as exc:
        raise GhError(f"{path} is unreadable: {exc}") from exc
    section = data.get("artifact_prune") if isinstance(data, dict) else None
    if section is None:
        return [], MIN_AGE_SECONDS
    if not isinstance(section, dict):
        raise GhError(f"{path}: artifact_prune must be an object")
    groups: list[dict] = []
    for i, raw in enumerate(section.get("groups") or []):
        where = f"{path}: artifact_prune.groups[{i}]"
        if not isinstance(raw, dict) or not isinstance(raw.get("pattern"), str):
            raise GhError(f"{where} needs a `pattern` string")
        try:
            rx = re.compile(raw["pattern"])
        except re.error as exc:
            raise GhError(f"{where}.pattern is not a regex: {exc}") from exc
        if rx.groups != 1:
            raise GhError(f"{where}.pattern needs exactly one capture group")
        keep = raw.get("keep")
        if keep is not None and (isinstance(keep, bool) or not isinstance(keep, int) or keep < 0):
            raise GhError(f"{where}.keep must be an integer, 0 or more")
        pr = raw.get("protect_pr_heads")
        if pr is not None and not (isinstance(pr, dict) and isinstance(pr.get("head_prefix"), str)
                                   and isinstance(pr.get("base"), str)):
            raise GhError(f"{where}.protect_pr_heads needs head_prefix and base")
        hold = raw.get("hold_workflow")
        if hold is not None and not isinstance(hold, str):
            raise GhError(f"{where}.hold_workflow must be a string")
        groups.append({"regex": rx, "keep": keep, "protect_pr_heads": pr, "hold_workflow": hold})
    age = section.get("min_age_seconds", MIN_AGE_SECONDS)
    if isinstance(age, bool) or not isinstance(age, (int, float)) or age < 0:
        raise GhError(f"{path}: artifact_prune.min_age_seconds must be a number, 0 or more")
    return groups, float(age)


def load_workflows(path: str) -> list[str]:
    """The workflow names of `artifact_prune.workflows`; DEFAULT_WORKFLOWS when the file, section or key is unset."""
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.loads(fh.read())
    except FileNotFoundError:
        return list(DEFAULT_WORKFLOWS)
    except (OSError, ValueError) as exc:
        raise GhError(f"{path} is unreadable: {exc}") from exc
    section = data.get("artifact_prune") if isinstance(data, dict) else None
    if not isinstance(section, dict) or section.get("workflows") is None:
        return list(DEFAULT_WORKFLOWS)
    names = section["workflows"]
    if (not isinstance(names, list) or not names
            or not all(isinstance(n, str) and n.strip() and not re.search(r'["\n\r\\]', n) for n in names)):
        raise GhError(f"{path}: artifact_prune.workflows must be a non-empty list of workflow names")
    return [n.strip() for n in names]


def config_workflows(path: str) -> list[str] | None:
    """The configured `artifact_prune.workflows`, or None when the file, section or key is unset."""
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.loads(fh.read())
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        return load_workflows(path)
    section = data.get("artifact_prune") if isinstance(data, dict) else None
    if not isinstance(section, dict) or section.get("workflows") is None:
        return None
    return load_workflows(path)


def file_workflows(path: str) -> list[str] | None:
    """The names in the one-line `workflows: [...]` list of the workflow file, or None (no file or no list)."""
    try:
        with open(path, encoding="utf-8", newline="") as fh:
            text = fh.read()
    except OSError:
        return None
    m = WORKFLOWS_LINE_RE.search(text)
    if not m:
        return None
    inner = re.search(r"\[(.*)\]", m.group(0)).group(1)
    names = [n.strip().strip("\"'").strip() for n in inner.split(",")]
    names = [n for n in names if n]
    return names or None


def template_workflow_text() -> str | None:
    """The shipped prune workflow, when this script runs from the plugin; None in a project."""
    tpl = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".github", "workflows",
                       os.path.basename(DEFAULT_WORKFLOW_FILE))
    try:
        with open(tpl, encoding="utf-8", newline="") as fh:
            return fh.read()
    except OSError:
        return None


def pick_sync_names(config: str, wf_path: str) -> tuple[list[str], str]:
    """The list to sync and its source: config, existing file or default."""
    names = config_workflows(config)
    if names is not None:
        return names, "config"
    names = file_workflows(wf_path)
    if names is not None:
        return names, "existing file"
    return list(DEFAULT_WORKFLOWS), "default"


def render_workflows_text(text: str, names: list[str]) -> str:
    """`text` with the `workflows: [...]` line set to `names`. GhError when the file has no such line."""
    line = "[" + ", ".join(json.dumps(n) for n in names) + "]"
    new, count = WORKFLOWS_LINE_RE.subn(lambda m: f"{m.group('indent')}workflows: {line}", text, count=1)
    if not count:
        raise GhError("the workflow file has no one-line `workflows: [...]` list")
    return new


def sync_workflow(path: str, names: list[str], write: bool) -> bool:
    """True when the file's list already equals `names`; with `write`, the file is rewritten otherwise."""
    try:
        with open(path, encoding="utf-8", newline="") as fh:
            text = fh.read()
    except OSError as exc:
        raise GhError(f"{path} is unreadable: {exc}") from exc
    new = render_workflows_text(text, names)
    if new == text:
        return True
    if write:
        try:
            with open(path, "w", encoding="utf-8", newline="") as fh:
                fh.write(new)
        except OSError as exc:
            raise GhError(f"could not write {path}: {exc}") from exc
    return False


def group_match(name: str, groups: list[dict]) -> tuple[str, dict | None]:
    """(prune group, its config) for an artifact name; (name, None) when no configured pattern matches."""
    for g in groups:
        m = g["regex"].fullmatch(name)
        if m:
            return m.group(1), g
    return name, None


def busy_run_ids(repo: str) -> set:
    """Ids of the runs still waiting or running: their artifacts are never deleted."""
    ids: set = set()
    for status in BUSY_STATUSES:
        res = run_gh_retry(["api", "--paginate", f"repos/{repo}/actions/runs?status={status}&per_page=100"])
        if res.returncode != 0:
            raise GhError(f"gh api (list {status} runs) failed ({res.returncode}): "
                          f"{(res.stderr or res.stdout).strip()[:300]}")
        for value in parse_json_stream(res.stdout):
            runs = value.get("workflow_runs") if isinstance(value, dict) else None
            ids.update(r.get("id") for r in runs or [] if isinstance(r, dict))
    return ids


def open_pr_heads(repo: str, head_prefix: str, base: str) -> set:
    """Head commits of the open pull requests from a `head_prefix*` branch into `base`. Any failure raises."""
    res = run_gh_retry(["api", "--paginate", f"repos/{repo}/pulls?state=open&per_page=100"])
    if res.returncode != 0:
        raise GhError(f"gh api (list open pull requests) failed ({res.returncode}): "
                      f"{(res.stderr or res.stdout).strip()[:300]}")
    shas: set = set()
    for value in parse_json_stream(res.stdout):
        for pr in value if isinstance(value, list) else []:
            head, tgt = pr.get("head") or {}, pr.get("base") or {}
            if (str(head.get("ref", "")).startswith(head_prefix) and tgt.get("ref") == base
                    and isinstance(head.get("sha"), str)):
                shas.add(head["sha"])
    return shas


def held_workflow_runs(runs: list[dict], now: datetime | None = None,
                       window: float = HOLD_WINDOW_SECONDS) -> set:
    """Ids of the runs whose artifacts must stay for a re-run: the newest run of each head commit,
    finished within `window`, that failed, was cancelled or timed out. A later success of the same
    commit releases them."""
    now = now or datetime.now(timezone.utc)
    newest: dict = {}
    for run in runs:
        sha, created = run.get("head_sha"), parse_time(run.get("created_at"))
        if not isinstance(sha, str) or created is None:
            continue
        if sha not in newest or created > newest[sha][0]:
            newest[sha] = (created, run)
    held: set = set()
    for created, run in newest.values():
        updated = parse_time(run.get("updated_at")) or created
        if run.get("conclusion") in HOLD_CONCLUSIONS and (now - updated).total_seconds() < window:
            held.add(run.get("id"))
    return held


def held_runs_of(repo: str, workflow: str) -> set:
    """Ids held by `held_workflow_runs` for one workflow file. Any failure raises."""
    res = run_gh_retry(["api", "--paginate",
                        f"repos/{repo}/actions/workflows/{urllib.parse.quote(workflow)}/runs?per_page=100"])
    if res.returncode != 0:
        raise GhError(f"gh api (list {workflow} runs) failed ({res.returncode}): "
                      f"{(res.stderr or res.stdout).strip()[:300]}")
    runs: list[dict] = []
    for value in parse_json_stream(res.stdout):
        items = value.get("workflow_runs") if isinstance(value, dict) else None
        runs.extend(r for r in items or [] if isinstance(r, dict))
    return held_workflow_runs(runs)


def run_id_of(art: dict) -> object:
    run = art.get("workflow_run")
    return run.get("id") if isinstance(run, dict) else None


def head_sha_of(art: dict) -> object:
    run = art.get("workflow_run")
    return run.get("head_sha") if isinstance(run, dict) else None


def plan(artifacts: list[dict], keep: int,
         hold: frozenset[str] | set[str] = frozenset(), groups: list[dict] | None = None,
         now: datetime | None = None, busy_runs: frozenset | set = frozenset(),
         min_age: float = MIN_AGE_SECONDS, pr_heads: dict | None = None,
         held_runs: dict | None = None) -> tuple[dict[str, dict], list[str]]:
    """Group live artifacts by name and split each group into keep and delete.

    Returns ({name: {"keep": [artifact], "delete": [artifact]}}, warnings).
    An artifact with no usable id, name or created_at is left alone: with any
    doubt about its age it is never a deletion candidate.

    `groups` (see load_groups) regroups the artifacts whose name matches a pattern and gives them their
    own keep count. Of those, one of a run in `busy_runs`, one younger than `min_age` seconds, one built
    from a commit in `pr_heads[pattern]`, and every one of a group whose `held_runs[pattern]` is not
    empty is kept. Without `groups` the result is the plain keep-the-newest rule.
    """
    cfg = groups or []
    now = now or datetime.now(timezone.utc)
    pr_heads, held_runs = pr_heads or {}, held_runs or {}
    buckets: dict[str, list[tuple[datetime, int, dict]]] = {}
    gcfg: dict[str, dict] = {}
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
        key, g = group_match(name, cfg)
        buckets.setdefault(key, []).append((created, ident, art))
        if g is not None:
            gcfg[key] = g
    result: dict[str, dict] = {}
    for name in sorted(buckets):
        ordered = sorted(buckets[name], key=lambda t: (t[0], t[1]), reverse=True)
        if name in hold:
            result[name] = {"keep": [t[2] for t in ordered], "delete": [], "held": True}
            continue
        g = gcfg.get(name)
        if g is None:
            result[name] = {"keep": [t[2] for t in ordered[:keep]],
                            "delete": [t[2] for t in ordered[keep:]]}
            continue
        n = keep if g["keep"] is None else g["keep"]
        pattern = g["regex"].pattern
        heads, hold_all = pr_heads.get(pattern, set()), bool(held_runs.get(pattern))
        kept, doomed = [t[2] for t in ordered[:n]], []
        for created, _, art in ordered[n:]:
            protected = (run_id_of(art) in busy_runs or head_sha_of(art) in heads or hold_all
                         or (now - created).total_seconds() < min_age)
            (kept if protected else doomed).append(art)
        result[name] = {"keep": kept, "delete": doomed}
    return result, warnings


def delete_artifact(repo: str, ident: int) -> str:
    """'deleted', 'gone' (404) or 'failed: <why>'."""
    try:
        res = run_gh_retry(["api", "--method", "DELETE", f"repos/{repo}/actions/artifacts/{ident}"],
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
    ap.add_argument("--hold", action="append", default=[], metavar="NAME",
                    help="keep every artifact of NAME while the newest run of --hold-workflow "
                         "has not succeeded (repeatable)")
    ap.add_argument("--hold-workflow", metavar="FILE",
                    help="the workflow whose newest run decides the hold, e.g. package.yml")
    ap.add_argument("--config", default=DEFAULT_CONFIG,
                    help="project config with an optional artifact_prune section (default "
                         ".delivery/config.json; a missing file means none)")
    ap.add_argument("--print-workflows", action="store_true",
                    help="print the artifact_prune.workflows list of the config and exit")
    ap.add_argument("--sync-workflow", nargs="?", const=DEFAULT_WORKFLOW_FILE, metavar="FILE",
                    help="set the `workflows:` line of FILE and exit (config list, else the file's own list, else the default)")
    ap.add_argument("--check-workflow", nargs="?", const=DEFAULT_WORKFLOW_FILE, metavar="FILE",
                    help="exit 1 when the `workflows:` line of FILE differs from that list")
    ap.add_argument("--dry-run", action="store_true", help="delete nothing, print the plan")
    ap.add_argument("--json", action="store_true", dest="as_json",
                    help="print one JSON document instead of rows")
    args = ap.parse_args(argv)

    if args.print_workflows or args.sync_workflow or args.check_workflow:
        try:
            names = load_workflows(args.config)
            if args.print_workflows:
                print("\n".join(names))
            if args.sync_workflow:
                names, source = pick_sync_names(args.config, args.sync_workflow)
                print(f"workflow list from: {source}")
                if not os.path.exists(args.sync_workflow):
                    tpl = template_workflow_text()
                    if tpl is None:
                        raise GhError(f"{args.sync_workflow} does not exist and the template is not at hand")
                    os.makedirs(os.path.dirname(os.path.abspath(args.sync_workflow)), exist_ok=True)
                    with open(args.sync_workflow, "w", encoding="utf-8", newline="") as fh:
                        fh.write(tpl)
                same = sync_workflow(args.sync_workflow, names, write=True)
                print("unchanged" if same else "synced")
            if args.check_workflow:
                if not sync_workflow(args.check_workflow, names, write=False):
                    print(f"artifact_prune: {args.check_workflow} lists other workflows than "
                          f"artifact_prune.workflows; run --sync-workflow", file=sys.stderr)
                    return 1
        except GhError as exc:
            print(f"artifact_prune: {exc}", file=sys.stderr)
            return 2
        return 0
    if args.keep < 1:
        print("artifact_prune: --keep must be at least 1 (keeping 0 would delete every "
              "artifact)", file=sys.stderr)
        return 2
    if args.hold and not args.hold_workflow:
        print("artifact_prune: --hold needs --hold-workflow", file=sys.stderr)
        return 2
    if shutil.which("gh") is None and not (os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")):
        print("artifact_prune: the GitHub CLI (gh) is not installed or not on PATH, and neither "
              "GH_TOKEN nor GITHUB_TOKEN is set (the REST fallback needs one of them)",
              file=sys.stderr)
        return 2
    try:
        repo = resolve_repo(args.repo)
        artifacts = list_artifacts(repo)
        cfg_groups, min_age = load_groups(args.config)
        busy = busy_run_ids(repo) if cfg_groups else set()
        pr_heads: dict = {}
        held_runs: dict = {}
        for g in cfg_groups:
            pat = g["regex"].pattern
            if g["protect_pr_heads"]:
                pr_heads[pat] = open_pr_heads(repo, g["protect_pr_heads"]["head_prefix"],
                                              g["protect_pr_heads"]["base"])
            if g["hold_workflow"]:
                held_runs[pat] = held_runs_of(repo, g["hold_workflow"])
    except GhError as exc:
        print(f"artifact_prune: {exc}", file=sys.stderr)
        return 2

    hold: set[str] = set()
    if args.hold and not newest_run_succeeded(repo, args.hold_workflow):
        hold = set(args.hold)
        print(f"artifact_prune: holding {', '.join(sorted(hold))}: the newest run of "
              f"{args.hold_workflow} has not succeeded", file=sys.stderr)
    groups, warnings = plan(artifacts, args.keep, hold, cfg_groups, busy_runs=busy, min_age=min_age,
                            pr_heads=pr_heads, held_runs=held_runs)
    for warning in warnings:
        print(f"artifact_prune: warning: {warning}", file=sys.stderr)

    report: list[dict] = []
    failures = 0
    for name, g in groups.items():
        row = {"name": name, "kept": [a["id"] for a in g["keep"]],
               "deleted": [], "already_gone": [], "failed": [], "errors": [],
               "would_delete": [a["id"] for a in g["delete"]] if args.dry_run else [],
               "bytes_freed": 0, "held": bool(g.get("held"))}
        if not args.dry_run:
            for art in g["delete"]:
                time.sleep(_env_float("ARTIFACT_PRUNE_PAUSE", 0.3))
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
            if row["held"]:
                extra += ", HELD"
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
