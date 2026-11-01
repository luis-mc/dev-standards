#!/usr/bin/env python3
"""Prove artifact_prune.py and artifact-prune.yml do what CONTRACT.md says.

artifact_prune.py runs against a stub `gh` on PATH that serves artifact pages
from a JSON fixture per test, the way `gh api --paginate` does (one JSON document
per page, back to back), and records every call. The stub can only delete from a
fixture: no real repository is ever touched.

Each behaviour is a scenario function that returns a list of problems. The test
runs it against the real script (must return none) and against mutants of the
script, copies with one rule broken (keeps 0, keeps the oldest, deletes expired,
ignores a failed deletion, misses page 2, ...), which must each return at least
one problem. A check that cannot fail is a check that proves nothing.

artifact-prune.yml and the four ci.yml files are checked structurally (text and
regex, no YAML library), also against broken copies.

Run:  python3 tools/test_artifact_prune.py
"""
from __future__ import annotations

import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLING = (ROOT / "claude/plugins/project-setup/skills/tech-stack-setup/assets/tooling")
SCRIPT = TOOLING / "shared/scripts/delivery/artifact_prune.py"
WORKFLOW = TOOLING / "shared/.github/workflows/artifact-prune.yml"
TRACKS = ("ts", "go", "rust", "dotnet")

REPO = "acme/widgets"

# ---------------------------------------------------------------------------
# Stub gh
# ---------------------------------------------------------------------------

STUB_GH = r'''
import json, os, sys

argv = sys.argv[1:]
log = os.environ.get("GH_STUB_LOG")
if log:
    with open(log, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(argv) + "\n")


def fail(msg, code=1):
    sys.stderr.write(msg + "\n")
    sys.exit(code)


with open(os.environ["GH_STUB_FIXTURE"], encoding="utf-8") as fh:
    fx = json.load(fh)

if argv[:1] != ["api"] and argv[:2] != ["repo", "view"]:
    fail("stub gh: unexpected call " + " ".join(argv), 97)

if argv[:2] == ["repo", "view"]:
    if "repo_view" not in fx:
        fail("stub gh: no repository here")
    print(fx["repo_view"])
    sys.exit(0)

method = "GET"
if "--method" in argv:
    method = argv[argv.index("--method") + 1]
paths = [a for a in argv[1:] if a.startswith("repos/")]
if len(paths) != 1:
    fail("stub gh: expected one repos/ path in " + " ".join(argv), 97)
path = paths[0]

if method == "DELETE":
    ident = path.rsplit("/", 1)[-1]
    err = fx.get("delete", {}).get(ident)
    if err:
        fail(err["message"])
    with open(os.environ["GH_STUB_DELETED"], "a", encoding="utf-8") as fh:
        fh.write(ident + "\n")
    sys.exit(0)

if fx.get("list_error"):
    fail(fx["list_error"])
base = fx.get("path", "repos/%s/actions/artifacts?per_page=100" % fx["repo"])
if path != base:
    fail("stub gh: no fixture for " + path, 97)
pages = fx["pages"]
if "--paginate" not in argv:
    pages = pages[:1]  # without --paginate gh returns the first page only
total = sum(len(p) for p in fx["pages"])
fmt = fx.get("format", "concat")
docs = [json.dumps(p if fmt == "list" else {"total_count": total, "artifacts": p})
        for p in pages]
sys.stdout.write(("\n" if fmt == "lines" else "").join(docs) + ("\n" if fmt != "concat" else ""))
'''


