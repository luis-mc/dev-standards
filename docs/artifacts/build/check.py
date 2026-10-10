"""Check the rendered artifacts in <out-dir>: python -I check.py <out-dir>

Checks every *.html in <out-dir> (the full-progress artifact and each feature artifact):
div balance, parse with html.parser, tiles equal checklist rows, checklist header columns
(4 on a feature artifact, 5 on the full-progress artifact), the embedded task registry
(parses; task count equals the full-progress rows), every SVG has role="img" and an aria-label,
and no literal hex colour in any inline style attribute. Exit 0 clean, 1 findings.
"""
import glob
import json
import os
import re
import sys
from html.parser import HTMLParser

VOID = {'meta', 'link', 'br', 'hr', 'img', 'input', 'col', 'area', 'base', 'wbr', 'source'}
SVG_VOID_OK = {'path', 'rect', 'line', 'circle', 'ellipse', 'polygon', 'polyline', 'text', 'defs', 'marker', 'use', 'g', 'tspan'}


class Scan(HTMLParser):
    def __init__(self):
        super().__init__()
        self.svgs = []
        self.styles = []
        self.stack = []
        self.errors = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'svg':
            self.svgs.append(a)
        if a.get('style') is not None:
            self.styles.append((tag, a['style']))
        if tag not in VOID and tag not in SVG_VOID_OK:
            self.stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        a = dict(attrs)
        if a.get('style') is not None:
            self.styles.append((tag, a['style']))

    def handle_endtag(self, tag):
        if tag in VOID or tag in SVG_VOID_OK:
            return
        if tag in self.stack:
            while self.stack and self.stack[-1] != tag:
                self.errors.append('unclosed <%s> before </%s>' % (self.stack.pop(), tag))
            self.stack.pop()
        else:
            self.errors.append('stray </%s>' % tag)


def check_file(path):
    name = os.path.basename(path)
    problems = []
    s = open(path, encoding='utf-8').read()
    is_fp = 'content="full-progress-artifact"' in s
    kind = 'full-progress' if is_fp else 'feature'

    def say(msg):
        print(' ', msg)

    print(name, '(%s)' % kind)
    divs, closes = len(re.findall(r'<div\b', s)), s.count('</div>')
    say('div %d / </div> %d' % (divs, closes))
    if divs != closes:
        problems.append('div balance')

    scan = Scan()
    scan.feed(s)
    scan.close()
    if scan.errors or scan.stack:
        problems.append('tag balance: %s' % (scan.errors[:3] + ['open: %s' % scan.stack[:3]]))
    say('html.parser ok, tag balance %s' % ('ok' if not (scan.errors or scan.stack) else 'FAIL'))

    rows = re.findall(r'<tr data-task="([^"]+)"><td><span class="status-chip [^"]+">([^<]+)</span>', s)
    counts = {}
    for _, st in rows:
        counts[st] = counts.get(st, 0) + 1
    tiles = {l: int(c) for c, l in re.findall(r'<div class="count">(\d+)</div><div class="label">([^<]+)</div>', s)}
    match = {k.lower(): v for k, v in counts.items()} == tiles
    say('rows %d %s | tiles %s | match %s' % (len(rows), counts, tiles, match))
    if not match:
        problems.append('tiles differ from rows')
    if len(set(r[0] for r in rows)) != len(rows):
        problems.append('duplicate task ids')

    m = re.search(r'<table class="status-checklist"><thead>(.*?)</thead>', s)
    cols = re.findall(r'<th>([^<]*)</th>', m.group(1)) if m else []
    want = 5 if is_fp else 4
    say('header columns %d (want %d) %s' % (len(cols), want, cols))
    if len(cols) != want:
        problems.append('header columns')
    spans = set(re.findall(r'status-group" data-group="\w+"><td colspan="(\d)"', s))
    if spans and spans != {str(want)}:
        problems.append('group colspan %s != %d' % (spans, want))

    reg = re.search(r'<script type="application/json" id="task-registry">(.*?)</script>', s, re.S)
    if is_fp:
        if not reg:
            problems.append('no registry in full-progress artifact')
        else:
            try:
                j = json.loads(reg.group(1).replace('<\\/', '</'))
                ok = len(j['tasks']) == len(rows)
                say('registry parses; tasks %d, rows %d, equal %s' % (len(j['tasks']), len(rows), ok))
                if not ok:
                    problems.append('registry count != rows')
                if set(t['id'] for t in j['tasks']) != set(r[0] for r in rows):
                    problems.append('registry ids != row ids')
            except Exception as exc:  # noqa: BLE001
                problems.append('registry does not parse: %s' % exc)
    elif reg:
        problems.append('feature artifact embeds a registry')

    bad_svg = [a for a in scan.svgs if a.get('role') != 'img' or not (a.get('aria-label') or '').strip()]
    say('svg %d, without role=img and aria-label: %d' % (len(scan.svgs), len(bad_svg)))
    if bad_svg:
        problems.append('svg role/aria-label')

    hexes = [(t, st) for t, st in scan.styles if re.search(r'#[0-9a-fA-F]{3,8}\b', st)]
    say('inline style attributes %d, with a literal hex colour: %d' % (len(scan.styles), len(hexes)))
    if hexes:
        problems.append('hex colour in inline style: %s' % hexes[:3])
    return problems


def main():
    out = sys.argv[1]
    files = sorted(glob.glob(os.path.join(out, '*.html')))
    findings = []
    if len(files) < 3:
        findings.append('expected at least 3 HTML files, found %d' % len(files))
    fp = [f for f in files if 'content="full-progress-artifact"' in open(f, encoding='utf-8').read()]
    if len(fp) != 1:
        findings.append('expected exactly one full-progress artifact, found %d' % len(fp))
    for f in files:
        for p in check_file(f):
            findings.append('%s: %s' % (os.path.basename(f), p))
    print('FINDINGS' if findings else 'CLEAN', *findings, sep='\n  ' if findings else ' ')
    return 1 if findings else 0


if __name__ == '__main__':
    sys.exit(main())
