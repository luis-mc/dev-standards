#!/usr/bin/env python3
"""One-off converter: dev-standards' interim artifact record -> the ARTIFACTSPEC 1.0.0 record (section 4).

    python tools/convert_interim_record.py --build <old docs/artifacts/build> --out <new docs/artifacts>
                                           [--now 2026-10-10T14:30+01:00] [--clean]

The interim generator (build.py, content_artifacts.py, content_models.py, figures_models.py) held the
tasks and the content as Python. This script reads those modules (build.py is parsed, never run) and
writes manifest.json, registry.json and content/<key>/ in the plugin's format. It renders nothing:
`project_artifacts.py render --all` does that. With --clean it first deletes the interim files in --out
(build/, the three HTML files, README.md, the old manifest and registry).

Standard library only. It is kept in the repository as the record of how the conversion was made.
"""
import argparse
import ast
import html
import json
import os
import re
import shutil
import sys
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser

SPEC = 'ARTIFACTSPEC 1.0.0'
TZ_NAME, TZ_LABEL, WIN_TZ = 'Europe/Lisbon', 'Lisbon', 'GMT Standard Time'
OPEN = ('Running', 'Waiting', 'To do', 'Needs you', 'On hold', 'Failed')
MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

# Details over 600 characters (R4.8), shortened by hand, faithfully: ID -> new text.
SHORTENED = {}


