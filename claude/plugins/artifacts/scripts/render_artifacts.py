"""Render project artifacts from the record (ARTIFACTSPEC 1.0.0, sections 4 to 6 and 14).

Pure functions: the record in (manifest, registry, content), HTML out, plus the checks
of section 14 that can be made on one artifact's HTML. Standard library only, Python 3.10+.

Public API (imported by project_artifacts.py):
    ContentError, load_content, artifact_file, render_artifact, check_html,
    structure_css, design_css, check_tokens, REQUIRED_TOKENS, STATUSES

Templates hold {{placeholders}}. Section 0 is in the template; its parts come from the
placeholders stamp, lede, tiles, key and checklist. The other placeholders are title,
fonts_link, design_css, structure_css, extra_css, kind_label, project, hero, contents,
sections, and registry (full-progress template only).
"""
from __future__ import annotations

import html as _html
import json
import os
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser

SPEC = 'ARTIFACTSPEC 1.0.0'
PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

STATUSES = ('Live', 'Built', 'Running', 'Needs you', 'Waiting', 'To do', 'On hold', 'Failed')
OPEN_STATUSES = ('Running', 'Waiting', 'To do', 'Needs you', 'On hold')  # R6.6
REQUIRED_TOKENS = (
    '--font-display', '--font-display-stretch', '--font-body', '--font-mono',
    '--paper', '--surface', '--surface-2', '--ink', '--ink-muted',
    '--rule', '--rule-strong',
    '--signal', '--on-signal', '--focus',
    '--live', '--on-live', '--done-bg', '--running-bg', '--running-mark',
    '--waiting-bg', '--failed', '--on-failed',
)
DARK_TOKENS = tuple(t for t in REQUIRED_TOKENS if not t.startswith('--font'))  # fonts need no dark value

KIND_PREFIX = {'feature': 'Feature: ', 'full-progress': 'Full Progress: '}
KIND_LABEL = {'feature': 'Feature artifact', 'full-progress': 'Full-progress artifact'}
FULL_PROGRESS_NAME = 'full-progress'
EARLIER_DAYS = 14  # R6.3; may only be lengthened (section 12)
MONTHS = ('Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec')

GROUPS = (
    ('now', 'Running now and next', ('Running', 'Waiting', 'To do')),
    ('you', 'Needs you, failed or on hold', ('Needs you', 'Failed', 'On hold')),
    ('built', 'Live or built', ('Live', 'Built')),
)
YOU_ORDER = ('Needs you', 'Failed', 'On hold')

EXPECTED_RE = re.compile(
    r'^(0[1-9]|[12]\d|3[01]) (' + '|'.join(MONTHS) + r')(?: ~([01]\d|2[0-3]):([0-5]\d))?(?:; \S.*)?$')
STAMP_TEXT_RE = re.compile(r'^(\d{2}) (' + '|'.join(MONTHS) + r') (\d{2}):(\d{2})$')
ISO_OFFSET_RE = re.compile(r'^\d{4}-\d\d-\d\dT\d\d:\d\d(:\d\d)?[+-]\d\d:\d\d$')
TASK_ID_RE = re.compile(r'^([A-Z]{2,5})(\d+)$')


class ContentError(Exception):
    """The record cannot be rendered. `.problems` lists every problem found."""

    def __init__(self, problems):
        if isinstance(problems, str):
            problems = [problems]
        self.problems = list(problems)
        super().__init__('; '.join(self.problems))


# ------------------------------------------------------------------ small helpers
def esc(value) -> str:
    return _html.escape(str(value), quote=True)


def _read(path: str) -> str:
    with open(path, 'rb') as handle:
        return handle.read().decode('utf-8-sig').replace('\r\n', '\n')


def _norm(text: str) -> str:
    return ' '.join(str(text).split())


def status_class(status: str) -> str:
    return 'status-' + status.lower().replace(' ', '-')


def _parse_iso(value, default=None):
    """Aware datetime from an ISO string; naive values count as UTC; default when unparsable."""
    try:
        text = str(value).strip()
        if text.endswith('Z'):
            text = text[:-1] + '+00:00'
        parsed = datetime.fromisoformat(text)
    except (ValueError, TypeError):
        return default
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _expected_datetime(expected: str, ref: datetime):
    """Naive datetime of an Expected value ('DD Mon' or 'DD Mon ~HH:MM'), or None. Year follows `ref`."""
    match = EXPECTED_RE.match(str(expected))
    if not match:
        return None
    day, month = int(match.group(1)), MONTHS.index(match.group(2)) + 1
    hour, minute = (int(match.group(3)), int(match.group(4))) if match.group(3) else (23, 59)
    base = ref.replace(tzinfo=None)
    best = None
    for year in (base.year - 1, base.year, base.year + 1):
        try:
            candidate = datetime(year, month, day, hour, minute)
        except ValueError:
            return None
        if best is None or abs(candidate - base) < abs(best - base):
            best = candidate
    return best


def _fmt_stamp(moment: datetime) -> str:
    return '%02d %s %02d:%02d' % (moment.day, MONTHS[moment.month - 1], moment.hour, moment.minute)


# ------------------------------------------------------------------ files
def structure_css(plugin_dir: str = PLUGIN_DIR) -> str:
    """The fixed structure stylesheet, line endings normalised to LF."""
    return _read(os.path.join(plugin_dir, 'templates', 'project-artifact.css'))


def design_css(manifest: dict, plugin_dir: str = PLUGIN_DIR, record_dir: str = '') -> str:
    """The token block: the project's design.css when the manifest says so, else the plugin default (R5.10)."""
    choice = manifest.get('design', 'default')
    if choice == 'default':
        path = os.path.join(plugin_dir, 'design', 'default-design.css')
    elif choice == 'design.css':
        path = os.path.join(record_dir, 'design.css')
    else:
        raise ContentError('manifest design is %r; it must be "default" or "design.css"' % (choice,))
    try:
        return _read(path)
    except OSError as exc:
        raise ContentError('design file not readable: %s' % exc) from exc


def _template(plugin_dir: str, kind: str) -> str:
    name = 'feature-artifact.html' if kind == 'feature' else 'full-progress-artifact.html'
    return _read(os.path.join(plugin_dir, 'templates', name))


