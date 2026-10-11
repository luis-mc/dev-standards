#!/usr/bin/env python3
"""The delivery log: how long each change of a train took to go live (STACKSPEC 13.6).

    delivery_log.py live    --pr N [--at ISO] [--remote origin] [--repo OWNER/NAME] [--dry-run]
    delivery_log.py publish --pr N [--remote origin] [--repo OWNER/NAME] [--dry-run]

N is the train's ready pull request (merged into the default branch). The log is
a table in the train's GitHub release notes; it is never committed to the default
branch. `cleanup.py --pr N` calls `publish` through this module before it deletes
the train's branches (the branches are where the timestamps are); the deploy job
calls `live` after its smoke test to add the moment the change went live.

Per change (the ready pull request's branch and every branch joined into it):
  finished   the last commit on the branch
  joined     the merge commit that brought the branch into the integration branch
  CI start   the earliest start of a workflow run on the ready pull request's branch
             created at or after the pull request was created (so an earlier
             fix-forward round counts); the final head's runs when that listing fails
  CI end     the latest end of the runs on the ready pull request's final head
  merged     the pull request's mergedAt
  live       set by `live`
and the time to live (live minus finished) split into
  testing    CI end minus CI start
  queueing   the longest wait of a run between created and started, among the runs of CI start
  waiting    the rest: time before CI, in the train, in the merge and in the deploy
Every time in the table is UTC (the headers say so). A timestamp that cannot be found is "unknown", and so is every figure that needs
it. Rows already in the release notes are kept; a later call only fills what is
missing (and `live` sets the live time of rows that have none).

The release is the one whose tag points at the merge commit; without one,
`train-<merge date>-<N>` is created for the merge commit. The table lives between
two HTML comments in the notes, with the rows as JSON in a third, so the notes
around it are never touched and a second call replaces the table, not appends.

Offline, without `gh`, without permission, or on any error: a warning on stderr
and exit 0, because a delivery log must never fail a cleanup or a deploy.
Exit 2 only for usage. Python 3.11+, standard library only.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.dont_write_bytecode = True

import delivery_common as dc

START = "<!-- delivery-log:start -->"
END = "<!-- delivery-log:end -->"
DATA = re.compile(r"<!-- delivery-log:data (.*?) -->", re.S)
UNKNOWN = "unknown"
FIELDS = ("finished", "joined", "ci_start", "ci_end", "queued_s", "merged", "live")


class GhFailure(Exception):
    pass


def warn(msg: str) -> None:
    dc.eprint("delivery_log: warning: %s" % msg)


def gh(args: list[str], repo: str | None, *, as_json: bool = False):
    exe = shutil.which("gh")
    if exe is None:
        raise GhFailure("gh is not installed")
    cmd = [exe, *args] + (["--repo", repo] if repo else [])
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
    except (OSError, subprocess.SubprocessError) as exc:
        raise GhFailure("could not run gh: %s" % exc) from exc
    if p.returncode != 0:
        raise GhFailure("gh %s failed (%d): %s" % (" ".join(args[:2]), p.returncode, (p.stderr or p.stdout).strip()[:200]))
    if not as_json:
        return p.stdout
    try:
        return json.loads(p.stdout or "null")
    except json.JSONDecodeError as exc:
        raise GhFailure("gh %s returned invalid JSON" % " ".join(args[:2])) from exc


# --------------------------------------------------------------------------
# time
# --------------------------------------------------------------------------

def parse(ts: object) -> datetime | None:
    if not isinstance(ts, str) or not ts or ts.startswith("0001-"):
        return None
    try:
        d = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def iso(d: datetime) -> str:
    return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def seconds(a: object, b: object) -> float | None:
    x, y = parse(a), parse(b)
    return None if x is None or y is None else (y - x).total_seconds()


def human(s: float | None) -> str:
    if s is None or s < 0:
        return UNKNOWN
    s = int(round(s))
    h, rest = divmod(s, 3600)
    m, sec = divmod(rest, 60)
    if h:
        return "%dh %02dm" % (h, m)
    return "%dm %02ds" % (m, sec) if m else "%ds" % sec


def stamp(ts: object) -> str:
    d = parse(ts)
    return d.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M") if d else UNKNOWN


# --------------------------------------------------------------------------
# collecting
# --------------------------------------------------------------------------

def git_time(root: Path, args: list[str]) -> str | None:
    p = dc.run_git(args, cwd=root, check=False)
    out = (p.stdout or "").strip().splitlines()
    return out[0].strip() if p.returncode == 0 and out and out[0].strip() else None


def joined_time(root: Path, head: str, tip: str) -> str | None:
    """Committer date of the merge commit under `head` that has `tip` as a merged-in parent."""
    p = dc.run_git(["log", "--merges", "--format=%cI %P", head], cwd=root, check=False)
    if p.returncode != 0:
        return None
    found = None
    for line in (p.stdout or "").splitlines():
        parts = line.split()
        if len(parts) >= 3 and tip in parts[2:]:
            found = parts[0]  # log runs newest first; the last match is the oldest
    return found


RUN_FIELDS = "databaseId,workflowName,status,conclusion,createdAt,startedAt,updatedAt"


def ci_of(repo: str | None, head: str, branch: str | None = None, pr_created: str | None = None) -> dict:
    """CI start, end and queued time. End: the latest end of the runs on the ready pull
    request's final head. Start and queued: the runs on its branch created at or after
    the pull request, earlier fix-forward rounds included; the head's runs alone when
    that listing fails or yields nothing."""
    out: dict = {"ci_start": None, "ci_end": None, "queued_s": None}
    runs = gh(["run", "list", "--commit", head, "--limit", "100", "--json", RUN_FIELDS], repo, as_json=True)
    if not isinstance(runs, list):
        return out
    runs = [r for r in runs if isinstance(r, dict)]
    ends = [parse(r.get("updatedAt")) for r in runs if r.get("status") == "completed"]
    ends = [e for e in ends if e]
    out["ci_end"] = iso(max(ends)) if ends else None
    rounds = runs
    since = parse(pr_created)
    if branch and since:
        try:
            listed = gh(["run", "list", "--branch", branch, "--limit", "200", "--json", RUN_FIELDS], repo, as_json=True)
        except GhFailure as exc:
            warn("%s; CI start is taken from the final head's runs" % exc)
            listed = None
        if isinstance(listed, list):
            since_runs = []
            for r in listed:
                created = parse(r.get("createdAt")) if isinstance(r, dict) else None
                if created and created >= since:
                    since_runs.append(r)
            if any(parse(r.get("startedAt")) for r in since_runs):
                rounds = since_runs
    starts = [x for x in (parse(r.get("startedAt")) for r in rounds) if x]
    queued = [q for q in (seconds(r.get("createdAt"), r.get("startedAt")) for r in rounds) if q is not None and q >= 0]
    out["ci_start"] = iso(min(starts)) if starts else None
    out["queued_s"] = max(queued) if queued else None
    return out


def collect(root: Path, repo: str | None, pr: int, tips: dict[str, str]) -> dict:
    """The train's facts. `tips` maps each branch of the train (the ready pull request's
    branch included) to a commit that is still reachable. Never raises."""
    info: dict = {"pr": pr, "merge_commit": None, "head_branch": None, "rows": []}
    pr_data: dict = {}
    try:
        data = gh(["pr", "view", str(pr), "--json", "number,headRefName,headRefOid,mergedAt,mergeCommit,createdAt"], repo, as_json=True)
        pr_data = data if isinstance(data, dict) else {}
    except GhFailure as exc:
        warn(str(exc))
    head = pr_data.get("headRefOid") or ""
    mc = pr_data.get("mergeCommit")
    info["merge_commit"] = mc.get("oid") if isinstance(mc, dict) else None
    info["head_branch"] = pr_data.get("headRefName")
    info["merged_at"] = pr_data.get("mergedAt")
    ci: dict = {"ci_start": None, "ci_end": None, "queued_s": None}
    if head:
        try:
            ci = ci_of(repo, head, pr_data.get("headRefName"), pr_data.get("createdAt"))
        except GhFailure as exc:
            warn(str(exc))
    for branch in sorted(tips):
        tip = tips[branch]
        row = {"change": branch, "finished": git_time(root, ["log", "-1", "--format=%cI", tip]) if tip else None,
               "joined": None, "merged": pr_data.get("mergedAt") or None, "live": None, **ci}
        if head and tip and branch != info["head_branch"]:
            row["joined"] = joined_time(root, head, tip)
        info["rows"].append(row)
    return info


# --------------------------------------------------------------------------
# the table
# --------------------------------------------------------------------------

def figures(row: dict) -> tuple[float | None, float | None, float | None, float | None]:
    """(time to live, waiting, testing, queueing) in seconds; None where unknown."""
    ttl = seconds(row.get("finished"), row.get("live"))
    testing = seconds(row.get("ci_start"), row.get("ci_end"))
    queued = row.get("queued_s")
    queued = float(queued) if isinstance(queued, (int, float)) else None
    waiting = None
    if ttl is not None and testing is not None and queued is not None:
        waiting = ttl - testing - queued
    return ttl, waiting, testing, queued


def render(info: dict) -> str:
    head = ("| Change | Finished (UTC) | Joined (UTC) | CI start (UTC) | CI end (UTC) | Merged (UTC) | Live (UTC) | Waiting | Testing | Queueing | Time to live |\n"
            "|---|---|---|---|---|---|---|---|---|---|---|")
    lines = []
    for row in info.get("rows", []):
        ttl, waiting, testing, queued = figures(row)
        lines.append("| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            row.get("change", UNKNOWN), stamp(row.get("finished")), stamp(row.get("joined")),
            stamp(row.get("ci_start")), stamp(row.get("ci_end")), stamp(row.get("merged")), stamp(row.get("live")),
            human(waiting), human(testing), human(queued), human(ttl)))
    data = json.dumps({"pr": info.get("pr"), "rows": info.get("rows", [])}, separators=(",", ":")).replace("--", "--")
    return "\n".join([START, "## Delivery log, pull request #%s" % info.get("pr"), "", head, *lines, "",
                      "Times are UTC. Time to live is live minus finished: waiting (before CI, in the train, in the merge and the deploy), "
                      "testing (CI start to end) and queueing (longest wait for a runner). unknown: not recorded.",
                      "<!-- delivery-log:data %s -->" % data, END])


def merge_rows(old: list[dict], new: list[dict]) -> list[dict]:
    """Rows already published win; a new fact only fills what is missing."""
    by = {r.get("change"): dict(r) for r in old if isinstance(r, dict)}
    for r in new:
        cur = by.setdefault(r["change"], {"change": r["change"]})
        for k in FIELDS:
            if cur.get(k) in (None, "") and r.get(k) not in (None, ""):
                cur[k] = r[k]
    return [by[k] for k in sorted(by)]


def replace_section(body: str, section: str) -> str:
    if START in body and END in body:
        a, b = body.index(START), body.index(END) + len(END)
        return body[:a] + section + body[b:]
    return (body.rstrip() + "\n\n" if body.strip() else "") + section + "\n"


def existing_info(body: str) -> list[dict]:
    m = DATA.search(body or "")
    if not m:
        return []
    try:
        rows = json.loads(m.group(1)).get("rows", [])
    except (json.JSONDecodeError, AttributeError):
        return []
    return rows if isinstance(rows, list) else []


# --------------------------------------------------------------------------
# the release
# --------------------------------------------------------------------------

def find_tag(root: Path, info: dict) -> tuple[str | None, bool]:
    """(tag, tag exists). An existing tag on the merge commit is the repository's own
    convention; without one, train-<date>-<N>."""
    sha = info.get("merge_commit")
    if sha:
        p = dc.run_git(["tag", "--points-at", sha], cwd=root, check=False)
        tags = [t for t in (p.stdout or "").split() if t] if p.returncode == 0 else []
        if tags:
            return sorted(tags)[0], True
    d = parse(info.get("merged_at"))
    return ("train-%s-%s" % (d.strftime("%Y-%m-%d"), info["pr"]) if d else None), False


def write_release(root: Path, repo: str | None, info: dict, rows: list[dict], dry: bool, live: str | None = None) -> bool:
    info = {**info, "rows": rows}
    tag, tag_exists = find_tag(root, info)
    if not tag:
        warn("no merge date for pull request #%s; the delivery log is not published" % info["pr"])
        return False
    body, exists = "", False
    try:
        data = gh(["release", "view", tag, "--json", "body,tagName"], repo, as_json=True)
        if isinstance(data, dict):
            body, exists = data.get("body") or "", True
    except GhFailure:
        exists = False
    if exists:
        info["rows"] = merge_rows(existing_info(body), rows)
    if live:  # the deploy went live: every change of the train that has no live time gets it
        info["rows"] = [{**r, "live": r.get("live") or live} for r in info["rows"]]
    section = render(info)
    if dry:
        print(section)
        return True
    with tempfile.TemporaryDirectory(prefix="delivery-log-") as tmp:
        notes = Path(tmp) / "notes.md"
        notes.write_text(replace_section(body, section) if exists else section + "\n", encoding="utf-8")
        try:
            if exists:
                gh(["release", "edit", tag, "--notes-file", str(notes)], repo)
            else:
                cmd = ["release", "create", tag, "--title", "Train #%s" % info["pr"], "--notes-file", str(notes)]
                if not tag_exists:
                    target = info.get("merge_commit")
                    if not target:
                        warn("merge commit of pull request #%s unknown; the delivery log is not published" % info["pr"])
                        return False
                    cmd += ["--target", target]
                gh(cmd, repo)
        except GhFailure as exc:
            warn("%s; the delivery log is not published" % exc)
            return False
    print("delivery_log: release %s updated for pull request #%s" % (tag, info["pr"]))
    return True


def existing_rows(root: Path, repo: str | None, pr: int) -> tuple[dict, list[dict]]:
    """The published rows of pull request `pr`, found through its merge commit; used
    when the branches are gone and only the release notes still hold the facts."""
    info: dict = {"pr": pr, "merge_commit": None, "merged_at": None, "head_branch": None, "rows": []}
    try:
        d = gh(["pr", "view", str(pr), "--json", "mergedAt,mergeCommit,headRefName"], repo, as_json=True)
    except GhFailure as exc:
        warn(str(exc))
        return info, []
    if isinstance(d, dict):
        info["merged_at"] = d.get("mergedAt")
        info["head_branch"] = d.get("headRefName")
        mc = d.get("mergeCommit")
        info["merge_commit"] = mc.get("oid") if isinstance(mc, dict) else None
    return info, []


def publish(root: Path, repo: str | None, pr: int, tips: dict[str, str], *, live: str | None = None, dry: bool = False) -> bool:
    """Collect (when branches are left), optionally set live, and write the release notes.
    Never raises: a delivery log must not fail a cleanup or a deploy."""
    try:
        info = collect(root, repo, pr, tips) if tips else existing_rows(root, repo, pr)[0]
        return write_release(root, repo, info, info["rows"], dry, live)
    except Exception as exc:  # noqa: BLE001 - see the docstring
        warn("%s: %s" % (type(exc).__name__, exc))
        return False


def train_tips(root: Path, remote: str, repo: str | None, pr: int) -> dict[str, str]:
    """The ready pull request's branch and every branch joined into it, with a tip each:
    what `cleanup.py --pr` is about to delete. Empty when they are already gone."""
    tips: dict[str, str] = {}
    try:
        d = gh(["pr", "view", str(pr), "--json", "headRefName,headRefOid"], repo, as_json=True)
    except GhFailure as exc:
        warn(str(exc))
        return tips
    if not isinstance(d, dict) or not d.get("headRefOid"):
        return tips
    head = d["headRefOid"]
    tips[d.get("headRefName") or "pr-%d" % pr] = head
    if dc.rev(head, root) is None:
        dc.run_git(["fetch", "--quiet", remote, "refs/pull/%d/head" % pr], cwd=root, check=False)
    p = dc.run_git(["for-each-ref", "--format=%(refname:short) %(objectname)", "refs/remotes/%s/" % remote], cwd=root, check=False)
    default = dc.git(["symbolic-ref", "--quiet", "--short", "refs/remotes/%s/HEAD" % remote], cwd=root, check=False)
    for line in (p.stdout or "").splitlines():
        name, _, sha = line.partition(" ")
        short = name[len(remote) + 1:]
        if not short or short == "HEAD" or name == default or short in tips:
            continue
        if sha and dc.is_ancestor(sha, head, root) and not (default and dc.is_ancestor(sha, default, root)):
            tips[short] = sha
    return tips


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="delivery_log.py", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("publish", "live"):
        p = sub.add_parser(name)
        p.add_argument("--pr", type=int, required=True, metavar="N")
        p.add_argument("--remote", default="origin")
        p.add_argument("--repo", metavar="OWNER/NAME")
        p.add_argument("--dry-run", action="store_true", help="print the table; change nothing")
        if name == "live":
            p.add_argument("--at", metavar="ISO", help="the live time (default: now)")
    args = ap.parse_args(argv)
    live = None
    if args.cmd == "live":
        when = parse(args.at) if args.at else datetime.now(timezone.utc)
        if when is None:
            raise dc.DeliveryError("--at is not an ISO timestamp: %s" % args.at)
        live = iso(when)
    root = dc.repo_root()
    tips = train_tips(root, args.remote, args.repo, args.pr)
    publish(root, args.repo, args.pr, tips, live=live, dry=args.dry_run)
    return dc.EXIT_OK


if __name__ == "__main__":
    dc.main_guard(main)
