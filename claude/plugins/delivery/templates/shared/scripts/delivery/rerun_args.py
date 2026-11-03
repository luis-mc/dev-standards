#!/usr/bin/env python3
"""Safe re-run of failed test files, for the test-report helper (CIR10, Windows).

A flaky-test re-run builds a command line from the files that failed. On Windows the
report holds absolute paths with backslashes and drive letters, and a naive split of an
option such as `--reporter=junit` loses the value. This module is the one place that:

  - turns every failed file into a path relative to the test root, with forward slashes
    (`rerun_paths`); a file outside the root is refused, never passed on;
  - keeps option values: `--name value` and `--name=value` stay as given (`split_args`);
  - separates a re-run that crashed before running a test from a second failure
    (`classify_rerun`): no test result and a non-zero exit is "crash", never "failed again".

Python 3.11+, standard library only.
"""
from __future__ import annotations

import ntpath
import posixpath
import sys

sys.dont_write_bytecode = True


def rerun_paths(files: list[str], root: str) -> list[str]:
    """Relative, forward-slash paths of `files` under `root`. Raises ValueError outside it."""
    if "\\" in root or (len(root) > 1 and root[1] == ":"):
        mod, sep = ntpath, "\\"
    else:
        mod, sep = posixpath, "/"
    base = mod.normcase(mod.normpath(root))
    out: list[str] = []
    for f in files:
        fmod = ntpath if ("\\" in f or (len(f) > 1 and f[1] == ":")) else posixpath
        full = f if fmod.isabs(f) else mod.join(root, f)
        full = mod.normcase(mod.normpath(full))
        rel = mod.relpath(full, base) if mod.splitdrive(full)[0] == mod.splitdrive(base)[0] else ".."
        rel = rel.replace("\\", "/")
        if rel == ".." or rel.startswith("../") or rel == ".":
            raise ValueError("%s is outside the test root %s" % (f, root))
        out.append(rel)
    return out


def split_args(options: list[str]) -> list[str]:
    """Option tokens kept as they are: `--k=v` stays one token, `--k v` stays two, in order."""
    out: list[str] = []
    for tok in options:
        if not isinstance(tok, str) or tok == "":
            continue
        out.append(tok)
    return out


def rerun_command(base: list[str], options: list[str], files: list[str], root: str) -> list[str]:
    """base command + options (values kept) + relative forward-slash files after `--`."""
    return [*base, *split_args(options), "--", *rerun_paths(files, root)]


def classify_rerun(exit_code: int, tests_run: int, failures: int) -> str:
    """'passed', 'failed' (a test ran and failed again) or 'crash' (nothing ran, exit != 0)."""
    if exit_code == 0 and failures == 0:
        return "passed"
    if tests_run == 0:
        return "crash"
    return "failed"