def artifact_file(kind: str, title: str) -> str:
    """R4.4: `<kind>-<slug>.html`; the slug is the title's words, lowercase, hyphenated."""
    if kind not in KIND_PREFIX:
        raise ValueError('kind must be "feature" or "full-progress", got %r' % (kind,))
    name = str(title).strip()
    for prefix in KIND_PREFIX.values():
        if name.startswith(prefix):
            name = name[len(prefix):]
            break
    folded = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode('ascii')
    slug = re.sub(r'[^a-z0-9]+', '-', folded.lower()).strip('-')
    if not slug:
        raise ValueError('title %r has no letters or digits to make a file name from' % (title,))
    return '%s-%s.html' % (kind, slug)


# ------------------------------------------------------------------ CSS reading
def _strip_comments(css: str) -> str:
    return re.sub(r'/\*.*?\*/', '', css, flags=re.S)


def _split_declarations(body: str) -> dict:
    out, depth, quote, start = {}, 0, '', 0
    parts = []
    for i, char in enumerate(body):
        if quote:
            if char == quote:
                quote = ''
        elif char in '"\'':
            quote = char
        elif char == '(':
            depth += 1
        elif char == ')':
            depth = max(0, depth - 1)
        elif char == ';' and depth == 0:
            parts.append(body[start:i])
            start = i + 1
    parts.append(body[start:])
    for part in parts:
        if ':' in part:
            name, value = part.split(':', 1)
            out[name.strip()] = value.strip()
    return out


def _parse_rules(css: str, context: str = '') -> list:
    """[(context, selector text, {property: value})]; rules inside @media and similar keep their context."""
    rules, i, n = [], 0, len(css)
    while i < n:
        j = css.find('{', i)
        if j < 0:
            break
        prelude = css[i:j].split(';')[-1].strip()
        depth, k = 1, j + 1
        while k < n and depth:
            depth += (css[k] == '{') - (css[k] == '}')
            k += 1
        body = css[j + 1:k - 1]
        if prelude.startswith('@'):
            if prelude.split()[0].lower() in ('@media', '@supports', '@layer', '@container'):
                rules += _parse_rules(body, (context + ' ' + _norm(prelude)).strip())
        elif prelude:
            rules.append((context, _norm(prelude), _split_declarations(body)))
        i = k
    return rules


def _selectors(css: str) -> set:
    found = set()
    for _, selector, _ in _parse_rules(_strip_comments(css)):
        for part in selector.split(','):
            found.add(_norm(part))
    return found


def check_tokens(css: str) -> list:
    """R5.11: problems of a token block against the contract in design/DESIGN.md; [] when complete."""
    rules = _parse_rules(_strip_comments(css))
    problems = []
    dark_media = re.compile(r'\(\s*prefers-color-scheme\s*:\s*dark\s*\)')

    def defined(match):
        names = set()
        for context, selector, decls in rules:
            if match(context, [_norm(p).replace("'", '"') for p in selector.split(',')]):
                names.update(k for k, v in decls.items() if k.startswith('--') and v)
        return names

    light = defined(lambda c, s: c == '' and ':root' in s)
    dark_media_set = defined(lambda c, s: bool(dark_media.search(c)) and ':root:not([data-theme="light"])' in s)
    dark_attr = defined(lambda c, s: c == '' and ':root[data-theme="dark"]' in s)
    for name in REQUIRED_TOKENS:
        if name not in light:
            problems.append('token %s is not defined on :root' % name)
    for name in DARK_TOKENS:
        if name not in dark_media_set:
            problems.append('token %s has no dark value under @media (prefers-color-scheme: dark) :root:not([data-theme="light"])' % name)
        if name not in dark_attr:
            problems.append('token %s has no dark value under :root[data-theme="dark"]' % name)
    return problems


# ------------------------------------------------------------------ a small DOM (html.parser based)
VOID = frozenset({'meta', 'link', 'br', 'hr', 'img', 'input', 'col', 'area', 'base', 'wbr', 'source', 'track', 'embed'})
# Tags whose end tag may not be omitted; used to catch unbalanced content fragments.
STRICT_TAGS = frozenset({'div', 'section', 'article', 'aside', 'span', 'a', 'table', 'details', 'ul', 'ol', 'pre',
                         'code', 'strong', 'em', 'blockquote', 'figure', 'svg', 'nav', 'main', 'header', 'footer',
                         'button', 'summary', 'figcaption'})


class Node:
    __slots__ = ('tag', 'attrs', 'children', 'parent', 'text')

    def __init__(self, tag, attrs=None, parent=None, text=''):
        self.tag, self.attrs, self.parent, self.text = tag, attrs or {}, parent, text
        self.children = []


class _Builder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node('#root')
        self.cur = self.root

    def handle_starttag(self, tag, attrs):
        node = Node(tag, {k: (v if v is not None else '') for k, v in attrs}, self.cur)
        self.cur.children.append(node)
        if tag not in VOID:
            self.cur = node

    def handle_startendtag(self, tag, attrs):
        self.cur.children.append(Node(tag, {k: (v if v is not None else '') for k, v in attrs}, self.cur))

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        node = self.cur
        while node is not self.root:
            if node.tag == tag:
                self.cur = node.parent
                return
            node = node.parent

    def handle_data(self, data):
        self.cur.children.append(Node('#text', parent=self.cur, text=data))


def parse_dom(markup: str) -> Node:
    builder = _Builder()
    builder.feed(markup)
    builder.close()
    return builder.root


def elements(node):
    for child in node.children:
        if child.tag != '#text':
            yield child
            yield from elements(child)


def has_class(node, name) -> bool:
    return name in node.attrs.get('class', '').split()


def find_all(node, tag=None, cls=None, pred=None) -> list:
    return [n for n in elements(node)
            if (tag is None or n.tag == tag) and (cls is None or has_class(n, cls)) and (pred is None or pred(n))]


def find(node, tag=None, cls=None, pred=None):
    found = find_all(node, tag, cls, pred)
    return found[0] if found else None


def text_of(node, skip=None) -> str:
    parts = []

    def walk(current):
        for child in current.children:
            if child.tag == '#text':
                parts.append(child.text)
            elif not (skip and skip(child)):
                walk(child)
    walk(node)
    return _norm(''.join(parts))


def has_ancestor(node, pred) -> bool:
    current = node.parent
    while current is not None:
        if pred(current):
            return True
        current = current.parent
    return False


# ------------------------------------------------------------------ content (R4.4, R4.10, R4.11)
SECTION_FILE_RE = re.compile(r'^(\d{2})-([a-z0-9]+(?:-[a-z0-9]+)*)\.html$')
TITLE_COMMENT_RE = re.compile(r'^\s*<!--\s*title:\s*(.*?)\s*-->[ \t]*\n?', re.S)
SECTION_NUMBER_TEXT_RE = re.compile(r'§\s*\d')
TITLE_NUMBER_RE = re.compile(r'^\s*(§|\d+\s*[.):\-–])')