class Sandbox:
    """A temp dir holding a stub `gh` (script + shim) and a fixture."""

    def __init__(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="ds20-")
        self.dir = Path(self._tmp.name)
        self.bin = self.dir / "bin"
        self.bin.mkdir()
        (self.bin / "gh.py").write_text(STUB_GH, encoding="utf-8")
        if os.name == "nt":
            (self.bin / "gh.cmd").write_text(
                f'@"{sys.executable}" "%~dp0gh.py" %*\r\n', encoding="utf-8")
        else:
            shim = self.bin / "gh"
            shim.write_text(f'#!/bin/sh\nexec "{sys.executable}" "$(dirname "$0")/gh.py" "$@"\n',
                            encoding="utf-8")
            shim.chmod(shim.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        self.fixture = self.dir / "fixture.json"
        self.log = self.dir / "gh.log"
        self.deleted = self.dir / "deleted.txt"
        self.write_fixture({})

    def write_fixture(self, fx: dict) -> None:
        self.fixture.write_text(json.dumps({"repo": REPO, **fx}), encoding="utf-8")

    def calls(self) -> list[list[str]]:
        if not self.log.exists():
            return []
        return [json.loads(line) for line in self.log.read_text(encoding="utf-8").splitlines()]

    def deletions(self) -> list[str]:
        """Ids the stub actually deleted, as strings, in call order."""
        if not self.deleted.exists():
            return []
        return self.deleted.read_text(encoding="utf-8").split()

    def delete_calls(self) -> list[str]:
        """Ids a DELETE was attempted for (including ones the stub refused)."""
        return [c[-1].rsplit("/", 1)[-1] for c in self.calls() if "DELETE" in c]

    def env(self, extra: dict | None = None, with_stub: bool = True) -> dict:
        env = {k: v for k, v in os.environ.items()
               if not k.startswith("GITHUB_") and k not in ("GH_TOKEN", "GITHUB_TOKEN")}
        env["PYTHONUTF8"] = "1"
        if with_stub:
            env["PATH"] = str(self.bin) + os.pathsep + env.get("PATH", "")
        else:
            empty = self.dir / "empty"
            empty.mkdir(exist_ok=True)
            env["PATH"] = str(empty)
        env["GH_STUB_FIXTURE"] = str(self.fixture)
        env["GH_STUB_LOG"] = str(self.log)
        env["GH_STUB_DELETED"] = str(self.deleted)
        env.update(extra or {})
        return env

    def run(self, script: Path, args: list[str], *, env_extra: dict | None = None,
            with_stub: bool = True) -> tuple[int, str, str]:
        proc = subprocess.run(
            [sys.executable, "-I", str(script), *args], cwd=self.dir,
            env=self.env(env_extra, with_stub), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=120)
        return proc.returncode, proc.stdout, proc.stderr

    def close(self) -> None:
        self._tmp.cleanup()


def art(ident: int, name: str, created: str, *, expired: bool = False, size: int = 1000) -> dict:
    return {"id": ident, "name": name, "size_in_bytes": size, "expired": expired,
            "created_at": created, "updated_at": created,
            "expires_at": "2027-01-01T00:00:00Z"}


def day(n: int, hour: int = 12) -> str:
    return f"2026-10-{n:02d}T{hour:02d}:00:00Z"


# ---------------------------------------------------------------------------
# Mutants
# ---------------------------------------------------------------------------

def mutate(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise AssertionError(f"mutation anchor {old!r} found {text.count(old)} times; "
                             "the script changed, update the test")
    return text.replace(old, new)


SOURCE = SCRIPT.read_text(encoding="utf-8")

MUTANTS: dict[str, str] = {
    "keeps 0 (deletes the newest too)":
        mutate(SOURCE, '"keep": [t[2] for t in ordered[:keep]]',
               '"keep": [t[2] for t in ordered[:0]]').replace(
            "ordered[keep:]", "ordered[0:]"),
    "keeps the oldest (sort ascending)":
        mutate(SOURCE, "key=lambda t: (t[0], t[1]), reverse=True)",
               "key=lambda t: (t[0], t[1]), reverse=False)"),
    "ties broken by the lowest id":
        mutate(SOURCE, "key=lambda t: (t[0], t[1]), reverse=True)",
               "key=lambda t: (t[0], -t[1]), reverse=True)"),
    "deletes expired (does not ignore them)":
        mutate(SOURCE, 'if art.get("expired") is True:', 'if False:'),
    "ignores a failed deletion (exit 0)":
        mutate(SOURCE, "failures += 1", "failures += 0"),
    "stops at the first failed deletion":
        mutate(SOURCE, "failures += 1", "failures += 1\n                    break"),
    "misses page 2 (reads the first JSON document only)":
        mutate(SOURCE, "    for value in values:\n        if isinstance(value, dict):",
               "    for value in values[:1]:\n        if isinstance(value, dict):"),
    "does not pass --paginate":
        mutate(SOURCE, '["api", "--paginate", f"repos/', '["api", f"repos/'),
    "a 404 on delete is a failure":
        mutate(SOURCE, '    if NOT_FOUND_RE.search(text):\n        return "gone"\n', ""),
    "dry run still deletes":
        mutate(SOURCE, "        if not args.dry_run:\n            for art in g",
               "        if True:\n            for art in g"),
    "groups by id instead of name":
        mutate(SOURCE, "groups.setdefault(name, [])", "groups.setdefault(str(ident), [])"),
    "ignores --keep":
        mutate(SOURCE, "ordered[:keep]", "ordered[:1]").replace("ordered[keep:]", "ordered[1:]"),
}


def script_for(mutant: str | None, scratch: Path) -> Path:
    if mutant is None:
        return SCRIPT
    path = scratch / "artifact_prune_mutant.py"
    path.write_text(MUTANTS[mutant], encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Test registry
# ---------------------------------------------------------------------------

TESTS: list = []


def test(fn):
    TESTS.append(fn)
    return fn


test.__test__ = False  # the decorator is not a pytest test


def check(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def prove(name: str, scenario, mutants: list[str]) -> None:
    """The scenario passes on the real script and fails on every named mutant."""
    problems = scenario(SCRIPT)
    check(not problems, f"{name}: real script should conform; got {problems}")
    with tempfile.TemporaryDirectory(prefix="ds20-mut-") as tmp:
        for mutant in mutants:
            found = scenario(script_for(mutant, Path(tmp)))
            check(found, f"{name}: mutant `{mutant}` was NOT detected")


def with_sb(fn):
    """Run `fn(sb)` in a fresh sandbox and return its problems list."""
    sb = Sandbox()
    try:
        return fn(sb)
    finally:
        sb.close()


def sorted_ids(ids: list[str]) -> list[int]:
    return sorted(int(i) for i in ids)


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------

def sc_grouping(script: Path) -> list[str]:
    """Three names: several builds, one build, and an expired newest build."""
    def go(sb: Sandbox) -> list[str]:
        sb.write_fixture({"pages": [[
            art(1, "windows-installer", day(1)),
            art(3, "windows-installer", day(3)),
            art(2, "windows-installer", day(2)),
            art(4, "coverage-report", day(2)),
            art(7, "test-report", day(1)),
            art(8, "test-report", day(5), expired=True),
        ]]})
        rc, out, err = sb.run(script, ["--repo", REPO])
        p = []
        if rc != 0:
            p.append(f"exit {rc}\n{out}\n{err}")
        # newest windows-installer (3) kept; 1 and 2 deleted; 4 and 7 alone; 8 untouched
        if sorted_ids(sb.deletions()) != [1, 2]:
            p.append(f"deleted {sb.deletions()}, wanted [1, 2]")
        if "windows-installer" not in out or "coverage-report" not in out:
            p.append(f"one row per name expected, got {out!r}")
        return p
    return with_sb(go)


def sc_keeps_newest_by_time_not_input_order(script: Path) -> list[str]:
    def go(sb: Sandbox) -> list[str]:
        # Input order is deliberately not chronological; ids are deliberately
        # not chronological either (the newest build has the lowest id).
        sb.write_fixture({"pages": [[
            art(30, "bundle", day(2)),
            art(10, "bundle", day(9)),
            art(20, "bundle", day(4)),
        ]]})
        rc, out, err = sb.run(script, ["--repo", REPO])
        p = []
        if rc != 0:
            p.append(f"exit {rc}\n{out}\n{err}")
        if sorted_ids(sb.deletions()) != [20, 30]:
            p.append(f"deleted {sb.deletions()}, wanted [20, 30] (kept 10, the newest)")
        return p
    return with_sb(go)


def sc_tie_on_created_at(script: Path) -> list[str]:
    def go(sb: Sandbox) -> list[str]:
        sb.write_fixture({"pages": [[
            art(11, "bundle", day(3)),
            art(10, "bundle", day(3)),
            art(12, "bundle", day(1)),
        ]]})
        rc, out, err = sb.run(script, ["--repo", REPO])
        p = []
        if rc != 0:
            p.append(f"exit {rc}\n{out}\n{err}")
        if sorted_ids(sb.deletions()) != [10, 12]:
            p.append(f"deleted {sb.deletions()}, wanted [10, 12] (tie on time keeps id 11)")
        return p
    return with_sb(go)


def sc_expired_ignored(script: Path) -> list[str]:
    def go(sb: Sandbox) -> list[str]:
        # The only newer artifact is expired: the live one must stay, and the
        # expired one must never get a DELETE call.
        sb.write_fixture({"pages": [[
            art(1, "report", day(1)),
            art(2, "report", day(8), expired=True),
            art(3, "other", day(1), expired=True),
        ]]})
        rc, out, err = sb.run(script, ["--repo", REPO])
        p = []
        if rc != 0:
            p.append(f"exit {rc}\n{out}\n{err}")
        if sb.delete_calls():
            p.append(f"expected no deletion, got {sb.delete_calls()}")
        return p
    return with_sb(go)


def sc_keep_n(script: Path) -> list[str]:
    def go(sb: Sandbox) -> list[str]:
        sb.write_fixture({"pages": [[art(i, "bundle", day(i)) for i in range(1, 6)]]})
        rc, out, err = sb.run(script, ["--repo", REPO, "--keep", "2"])
        p = []
        if rc != 0:
            p.append(f"exit {rc}\n{out}\n{err}")
        if sorted_ids(sb.deletions()) != [1, 2, 3]:
            p.append(f"--keep 2 deleted {sb.deletions()}, wanted [1, 2, 3]")
        return p
    return with_sb(go)


def sc_pagination(script: Path) -> list[str]:
    def go(sb: Sandbox) -> list[str]:
        # The newest build is on page 3 and old builds are on all three pages:
        # a script that reads only page 1 deletes the wrong ones.
        sb.write_fixture({"pages": [
            [art(1, "bundle", day(1)), art(2, "bundle", day(2)), art(5, "solo", day(1))],
            [art(3, "bundle", day(3)), art(4, "bundle", day(4))],
            [art(9, "bundle", day(9)), art(8, "late", day(1)), art(7, "late", day(2))],
        ]})
        rc, out, err = sb.run(script, ["--repo", REPO])
        p = []
        if rc != 0:
            p.append(f"exit {rc}\n{out}\n{err}")
        if sorted_ids(sb.deletions()) != [1, 2, 3, 4, 8]:
            p.append(f"deleted {sb.deletions()}, wanted [1, 2, 3, 4, 8]")
        listing = [c for c in sb.calls() if "DELETE" not in c]
        if not listing or "--paginate" not in listing[0]:
            p.append(f"the listing call must use --paginate, got {listing}")
        return p
    return with_sb(go)


def sc_failed_deletion(script: Path) -> list[str]:
    def go(sb: Sandbox) -> list[str]:
        sb.write_fixture({
            "pages": [[art(i, "bundle", day(i)) for i in range(1, 5)]],
            "delete": {"2": {"message": "gh: Server Error (HTTP 500)"}},
        })
        rc, out, err = sb.run(script, ["--repo", REPO])
        p = []
        if rc != 1:
            p.append(f"a failed deletion must exit 1, got {rc}\n{out}\n{err}")
        if sorted_ids(sb.delete_calls()) != [1, 2, 3]:
            p.append(f"all deletions must still be attempted, got {sb.delete_calls()}")
        if sorted_ids(sb.deletions()) != [1, 3]:
            p.append(f"actually deleted {sb.deletions()}, wanted [1, 3]")
        if "2" not in err:
            p.append(f"the failure for id 2 must be named on stderr, got {err!r}")
        return p
    return with_sb(go)


def sc_gone_is_not_a_failure(script: Path) -> list[str]:
    def go(sb: Sandbox) -> list[str]:
        sb.write_fixture({
            "pages": [[art(i, "bundle", day(i)) for i in range(1, 4)]],
            "delete": {"1": {"message": "gh: Not Found (HTTP 404)"}},
        })
        rc, out, err = sb.run(script, ["--repo", REPO])
        p = []
        if rc != 0:
            p.append(f"a 404 on delete is not a failure; exit {rc}\n{out}\n{err}")
        if sorted_ids(sb.deletions()) != [2]:
            p.append(f"actually deleted {sb.deletions()}, wanted [2]")
        return p
    return with_sb(go)


def sc_dry_run(script: Path) -> list[str]:
    def go(sb: Sandbox) -> list[str]:
        sb.write_fixture({"pages": [[art(i, "bundle", day(i)) for i in range(1, 4)]]})
        rc, out, err = sb.run(script, ["--repo", REPO, "--dry-run"])
        p = []
        if rc != 0:
            p.append(f"exit {rc}\n{out}\n{err}")
        if sb.delete_calls():
            p.append(f"--dry-run must not call DELETE, got {sb.delete_calls()}")
        if "would delete 2" not in out:
            p.append(f"--dry-run should report `would delete 2`, got {out!r}")
        return p
    return with_sb(go)


def sc_json(script: Path) -> list[str]:
    def go(sb: Sandbox) -> list[str]:
        sb.write_fixture({
            "pages": [[art(1, "a", day(1), size=500), art(2, "a", day(2), size=700),
                       art(3, "a", day(3), size=900), art(4, "b", day(1)),
                       art(5, "c", day(1)), art(6, "c", day(2))]],
            "delete": {"1": {"message": "gh: Not Found (HTTP 404)"},
                       "5": {"message": "gh: Server Error (HTTP 500)"}},
        })
        rc, out, err = sb.run(script, ["--repo", REPO, "--json"])
        p = []
        if rc != 1:
            p.append(f"exit {rc}, wanted 1 (id 5 failed)\n{out}\n{err}")
        try:
            doc = json.loads(out)
        except json.JSONDecodeError:
            return p + [f"--json output is not one JSON document: {out!r}"]
        rows = {r.get("name"): r for r in doc.get("artifacts", [])}
        if doc.get("repo") != REPO or doc.get("dry_run") is not False or doc.get("keep") != 1:
            p.append(f"json header wrong: { {k: v for k, v in doc.items() if k != 'artifacts'} }")
        if doc.get("failed") != 1:
            p.append(f"json `failed` should be 1, got {doc.get('failed')}")
        if sorted(rows) != ["a", "b", "c"]:
            p.append(f"one row per name expected, got {sorted(rows)}")
            return p
        a, b, c = rows["a"], rows["b"], rows["c"]
        if a.get("kept") != [3] or a.get("deleted") != [2] or a.get("already_gone") != [1]:
            p.append(f"row a wrong: {a}")
        if a.get("bytes_freed") != 700:
            p.append(f"row a freed {a.get('bytes_freed')}, wanted 700 (only id 2 was deleted)")
        if b.get("kept") != [4] or b.get("deleted") != []:
            p.append(f"row b wrong: {b}")
        if c.get("kept") != [6] or c.get("failed") != [5] or c.get("deleted") != []:
            p.append(f"row c wrong: {c}")
        return p
    return with_sb(go)


def sc_json_dry_run(script: Path) -> list[str]:
    def go(sb: Sandbox) -> list[str]:
        sb.write_fixture({"pages": [[art(1, "a", day(1), size=40), art(2, "a", day(2))]]})
        rc, out, err = sb.run(script, ["--repo", REPO, "--json", "--dry-run"])
        p = []
        if rc != 0:
            p.append(f"exit {rc}\n{out}\n{err}")
        try:
            doc = json.loads(out)
        except json.JSONDecodeError:
            return p + [f"--json output is not JSON: {out!r}"]
        row = (doc.get("artifacts") or [{}])[0]
        if doc.get("dry_run") is not True or row.get("would_delete") != [1]:
            p.append(f"dry-run json wrong: {doc}")
        if row.get("deleted") != [] or sb.delete_calls():
            p.append("dry run must record nothing as deleted")
        return p
    return with_sb(go)


@test
def groups_by_name_and_keeps_the_newest():
    prove("grouping", sc_grouping,
          ["keeps 0 (deletes the newest too)", "keeps the oldest (sort ascending)",
           "groups by id instead of name"])


@test
def newest_means_created_at_not_input_order_or_id():
    prove("created_at order", sc_keeps_newest_by_time_not_input_order,
          ["keeps the oldest (sort ascending)", "keeps 0 (deletes the newest too)"])


@test
def ties_on_created_at_keep_the_highest_id():
    prove("tie", sc_tie_on_created_at, ["ties broken by the lowest id"])


@test
def expired_artifacts_are_ignored():
    prove("expired", sc_expired_ignored, ["deletes expired (does not ignore them)"])
    # And the expired-newest case from the grouping scenario is covered there.
    problems = sc_grouping(script_for_mutant("deletes expired (does not ignore them)"))
    check(problems, "grouping scenario should also catch deleting expired artifacts")


def script_for_mutant(mutant: str) -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="ds20-mut-"))
    return script_for(mutant, tmp)


@test
def keep_n_keeps_the_newest_n():
    prove("--keep 2", sc_keep_n, ["ignores --keep", "keeps 0 (deletes the newest too)"])


@test
def every_page_is_read():
    prove("pagination", sc_pagination,
          ["misses page 2 (reads the first JSON document only)", "does not pass --paginate"])


@test
def a_failed_deletion_exits_1_and_the_rest_are_still_tried():
    prove("failed deletion", sc_failed_deletion,
          ["ignores a failed deletion (exit 0)", "stops at the first failed deletion"])


@test
def a_404_on_delete_is_not_a_failure():
    prove("404", sc_gone_is_not_a_failure, ["a 404 on delete is a failure"])


@test
def dry_run_deletes_nothing():
    prove("dry run", sc_dry_run, ["dry run still deletes"])


@test
def json_output_is_machine_readable():
    prove("--json", sc_json,
          ["ignores a failed deletion (exit 0)", "a 404 on delete is a failure",
           "groups by id instead of name"])
    prove("--json --dry-run", sc_json_dry_run, ["dry run still deletes"])


@test
def page_formats_all_parse():
    """Concatenated objects, newline-separated objects, bare lists, one page."""
    for fmt in ("concat", "lines", "list"):
        for pages in (
            [[art(1, "a", day(1)), art(2, "a", day(2))]],
            [[art(1, "a", day(1))], [art(2, "a", day(2))], []],
        ):
            sb = Sandbox()
            try:
                sb.write_fixture({"pages": pages, "format": fmt})
                rc, out, err = sb.run(SCRIPT, ["--repo", REPO])
                check(rc == 0, f"{fmt}/{len(pages)} pages: exit {rc}\n{out}\n{err}")
                check(sb.deletions() == ["1"],
                      f"{fmt}/{len(pages)} pages: deleted {sb.deletions()}, wanted ['1']")
            finally:
                sb.close()


@test
def nothing_to_prune_is_quiet_success():
    for pages in ([[]], [[art(1, "a", day(1))]], [[art(1, "a", day(1), expired=True)]]):
        sb = Sandbox()
        try:
            sb.write_fixture({"pages": pages})
            rc, out, err = sb.run(SCRIPT, ["--repo", REPO])
            check(rc == 0 and not sb.delete_calls(), f"exit {rc}, calls {sb.calls()}\n{out}{err}")
        finally:
            sb.close()


@test
def artifacts_without_usable_fields_are_never_deleted():
    sb = Sandbox()
    try:
        broken = [{"id": 5, "name": "a", "created_at": None},
                  {"id": "x", "name": "a", "created_at": day(1)},
                  {"name": "a", "created_at": day(1)},
                  {"id": 6, "created_at": day(1)}]
        sb.write_fixture({"pages": [[art(1, "a", day(1)), art(2, "a", day(2)), *broken]]})
        rc, out, err = sb.run(SCRIPT, ["--repo", REPO])
        check(rc == 0, f"exit {rc}\n{out}\n{err}")
        check(sb.deletions() == ["1"], f"deleted {sb.deletions()}, wanted only ['1']")
        check("skipped" in err, f"skipped artifacts should be named on stderr, got {err!r}")
    finally:
        sb.close()


@test
def repository_resolution():
    # --repo wins; then GITHUB_REPOSITORY; then `gh repo view`.
    cases = [
        (["--repo", REPO], {"GITHUB_REPOSITORY": "other/ignored"}, {}, REPO, False),
        ([], {"GITHUB_REPOSITORY": REPO}, {}, REPO, False),
        ([], {}, {"repo_view": REPO + "\n"}, REPO, True),
    ]
    for args, env, extra_fx, repo, uses_view in cases:
        sb = Sandbox()
        try:
            sb.write_fixture({"pages": [[art(1, "a", day(1)), art(2, "a", day(2))]],
                              "repo": repo, **extra_fx})
            rc, out, err = sb.run(SCRIPT, args, env_extra=env)
            check(rc == 0, f"{args} {env}: exit {rc}\n{out}\n{err}")
            check(sb.deletions() == ["1"], f"{args} {env}: deleted {sb.deletions()}")
            viewed = any(c[:2] == ["repo", "view"] for c in sb.calls())
            check(viewed == uses_view, f"{args} {env}: `gh repo view` used={viewed}")
            check(any(f"repos/{repo}/actions/artifacts/1" in c[-1] for c in sb.calls()),
                  f"{args} {env}: DELETE must target repos/{repo}")
        finally:
            sb.close()
    # No way to learn the repository, or a malformed one: exit 2, nothing deleted.
    for args, env in (([], {}), (["--repo", "not a repo"], {}), (["--repo", "a/b/c"], {})):
        sb = Sandbox()
        try:
            sb.write_fixture({"pages": [[art(1, "a", day(1)), art(2, "a", day(2))]]})
            rc, out, err = sb.run(SCRIPT, args, env_extra=env)
            check(rc == 2 and not sb.delete_calls(), f"{args}: exit {rc}, calls {sb.calls()}")
        finally:
            sb.close()


@test
def usage_and_gh_failures_exit_2():
    sb = Sandbox()
    try:
        sb.write_fixture({"pages": [[art(1, "a", day(1)), art(2, "a", day(2))]]})
        for bad in (["--keep", "0"], ["--keep", "-1"], ["--keep", "x"], ["--nope"]):
            rc, out, err = sb.run(SCRIPT, ["--repo", REPO, *bad])
            check(rc == 2, f"{bad}: exit {rc}, wanted 2\n{out}\n{err}")
        check(not sb.delete_calls(), "usage errors must delete nothing")
        # gh fails to list
        sb.write_fixture({"pages": [[]], "list_error": "gh: HTTP 502: bad gateway"})
        rc, out, err = sb.run(SCRIPT, ["--repo", REPO])
        check(rc == 2 and "502" in err, f"list failure: exit {rc}\n{out}\n{err}")
        # gh is not installed
        rc, out, err = sb.run(SCRIPT, ["--repo", REPO], with_stub=False)
        check(rc == 2 and "gh" in err, f"no gh: exit {rc}\n{out}\n{err}")
        check("GH_TOKEN" in err and "GITHUB_TOKEN" in err, f"no gh, no token must name both: {err}")
        # gh missing but a token set: the REST fallback is used, so the "not installed" refusal
        # does not fire (the dead proxy makes the REST call fail fast, offline).
        dead = {"GH_TOKEN": "x", "HTTPS_PROXY": "http://127.0.0.1:9", "https_proxy": "http://127.0.0.1:9"}
        rc, out, err = sb.run(SCRIPT, ["--repo", REPO], env_extra=dead, with_stub=False)
        check(rc == 2 and "not installed" not in err and "could not call the GitHub API" in err,
              f"no gh + token must reach the REST call: exit {rc} {out} {err}")
        # resolve_repo needs no gh when GITHUB_REPOSITORY is set (Actions)
        rc, out, err = sb.run(SCRIPT, [], env_extra={**dead, "GITHUB_REPOSITORY": REPO}, with_stub=False)
        check("no repository" not in err and "not installed" not in err, f"GITHUB_REPOSITORY: {err}")
    finally:
        sb.close()


@test
def invalid_json_from_gh_exits_2_and_deletes_nothing():
    sb = Sandbox()
    try:
        # A stub variant that prints a truncated second page.
        stub = sb.bin / "gh.py"
        stub.write_text(
            "import sys\n"
            "if '--method' in sys.argv:\n    sys.exit(0)\n"
            "sys.stdout.write('{\"artifacts\": [{\"id\": 1, \"name\": \"a\", "
            "\"created_at\": \"2026-10-01T00:00:00Z\"}]}{\"artifacts\": [{\"id\"')\n",
            encoding="utf-8")
        rc, out, err = sb.run(SCRIPT, ["--repo", REPO])
        check(rc == 2, f"exit {rc}, wanted 2\n{out}\n{err}")
        check(not sb.deletions(), "must not delete when the listing could not be read")
    finally:
        sb.close()


# ---------------------------------------------------------------------------
# artifact-prune.yml and the track ci.yml files
# ---------------------------------------------------------------------------

def workflow_problems(text: str) -> list[str]:
    p: list[str] = []

    def need(pattern: str, msg: str, flags: int = re.M) -> None:
        if not re.search(pattern, text, flags):
            p.append(msg)

    need(r"^on:\s*$", "no top-level `on:`")
    need(r"^  workflow_run:\s*\n(?:    .*\n)*?    workflows:\s*\[\s*[\"']CI[\"']\s*,\s*[\"']Package[\"']\s*\]",
         "workflow_run must list workflows: [\"CI\", \"Package\"]")
    need(r"^  workflow_run:\s*\n(?:    .*\n)*?    types:\s*\[\s*completed\s*\]",
         "workflow_run must use types: [completed]")
    need(r"^  schedule:\s*\n\s+- cron:\s*'[^']+'", "no schedule cron")
    need(r"^  workflow_dispatch:", "no workflow_dispatch")
    # a daily cron: five fields, day-of-month, month and day-of-week are *
    m = re.search(r"cron:\s*'(\S+) (\S+) (\S+) (\S+) (\S+)'", text)
    if m and (m.group(1) == "*" or m.group(2) == "*" or m.group(3, 4, 5) != ("*", "*", "*")):
        p.append(f"cron must run once a day, got {m.group(0)!r}")
    need(r"^concurrency:\s*\n(?:  .*\n)*?  group:\s*\S+", "no top-level concurrency group")
    need(r"^concurrency:\s*\n(?:  .*\n)*?  cancel-in-progress:\s*false",
         "concurrency must not cancel a running prune (cancel-in-progress: false)")
    jobs = re.split(r"^jobs:\s*$", text, maxsplit=1, flags=re.M)
    if len(jobs) != 2:
        return p + ["no jobs: block"]
    top, body = jobs
    if not re.search(r"^permissions:\s*\n  contents:\s*read\s*$", top, re.M):
        p.append("top-level permissions must be `contents: read`")
    if re.search(r"^\s*actions:\s*write", top, re.M):
        p.append("actions: write belongs on the job, not the workflow")
    job_names = re.findall(r"^  ([A-Za-z0-9_-]+):\s*$", body, re.M)
    if len(job_names) != 1:
        p.append(f"exactly one job expected, got {job_names}")
    if not re.search(r"^    permissions:\s*\n(?:      .*\n)*?      actions:\s*write\s*$",
                     body, re.M):
        p.append("the job needs `permissions: actions: write`")
    if not re.search(r"^    permissions:\s*\n(?:      .*\n)*?      contents:\s*read\s*$",
                     body, re.M):
        p.append("the job needs `contents: read` to check out")
    if not any(line.strip() == "GH_TOKEN: ${{ github.token }}" for line in body.splitlines()):
        p.append("GH_TOKEN must be ${{ github.token }}")
    if not re.search(r"^\s*run:\s*python3 scripts/delivery/artifact_prune\.py\s*$", body, re.M):
        p.append("the job must run `python3 scripts/delivery/artifact_prune.py`")
    if re.search(r"artifact_prune\.py[^\n]*--dry-run", body):
        p.append("the scheduled job must not be a dry run")
    uses = re.findall(r"^\s*-?\s*uses:\s*(\S+)", body, re.M)
    # DS162: actions are pinned by full commit SHA, like the track ci.yml files.
    if not any(re.fullmatch(r"actions/checkout@[0-9a-f]{40}", u) for u in uses):
        p.append("checkout must be pinned the way the track ci.yml files pin it "
                 "(actions/checkout@<commit SHA>)")
    for u in uses:
        if not re.fullmatch(r"[\w.-]+/[\w./-]+@[0-9a-f]{40}", u):
            p.append(f"action {u!r} is not pinned like the track ci.yml files (@<commit SHA>)")
    need(r"^\s*timeout-minutes:\s*\d+", "the job needs a timeout-minutes")
    # The instruction to products: a comment above `on:` that names `workflows:`.
    head = text.split("\non:", 1)[0]
    if not (re.search(r"^# .*workflows:", head, re.M) and "upload-artifact" in head):
        p.append("a comment must tell a product to list every artifact-uploading workflow "
                 "in `workflows:`")
    if not re.search(r"^# .*stable", head, re.M | re.I):
        p.append("a comment must say artifact names are stable per kind")
    return p


@test
def workflow_structure():
    text = WORKFLOW.read_text(encoding="utf-8")
    check("\r" not in text, "workflow must use LF line endings")
    check(text.startswith("name:"), "workflow must start with a name")
    problems = workflow_problems(text)
    check(not problems, "artifact-prune.yml: " + "; ".join(problems))
    # The workflow named in `workflows:` is the one the tracks really have.
    for track in TRACKS:
        ci = (TOOLING / track / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        check(re.search(r"^name:\s*CI\s*$", ci, re.M), f"{track} ci.yml `name:` is not CI")


@test
def workflow_checker_catches_each_defect():
    text = WORKFLOW.read_text(encoding="utf-8")
    cases = [
        ('workflows: ["CI", "Package"]', 'workflows: ["CI"]', "workflows: [\"CI\", \"Package\"]"),
        ("types: [completed]", "types: [requested]", "types: [completed]"),
        ("  schedule:\n    - cron: '23 3 * * *'\n", "", "schedule cron"),
        ("  workflow_dispatch:\n", "", "workflow_dispatch"),
        ("cron: '23 3 * * *'", "cron: '*/5 * * * *'", "once a day"),
        ("cancel-in-progress: false", "cancel-in-progress: true", "cancel-in-progress: false"),
        ("concurrency:\n  group: artifact-prune\n  cancel-in-progress: false\n", "",
         "concurrency group"),
        ("      actions: write\n", "", "actions: write"),
        ("      contents: read\n      actions: write\n", "      actions: write\n",
         "contents: read"),
        ("GH_TOKEN: ${{ github.token }}", "GH_TOKEN: ${{ secrets.PAT }}", "GH_TOKEN"),
        ("python3 scripts/delivery/artifact_prune.py", "python3 scripts/delivery/artifact_prune.py "
         "--dry-run", "dry run"),
        ("python3 scripts/delivery/artifact_prune.py", "python3 scripts/other.py", "must run"),
        ("actions/checkout@11d5960a326750d5838078e36cf38b85af677262", "actions/checkout@main", "pinned"),
        ("    timeout-minutes: 10\n", "", "timeout-minutes"),
        ("# PRODUCT: `workflows:` below must list", "# `below` must list", "must tell a product"),
        ("# Artifact names must be stable", "# Artifact names must be", "stable per kind"),
    ]
    for old, new, expect in cases:
        check(old in text, f"mutation anchor {old!r} missing from artifact-prune.yml")
        found = workflow_problems(text.replace(old, new, 1))
        check(any(expect in x for x in found),
              f"defect {old!r} -> {new!r} not detected (wanted {expect!r}); got {found}")
    # Job-level permissions swapped for write-all at the top is also rejected.
    top_write = text.replace("permissions:\n  contents: read\n\njobs:",
                             "permissions:\n  contents: read\n  actions: write\n\njobs:", 1)
    check(any("actions: write belongs on the job" in x for x in workflow_problems(top_write)),
          "workflow-level actions: write not detected")


@test
def upload_artifact_steps_use_stable_names():
    """Any upload-artifact step in a track ci.yml has a name that cannot vary per run."""
    def unstable(text: str) -> list[str]:
        bad = []
        for m in re.finditer(r"uses:\s*actions/upload-artifact@\S+[^\n]*\n((?:\s+(?:with:|[\w-]+:).*\n)+)",
                             text):
            name = re.search(r"^\s+name:\s*(.+)$", m.group(1), re.M)
            if not name:
                bad.append("upload-artifact without a name (defaults to `artifact`)")
            elif re.search(r"\$\{\{.*(sha|run_|run_number|run_id|version|ref|github\.event)", name.group(1)):
                bad.append(name.group(1).strip())
        return bad

    for track in TRACKS:
        text = (TOOLING / track / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        check(not unstable(text), f"{track} ci.yml: unstable artifact names {unstable(text)}")
    # The detector can fail.
    sample = ("      - uses: actions/upload-artifact@v4\n        with:\n"
              "          name: installer-${{ github.run_number }}\n          path: out/\n")
    check(unstable(sample), "unstable-name detector cannot fail")
    ok = sample.replace("-${{ github.run_number }}", "")
    check(not unstable(ok), "stable name wrongly rejected")


@test
def script_is_stdlib_python_with_no_bytecode():
    check(SOURCE.startswith("#!/usr/bin/env python3"), "missing shebang")
    check("sys.dont_write_bytecode = True" in SOURCE, "must set sys.dont_write_bytecode = True")
    imports = set(re.findall(r"^(?:import|from)\s+([A-Za-z_][\w]*)", SOURCE, re.M))
    stdlib = set(sys.stdlib_module_names)
    check(imports <= stdlib, f"non-stdlib imports: {sorted(imports - stdlib)}")
    check("shell=True" not in SOURCE, "gh must be called with an argument list, not a shell")
    check("\r" not in SOURCE, "script must use LF line endings")


# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# F7: the REST fallback never sends the token to a foreign host (DS163)
# ---------------------------------------------------------------------------
def load_script_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location("artifact_prune_under_test", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class FakeResp:
    def __init__(self, body: str, link: str = "") -> None:
        self._body = body
        self.headers = {"Link": link} if link else {}

    def read(self) -> bytes:
        return self._body.encode()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def run_rest(next_url: str, env: dict | None = None):
    """Page 1 links to `next_url`; returns (urls requested, result)."""
    mod = load_script_module()
    seen: list[tuple[str, str]] = []

    def fake_urlopen(req, timeout=None):
        seen.append((req.full_url, req.get_header("Authorization")))
        if len(seen) == 1:
            return FakeResp("[1]", f'<{next_url}>; rel="next"')
        return FakeResp("[2]")

    old_env = {k: os.environ.get(k) for k in ("GH_TOKEN", "GITHUB_API_URL")}
    old_open = mod.urllib.request.urlopen
    os.environ["GH_TOKEN"] = "secret-token"
    os.environ.pop("GITHUB_API_URL", None)
    os.environ.update(env or {})
    mod.urllib.request.urlopen = fake_urlopen
    try:
        res = mod.rest_call(["api", "--paginate", "repos/a/b/actions/artifacts"], 5)
    finally:
        mod.urllib.request.urlopen = old_open
        for k, v in old_env.items():
            os.environ.pop(k, None)
            if v is not None:
                os.environ[k] = v
    return seen, res


@test
def test_rest_fallback_refuses_a_foreign_next_host():
    for bad in ("https://evil.example/x?page=2", "http://api.github.com/x?page=2",
                "https://api.github.com.evil.example/x?page=2"):
        seen, res = run_rest(bad)
        check(len(seen) == 1, f"{bad}: a request was sent to the next URL: {seen}")
        check(res.returncode == 0, f"{bad}: paging should stop quietly, not fail")


@test
def test_rest_fallback_follows_a_normal_next_page():
    seen, res = run_rest("https://api.github.com/repos/a/b/actions/artifacts?page=2")
    check(len(seen) == 2 and seen[1][0].endswith("page=2"), f"page 2 not followed: {seen}")
    check(seen[1][1] == "Bearer secret-token", "page 2 sent without the token")


@test
def test_rest_fallback_allows_the_enterprise_host_from_github_api_url():
    url = "https://ghe.example/api/v3/repos/a/b/actions/artifacts?page=2"
    seen, _ = run_rest(url, {"GITHUB_API_URL": "https://ghe.example/api/v3"})
    check(len(seen) == 2, f"enterprise next page not followed: {seen}")
    seen, _ = run_rest("https://api.github.com/x?page=2", {"GITHUB_API_URL": "https://ghe.example/api/v3"})
    check(len(seen) == 1, "api.github.com should not be allowed when GITHUB_API_URL names another host")


def main() -> int:
    failed = 0
    for fn in TESTS:
        try:
            fn()
        except Exception:  # noqa: BLE001 - report every failing test
            failed += 1
            print(f"FAIL  {fn.__name__}")
            print("      " + traceback.format_exc().strip().replace("\n", "\n      "))
        else:
            print(f"ok    {fn.__name__}")
    print(f"\n{len(TESTS) - failed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
