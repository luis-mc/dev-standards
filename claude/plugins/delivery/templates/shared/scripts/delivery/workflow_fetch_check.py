#!/usr/bin/env python3
"""DL-94: CI jobs fetch pinned tools through the per-runner cache.

Usage:
    python3 scripts/delivery/workflow_fetch_check.py [FILES...]

Without FILES it reads .github/workflows/*.yml and *.yaml.

A step that downloads a release asset or binary is flagged when the download:
  1. does not go through ci_tool.py (a per-runner cache with retries), or
  2. writes into $RUNNER_TEMP / ${{ runner.temp }} (wiped every job), or
  3. has no sha256 check on the same step (sha256sum -c, Get-FileHash, --sha256).

A download is curl, wget, Invoke-WebRequest, iwr or urllib on a URL with
/releases/download/ or ending in .zip .tar.gz .tgz .exe .msi .xz.
Only `run:` blocks are read (plain text, no PyYAML).
A line opts out with a trailing comment `# ci-tool: ok <reason>`; the reason is required.

Output: one line per finding, `<file>:<line>: DL-94 <what> (<fix>)`.
Exit codes: 0 clean, 1 findings, 2 usage (a file cannot be read).
"""
import glob
import re
import sys

FIX = ('python3 scripts/delivery/ci_tool.py fetch <url> --sha256 <hex> --name <tool>/<version>/<file>')
URL_RE = re.compile(r'https?://[^\s\'"`)]+', re.I)
ASSET_RE = re.compile(r'/releases/download/|\.(?:zip|tar\.gz|tgz|exe|msi|xz)(?:[?#]|$)', re.I)
CMD_RE = re.compile(r'\b(?:curl|wget|invoke-webrequest|iwr)\b|urllib', re.I)
TEMP_RE = re.compile(r'\$\{?\{?\s*runner\.temp\s*\}?\}?|\$\{?RUNNER_TEMP\}?|\$env:RUNNER_TEMP|%RUNNER_TEMP%', re.I)
SHA_RE = re.compile(r'sha256sum|shasum\s+-a\s+256|Get-FileHash|--sha256|certutil[^\n]*sha256', re.I)
OPT_RE = re.compile(r'#\s*ci-tool:\s*ok\b(.*)$', re.I)
RUN_RE = re.compile(r'^(\s*)(?:-\s+)?run:\s*(.*)$')


def _indent(s):
    return len(s) - len(s.lstrip(' '))


def _run_blocks(lines):
    """Yield (first_line_no, [(line_no, text), ...]) for each run: step."""
    i, n = 0, len(lines)
    while i < n:
        m = RUN_RE.match(lines[i])
        if not m:
            i += 1
            continue
        key_col = len(m.group(1)) + (2 if lines[i].lstrip().startswith('-') else 0)
        rest = m.group(2).strip()
        block = []
        if rest and not rest.startswith(('|', '>')):
            block.append((i + 1, rest))
            i += 1
        else:
            i += 1
            while i < n and (not lines[i].strip() or _indent(lines[i]) > key_col):
                block.append((i + 1, lines[i].strip()))
                i += 1
        yield block


def _join(block):
    """Join backslash / backtick continuations into logical commands: (line_no, text)."""
    out, cur, start = [], '', None
    for no, text in block:
        if start is None:
            start = no
        if text.rstrip().endswith(('\\', '`')):
            cur += text.rstrip()[:-1] + ' '
            continue
        out.append((start, cur + text))
        cur, start = '', None
    if start is not None:
        out.append((start, cur))
    return out


def check_text(text, name='workflow.yml'):
    """Return a list of 'name:line: DL-94 ...' findings for the workflow text."""
    findings = []
    lines = text.splitlines()
    for block in _run_blocks(lines):
        cmds = _join(block)
        step_has_sha = any(SHA_RE.search(t) for _, t in cmds)
        step_via_tool = any('ci_tool.py' in t for _, t in cmds)
        for no, t in cmds:
            code = t
            opt = OPT_RE.search(t)
            if opt:
                if opt.group(1).strip():
                    continue
                findings.append('%s:%d: DL-94 "# ci-tool: ok" needs a reason (write "# ci-tool: ok <reason>")' % (name, no))
                continue
            if t.lstrip().startswith('#') or not CMD_RE.search(code):
                continue
            if not any(ASSET_RE.search(u) for u in URL_RE.findall(code)):
                continue
            if 'ci_tool.py' in code:
                continue
            probs = []
            if not step_via_tool:
                probs.append('download not through ci_tool.py')
            if TEMP_RE.search(code):
                probs.append('writes into RUNNER_TEMP, which is wiped every job')
            if not step_has_sha:
                probs.append('no sha256 check')
            if probs:
                findings.append('%s:%d: DL-94 %s (%s)' % (name, no, '; '.join(probs), FIX))
    return findings


def check_file(path):
    with open(path, encoding='utf-8') as fh:
        return check_text(fh.read(), path.replace('\\', '/'))


def main(argv):
    files = argv[1:]
    if any(a in ('-h', '--help') for a in files):
        print(__doc__)
        return 0
    if any(a.startswith('-') for a in files):
        print('usage: workflow_fetch_check.py [FILES...]', file=sys.stderr)
        return 2
    if not files:
        files = sorted(glob.glob('.github/workflows/*.yml') + glob.glob('.github/workflows/*.yaml'))
    found = []
    for f in files:
        try:
            found += check_file(f)
        except OSError as exc:
            print('workflow_fetch_check.py: cannot read %s (%s)' % (f, exc), file=sys.stderr)
            return 2
    for line in found:
        print(line)
    return 1 if found else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