class Text(HTMLParser):
    """HTML to plain text, whitespace collapsed."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def plain(markup):
    parser = Text()
    parser.feed(markup)
    parser.close()
    return re.sub(r'\s+', ' ', ''.join(parser.parts)).strip()


class Rows(HTMLParser):
    """The <td> cell markup of every body row of a table, as raw inner HTML."""

    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.rows, self.cell, self.row = [], None, None

    def handle_starttag(self, tag, attrs):
        if tag == 'tr':
            self.row = []
        elif tag == 'td' and self.row is not None:
            self.cell = []
        elif self.cell is not None:
            self.cell.append(self.get_starttag_text())

    def handle_endtag(self, tag):
        if tag == 'td' and self.cell is not None:
            self.row.append(''.join(self.cell))
            self.cell = None
        elif tag == 'tr' and self.row is not None:
            if self.row:
                self.rows.append(self.row)
            self.row = None
        elif self.cell is not None:
            self.cell.append('</%s>' % tag)

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)

    def handle_entityref(self, name):
        if self.cell is not None:
            self.cell.append('&%s;' % name)

    def handle_charref(self, name):
        if self.cell is not None:
            self.cell.append('&#%s;' % name)


def table_rows(markup):
    parser = Rows()
    parser.feed(markup)
    parser.close()
    return parser.rows


def slug(text):
    return re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8', newline='\n') as handle:
        handle.write(text)


def write_json(path, data):
    write(path, json.dumps(data, ensure_ascii=False, indent=2) + '\n')


def lisbon_zone():
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(TZ_NAME)
    except Exception:
        return None


def iso_at(zone, year, month, day, hour, minute):
    """ISO time with offset for a wall-clock time in Lisbon."""
    if zone is not None:
        moment = datetime(year, month, day, hour, minute, tzinfo=zone)
        offset = moment.utcoffset()
    else:  # no tz data: WEST (+01:00) from the last Sunday of March to the last Sunday of October
        offset = timedelta(hours=1 if 4 <= month <= 9 or (month == 10 and day < 25) else 0)
    sign = '+' if offset >= timedelta(0) else '-'
    total = abs(int(offset.total_seconds())) // 60
    return '%04d-%02d-%02dT%02d:%02d%s%02d:%02d' % (year, month, day, hour, minute, sign, total // 60, total % 60)


# ---------------------------------------------------------------- reading the interim generator
def load_modules(build_dir):
    sys.dont_write_bytecode = True
    sys.path.insert(0, build_dir)
    import content_artifacts
    import content_models
    return [content_artifacts, content_models]


def read_build_py(build_dir):
    """Project tasks and the full-progress content from build.py, by parsing it (it is a script)."""
    with open(os.path.join(build_dir, 'build.py'), encoding='utf-8') as handle:
        tree = ast.parse(handle.read())
    wanted = {'PROJECT_TASKS', 'p_lede', 'p_s2', 'FP_TITLE', 'FP_FILE', 'PROJECT'}
    values = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) \
                and node.targets[0].id in wanted:
            code = compile(ast.Expression(node.value), 'build.py', 'eval')
            values[node.targets[0].id] = eval(code, {'__builtins__': {'dict': dict}}, {})  # literals and dict() only
    hero = None
    for node in ast.walk(tree):  # progress = page(FP_TITLE, kind, label, <hero>, meta, sections, ...)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'page' \
                and node.args and isinstance(node.args[0], ast.Name) and node.args[0].id == 'FP_TITLE':
            hero = ast.literal_eval(node.args[3])
    missing = (wanted - set(values)) | ({'hero'} if hero is None else set())
    if missing:
        raise SystemExit('build.py: could not read %s' % ', '.join(sorted(missing)))
    values['hero'] = hero
    return values


def read_manifest(build_dir):
    with open(os.path.join(os.path.dirname(build_dir), 'manifest.json'), encoding='utf-8') as handle:
        return json.load(handle)


# ---------------------------------------------------------------- conversion rules
NOTHING_NEEDS_YOU = re.compile(r'\s*<strong>Nothing needs you(?: right now)?\.?</strong>(?: on this feature\.)?')


def inline_lede(markup, fp_url, notes, where):
    """meta.json lede: inline text. Drops the <p class="lede"> wrapper, the hand-typed 'Nothing needs you'
    (the renderer appends the needs-you sentence, R5.7) and turns {fp_link} into a link."""
    text = markup.strip()
    match = re.fullmatch(r'<p class="lede">(.*)</p>', text, re.S)
    if match:
        text = match.group(1)
    if NOTHING_NEEDS_YOU.search(text):
        notes.append('%s lede: removed the hand-typed "Nothing needs you" sentence (generated now, R5.7)' % where)
        text = NOTHING_NEEDS_YOU.sub('', text)
    text = text.replace('{fp_link}', '<a href="%s">Full Progress: dev-standards</a>' % fp_url)
    return re.sub(r'\s+', ' ', text).strip()


def convert(build_dir, out_dir, now_iso, clean):
    notes = []
    zone = lisbon_zone()
    modules = load_modules(build_dir)
    fp = read_build_py(build_dir)
    interim = read_manifest(build_dir)
    fp_url = interim['full_progress_artifact']['url']
    if not fp_url:
        raise SystemExit('the interim manifest has no full-progress URL')

    # the History stamp the interim generator used: the interim record's last update
    updated = datetime.fromisoformat(interim['updated'])
    history_stamp = '%02d %s %02d:%02d' % (updated.day, MONTHS[updated.month - 1], updated.hour, updated.minute)
    year = updated.year

    # tasks
    project_prefixes = list(interim['project_prefixes'])
    prefix_of = {m.KEY: m.PREFIX for m in modules}
    raw = []
    for t in fp['PROJECT_TASKS']:
        raw.append(dict(t, owner='project', app=t.get('app', 'luismc-project-setup')))
    for m in modules:
        for t in m.TASKS:
            if not t['id'].startswith(m.PREFIX):
                # R4.6: a task moved into a feature keeps its project prefix (DS2, DS5 in the models feature)
                if not re.match(r'^(%s)\d+$' % '|'.join(project_prefixes), t['id']):
                    raise SystemExit('%s: prefix is neither %s nor a project prefix' % (t['id'], m.PREFIX))
                notes.append('%s: stays owned by %s with its project-prefix ID (R4.6)' % (t['id'], m.KEY))
            raw.append(dict(t, owner=m.KEY, app=m.APP))
    tasks = []
    for t in raw:
        changed_expected = re.match(r'^(\d{2}) (%s)' % '|'.join(MONTHS), t['expected'])
        if t['status'] in OPEN:
            changed = now_iso
        else:
            if not changed_expected:
                raise SystemExit('%s: Live/Done task without a date in expected: %r' % (t['id'], t['expected']))
            changed = iso_at(zone, year, MONTHS.index(changed_expected.group(2)) + 1, int(changed_expected.group(1)), 12, 0)
        detail, item = t['detail'], t['item']
        for field, text in (('detail', detail), ('item', item)):
            if re.search(r'[<>]|&[a-z#0-9]+;', text):
                notes.append('%s %s: contains markup, converted to plain text' % (t['id'], field))
        detail, item = plain(detail), plain(item)
        if t['id'] in SHORTENED:
            notes.append('%s detail shortened from %d to %d characters' % (t['id'], len(detail), len(SHORTENED[t['id']])))
            detail = SHORTENED[t['id']]
        if len(detail) > 600:
            raise SystemExit('%s: detail is %d characters (> 600); add it to SHORTENED' % (t['id'], len(detail)))
        if len(item) > 80:
            raise SystemExit('%s: item is %d characters (> 80)' % (t['id'], len(item)))
        tasks.append({'id': t['id'], 'owner': t['owner'], 'app': t['app'], 'status': t['status'],
                      'item': item, 'detail': detail, 'expected': t['expected'], 'changed': changed})

    def sort_key(task):
        match = re.match(r'^([A-Z]+)(\d+)$', task['id'])
        return (match.group(1), int(match.group(2)))
    tasks.sort(key=sort_key)
    ids = [t['id'] for t in tasks]
    if len(ids) != len(set(ids)):
        raise SystemExit('duplicate task IDs')

    # manifest
    manifest = {
        'spec': SPEC,
        'project': fp['PROJECT'],
        'timezone': TZ_NAME,
        'timezone_label': TZ_LABEL,
        'windows_timezone': WIN_TZ,
        'design': interim['design'],
        'default_branch': 'main',
        'merged_status': 'Live',
        'full_progress_artifact': {'key': 'full-progress', 'title': fp['FP_TITLE'], 'url': fp_url,
                                   'file': fp['FP_FILE'], 'published_sha256': ''},
        'feature_artifacts': [
            {'key': m.KEY, 'title': m.TITLE, 'url': m.URL, 'file': m.SLUG + '.html', 'prefix': m.PREFIX,
             'apps': [m.APP], 'published_sha256': ''} for m in modules],
        'project_prefixes': project_prefixes,
        'updated': now_iso,
    }
    # The three artifacts are adopted: their URLs exist, the HTML published there was made by the interim
    # generator, so published_sha256 stays empty and `pending` lists them until they are published (R4.3).
    registry = {'spec': SPEC, 'updated': now_iso, 'tasks': tasks}

    if clean:
        for name in os.listdir(out_dir):
            path = os.path.join(out_dir, name)
            if name == 'build':
                shutil.rmtree(path)
            elif name in ('README.md', 'manifest.json', 'registry.json') or name.endswith('.html'):
                os.remove(path)
    write_json(os.path.join(out_dir, 'manifest.json'), manifest)
    write_json(os.path.join(out_dir, 'registry.json'), registry)

    # content: feature artifacts
    for m in modules:
        folder = os.path.join(out_dir, 'content', m.KEY)
        write_json(os.path.join(folder, 'meta.json'), {
            'title': m.TITLE, 'hero': m.HERO, 'lede': inline_lede(m.LEDE, fp_url, notes, m.KEY),
            'extra_css': m.EXTRA_CSS})
        number = 0
        for label, body in m.SECTIONS:
            if body is None:
                continue  # History: history.json
            number += 1
            write(os.path.join(folder, '%02d-%s.html' % (number, slug(label))), '<!-- title: %s -->\n%s\n' % (label, body.strip('\n')))
        rows = [{'date': plain(date), 'change': plain(change)} for date, change in table_rows(m.history(history_stamp))]
        write_json(os.path.join(folder, 'history.json'), rows)
        notes.append('%s: %d sections + History of %d rows' % (m.KEY, number, len(rows)))

    # content: the full-progress artifact. Its section 1 (Feature artifacts) is generated by the renderer;
    # only the later interim section (How it stays current) becomes a content file.
    folder = os.path.join(out_dir, 'content', 'full-progress')
    write_json(os.path.join(folder, 'meta.json'), {
        'title': fp['FP_TITLE'], 'hero': fp['hero'], 'lede': inline_lede(fp['p_lede'], fp_url, notes, 'full-progress'),
        'extra_css': ''})
    write(os.path.join(folder, '01-how-it-stays-current.html'),
          '<!-- title: How it stays current -->\n%s\n' % fp['p_s2'].strip('\n'))
    notes.append('full-progress: interim section 1 (Feature artifacts) dropped, generated now (R5.6); '
                 'section 2 -> content file 01')
    return notes


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--build', required=True, help='the interim docs/artifacts/build folder')
    parser.add_argument('--out', required=True, help='the docs/artifacts folder to write')
    parser.add_argument('--now', help='conversion time, ISO with offset (default: the real clock in Lisbon)')
    parser.add_argument('--clean', action='store_true', help='delete the interim files in --out first')
    args = parser.parse_args()
    build_dir = os.path.abspath(args.build)
    if args.now:
        now_iso = args.now
    else:
        zone = lisbon_zone()
        now = datetime.now(zone) if zone else datetime.now(timezone(timedelta(hours=1)))
        now_iso = iso_at(zone, now.year, now.month, now.day, now.hour, now.minute)
    for line in convert(build_dir, os.path.abspath(args.out), now_iso, args.clean):
        print(line)
    print('converted at', now_iso)


if __name__ == '__main__':
    main()