class _Fragment(HTMLParser):
    """Scans a content fragment for what R4.10 forbids and for unbalanced tags."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.problems = []
        self.stack = []

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'):
            self.problems.append('<%s> is not allowed in content (R4.10)' % tag)
        if 'section-number' in (dict(attrs).get('class') or '').split():
            self.problems.append('a section number element is not allowed; the renderer numbers sections (R4.10)')
        if tag in STRICT_TAGS:
            self.stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        if tag in ('script', 'style'):
            self.problems.append('<%s> is not allowed in content (R4.10)' % tag)

    def handle_endtag(self, tag):
        if tag not in STRICT_TAGS:
            return
        if tag in self.stack:
            while self.stack[-1] != tag:
                self.problems.append('<%s> is not closed before </%s>' % (self.stack.pop(), tag))
            self.stack.pop()
        else:
            self.problems.append('</%s> has no opening tag' % tag)

    def handle_data(self, data):
        if SECTION_NUMBER_TEXT_RE.search(data):
            self.problems.append('a section number ("%s") is not allowed; the renderer numbers sections (R4.10)'
                                 % SECTION_NUMBER_TEXT_RE.search(data).group(0))

    def finish(self):
        self.close()
        for tag in self.stack:
            self.problems.append('<%s> is not closed' % tag)
        return list(dict.fromkeys(self.problems))


def _scan_fragment(markup: str) -> list:
    scanner = _Fragment()
    scanner.feed(markup)
    return scanner.finish()


def load_content(record_dir: str, key: str, plugin_dir: str = PLUGIN_DIR) -> dict:
    """Read and validate content/<key>/ of the record (R4.4, R4.10, R4.11).

    Returns {"meta": {title, hero, lede, extra_css}, "sections": [{title, html}], "history": [{date, change}]}.
    Raises ContentError listing every problem.
    """
    folder = os.path.join(record_dir, 'content', key)
    problems = []
    if not os.path.isdir(folder):
        raise ContentError('content/%s/ does not exist' % key)

    meta = {'title': '', 'hero': '', 'lede': '', 'extra_css': ''}
    meta_path = os.path.join(folder, 'meta.json')
    try:
        loaded = json.loads(_read(meta_path))
        if not isinstance(loaded, dict):
            raise ValueError('meta.json must hold an object')
    except (OSError, ValueError) as exc:
        problems.append('content/%s/meta.json: %s' % (key, exc))
        loaded = {}
    for field in ('title', 'hero', 'lede'):
        value = loaded.get(field)
        if not isinstance(value, str) or not value.strip():
            if loaded:
                problems.append('content/%s/meta.json: "%s" must be a non-empty string' % (key, field))
        else:
            meta[field] = value.strip()
    extra = loaded.get('extra_css', '')
    if not isinstance(extra, str):
        problems.append('content/%s/meta.json: "extra_css" must be a string' % key)
    else:
        meta['extra_css'] = extra
    for field in ('hero', 'lede'):
        value = meta[field]
        for tag in ('script', 'style', 'p', 'div', 'table', 'section', 'h1', 'h2', 'h3', 'ul', 'ol'):
            if re.search(r'<%s[\s>/]' % tag, value, re.I):
                problems.append('content/%s/meta.json: "%s" is inline text; <%s> is not allowed (R4.10)' % (key, field, tag))
        for issue in _scan_fragment(value):
            problems.append('content/%s/meta.json "%s": %s' % (key, field, issue))
    if re.search(r'</style|<script', meta['extra_css'], re.I):
        problems.append('content/%s/meta.json: extra_css must hold CSS only (R4.10)' % key)
    else:
        try:
            redefined = sorted(_selectors(meta['extra_css']) & _selectors(structure_css(plugin_dir)))
        except OSError as exc:
            redefined = []
            problems.append('structure stylesheet not readable: %s' % exc)
        for selector in redefined:
            problems.append('content/%s/meta.json: extra_css redefines the structure selector "%s" (R4.11)' % (key, selector))

    sections, numbers = [], []
    for name in sorted(os.listdir(folder)):
        if name in ('meta.json', 'history.json'):
            continue
        match = SECTION_FILE_RE.match(name)
        if not name.endswith('.html'):
            problems.append('content/%s/%s: not a content file (sections are NN-slug.html)' % (key, name))
            continue
        if not match:
            problems.append('content/%s/%s: the name must be NN-slug.html, e.g. 01-what-and-why.html' % (key, name))
            continue
        number = int(match.group(1))
        numbers.append(number)
        try:
            raw = _read(os.path.join(folder, name))
        except OSError as exc:
            problems.append('content/%s/%s: %s' % (key, name, exc))
            continue
        head = TITLE_COMMENT_RE.match(raw)
        if not head or not head.group(1):
            problems.append('content/%s/%s: the first line must be <!-- title: Section title -->' % (key, name))
            continue
        title, body = head.group(1), raw[head.end():].strip('\n')
        if TITLE_NUMBER_RE.match(title):
            problems.append('content/%s/%s: the title "%s" starts with a section number; the renderer numbers sections (R4.10)'
                            % (key, name, title))
        for issue in _scan_fragment(body):
            problems.append('content/%s/%s: %s' % (key, name, issue))
        sections.append({'title': title, 'html': body + '\n' if body else ''})
    if numbers != list(range(1, len(numbers) + 1)):
        problems.append('content/%s: section files must be numbered 01..NN without gaps or repeats, found %s'
                        % (key, ', '.join('%02d' % n for n in numbers) or 'none'))

    history = []
    history_path = os.path.join(folder, 'history.json')
    if os.path.exists(history_path):
        if key == FULL_PROGRESS_NAME:
            problems.append('content/%s/history.json: the full-progress artifact has no History (R5.4)' % key)
        else:
            try:
                rows = json.loads(_read(history_path))
                if not isinstance(rows, list):
                    raise ValueError('history.json must hold a list')
                for index, row in enumerate(rows, 1):
                    if not (isinstance(row, dict) and isinstance(row.get('date'), str) and isinstance(row.get('change'), str)
                            and row['date'].strip() and row['change'].strip()):
                        problems.append('content/%s/history.json: row %d needs non-empty "date" and "change" strings' % (key, index))
                    else:
                        history.append({'date': row['date'].strip(), 'change': row['change'].strip()})
            except (OSError, ValueError) as exc:
                problems.append('content/%s/history.json: %s' % (key, exc))
    if problems:
        raise ContentError(problems)
    return {'meta': meta, 'sections': sections, 'history': history}


# ------------------------------------------------------------------ the record: kinds and tasks
def _kind_entry(manifest: dict, key: str):
    full = manifest.get('full_progress_artifact') or {}
    if key == full.get('key', FULL_PROGRESS_NAME) and full:
        return 'full-progress', full
    for entry in manifest.get('feature_artifacts') or []:
        if entry.get('key') == key:
            return 'feature', entry
    raise ContentError('artifact key %r is not in the manifest' % (key,))


def _tasks(registry: dict) -> list:
    problems, tasks = [], list(registry.get('tasks') or [])
    for task in tasks:
        if task.get('status') not in STATUSES:
            problems.append('task %s has status %r; the eight statuses are %s (R6.1)'
                            % (task.get('id', '?'), task.get('status'), ', '.join(STATUSES)))
        for field in ('id', 'item', 'detail', 'expected'):
            if not isinstance(task.get(field), str):
                problems.append('task %s: "%s" must be a string' % (task.get('id', '?'), field))
    if problems:
        raise ContentError(problems)
    return tasks


def _tasks_of(kind: str, key: str, tasks: list) -> list:
    return tasks if kind == 'full-progress' else [t for t in tasks if t.get('owner') == key]


def group_tasks(tasks: list, ref: datetime, kind: str) -> list:
    """R6.2 and R6.3: [(group key, group title, shown tasks, folded tasks)], empty groups omitted."""
    out = []
    for gkey, title, statuses in GROUPS:
        mine = [t for t in tasks if t['status'] in statuses]
        if gkey == 'now':
            def when(task):
                moment = _expected_datetime(task['expected'], ref)
                return (1, datetime.max) if moment is None else (0, moment)
            mine = sorted(mine, key=when)
        elif gkey == 'you':
            mine = sorted(mine, key=lambda t: YOU_ORDER.index(t['status']))
        else:
            floor = datetime.min.replace(tzinfo=timezone.utc)
            mine = sorted(mine, key=lambda t: _parse_iso(t.get('changed'), floor), reverse=True)
        folded = []
        if gkey == 'built' and kind == 'full-progress':
            cutoff = ref - timedelta(days=EARLIER_DAYS)
            folded = [t for t in mine if (_parse_iso(t.get('changed')) or ref) < cutoff]
            mine = [t for t in mine if t not in folded]
        if mine or folded:
            out.append((gkey, title, mine, folded))
    return out


def needs_you_sentence(tasks: list) -> str:
    """R5.7."""
    waiting = [t for t in sorted(tasks, key=lambda t: YOU_ORDER.index(t['status']) if t['status'] in YOU_ORDER else 9)
               if t['status'] in ('Needs you', 'Failed')]
    if not waiting:
        return 'Nothing needs you.'
    return 'Needs you: ' + '; '.join('%s %s' % (t['id'], _norm(t['item'])) for t in waiting) + '.'


def _first_sentence(lede_html: str) -> str:
    node = parse_dom(lede_html)
    text = text_of(node)
    match = re.match(r'(.+?[.!?])(?=\s|$)', text)
    return match.group(1) if match else text


def _id_ranges(key: str, prefix: str, tasks: list) -> str:
    by_prefix = {}
    for task in tasks:
        if task.get('owner') != key:
            continue
        match = TASK_ID_RE.match(task['id'])
        if match:
            by_prefix.setdefault(match.group(1), []).append(int(match.group(2)))
    if not by_prefix:
        return 'No tasks yet'
    out = []
    for pre in sorted(by_prefix, key=lambda p: (p != prefix, p)):
        numbers = by_prefix[pre]
        out.append('%s%d' % (pre, min(numbers)) if min(numbers) == max(numbers)
                   else '%s%d to %s%d' % (pre, min(numbers), pre, max(numbers)))
    return ', '.join(out)


# ------------------------------------------------------------------ rendering pieces
def _chip(status: str) -> str:
    return '<span class="status-chip %s">%s</span>' % (status_class(status), status)


def _fonts_link(design: str) -> str:
    match = re.search(r'https://fonts\.googleapis\.com/css2\?[^\s"\'<>)]+', design)
    if not match:
        return ''
    return ('<link rel="preconnect" href="https://fonts.googleapis.com">\n'
            '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
            '<link rel="stylesheet" href="%s">' % esc(match.group(0)))


def _columns(kind: str, label: str) -> list:
    base = ['Status', 'Item'] + (['App / service'] if kind == 'full-progress' else []) + ['Detail']
    return base + ['Expected (%s)' % label]


def _row(task: dict, kind: str, feature_urls: dict) -> str:
    item = '<span class="task-id">%s</span>%s' % (esc(task['id']), esc(task['item']))
    url = feature_urls.get(task.get('owner'), '') if kind == 'full-progress' else ''
    if url:
        item = '<a href="%s">%s</a>' % (esc(url), item)
    app = '<td>%s</td>' % ('<code>%s</code>' % esc(task['app']) if task.get('app') else '') if kind == 'full-progress' else ''
    return '<tr data-task="%s"><td>%s</td><td>%s</td>%s<td>%s</td><td>%s</td></tr>' % (
        esc(task['id']), _chip(task['status']), item, app, esc(task['detail']), esc(task['expected']))


def _table(body_rows: list, kind: str, label: str) -> str:
    head = ''.join('<th>%s</th>' % esc(c) for c in _columns(kind, label))
    return ('<div class="table-scroll"><table class="status-checklist"><thead><tr>%s</tr></thead><tbody>\n%s\n</tbody></table></div>'
            % (head, '\n'.join(body_rows)))


def _checklist(tasks: list, kind: str, label: str, ref: datetime, feature_urls: dict) -> str:
    groups = group_tasks(tasks, ref, kind)
    width = len(_columns(kind, label))
    rows, folded = [], []
    for gkey, title, shown, old in groups:
        if shown:
            rows.append('<tr class="status-group" data-group="%s"><td colspan="%d"><strong>%s</strong></td></tr>'
                        % (gkey, width, esc(title)))
            rows += [_row(t, kind, feature_urls) for t in shown]
        folded += old
    out = _table(rows, kind, label) if rows or not folded else ''
    if folded:
        out += ('\n<details class="earlier"><summary>Earlier</summary>\n%s\n</details>'
                % _table([_row(t, kind, feature_urls) for t in folded], kind, label))
    return out


def _tiles(tasks: list) -> str:
    counts = {s: 0 for s in STATUSES}
    for task in tasks:
        counts[task['status']] += 1
    return '<div class="status-count-tiles">' + ''.join(
        '<div class="status-count-tile %s"><div class="count">%d</div><div class="label">%s</div></div>'
        % (status_class(s), counts[s], s.lower()) for s in STATUSES if counts[s]) + '</div>'


def _key(label: str) -> str:
    return ('<p class="note">Key: ' + ' · '.join(_chip(s) for s in STATUSES)
            + '. Times are %s time; each estimate names what sets it.</p>' % esc(label))


def _section(number: int, title: str, inner: str) -> str:
    return ('<section id="s%d"><h2><span class="section-number">&sect; %d</span>%s</h2>\n%s</section>'
            % (number, number, esc(title), inner))


def _history(rows: list) -> str:
    body = '\n'.join('<tr><td>%s</td><td>%s</td></tr>' % (esc(r['date']), esc(r['change'])) for r in rows)
    return ('<div class="table-scroll"><table class="history-table"><thead><tr><th>Date</th><th>Change</th></tr></thead>'
            '<tbody>\n%s\n</tbody></table></div>\n' % body)


def _feature_section(manifest: dict, tasks: list, contents: dict, problems: list) -> str:
    rows = []
    for entry in manifest.get('feature_artifacts') or []:
        content = contents.get(entry['key'])
        if content is None:
            problems.append('no content loaded for feature artifact %r (needed for R5.6)' % entry['key'])
            continue
        title = esc(entry['title'])
        link = '<a href="%s">%s</a>' % (esc(entry['url']), title) if entry.get('url') else title
        rows.append('<tr><td>%s</td><td>%s</td><td>%s</td></tr>' % (
            link, esc(_id_ranges(entry['key'], entry.get('prefix', ''), tasks)),
            esc(_first_sentence(content['meta']['lede']))))
    return ('<div class="table-scroll"><table class="feature-list"><thead><tr><th>Feature artifact</th><th>Tasks</th>'
            '<th>Where it stands</th></tr></thead><tbody>\n%s\n</tbody></table></div>\n' % '\n'.join(rows))


def _registry_script(registry: dict) -> str:
    text = json.dumps(registry, ensure_ascii=False, indent=1).replace('</', '<\\/').replace('<!--', '\\u003c!--')
    return '<script type="application/json" id="task-registry">%s</script>\n' % text


def _fill(template: str, values: dict) -> str:
    def replace(match):
        name = match.group(1)
        if name not in values:
            raise ContentError('template placeholder {{%s}} has no value' % name)
        return values[name]
    return re.sub(r'\{\{(\w+)\}\}', replace, template)


def render_artifact(manifest: dict, registry: dict, contents: dict, key: str, plugin_dir: str,
                    record_dir: str, stamp_text: str, stamp_iso: str) -> str:
    """The artifact's HTML, a fragment beginning with <title>. Same inputs, same bytes (R7.4)."""
    kind, entry = _kind_entry(manifest, key)
    problems = []
    title = str(entry.get('title', ''))
    if not title.startswith(KIND_PREFIX[kind]) or not title[len(KIND_PREFIX[kind]):].strip():
        problems.append('title %r must start with "%s" and name the artifact (R5.1)' % (title, KIND_PREFIX[kind]))
    label = str(manifest.get('timezone_label', '')).strip()
    if not label:
        problems.append('manifest timezone_label is missing (R5.5)')
    moment = _parse_iso(stamp_iso)
    if moment is None or not ISO_OFFSET_RE.match(str(stamp_iso)):
        problems.append('stamp_iso %r must be an ISO time with an offset, e.g. 2026-10-10T12:39+01:00 (R5.5)' % (stamp_iso,))
    elif not STAMP_TEXT_RE.match(str(stamp_text)):
        problems.append('stamp_text %r must read DD Mon HH:MM (R5.5)' % (stamp_text,))
    else:
        wall = datetime.fromisoformat(str(stamp_iso))
        if _fmt_stamp(wall) != stamp_text:
            problems.append('stamp_text %r does not match stamp_iso %r (R5.5)' % (stamp_text, stamp_iso))
    content = contents.get(key)
    if content is None:
        problems.append('no content loaded for %r' % key)
    try:
        tasks = _tasks(registry)
    except ContentError as exc:
        problems += exc.problems
        tasks = []
    try:
        design = design_css(manifest, plugin_dir, record_dir)
        structure = structure_css(plugin_dir)
        template = _template(plugin_dir, kind)
    except (ContentError, OSError) as exc:
        problems += exc.problems if isinstance(exc, ContentError) else [str(exc)]
        design = structure = template = ''
    else:
        problems += ['design: ' + p for p in check_tokens(design)]
        for name, css in (('design', design), ('structure', structure)):
            if re.search(r'</style', css, re.I):
                problems.append('%s stylesheet contains </style' % name)
    if content is not None and re.search(r'</style', content['meta']['extra_css'], re.I):
        problems.append('extra_css contains </style (R4.10)')
    if problems:
        raise ContentError(problems)

    mine = _tasks_of(kind, key, tasks)
    feature_urls = {e['key']: e.get('url', '') for e in manifest.get('feature_artifacts') or []}
    project = str(manifest.get('project', ''))
    meta = content['meta']

    sentence = needs_you_sentence(mine)
    lede = '<p class="lede">%s<strong>%s</strong></p>' % (meta['lede'] + ' ' if meta['lede'] else '', esc(sentence))

    sections = []  # (title, inner html) for sections 1..N
    if kind == 'full-progress':
        feature_problems = []
        sections.append(('Feature artifacts', _feature_section(manifest, tasks, contents, feature_problems)))
        if feature_problems:
            raise ContentError(feature_problems)
    sections += [(s['title'], s['html']) for s in content['sections']]
    if kind == 'feature':
        sections.append(('History', _history(content['history'])))

    all_titles = ['Status and checklist'] + [t for t, _ in sections]
    nav = ''.join('<a href="#s%d"><b>%d</b>%s</a>' % (i, i, esc(t)) for i, t in enumerate(all_titles))
    body = '\n'.join(_section(i, t, inner) for i, (t, inner) in enumerate(sections, 1))
    ref = moment

    values = {
        'title': esc(title),
        'fonts_link': _fonts_link(design),
        'design_css': design,
        'structure_css': structure,
        'extra_css': meta['extra_css'],
        'kind_label': KIND_LABEL[kind],
        'project': esc(project),
        'hero': meta['hero'],
        'contents': nav,
        'stamp': '<time datetime="%s">%s</time> (%s)' % (esc(stamp_iso), esc(stamp_text), esc(label)),
        'lede': lede,
        'tiles': _tiles(mine),
        'key': _key(label),
        'checklist': _checklist(mine, kind, label, ref, feature_urls),
        'sections': body,
        'registry': _registry_script(registry) if kind == 'full-progress' else '',
    }
    out = _fill(template, values)
    return out if out.endswith('\n') else out + '\n'


# ------------------------------------------------------------------ checks on one artifact's HTML (section 14)
def _ui_script(plugin_dir: str, kind: str):
    try:
        root = parse_dom(_template(plugin_dir, kind))
    except OSError:
        return None
    script = find(root, 'script')
    return script and ''.join(c.text for c in script.children)


def check_html(html: str, key: str, manifest: dict, registry: dict, plugin_dir: str, record_dir: str) -> list:
    """Checks of section 14 made on one artifact's HTML. Returns [(requirement id, message)]; [] when clean."""
    found = []

    def add(req, msg):
        found.append((req, msg))

    try:
        kind, entry = _kind_entry(manifest, key)
    except ContentError as exc:
        return [('R4.2', p) for p in exc.problems]
    label = str(manifest.get('timezone_label', ''))
    try:
        all_tasks = _tasks(registry)
    except ContentError as exc:
        return [('R6.1' if 'status' in p else 'R4.7', p) for p in exc.problems]
    mine = _tasks_of(kind, key, all_tasks)
    feature_urls = {e['key']: e.get('url', '') for e in manifest.get('feature_artifacts') or []}
    root = parse_dom(html)

    # R5.1 titles
    prefix = KIND_PREFIX[kind]
    title_node = find(root, 'title')
    title = text_of(title_node) if title_node else ''
    h1 = find(root, 'h1')
    if not title.startswith(prefix) or not title[len(prefix):].strip():
        add('R5.1', 'the title %r must start with "%s" and name the artifact' % (title, prefix))
    elif title != entry.get('title'):
        add('R5.1', 'the title %r differs from the manifest title %r' % (title, entry.get('title')))
    if h1 is None or text_of(h1) != title:
        add('R5.1', 'the heading %r must equal the title %r' % (text_of(h1) if h1 else None, title))

    main = find(root, 'main')
    sections = [c for c in main.children if c.tag == 'section'] if main else []
    info = []
    for section in sections:
        h2 = find(section, 'h2')
        number = find(h2, 'span', 'section-number') if h2 else None
        info.append({'id': section.attrs.get('id', ''), 'number': text_of(number).replace('§', '').strip() if number else None,
                     'title': text_of(h2, skip=lambda n: has_class(n, 'section-number')) if h2 else '', 'node': section})

    # R5.2 numbering and contents
    if not info:
        add('R5.2', 'the artifact has no sections')
    bad_ids = [i['id'] for n, i in enumerate(info) if i['id'] != 's%d' % n or i['number'] != str(n)]
    if bad_ids:
        add('R5.2', 'sections must be numbered 0..%d in order with no gaps; found %s'
            % (len(info) - 1, ', '.join('%s (§ %s)' % (i['id'] or '-', i['number']) for i in info)))
    nav = find(root, 'nav', 'contents')
    links = find_all(nav, 'a') if nav else []
    listed = [(l.attrs.get('href', ''), text_of(find(l, 'b')) if find(l, 'b') else None,
               text_of(l, skip=lambda n: n.tag == 'b')) for l in links]
    wanted = [('#s%d' % n, str(n), i['title']) for n, i in enumerate(info)]
    if listed != wanted:
        add('R5.2', 'the contents list %s does not match the sections %s' % (listed, wanted))

    # R5.3 section 0
    s0 = info[0]['node'] if info else None
    if not info or info[0]['title'] != 'Status and checklist':
        add('R5.3', 'section 0 must come first and be named "Status and checklist"; found %r'
            % (info[0]['title'] if info else None))
    if s0 is not None:
        order = [n for n in elements(s0)]
        parts = [('stamp', find(s0, 'p', 'last-update')), ('lede', find(s0, 'p', 'lede')),
                 ('tiles', find(s0, 'div', 'status-count-tiles')), ('status key', find(s0, 'p', 'note')),
                 ('checklist', find(s0, 'table', 'status-checklist'))]
        missing = [name for name, node in parts if node is None]
        if missing:
            add('R5.3', 'section 0 lacks: %s' % ', '.join(missing))
        else:
            positions = [order.index(node) for _, node in parts]
            if positions != sorted(positions):
                add('R5.3', 'section 0 must hold the stamp, lede, tiles, status key and checklist in that order')
        key_node = parts[3][1]
        if key_node is not None and [text_of(c) for c in find_all(key_node, 'span', 'status-chip')] != list(STATUSES):
            add('R5.3', 'the status key must show the eight statuses in order')

    # R5.5 stamp
    ref = _parse_iso('2000-01-01T00:00+00:00')
    stamp_p = find(s0, 'p', 'last-update') if s0 is not None else None
    time_node = find(stamp_p, 'time') if stamp_p else None
    if time_node is None:
        add('R5.5', 'the stamp has no <time> element')
    else:
        dt_attr, shown = time_node.attrs.get('datetime', ''), text_of(time_node)
        tail = text_of(stamp_p, skip=lambda n: n is time_node)
        if not ISO_OFFSET_RE.match(dt_attr) or _parse_iso(dt_attr) is None:
            add('R5.5', 'the <time> datetime %r is not an ISO time with an offset' % dt_attr)
        else:
            ref = _parse_iso(dt_attr)
            if shown != _fmt_stamp(datetime.fromisoformat(dt_attr)):
                add('R5.5', 'the stamp shows %r but its datetime is %r' % (shown, dt_attr))
        if not STAMP_TEXT_RE.match(shown):
            add('R5.5', 'the stamp %r must read DD Mon HH:MM' % shown)
        if tail != 'Last update: (%s)' % label:
            add('R5.5', 'the stamp must read "Last update: DD Mon HH:MM (%s)"; around the time it reads %r' % (label, tail))

    # R5.7 lede
    lede = find(s0, 'p', 'lede') if s0 is not None else None
    sentence = needs_you_sentence([t for t in mine if t.get('status') in STATUSES])
    if lede is not None and not text_of(lede).endswith(sentence):
        add('R5.7', 'the lede must end with %r; it reads %r' % (sentence, text_of(lede)[-120:]))

    # checklist tables
    tables = find_all(root, 'table', 'status-checklist')
    wanted_cols = _columns(kind, label)
    rows = []
    group_marks = []  # (group key, title, colspan) from the shown table
    for table_no, table in enumerate(tables):
        folded = has_ancestor(table, lambda n: n.tag == 'details' and has_class(n, 'earlier'))
        cols = [text_of(th) for th in find_all(table, 'th')]
        if cols != wanted_cols:
            add('R6.4', 'checklist columns are %s; this kind needs %s' % (cols, wanted_cols))
        current = ''
        for tr in find_all(table, 'tr', pred=lambda n: has_ancestor(n, lambda a: a.tag == 'tbody')):
            if has_class(tr, 'status-group'):
                cell = find(tr, 'td')
                current = tr.attrs.get('data-group', '')
                group_marks.append((current, text_of(cell) if cell else '', cell.attrs.get('colspan', '') if cell else ''))
                continue
            cells = [c for c in tr.children if c.tag == 'td']
            if len(cells) != len(wanted_cols):
                add('R6.4', 'row %s has %d cells; the checklist has %d columns' % (tr.attrs.get('data-task', '?'), len(cells), len(wanted_cols)))
            if 'data-task' not in tr.attrs:
                add('INV-1', 'a checklist row has no data-task attribute')
                continue
            row = {'id': tr.attrs['data-task'], 'group': current, 'folded': folded, 'cells': cells, 'tr': tr}
            chip = find(cells[0], 'span', 'status-chip') if cells else None
            row['status'] = text_of(chip) if chip else ''
            row['chip_class'] = [c for c in chip.attrs.get('class', '').split() if c.startswith('status-') and c != 'status-chip'] if chip else []
            item_cell = cells[1] if len(cells) > 1 else None
            idnode = find(item_cell, 'span', 'task-id') if item_cell else None
            row['label'] = text_of(idnode) if idnode else ''
            row['item'] = text_of(item_cell, skip=lambda n: has_class(n, 'task-id')) if item_cell else ''
            anchor = find(item_cell, 'a') if item_cell else None
            row['href'] = anchor.attrs.get('href') if anchor else None
            offset = 1 if kind == 'full-progress' else 0
            row['app'] = text_of(cells[2]) if kind == 'full-progress' and len(cells) > 2 else ''
            row['detail'] = text_of(cells[2 + offset]) if len(cells) > 2 + offset else ''
            row['expected'] = text_of(cells[3 + offset]) if len(cells) > 3 + offset else ''
            rows.append(row)
    for mark in group_marks:
        if mark[2] != str(len(wanted_cols)):
            add('R6.4', 'group row %r spans %r columns; the checklist has %d' % (mark[1], mark[2], len(wanted_cols)))
    if not tables:
        add('R6.4', 'the artifact has no checklist table')

    # R6.1 statuses and chip classes
    for row in rows:
        if row['status'] not in STATUSES:
            add('R6.1', 'task %s has status %r, which is not one of the eight' % (row['id'], row['status']))
        elif row['chip_class'] != [status_class(row['status'])]:
            add('R6.1', 'task %s chip class %s does not match status %r' % (row['id'], row['chip_class'], row['status']))

    # R6.2 and R6.3 groups, order and the Earlier fold
    group_of = {s: (gkey, gtitle) for gkey, gtitle, sts in GROUPS for s in sts}
    expected_groups = group_tasks([t for t in mine if t.get('status') in STATUSES], ref, kind)
    shown_wanted = [(g, t) for g, t, shown, _ in expected_groups if shown]
    shown_found = [(m[0], m[1]) for m in group_marks]
    if shown_found != shown_wanted:
        add('R6.2', 'the checklist groups are %s; the registry needs %s, in that order' % (
            [t for _, t in shown_found], [t for _, t in shown_wanted]))
    for row in rows:
        if row['status'] in group_of and not row['folded'] and row['group'] != group_of[row['status']][0]:
            add('R6.2', 'task %s (%s) is under group %r; it belongs under %r' % (
                row['id'], row['status'], row['group'], group_of[row['status']][0]))
    by_id = {t['id']: t for t in mine if 'id' in t}
    for gkey, _, shown, _ in expected_groups:
        want = [t['id'] for t in shown]
        have = [r['id'] for r in rows if r['group'] == gkey and not r['folded'] and r['id'] in want]
        if have != [i for i in want if i in have]:
            add('R6.2', 'rows under group %r are in the order %s; they must be %s' % (gkey, have, [i for i in want if i in have]))
    details = find_all(root, 'details', 'earlier')
    folded_wanted = {t['id'] for _, _, _, old in expected_groups for t in old}
    folded_found = {r['id'] for r in rows if r['folded']}
    if kind == 'feature' and details:
        add('R6.3', 'only the full-progress artifact has an Earlier fold')
    if kind == 'full-progress':
        if folded_found != folded_wanted:
            add('R6.3', 'Live or built rows older than %d days belong in Earlier: expected %s, found %s'
                % (EARLIER_DAYS, sorted(folded_wanted), sorted(folded_found)))
        for node in details:
            summary = find(node, 'summary')
            if 'open' in node.attrs or summary is None or text_of(summary) != 'Earlier':
                add('R6.3', 'the Earlier fold must be a closed <details> titled "Earlier"')

    # R6.6 Expected on open rows
    for row in rows:
        if row['status'] in OPEN_STATUSES:
            if not EXPECTED_RE.match(row['expected']) or _expected_datetime(row['expected'], ref) is None:
                add('R6.6', 'task %s is %s and its Expected %r is not "DD Mon" or "DD Mon ~HH:MM" (optionally "; note")'
                    % (row['id'], row['status'], row['expected']))

    # INV-1 the checklist equals the registry
    seen = {}
    for row in rows:
        seen.setdefault(row['id'], []).append(row)
    for tid, same in seen.items():
        if len(same) > 1:
            add('INV-1', 'task %s appears in %d rows' % (tid, len(same)))
    for task in mine:
        tid = task.get('id')
        if tid not in seen:
            add('INV-1', 'task %s is in the registry but not in the checklist' % tid)
            continue
        row = seen[tid][0]
        pairs = [('status', task.get('status'), row['status']), ('item', _norm(task.get('item', '')), row['item']),
                 ('detail', _norm(task.get('detail', '')), row['detail']), ('expected', _norm(task.get('expected', '')), row['expected'])]
        if kind == 'full-progress':
            pairs.append(('app', _norm(task.get('app', '')), row['app']))
        for field, want, have in pairs:
            if want != have:
                add('INV-1', 'task %s %s is %r in the checklist; the registry says %r' % (tid, field, have, want))
        if row['label'] != tid:
            add('INV-1', 'task %s row shows the ID %r' % (tid, row['label']))
    for tid in seen:
        if tid not in {t.get('id') for t in mine}:
            add('INV-1', 'the checklist has task %s, which is not in the registry for this artifact' % tid)

    # R5.8 tiles
    tiles_node = find(root, 'div', 'status-count-tiles')
    have_tiles = []
    for tile in (find_all(tiles_node, 'div', 'status-count-tile') if tiles_node else []):
        count, lab = find(tile, 'div', 'count'), find(tile, 'div', 'label')
        have_tiles.append((text_of(lab) if lab else '', text_of(count) if count else '',
                           [c for c in tile.attrs.get('class', '').split() if c.startswith('status-') and c != 'status-count-tile']))
    want_tiles = [(s.lower(), str(sum(1 for t in mine if t.get('status') == s)), [status_class(s)])
                  for s in STATUSES if any(t.get('status') == s for t in mine)]
    if have_tiles != want_tiles:
        add('R5.8', 'the tiles read %s; the registry needs %s' % (
            [(a, b) for a, b, _ in have_tiles], [(a, b) for a, b, _ in want_tiles]))

    # R6.5 full-progress links
    if kind == 'full-progress':
        for task in mine:
            owner = task.get('owner')
            if owner == 'project' or owner not in feature_urls:
                continue
            row = seen.get(task.get('id'), [None])[0]
            if row is None:
                add('R6.5', 'feature task %s is missing from the full-progress artifact' % task.get('id'))
            elif feature_urls[owner] and row['href'] != feature_urls[owner]:
                add('R6.5', 'feature task %s must link to %s; it links to %r' % (task.get('id'), feature_urls[owner], row['href']))

    # R5.6 feature list on the full-progress artifact
    if kind == 'full-progress':
        s1 = info[1]['node'] if len(info) > 1 else None
        if s1 is None or info[1]['title'] != 'Feature artifacts':
            add('R5.6', 'section 1 must list the feature artifacts')
        else:
            shown = text_of(s1)
            for e in manifest.get('feature_artifacts') or []:
                anchors = [a for a in find_all(s1, 'a') if text_of(a) == e.get('title')]
                if e.get('title') not in shown or (e.get('url') and not any(a.attrs.get('href') == e['url'] for a in anchors)):
                    add('R5.6', 'section 1 must list %r with its link' % e.get('title'))

    # R5.4 History
    history_sections = [i for i in info if i['title'] == 'History']
    if kind == 'feature':
        if not info or info[-1]['title'] != 'History' or len(history_sections) != 1:
            add('R5.4', 'the last section of a feature artifact must be History, and only one')
        else:
            table = find(info[-1]['node'], 'table')
            if table is None or [text_of(th) for th in find_all(table, 'th')] != ['Date', 'Change']:
                add('R5.4', 'History must be a table with the columns Date and Change')
            else:
                moments = []
                for tr in find_all(table, 'tr', pred=lambda n: has_ancestor(n, lambda a: a.tag == 'tbody')):
                    cells = [c for c in tr.children if c.tag == 'td']
                    if len(cells) != 2:
                        add('R5.4', 'a History row needs a date and a change')
                    else:
                        m = re.match(r'^(\d{2}) (' + '|'.join(MONTHS) + r') (\d{2}):(\d{2})$', text_of(cells[0]))
                        moments.append(_expected_datetime('%s %s ~%s:%s' % (m.group(1), m.group(2), m.group(3), m.group(4)), ref) if m else None)
                dated = [m for m in moments if m is not None]
                if dated != sorted(dated, reverse=True):
                    add('R5.4', 'History must be newest first')
    elif history_sections:
        add('R5.4', 'the full-progress artifact has no History')

    # R5.9, R4.10 scripts; R4.10 styles
    scripts = find_all(root, 'script')
    registry_scripts = [s for s in scripts if s.attrs.get('type') == 'application/json']
    ui_expected = _ui_script(plugin_dir, kind)
    for script in scripts:
        if script in registry_scripts:
            continue
        if ui_expected is None or ''.join(c.text for c in script.children) != ui_expected:
            add('R4.10', 'the artifact holds a script that is not the template\'s own')
    if kind == 'full-progress':
        if len(registry_scripts) != 1 or registry_scripts[0].attrs.get('id') != 'task-registry':
            add('R5.9', 'the full-progress artifact must embed the registry once as <script type="application/json" id="task-registry">')
        else:
            try:
                embedded = json.loads(''.join(c.text for c in registry_scripts[0].children))
            except ValueError as exc:
                add('R5.9', 'the embedded registry does not parse: %s' % exc)
            else:
                if embedded != registry:
                    add('R5.9', 'the embedded registry differs from the task registry')
    elif registry_scripts:
        add('R5.9', 'a feature artifact embeds no registry')
    styles = find_all(root, 'style')
    allowed = {'design-tokens', 'structure-css', 'extra-css'}
    for style in styles:
        if style.attrs.get('id') not in allowed:
            add('R4.10', 'the artifact holds a <style> that is not part of the template')
    by_style = {s.attrs.get('id'): ''.join(c.text for c in s.children) for s in styles}

    # R5.10 and R5.11 stylesheets
    try:
        want_structure = structure_css(plugin_dir)
    except OSError as exc:
        want_structure = None
        add('R5.10', 'the structure stylesheet is not readable: %s' % exc)
    if want_structure is not None and by_style.get('structure-css') != want_structure:
        add('R5.10', 'the structure stylesheet is not byte-identical to templates/project-artifact.css')
    try:
        want_design = design_css(manifest, plugin_dir, record_dir)
    except ContentError as exc:
        want_design = None
        add('R5.10', 'the design is not readable: %s' % '; '.join(exc.problems))
    have_design = by_style.get('design-tokens')
    if have_design is None:
        add('R5.10', 'the artifact has no token block')
    else:
        if want_design is not None and have_design != want_design:
            add('R5.10', 'the token block differs from %s' % ('docs/artifacts/design.css' if manifest.get('design') == 'design.css'
                                                             else 'design/default-design.css'))
        for problem in check_tokens(have_design):
            add('R5.11', problem)

    # R4.11 extra_css
    extra = by_style.get('extra-css', '')
    if want_structure is not None and extra.strip():
        for selector in sorted(_selectors(extra) & _selectors(want_structure)):
            add('R4.11', 'extra_css redefines the structure selector "%s"' % selector)
    return found
