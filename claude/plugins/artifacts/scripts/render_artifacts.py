"""Render project artifacts from the record (ARTIFACTSPEC 1.0.0, sections 4 to 6 and 14).

Pure functions: the record in (manifest, registry, content), HTML out, plus the checks
of section 14 that can be made on one artifact's HTML. Standard library only, Python 3.10+.

Public API (imported by project_artifacts.py):
    ContentError, load_content, artifact_file, render_artifact, check_html,
    structure_css, design_css, check_tokens, REQUIRED_TOKENS, STATUSES

A feature artifact is rendered as a complete, standalone HTML document (R5.27, R5.28); the
full-progress artifact is rendered as a fragment beginning with <title> (R5.29). Both link to the
feature files by relative link unless render_artifact is given `links` (the publish copy, R5.31).

Templates hold {{placeholders}}. Section 0 is in the template; its parts come from the
placeholders stamp, lede, glance, tiles, key and checklist. The other placeholders are title,
fonts_link, design_css, structure_css, extra_css, kind_label, project, hero, contents,
sections, and registry (full-progress template only).
"""
from __future__ import annotations

import base64
import html as _html
import json
import os
import re
import unicodedata
from datetime import date, datetime, timedelta, timezone
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
RIDER_ORDER = ('Running', 'Waiting', 'To do', 'Needs you', 'Failed', 'On hold', 'Built', 'Live')    # R5.46
NOT_IN_RELEASE = 'Not in a release yet'


def release_number(task):
    """R5.45: the release number of a task row (a positive whole number), else None."""
    n = task.get('release') if isinstance(task, dict) else None
    return n if isinstance(n, int) and not isinstance(n, bool) and n > 0 else None


def is_release(task) -> bool:
    """R5.40, R5.45: a release row; an older `true` still counts (the script numbers it when it loads the record)."""
    return isinstance(task, dict) and (task.get('release') is True or release_number(task) is not None)


def release_name(task) -> str:
    """R5.45: `RELEASE-<n>`, the name a release is shown by."""
    n = release_number(task)
    return 'RELEASE-%d' % n if n is not None else 'RELEASE'


def shown_item(task) -> str:
    """R5.45: the Item of a release row without its own `RELEASE-<n>` lead (optionally followed by `:` or ` · `),
    so the number shows once; any other item is returned as it is."""
    item = str(task.get('item', ''))
    if release_number(task) is None:
        return item
    m = re.match(r'^%s(?:\s*[:·]\s*|\s+|$)' % re.escape(release_name(task)), item)
    rest = item[m.end():] if m else item
    return rest if m and rest else item


def _release_span(task) -> str:
    return '<span class="release-name">%s</span>' % release_name(task)

EXPECTED_RE = re.compile(
    r'^(0[1-9]|[12]\d|3[01]) (' + '|'.join(MONTHS) + r')(?: ~([01]\d|2[0-3]):([0-5]\d))?(?:; \S.*)?$')
STAMP_TEXT_RE = re.compile(r'^(\d{2}) (' + '|'.join(MONTHS) + r') (\d{2}):(\d{2})$')
ISO_OFFSET_RE = re.compile(r'^\d{4}-\d\d-\d\dT\d\d:\d\d(:\d\d)?[+-]\d\d:\d\d$')
TASK_ID_RE = re.compile(r'^([A-Z]{2,5})(\d+)$')

# Decisions (section 5.4)
DECISION_ID_RE = re.compile(r'^D([1-9]\d*)$')
ISO_DAY_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')
DECISION_KEYS = ('id', 'question', 'asked', 'status', 'options', 'chosen', 'decided', 'owner_words', 'task', 'replaces')
OPTION_KEYS = ('label', 'summary', 'recommended', 'preview', 'image')
DECISION_LIMITS = {'question': 200, 'label': 60, 'summary': 400, 'owner_words': 400, 'preview': 4000}
MAX_OPTIONS = 6
IMAGE_TYPES = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.gif': 'image/gif', '.webp': 'image/webp'}
MAX_IMAGE_BYTES = 300_000
IMAGE_PATH_RE = re.compile(r'^assets/([A-Za-z0-9][A-Za-z0-9._-]*)$')


class ContentError(Exception):
    """The record cannot be rendered. `.problems` lists every problem found."""

    def __init__(self, problems):
        if isinstance(problems, str):
            problems = [problems]
        self.problems = list(problems)
        self.partial = None          # load_content: what could be read of the content, when only some of it is invalid
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


# Tags a decision preview may not hold, and attributes that never belong in one (R5.17).
PREVIEW_BAD_TAGS = frozenset({
    'script', 'style', 'iframe', 'frame', 'frameset', 'object', 'embed', 'applet', 'link', 'meta', 'base', 'form',
    'input', 'button', 'select', 'textarea', 'noscript', 'template', 'math', 'foreignobject', 'use', 'animate', 'set',
    'animatetransform', 'animatemotion', 'title', 'html', 'head', 'body', 'main', 'nav', 'header', 'footer', 'section',
    'h1', 'h2', 'audio', 'video', 'source', 'track', 'canvas'})
PREVIEW_BAD_ATTRS = frozenset({'id', 'name', 'srcdoc', 'formaction', 'ping'})
DATA_IMAGE_RE = re.compile(r'^data:image/(png|jpeg|gif|webp);base64,[a-z0-9+/=]*$')


class _Preview(_Fragment):
    """A decision preview: the fragment rules of R4.10 plus no unsafe tag, attribute or URL (R5.17)."""

    def _look(self, tag, attrs):
        if tag in PREVIEW_BAD_TAGS:
            self.problems.append('<%s> is not allowed in a preview (R5.17)' % tag)
        for name, value in attrs:
            name, value = name.lower(), value or ''
            compact = re.sub(r'[\x00-\x20]+', '', value).lower()
            if name.startswith('on'):
                self.problems.append('the attribute %s is not allowed in a preview (R5.17)' % name)
            elif name in PREVIEW_BAD_ATTRS:
                self.problems.append('the attribute %s is not allowed in a preview (R5.17)' % name)
            if re.search(r'(javascript|vbscript):', compact):
                self.problems.append('a script URL is not allowed in a preview (R5.17)')
            elif re.search(r'https?:|^//', compact):
                self.problems.append('an external URL (%s) is not allowed in a preview (R5.17)' % name)
            elif 'data:' in compact and not DATA_IMAGE_RE.match(compact):
                self.problems.append('a data: URL in a preview must be a base64 png, jpeg, gif or webp image (R5.17)')
            if name == 'style' and re.search(r'url\(|@import|expression\(|behavior|-moz-binding|position:(fixed|sticky)', compact):
                self.problems.append('style="..." in a preview may not use url(), @import, expression() or fixed positions (R5.17)')
            if 'section-number' in value.split() and name == 'class':
                self.problems.append('a section number element is not allowed in a preview (R5.17)')

    def handle_starttag(self, tag, attrs):
        self._look(tag, attrs)
        super().handle_starttag(tag, attrs)

    def handle_startendtag(self, tag, attrs):
        self._look(tag, attrs)
        super().handle_startendtag(tag, attrs)


def preview_problems(markup: str) -> list:
    """R5.17: what is wrong with a decision preview fragment; [] when it is clean."""
    scanner = _Preview()
    scanner.feed(markup)
    return list(dict.fromkeys(p.replace('(R4.10)', '(R5.17)').replace('in content', 'in a preview') for p in scanner.finish()))


def _is_text(value, limit, empty_ok=False) -> bool:
    return isinstance(value, str) and len(value) <= limit and (empty_ok or bool(value.strip()))


def _real_day(value) -> bool:
    if not (isinstance(value, str) and ISO_DAY_RE.match(value)):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def load_decisions(folder: str, key: str):
    """Read and validate content/<key>/decisions.json (R5.14 to R5.19).

    Returns (decisions, problems). A decision is normalised: every key of DECISION_KEYS present, each option
    with label, summary, recommended (bool), preview and image ('' when absent) and image_uri (the image as a
    data: URI, '' when none). Problems are messages that end with their requirement ID.
    """
    where = 'content/%s/decisions.json' % key
    problems = []
    try:
        data = json.loads(_read(os.path.join(folder, 'decisions.json')))
    except (OSError, ValueError) as exc:
        return [], ['%s: %s (R5.14)' % (where, exc)]
    if not (isinstance(data, dict) and list(data) == ['decisions'] and isinstance(data['decisions'], list)):
        return [], ['%s: it must hold exactly {"decisions": [...]} (R5.14)' % where]
    out, seen = [], []
    for position, raw in enumerate(data['decisions'], 1):
        tag = '%s decision %d' % (where, position)
        if not isinstance(raw, dict):
            problems.append('%s is not an object (R5.14)' % tag)
            continue
        unknown = sorted(set(raw) - set(DECISION_KEYS))
        if unknown:
            problems.append('%s: unknown field(s) %s; the fields are %s (R5.14)' % (tag, ', '.join(unknown), ', '.join(DECISION_KEYS)))
        did = raw.get('id')
        if not (isinstance(did, str) and DECISION_ID_RE.match(did)):
            problems.append('%s: id %r must be D1, D2, ... (R5.15)' % (tag, did))
            did = '#%d' % position
        else:
            tag = '%s %s' % (where, did)
            if did != 'D%d' % position:
                problems.append('%s: ids run D1, D2, ... in file order with no gap, none reused or removed; this is decision %d (R5.15)'
                                % (tag, position))
        if not _is_text(raw.get('question'), DECISION_LIMITS['question']):
            problems.append('%s: "question" must be text of 1 to %d characters (R5.14)' % (tag, DECISION_LIMITS['question']))
        if not _real_day(raw.get('asked')):
            problems.append('%s: "asked" must be a date, YYYY-MM-DD (R5.14)' % tag)
        status = raw.get('status')
        if status not in ('decided', 'open'):
            problems.append('%s: "status" must be "decided" or "open" (R5.16)' % tag)
        options, labels, recommended = [], [], 0
        raw_options = raw.get('options')
        if not isinstance(raw_options, list) or not 2 <= len(raw_options) <= MAX_OPTIONS:
            problems.append('%s: "options" must list 2 to %d options; a yes/no question lists Yes and No (R5.16)' % (tag, MAX_OPTIONS))
            raw_options = []
        for number, option in enumerate(raw_options, 1):
            otag = '%s option %d' % (tag, number)
            if not isinstance(option, dict):
                problems.append('%s is not an object (R5.14)' % otag)
                continue
            extra = sorted(set(option) - set(OPTION_KEYS))
            if extra:
                problems.append('%s: unknown field(s) %s; the fields are %s (R5.14)' % (otag, ', '.join(extra), ', '.join(OPTION_KEYS)))
            label = option.get('label')
            if not _is_text(label, DECISION_LIMITS['label']):
                problems.append('%s: "label" must be text of 1 to %d characters (R5.16)' % (otag, DECISION_LIMITS['label']))
                label = ''
            elif label.strip().casefold() in labels:
                problems.append('%s: the label %r is used twice; labels are unique (R5.16)' % (otag, label))
            labels.append(label.strip().casefold())
            if not _is_text(option.get('summary'), DECISION_LIMITS['summary']):
                problems.append('%s: "summary" must be text of 1 to %d characters (R5.14)' % (otag, DECISION_LIMITS['summary']))
            flag = option.get('recommended', False)
            if not isinstance(flag, bool):
                problems.append('%s: "recommended" must be true or false (R5.16)' % otag)
                flag = False
            recommended += flag
            preview, image, uri = option.get('preview', ''), option.get('image', ''), ''
            if preview != '' and not _is_text(preview, DECISION_LIMITS['preview']):
                problems.append('%s: "preview" must be an HTML fragment of at most %d characters (R5.17)' % (otag, DECISION_LIMITS['preview']))
                preview = ''
            elif preview:
                problems += ['%s preview: %s' % (otag, p) if '(R5.17)' in p else '%s preview: %s (R5.17)' % (otag, p)
                             for p in preview_problems(preview)]
            if image != '':
                uri = _image_uri(folder, image, otag, problems)
                if preview:
                    problems.append('%s: give a preview or an image, not both (R5.17)' % otag)
            options.append({'label': label.strip() if isinstance(label, str) else '',
                            'summary': option.get('summary', '').strip() if isinstance(option.get('summary'), str) else '',
                            'recommended': flag, 'preview': preview if isinstance(preview, str) else '',
                            'image': image if isinstance(image, str) else '', 'image_uri': uri})
        if recommended > 1:
            problems.append('%s: %d options are marked recommended; at most one (R5.16)' % (tag, recommended))
        chosen, decided = raw.get('chosen'), raw.get('decided')
        if status == 'decided':
            if not (isinstance(chosen, str) and chosen in [o['label'] for o in options]):
                problems.append('%s: it is decided, so "chosen" must be the label of one of its options (R5.16)' % tag)
            if not _real_day(decided):
                problems.append('%s: it is decided, so "decided" must be a date, YYYY-MM-DD (R5.16)' % tag)
            elif _real_day(raw.get('asked')) and decided < raw['asked']:
                problems.append('%s: "decided" is before "asked" (R5.16)' % tag)
        elif status == 'open':
            if chosen is not None or decided is not None:
                problems.append('%s: it is open, so "chosen" and "decided" must be null (R5.16)' % tag)
        words = raw.get('owner_words')
        if words is not None:
            if not _is_text(words, DECISION_LIMITS['owner_words']):
                problems.append('%s: "owner_words" must be text of 1 to %d characters (R5.14)' % (tag, DECISION_LIMITS['owner_words']))
            elif status == 'open':
                problems.append('%s: it is open, so it has no "owner_words" (R5.16)' % tag)
        task = raw.get('task')
        if task is not None and not (isinstance(task, str) and re.match(r'^[A-Z]{2,5}[1-9]\d*$', task)):
            problems.append('%s: "task" must be a task ID such as AR9 (R5.18)' % tag)
        replaces = raw.get('replaces')
        if replaces is not None and replaces not in seen:
            problems.append('%s: "replaces" %r must name an earlier decision of this artifact (R5.18)' % (tag, replaces))
        seen.append(did)
        out.append({'id': did, 'question': raw.get('question', '').strip() if isinstance(raw.get('question'), str) else '',
                    'asked': raw.get('asked'), 'status': status, 'options': options,
                    'chosen': chosen if status == 'decided' else None, 'decided': decided if status == 'decided' else None,
                    'owner_words': words.strip() if isinstance(words, str) and words.strip() else None,
                    'task': task if isinstance(task, str) else None,
                    'replaces': replaces if isinstance(replaces, str) else None})
    return out, problems


def _image_uri(folder: str, rel, where: str, problems: list) -> str:
    """The image under content/<key>/assets/ as a data: URI; '' (and a problem) when it cannot be used (R5.17)."""
    match = IMAGE_PATH_RE.match(rel) if isinstance(rel, str) else None
    if not match:
        problems.append('%s: "image" %r must be assets/<file name> inside the content folder (R5.17)' % (where, rel))
        return ''
    kind = IMAGE_TYPES.get(os.path.splitext(match.group(1))[1].lower())
    if kind is None:
        problems.append('%s: the image %s must be png, jpg, gif or webp (R5.17)' % (where, rel))
        return ''
    path = os.path.join(folder, 'assets', match.group(1))
    try:
        with open(path, 'rb') as handle:
            data = handle.read()
    except OSError:
        problems.append('%s: the image %s does not exist in the content folder (R5.17)' % (where, rel))
        return ''
    if len(data) > MAX_IMAGE_BYTES:
        problems.append('%s: the image %s is %d bytes; at most %d (R5.17)' % (where, rel, len(data), MAX_IMAGE_BYTES))
        return ''
    return 'data:%s;base64,%s' % (kind, base64.b64encode(data).decode('ascii'))


def load_content(record_dir: str, key: str, plugin_dir: str = PLUGIN_DIR) -> dict:
    """Read and validate content/<key>/ of the record (R4.4, R4.10, R4.11, section 5.4).

    Returns {"meta": {title, hero, lede, extra_css}, "sections": [{title, html}], "history": [{date, change}],
    "decisions": [decision]}; decisions is [] when the artifact has no decisions.json.
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
        if field == 'lede' and (value is None or (isinstance(value, str) and not value.strip())):
            continue                     # R5.7: the lede is an optional note; the At a glance block carries the statuses
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
        if name in ('meta.json', 'history.json', 'decisions.json') or (name == 'assets' and os.path.isdir(os.path.join(folder, name))):
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
        if title.strip().casefold() == 'decisions' and key != FULL_PROGRESS_NAME:
            problems.append('content/%s/%s: a section titled Decisions is drawn from decisions.json only; move it there (R5.19)'
                            % (key, name))
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
    decisions = []
    if os.path.exists(os.path.join(folder, 'decisions.json')):
        if key == FULL_PROGRESS_NAME:
            problems.append('content/%s/decisions.json: the full-progress artifact has no decisions (R5.14)' % key)
        else:
            decisions, found = load_decisions(folder, key)
            problems += found
    content = {'meta': meta, 'sections': sections, 'history': history, 'decisions': decisions}
    if problems:
        error = ContentError(problems)
        if loaded:
            error.partial = content
        raise error
    return content


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
        if 'expected_basis' in task and not isinstance(task['expected_basis'], str):
            problems.append('task %s: "expected_basis" must be a string' % task.get('id', '?'))
    if problems:
        raise ContentError(problems)
    return tasks


def _tasks_of(kind: str, key: str, tasks: list) -> list:
    return tasks if kind == 'full-progress' else [t for t in tasks if t.get('owner') == key]


def group_tasks(tasks: list, ref: datetime, kind: str) -> list:
    """R6.2 and R6.3: [(group key, group title, shown tasks, folded tasks)], empty groups omitted.
    Only Live rows fold into Earlier; Built rows never do (unreleased work stays visible).
    The full-progress artifact groups by release instead (R5.46)."""
    if kind == 'full-progress':
        return release_groups(tasks, ref)
    return status_groups(tasks, ref, kind)


def _id_key(task):
    match = TASK_ID_RE.match(str(task.get('id', '')))
    return (match.group(1), int(match.group(2))) if match else (str(task.get('id', '')), 0)


def _soonest(task, ref):
    moment = _expected_datetime(task['expected'], ref)
    return (1, datetime.max) if moment is None else (0, moment)


def _release_heading(task: dict, ref: datetime, tasks: list) -> str:
    """R5.46: `RELEASE-<n> · live ~HH:MM`, with ` · worst ~HH:MM` when the release has a risk."""
    row = _release_row(task, ref, tasks)
    match = EXPECTED_RE.match(str(task.get('expected', '')))
    if row is not None and row['timed']:
        text = 'live ~%s' % _hhmm(row['exp_min'])
    elif match:
        text = 'live %s %s' % (match.group(1), match.group(2))
    else:
        text = 'live %s' % task.get('expected', '')
    if row is not None and row['worst'] is not None:
        text += ' · worst ~%s' % _hhmm(row['worst'])
    return '%s · %s' % (release_name(task), text)


def release_groups(tasks: list, ref: datetime) -> list:
    """R5.46: [(group key, title, shown, folded)] of the full-progress checklist: a group per open release (the
    release row, then the tasks riding it), Not in a release yet, Needs you, failed or on hold, Live or built."""
    opens = [t for t in tasks if is_release(t) and t.get('status') in OPEN_STATUSES]
    opens.sort(key=lambda t: (_soonest(t, ref), release_number(t) or 0, _id_key(t)))
    open_ids = {t['id'] for t in opens}
    out, placed = [], set()
    for rel in opens:
        riders = [t for t in tasks if t.get('rides') == rel['id'] and t['id'] != rel['id'] and not is_release(t)]
        riders += [t for t in tasks if t.get('rides') == rel['id'] and t['id'] != rel['id'] and is_release(t)
                   and t['id'] not in open_ids]
        riders.sort(key=lambda t: (RIDER_ORDER.index(t['status']), _id_key(t)))
        shown = [rel] + riders
        placed.update(t['id'] for t in shown)
        out.append(('release-%s' % (release_number(rel) or rel['id']), _release_heading(rel, ref, tasks), shown, []))
    rest = [t for t in tasks if t['id'] not in placed]
    now = sorted([t for t in rest if t['status'] in ('Running', 'Waiting', 'To do')], key=lambda t: _soonest(t, ref))
    you = sorted([t for t in rest if t['status'] in YOU_ORDER], key=lambda t: YOU_ORDER.index(t['status']))
    floor = datetime.min.replace(tzinfo=timezone.utc)
    done = sorted([t for t in rest if t['status'] in ('Live', 'Built')],
                  key=lambda t: _parse_iso(t.get('changed'), floor), reverse=True)
    cutoff = ref - timedelta(days=EARLIER_DAYS)
    folded = [t for t in done if t['status'] == 'Live' and (_parse_iso(t.get('changed')) or ref) < cutoff]
    done = [t for t in done if t not in folded]
    for gkey, title, shown, old in (('now', NOT_IN_RELEASE, now, []), ('you', GROUPS[1][1], you, []),
                                    ('built', GROUPS[2][1], done, folded)):
        if shown or old:
            out.append((gkey, title, shown, old))
    return out


def status_groups(tasks: list, ref: datetime, kind: str) -> list:
    """R6.2: the groups by status, as a feature artifact draws them."""
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
            folded = [t for t in mine if t['status'] == 'Live' and (_parse_iso(t.get('changed')) or ref) < cutoff]
            mine = [t for t in mine if t not in folded]
        if mine or folded:
            out.append((gkey, title, mine, folded))
    return out


def open_decisions(decisions) -> list:
    """The decisions that wait on the owner: open and not replaced (R5.23), oldest first."""
    replaced = {d.get('replaces') for d in decisions or [] if d.get('replaces')}
    return [d for d in decisions or [] if d.get('status') == 'open' and d.get('id') not in replaced]


def needs_you_sentence(tasks: list, decisions=()) -> str:
    """R5.7, R5.25 and R5.34a: tasks in Needs you, waiting on the owner, or Failed, then open decisions."""
    waiting = glance_you_tasks(tasks)
    parts = ['%s %s' % (t['id'], _norm(t['item'])) for t in waiting]
    parts += ['%s %s' % (d['id'], _norm(d['question'])) for d in open_decisions(decisions)]
    if not parts:
        return 'Nothing needs you.'
    return 'Needs you: ' + '; '.join(parts) + ('' if parts[-1].endswith('?') else '.')


GLANCE_LIVE_HOURS = 24      # R5.34
GLANCE_LIVE_MAX = 8         # R5.34
LEDE_WARN_CHARS = 300       # R5.37
GLANCE_GROUPS = (
    ('you', 'Needs you'), ('running', 'Running now'), ('built', 'Built, not released'),
    ('waiting', 'Waiting for other work'), ('live', 'Live in the last 24 hours'),
)
DEP_MAX = 80                # R5.34a: longest dependency text of a glance row


def waits_on_owner(task: dict) -> bool:
    """R5.34a: a Waiting or On hold task whose `waits_on` is `owner` waits on the owner, not on other work."""
    return task.get('status') in ('Waiting', 'On hold') and task.get('waits_on') == 'owner'


def glance_you_tasks(tasks: list) -> list:
    """R5.34: the tasks of the Needs you group: Needs you, then Waiting or On hold on the owner, then Failed."""
    def rank(t):
        return 0 if t['status'] == 'Needs you' else (1 if waits_on_owner(t) else 2)
    return sorted([t for t in tasks if t['status'] in ('Needs you', 'Failed') or waits_on_owner(t)], key=rank)


def glance_dependency(task: dict, by_id=None) -> str:
    """R5.34a: what the task waits on, from `expected_basis`, else the release it rides, else the first sentence
    of `detail`; at most DEP_MAX characters."""
    text = _norm(task.get('expected_basis') or '')
    if not text and task.get('rides'):
        rel = (by_id or {}).get(task['rides'])
        text = release_name(rel) if rel is not None else task['rides']
    if not text:
        text = _norm(re.split(r'(?<=[.!?])\s', _norm(task.get('detail') or ''), maxsplit=1)[0])
    return text if len(text) <= DEP_MAX else text[:DEP_MAX - 1].rstrip() + '\u2026'


def glance_groups(tasks: list, decisions, ref: datetime) -> list:
    """R5.33 and R5.34: [(group key, label, [task], [decision], more)] in display order. Empty groups are
    omitted except `you`. Each task list is ordered by the checklist's rules (R6.2)."""
    floor = datetime.min.replace(tzinfo=timezone.utc)

    def newest(items):
        return sorted(items, key=lambda t: _parse_iso(t.get('changed'), floor), reverse=True)

    def soonest(task):
        moment = _expected_datetime(task['expected'], ref)
        return (1, datetime.max) if moment is None else (0, moment)

    out = []
    for gkey, label in GLANCE_GROUPS:
        more = 0
        if gkey == 'you':
            shown = glance_you_tasks(tasks)
            found = open_decisions(decisions)
        else:
            found = []
            if gkey == 'running':
                shown = sorted([t for t in tasks if t['status'] == 'Running'], key=soonest)
            elif gkey == 'built':
                shown = newest([t for t in tasks if t['status'] == 'Built'])
            elif gkey == 'waiting':
                shown = sorted([t for t in tasks if t['status'] in ('Waiting', 'On hold') and not waits_on_owner(t)],
                               key=lambda t: (t['status'] == 'On hold',) + soonest(t))
            else:
                cutoff = ref - timedelta(hours=GLANCE_LIVE_HOURS)
                recent = newest([t for t in tasks if t['status'] == 'Live'
                                 and (_parse_iso(t.get('changed')) or floor) >= cutoff])
                shown, more = recent[:GLANCE_LIVE_MAX], max(0, len(recent) - GLANCE_LIVE_MAX)
        if shown or found or gkey == 'you':
            out.append((gkey, label, shown, found, more))
    return out


def _glance_task(task: dict, gkey='', by_id=None) -> str:
    """R5.33, R5.34a: ID, then (for a task that waits, in Needs you and Waiting for other work) the dependency
    first, the item, the Expected."""
    expected, dep = '', ''
    waits = task['status'] in ('Waiting', 'On hold') or (gkey == 'you' and task['status'] == 'Needs you')
    if gkey in ('you', 'waiting') and waits:
        text = glance_dependency(task, by_id)
        if text:
            dep = '<span class="glance-dep">%s</span> ' % esc(text)
    if task['status'] in OPEN_STATUSES and task.get('expected'):
        expected = ' <span class="glance-expected">%s</span>' % esc(task['expected'])
        if task.get('expected_basis') and not dep:
            expected += '<span class="glance-basis">%s</span>' % esc(task['expected_basis'])
    return '<li data-glance-task="%s"><span class="task-id">%s</span>%s%s%s%s</li>' % (
        esc(task['id']), esc(task['id']), dep, _release_span(task) if is_release(task) else '', esc(shown_item(task)), expected)


def glance_open(gkey: str) -> bool:
    """R6.13: the At a glance groups that are done (Built, not released; Live in the last 24 hours) render closed,
    every other group, and always Needs you, renders open."""
    return gkey not in ('built', 'live')


def _at_a_glance(tasks: list, decisions, ref: datetime) -> str:
    """R5.33 and R6.13: the At a glance block of section 0, generated from the registry; each group is a
    `<details class="glance-group">` whose `<summary>` holds the label and the count."""
    groups = []
    by_id = {t['id']: t for t in tasks}
    for gkey, label, shown, found, more in glance_groups(tasks, decisions, ref):
        items = [_glance_task(t, gkey, by_id) for t in shown]
        items += ['<li data-glance-decision="%s"><span class="task-id">%s</span>%s</li>'
                  % (esc(d['id']), esc(d['id']), esc(_norm(d['question']))) for d in found]
        if more:
            items.append('<li class="glance-more">and %d more</li>' % more)
        body = '<ul>\n%s\n</ul>' % '\n'.join(items) if items else '<p class="glance-none">Nothing needs you.</p>'
        count = len(shown) + len(found) + more
        groups.append('<details class="glance-group glance-%s" data-glance="%s"%s><summary>'
                      '<span class="glance-label">%s</span><span class="fold-count">%d task%s</span></summary>\n%s\n</details>'
                      % (gkey, gkey, ' open' if glance_open(gkey) else '', esc(label), count, '' if count == 1 else 's', body))
    return '<div class="at-a-glance">\n%s\n</div>' % '\n'.join(groups)


def feature_summary(tasks: list, decisions=()) -> str:
    """R5.36: a one-line summary generated from the registry, e.g. `2 running, 3 built, nothing needs you`."""
    counts = {s: sum(1 for t in tasks if t['status'] == s and not waits_on_owner(t)) for s in STATUSES}
    counts['Needs you'] += sum(1 for t in tasks if waits_on_owner(t))        # R5.34a
    parts = ['%d %s' % (counts[s], s.lower()) for s in ('Running', 'Built', 'Waiting', 'To do', 'On hold', 'Live') if counts[s]]
    needs = counts['Needs you'] + counts['Failed'] + len(open_decisions(decisions))
    parts.append('nothing needs you' if not needs else '%d need%s you' % (needs, 's' if needs == 1 else ''))
    return ', '.join(parts)


def lede_warnings(content: dict) -> list:
    """R5.37: [message] for a lede over 300 characters (a warning, never a finding)."""
    text = text_of(parse_dom(content['meta']['lede'])) if content['meta'].get('lede') else ''
    if len(text) <= LEDE_WARN_CHARS:
        return []
    return ['the lede is %d characters; keep the note to one or two sentences, the At a glance block lists the statuses'
            % len(text)]


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


def _copy_link(link) -> str:
    """R5.31: a page on claude.ai cannot open a file: link, so the publish copy names the feature as text and
    gives a button that copies its file:/// address to paste into the address bar; the address is shown, to
    copy by hand, only when the clipboard refuses."""
    return (' <button type="button" class="copy-link" data-copy="%s" title="%s">Copy link</button>'
            '<code class="local-path" hidden>%s</code>' % (esc(link[0]), esc(link[1]), esc(link[0])))


def _link(link, label: str) -> str:
    """`label` as a link to a feature file; `link` is (href, path text or ''). With path text (the publish
    copy) the label is plain text with a copy button instead (R5.31)."""
    if link[1]:
        return '<span class="feature-name">%s</span>%s' % (label, _copy_link(link))
    return '<a href="%s">%s</a>' % (esc(link[0]), label)


NO_RELEASE_LINE = 'ships nothing: %s'


def no_release_reason(task) -> str:
    """R5.47a: the reason a task ships nothing (`no_release`), '' when it has none."""
    reason = task.get('no_release') if isinstance(task, dict) else None
    return ' '.join(reason.split()) if isinstance(reason, str) else ''


def rode_release(task: dict, by_id: dict):
    """R5.46: the release task that `task` rides, or None."""
    target = by_id.get(task.get('rides')) if task.get('rides') else None
    return target if target is not None and is_release(target) else None


def _row(task: dict, kind: str, feature_links: dict, by_id=None, release_line: bool = False) -> str:
    item = '<span class="task-id">%s</span>%s%s' % (
        esc(task['id']), _release_span(task) if is_release(task) else '', esc(shown_item(task)))
    link = feature_links.get(task.get('owner')) if kind == 'full-progress' else None
    if link and not link[1]:             # the publish copy's rows stay text; section 1 has the copy buttons
        item = _link(link, item)
    target = rode_release(task, by_id or {}) if release_line else None
    if target is not None:               # R5.46: the release a Live or Built row rode, in a muted line under the Item
        item += '<span class="release-line">%s</span>' % _release_span(target)
    if no_release_reason(task):          # R5.47a: a task that ships nothing says so, in a muted line under the Item
        item += '<span class="no-release-line">%s</span>' % esc(NO_RELEASE_LINE % no_release_reason(task))
    app = '<td>%s</td>' % ('<code>%s</code>' % esc(task['app']) if task.get('app') else '') if kind == 'full-progress' else ''
    expected = esc(task['expected'])
    if task.get('expected_basis') and task['status'] in OPEN_STATUSES:     # R6.10
        expected += '<span class="expected-basis">%s</span>' % esc(task['expected_basis'])
    return '<tr data-task="%s"><td>%s</td><td>%s</td>%s<td>%s</td><td>%s</td></tr>' % (
        esc(task['id']), _chip(task['status']), item, app, esc(task['detail']), expected)


COLUMN_CLASSES = {'Status': 'col-status', 'Item': 'col-item', 'App / service': 'col-app', 'Detail': 'col-detail'}


def _table(body_rows: list, kind: str, label: str) -> str:
    cols = _columns(kind, label)
    head = ''.join('<th>%s</th>' % esc(c) for c in cols)
    group = '<colgroup>%s</colgroup>' % ''.join('<col class="%s">' % COLUMN_CLASSES.get(c, 'col-expected') for c in cols)
    return ('<div class="table-scroll"><table class="status-checklist">%s<thead><tr>%s</tr></thead><tbody>\n%s\n</tbody></table></div>'
            % (group, head, '\n'.join(body_rows)))


def wants_release_line(kind: str, gkey: str) -> bool:
    """R5.46: a feature artifact's rows, and the full-progress group Live or built, show the release they rode."""
    return kind == 'feature' or gkey == 'built'


def group_open(gkey: str) -> bool:
    """R6.12: every checklist group renders open except Live or built, which always renders closed."""
    return gkey != 'built'


def _count_label(gkey: str, rows: list) -> str:
    """The closed Live or built heading still says how much unreleased work it holds: `2 built, 31 live`."""
    if gkey == 'built' and any(t['status'] == 'Built' for t in rows):
        built = sum(1 for t in rows if t['status'] == 'Built')
        return '%d built, %d live' % (built, len(rows) - built)
    return '%d task%s' % (len(rows), '' if len(rows) == 1 else 's')


def _checklist(tasks: list, kind: str, label: str, ref: datetime, feature_links: dict, all_tasks=None) -> str:
    """R6.12: one `<details class="status-fold">` per group, its heading in the `<summary>`, a table of its rows
    inside; Live or built closed, the rest open. The Earlier fold sits inside Live or built (R6.3)."""
    groups = group_tasks(tasks, ref, kind)
    by_id = {t['id']: t for t in (tasks if all_tasks is None else all_tasks) if 'id' in t}
    out = []
    for gkey, title, shown, old in groups:
        if not shown and not old:
            continue
        body = ''
        if shown:
            body += _table([_row(t, kind, feature_links, by_id, wants_release_line(kind, gkey)) for t in shown],
                           kind, label)
        if old:
            body += ('\n<details class="earlier"><summary>Earlier</summary>\n%s\n</details>'
                     % _table([_row(t, kind, feature_links, by_id, True) for t in old], kind, label))
        out.append('<details class="status-fold%s" data-group="%s"%s><summary><strong>%s</strong>'
                   '<span class="fold-count">%s</span></summary>\n%s\n</details>'
                   % (' release-group' if gkey.startswith('release-') else '', gkey,
                      ' open' if group_open(gkey) else '', esc(title), _count_label(gkey, shown + old), body))
    return '\n'.join(out) if out else _table([], kind, label)


# ------------------------------------------------------------------ release timeline (R5.42, R5.43)
RELEASE_PHASES = ('agents', 'join', 'ci', 'merge')      # R5.40
PHASE_LABELS = {'agents': 'agents', 'join': 'join', 'ci': 'PR CI', 'merge': 'merge + cleanup'}
TL_X0, TL_X1 = 200, 720          # today's axis, in SVG units
TL_SLOT0, TL_SLOT_STEP = 820, 90
TL_ROW, TL_TOP = 62, 52
TL_WIDTH = 960                   # the design width of the drawing, in SVG units (R5.43)


def _n(value) -> str:
    return ('%.1f' % value).rstrip('0').rstrip('.')


def _hhmm(minutes) -> str:
    return '%02d:%02d' % (int(minutes) // 60 % 24, int(minutes) % 60)


def open_releases(tasks: list) -> list:
    """R5.40, R5.42: the release tasks still open, in registry order."""
    return [t for t in tasks if is_release(t) and t.get('status') in OPEN_STATUSES]


def _release_row(task: dict, ref: datetime, tasks: list):
    """The facts of one open release, or None when its Expected does not parse."""
    midnight = datetime.combine(ref.date(), datetime.min.time())
    local = ref.tzinfo

    def minutes(iso):
        moment = _parse_iso(iso)
        if moment is None:
            return None
        return (moment.astimezone(local).replace(tzinfo=None) - midnight).total_seconds() / 60

    phases = []
    for p in task.get('phases') or []:
        if not isinstance(p, dict) or p.get('name') not in RELEASE_PHASES:
            continue
        a, b = minutes(p.get('start')), minutes(p.get('end'))
        if a is not None and b is not None and b > a:
            phases.append((p['name'], a, b))
    expected = str(task.get('expected', ''))
    match = EXPECTED_RE.match(expected)
    exp_dt = _expected_datetime(expected, ref)
    if phases:
        exp_min = max(b for _, _, b in phases)
        exp_dt = midnight + timedelta(minutes=exp_min)
    elif exp_dt is None:
        return None
    else:
        exp_min = (exp_dt - midnight).total_seconds() / 60
    timed = bool(phases) or bool(match and match.group(3))
    risk = task.get('risk') if isinstance(task.get('risk'), dict) else None
    worst = None
    if risk and isinstance(risk.get('minutes'), int) and risk['minutes'] > 0 and timed:
        worst = exp_min + risk['minutes']
    riders = [t['id'] for t in tasks if t.get('rides') == task['id']]
    return {'task': task, 'phases': phases, 'exp_dt': exp_dt, 'exp_min': exp_min, 'timed': timed,
            'today': timed and abs(exp_dt - ref.replace(tzinfo=None)) <= timedelta(hours=24), 'risk': risk if worst is not None else None,
            'worst': worst, 'riders': riders}


OTHER_STATUSES = ('Running', 'Waiting', 'Needs you', 'To do')
OTHER_TITLE = 'Other work (no release)'


def _other_row(task: dict, ref: datetime):
    """R5.42b: the facts of one open no-release task for the second strip, or None when it does not belong
    (not open, a release, no `no_release`, or an Expected that is not today or tomorrow)."""
    if (not isinstance(task, dict) or task.get('status') not in OTHER_STATUSES or is_release(task)
            or not no_release_reason(task)):
        return None
    exp_dt = _expected_datetime(str(task.get('expected', '')), ref)
    if exp_dt is None or exp_dt.date() > ref.date() + timedelta(days=1):
        return None
    midnight = datetime.combine(ref.date(), datetime.min.time())
    now_min = (ref.replace(tzinfo=None) - midnight).total_seconds() / 60
    exp_min = (exp_dt - midnight).total_seconds() / 60
    match = EXPECTED_RE.match(str(task.get('expected', '')))
    timed = bool(match and match.group(3))
    start = _parse_iso(task.get('started'))
    start_min = now_min
    if start is not None:
        start_min = (start.astimezone(ref.tzinfo).replace(tzinfo=None) - midnight).total_seconds() / 60
    start_min = max(0, min(start_min, exp_min))
    return {'task': task, 'exp_dt': exp_dt, 'exp_min': exp_min, 'start_min': start_min, 'timed': timed,
            'today': timed and abs(exp_dt - ref.replace(tzinfo=None)) <= timedelta(hours=24),
            'overdue': exp_dt < ref.replace(tzinfo=None), 'phases': [], 'worst': None, 'risk': None}


def _cut(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit - 1].rstrip() + '…'


def release_timeline(tasks: list, ref: datetime, label: str) -> str:
    """R5.42, R5.43: the release timeline figure of section 0, '' when no release is open. Deterministic:
    `ref` (the render stamp) is "now", never the wall clock."""
    rows = [r for r in (_release_row(t, ref, tasks) for t in open_releases(tasks)) if r is not None]
    others = [r for r in (_other_row(t, ref) for t in tasks) if r is not None]
    if not rows and not others:
        return ''
    rows.sort(key=lambda r: (r['exp_dt'], r['task']['id']))
    others.sort(key=lambda r: (r['exp_dt'], r['task']['id']))
    every = rows + others
    today = [r for r in every if r['today']]
    days = sorted({r['exp_dt'].date() for r in every if not r['today']})
    now_min = ref.hour * 60 + ref.minute
    if today:
        starts = [a for r in today for _, a, _ in r['phases']] + [r['start_min'] for r in others if r['today']]
        lo = min(starts) if starts else min([now_min] + [r['exp_min'] for r in today])
        hi = max(r['worst'] or r['exp_min'] for r in today)
        t0 = int(lo // 30 * 30)
        t1 = int(-(-hi // 30) * 30)
        if t1 <= t0:
            t1 = t0 + 30
    else:
        t0 = int(now_min // 30 * 30)
        t1 = t0 + 30
    slot0 = TL_SLOT0 if today else 220
    width = max(slot0 + TL_SLOT_STEP * (max(len(days), 1) - 1) + 80, TL_WIDTH)     # R5.43: never drawn smaller than the design width
    x = lambda m: TL_X0 + (m - t0) * (TL_X1 - TL_X0) / (t1 - t0)
    slot = lambda day: slot0 + TL_SLOT_STEP * days.index(day)
    out, aria, aria_other, y = [], [], [], TL_TOP
    for r in rows:
        t = r['task']
        name = '%s · %s' % (release_name(t) if release_number(t) is not None else t['id'], shown_item(t))
        sub = ', '.join(r['riders'])
        out.append('<text class="rt-name" x="0" y="%d"><title>%s</title>%s</text>' % (y + 8, esc(name), esc(_cut(name, 26))))
        if sub:
            out.append('<text class="rt-sub" x="0" y="%d"><title>%s</title>%s</text>' % (y + 25, esc(sub), esc(_cut(sub, 34))))
        if r['today']:
            for name_, a, b in r['phases']:
                out.append('<rect class="rt-bar %s" x="%s" y="%d" width="%s" height="22"><title>%s</title></rect>'
                           % (name_, _n(x(a)), y, _n(x(b) - x(a)), esc('%s %s-%s' % (PHASE_LABELS[name_], _hhmm(a), _hhmm(b)))))
            ex = x(r['exp_min'])
            if r['worst'] is not None:
                rx = x(r['worst'])
                out.append('<rect class="rt-risk" x="%s" y="%d" width="%s" height="10"><title>%s</title></rect>'
                           % (_n(ex), y + 6, _n(rx - ex), esc(r['risk']['label'])))
                out.append('<polygon class="rt-worst" points="%s,%d %s,%d %s,%d %s,%d"/>'
                           % (_n(rx), y - 1, _n(rx + 7), y + 11, _n(rx), y + 23, _n(rx - 7), y + 11))
                out.append('<text class="rt-risk-label" x="%s" y="%d">%s</text>'
                           % (_n(rx + 11), y + 15, esc('%s → worst ~%s' % (r['risk']['label'], _hhmm(r['worst'])))))
            out.append('<polygon class="rt-expected" points="%s,%d %s,%d %s,%d %s,%d"/>'
                       % (_n(ex), y - 2, _n(ex + 8), y + 11, _n(ex), y + 24, _n(ex - 8), y + 11))
            out.append('<text class="rt-live-label" x="%s" y="%d">live ~%s</text>' % (_n(ex), y + 40, _hhmm(r['exp_min'])))
            said = 'expected live about %s' % _hhmm(r['exp_min'])
            if r['worst'] is not None:
                said += ', worst case %s' % _hhmm(r['worst'])
        else:
            day = r['exp_dt'].date()
            sx = slot(day)
            text = '%02d %s' % (day.day, MONTHS[day.month - 1])
            out.append('<polygon class="rt-day" points="%d,%d %d,%d %d,%d %d,%d"/><text class="rt-day-label" x="%d" y="%d">%s</text>'
                       % (sx, y, sx + 8, y + 13, sx, y + 26, sx - 8, y + 13, sx + 16, y + 17, esc(text)))
            said = 'expected %s' % text
        aria.append('%s (%s) %s' % (t['id'], shown_item(t), said))
        y += TL_ROW
    if others:                                            # R5.42b: the second strip, same axis
        out.append('<text class="rt-strip-title" x="0" y="%d">%s</text>' % (y + 8, esc(OTHER_TITLE)))
        y += 34
        for r in others:
            t = r['task']
            name = '%s · %s' % (t['id'], t['item'])
            cls = ' overdue' if r['overdue'] else ''
            out.append('<text class="rt-name" x="0" y="%d"><title>%s</title>%s</text>' % (y + 8, esc(name), esc(_cut(name, 26))))
            basis = t.get('expected_basis') or ''
            if r['today']:
                bx = x(r['start_min'])
                bw = max(x(r['exp_min']) - bx, 4)
                out.append('<rect class="rt-other %s%s" x="%s" y="%d" width="%s" height="16"><title>%s</title></rect>'
                           % (status_class(t['status']), cls, _n(bx), y + 3, _n(bw),
                              esc('%s %s-%s' % (t['status'], _hhmm(r['start_min']), _hhmm(r['exp_min'])))))
                label = ('~%s' % _hhmm(r['exp_min'])) + (' · %s' % basis if basis else '')
                out.append('<text class="rt-other-label" x="%s" y="%d">%s</text>' % (_n(bx), y + 36, esc(_cut(label, 60))))
                said = '%s, expected about %s' % (t['status'], _hhmm(r['exp_min']))
            else:
                day = r['exp_dt'].date()
                sx = slot(day)
                text = '%02d %s' % (day.day, MONTHS[day.month - 1])
                out.append('<polygon class="rt-day%s" points="%d,%d %d,%d %d,%d %d,%d"/><text class="rt-day-label" x="%d" y="%d">%s</text>'
                           % (cls, sx, y, sx + 8, y + 13, sx, y + 26, sx - 8, y + 13, sx + 16, y + 17, esc(text)))
                if basis:
                    out.append('<text class="rt-other-label" x="%d" y="%d">%s</text>' % (sx - 8, y + 40, esc(_cut(basis, 60))))
                said = '%s, expected %s' % (t['status'], text)
            if r['overdue']:
                said += ', overdue'
            aria_other.append('%s (%s) %s' % (t['id'], t['item'], said))
            y += TL_ROW
    height = y + 50
    grid = []
    if today:
        step = 30 if t1 - t0 <= 240 else 60
        m = -(-t0 // step) * step
        while m <= t1:
            tick = _hhmm(m)
            if m % 1440 == 0 or (m - step) % 1440 == 0:       # R5.42a: midnight and the first tick after it carry the date
                day = ref.date() + timedelta(days=int(m // 1440))
                tick = '%02d %s %s' % (day.day, MONTHS[day.month - 1], tick)
            grid.append('<line class="rt-grid" x1="%s" y1="36" x2="%s" y2="%d"/><text x="%s" y="28">%s</text>'
                        % (_n(x(m)), _n(x(m)), height - 24, _n(x(m)), tick))
            m += step
    for day in days:
        grid.append('<line class="rt-grid" x1="%d" y1="36" x2="%d" y2="%d"/><text x="%d" y="28">%02d %s</text>'
                    % (slot(day), slot(day), height - 24, slot(day), day.day, MONTHS[day.month - 1]))
    if today and days:
        grid.append('<path class="rt-break" d="M738 30 l8 -8 M750 30 l8 -8"/>')
    now = ''
    if today and t0 <= now_min <= t1:
        nx = x(now_min)
        now = ('<line class="rt-now" x1="%s" y1="36" x2="%s" y2="%d"/><text class="rt-now-label" x="%s" y="%d">now %s</text>'
               % (_n(nx), _n(nx), height - 16, _n(nx), height - 3, _hhmm(now_min)))
    sw = lambda k: '<span class="rt-swatch %s"></span>%s' % (k, PHASE_LABELS[k])
    legend = ('<p class="timeline-legend">Bars: %s, %s, %s and %s; Expected (filled diamond) is the sum of the phases. '
              'The thin grey extension is a named risk from the estimate\'s basis, ending at the outlined worst case. '
              'An outline diamond alone: a day estimate with no time yet. The axis breaks between today and later days.</p>'
              % tuple(sw(k) for k in RELEASE_PHASES))
    if others:
        legend = legend[:-4] + (' Under %s, a bar runs from the start to its Expected, coloured by status; '
                                'a red outline means it is past its Expected.</p>' % OTHER_TITLE)
    return ('<figure class="release-timeline">\n<figcaption>Next releases (%s)</figcaption>\n'
            '<div class="timeline-scroll"><svg viewBox="0 0 %d %d" role="img" aria-label="%s" style="min-width:%dpx;max-width:%dpx">'
            '<g class="rt-axis">%s</g>\n%s\n%s\n</svg></div>\n%s\n</figure>\n'
            % (esc(label), width, height, esc(('Next releases: ' + '; '.join(aria) + '.' if aria else '') + ((' ' if aria else '') + OTHER_TITLE + ': ' + '; '.join(aria_other) + '.' if aria_other else '')), max(360, round(width * 640 / 900)), width,
               ''.join(grid), '\n'.join(out), now, legend))


# ------------------------------------------------------------------ State column (R5.44)
STATE_ORDER = ('Running', 'Needs you', 'Failed', 'Waiting', 'Built', 'To do', 'On hold')


def state_chips(tasks: list, decisions=()) -> list:
    """R5.44: [(chip class, text)] for one feature: Complete, or a chip per open status and per open decision."""
    counts = {s: sum(1 for t in tasks if t.get('status') == s) for s in STATE_ORDER}
    waiting = len(open_decisions(decisions))
    if not any(counts.values()) and not waiting:
        return [('status-live', 'Complete')]
    chips = [(status_class(s), '%d %s' % (counts[s], s)) for s in STATE_ORDER if counts[s]]
    if waiting:
        chips.append(('status-needs-you', '%d open decision%s' % (waiting, '' if waiting == 1 else 's')))
    return chips


def _state_cell(tasks: list, decisions=()) -> str:
    chips = ''.join('<span class="status-chip %s">%s</span>' % (c, esc(t)) for c, t in state_chips(tasks, decisions))
    return '<td data-col="state"><span class="state-chips">%s</span></td>' % chips


def tile_label(status: str, count: int) -> str:
    """R5.8a: what a tile counts, `tasks live`, and `task running` for one."""
    return '%s %s' % ('task' if count == 1 else 'tasks', status.lower())


def _tiles(tasks: list) -> str:
    counts = {s: 0 for s in STATUSES}
    for task in tasks:
        counts[task['status']] += 1
    return '<div class="status-count-tiles">' + ''.join(
        '<div class="status-count-tile %s"><div class="count">%d</div><div class="label">%s</div></div>'
        % (status_class(s), counts[s], tile_label(s, counts[s])) for s in STATUSES if counts[s]) + '</div>'


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


def _fmt_day(iso: str) -> str:
    year, month, day = iso.split('-')
    return '%02d %s' % (int(day), MONTHS[int(month) - 1])


def _decision_number(decision: dict) -> int:
    return int(decision['id'][1:])


def _option_card(option: dict, decision: dict, replaced: bool) -> str:
    """One option as a card (R5.21, R5.22). A closed decision marks the chosen card and mutes the rest."""
    closed = decision['status'] == 'decided'
    chosen = closed and option['label'] == decision['chosen']
    cls = 'decision-option' + (' decision-chosen' if chosen else ' decision-muted' if closed else '')
    head = '<span class="decision-label">%s</span>' % esc(option['label'])
    if option['recommended']:
        head += ' <span class="decision-tag">Recommended</span>'
    if chosen:
        head += ' <span class="decision-chip decision-chip-chosen">Chosen by the owner &middot; %s</span>' % esc(_fmt_day(decision['decided']))
    elif closed:
        head += ' <span class="decision-chip decision-chip-muted">Not chosen</span>'
    out = ['<div class="%s">' % cls, '<div class="decision-option-head">%s</div>' % head,
           '<p class="decision-summary">%s</p>' % esc(option['summary'])]
    if option['preview']:
        out.append('<div class="decision-preview">%s</div>' % option['preview'])
    elif option['image_uri']:
        out.append('<div class="decision-preview"><img class="decision-image" src="%s" alt="%s"></div>'
                   % (esc(option['image_uri']), esc(option['label'])))
    if chosen and decision['owner_words']:
        out.append('<blockquote class="decision-words">&ldquo;%s&rdquo;</blockquote>' % esc(decision['owner_words']))
    out.append('</div>')
    return '\n'.join(out)


def _decisions(decisions: list) -> str:
    """The generated Decisions section, newest decision first (R5.20 to R5.23)."""
    replaced_by = {}
    for decision in sorted(decisions, key=_decision_number):
        if decision.get('replaces'):
            replaced_by[decision['replaces']] = decision['id']
    blocks = []
    for decision in sorted(decisions, key=_decision_number, reverse=True):
        did = decision['id']
        replaced = did in replaced_by
        meta = ['Asked %s' % _fmt_day(decision['asked'])]
        if decision['status'] == 'decided':
            meta.append('Decided %s' % _fmt_day(decision['decided']))
        if decision['task']:
            meta.append('Task %s' % decision['task'])
        if decision['replaces']:
            meta.append('Replaces %s' % decision['replaces'])
        question = '<span class="decision-id">%s</span> <span class="decision-question">%s</span>' % (esc(did), esc(decision['question']))
        if decision['status'] == 'open' and not replaced:
            question += ' ' + _chip('Needs you')
        body = ('<p class="decision-meta">%s</p>\n<div class="decision-options">\n%s\n</div>'
                % (esc(' \u00b7 '.join(meta)), '\n'.join(_option_card(o, decision, replaced) for o in decision['options'])))
        if replaced:
            blocks.append('<details class="decision decision-replaced" data-decision="%s"><summary>%s <span class="decision-replaced-by">'
                          'Replaced by %s</span></summary>\n%s\n</details>' % (esc(did), question, esc(replaced_by[did]), body))
        else:
            blocks.append('<article class="decision decision-%s" data-decision="%s">\n<h3 class="decision-head">%s</h3>\n%s\n</article>'
                          % (decision['status'], esc(did), question, body))
    return '<div class="decision-list">\n%s\n</div>\n' % '\n'.join(blocks)


def _decisions_open_line(decisions) -> str:
    count = len(open_decisions(decisions))
    return '' if not count else ' %d decision%s open.' % (count, '' if count == 1 else 's')


TIME_ATTR_RE = re.compile(r'<time\b[^>]*\bdatetime="([^"]+)"')


def feature_updated(entry: dict, record_dir: str) -> str:
    """The ISO stamp of a feature's page, as Full Progress section 1 shows it (R5.6): the manifest entry's
    `updated` (written whenever the script writes the page with a new stamp, R4.20), else the `<time datetime>`
    of the feature file for a record that has none, else ''."""
    value = entry.get('updated')
    if isinstance(value, str) and ISO_OFFSET_RE.match(value) and _parse_iso(value) is not None:
        return value
    try:
        text = _read(os.path.join(record_dir, str(entry.get('file', ''))))
    except (OSError, ContentError):
        return ''
    found = TIME_ATTR_RE.search(text)
    if found and ISO_OFFSET_RE.match(found.group(1)) and _parse_iso(found.group(1)) is not None:
        return found.group(1)
    return ''


def _utc_minutes(iso: str) -> int:
    moment = _parse_iso(iso)
    if moment is None:
        return 0
    return int(moment.astimezone(timezone.utc).timestamp() // 60)


def _sort_header(label: str, name: str, order: str) -> str:
    arrow = {'ascending': '&uarr;', 'descending': '&darr;'}.get(order, '')
    return ('<th scope="col"%s><button type="button" class="sort-header" data-sort="%s">%s '
            '<span class="sort-arrow" aria-hidden="true">%s</span></button></th>'
            % (' aria-sort="%s"' % order if order else '', name, esc(label), arrow))


def _feature_section(manifest: dict, tasks: list, contents: dict, problems: list, feature_links: dict,
                     record_dir: str = '') -> str:
    rows = []
    for entry in manifest.get('feature_artifacts') or []:
        content = contents.get(entry['key'])
        if content is None:
            problems.append('no content loaded for feature artifact %r (needed for R5.6)' % entry['key'])
            continue
        title = esc(entry['title'])
        link = _link(feature_links[entry['key']], title)
        stands = _first_sentence(content['meta']['lede'])
        if not stands:                    # R5.36: an empty note never leaves the column blank
            stands = feature_summary([t for t in tasks if t.get('owner') == entry['key']], content.get('decisions')) + '.'
            stands = stands[0].upper() + stands[1:]
        iso = feature_updated(entry, record_dir)
        when = ('<time datetime="%s">%s</time>' % (esc(iso), esc(_fmt_stamp(datetime.fromisoformat(iso)))) if iso else '')
        rows.append((not iso, -_utc_minutes(iso) if iso else 0, str(entry['title']).lower(),
                     '<tr><td data-value="%s">%s</td><td data-value="%d">%s</td><td>%s</td>%s<td>%s</td></tr>' % (
                         esc(str(entry['title']).lower()), link, _utc_minutes(iso) if iso else 0, when,
                         esc(_id_ranges(entry['key'], entry.get('prefix', ''), tasks)),
                         _state_cell([t for t in tasks if t.get('owner') == entry['key']], content.get('decisions')),
                         esc(stands + _decisions_open_line(content.get('decisions'))))))
    rows.sort(key=lambda r: r[:3])      # newest first, no stamp last, ties by title
    return ('<div class="table-scroll"><table class="feature-list"><thead><tr>%s%s<th>Tasks</th>'
            '<th data-col="state">State</th><th>Where it stands</th></tr></thead><tbody>\n%s\n</tbody></table></div>\n'
            % (_sort_header('Feature artifact', 'name', ''), _sort_header('Last updated', 'updated', 'descending'),
               '\n'.join(r[3] for r in rows)))


def _published_line(manifest: dict, label: str) -> str:
    """A feature page's line under its stamp: when Full Progress was last published, linking to it (R5.38).
    Empty before the first publish. It comes from the manifest, never moves the page's stamp."""
    fp = manifest.get('full_progress_artifact')
    if not isinstance(fp, dict):
        return ''
    url, at = fp.get('url'), fp.get('published_at')
    if not (isinstance(url, str) and re.match(r'^https?://\S+$', url) and isinstance(at, str)
            and ISO_OFFSET_RE.match(at) and _parse_iso(at) is not None):
        return ''
    return ('<p class="full-progress-published">Full Progress published: <a href="%s">%s</a> (%s)</p>\n'
            % (esc(url), esc(_fmt_stamp(datetime.fromisoformat(at))), esc(label)))


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


def feature_links_of(manifest: dict, links=None) -> dict:
    """{feature key: (href, path text)}: by default the relative file name with no path text (R5.30);
    `links` maps a key to (href, path text) for the publish copy (R5.31)."""
    out = {}
    for entry in manifest.get('feature_artifacts') or []:
        key = entry.get('key')
        if links is not None and key in links:
            href, shown = links[key]
            out[key] = (str(href), str(shown))
        else:
            out[key] = (str(entry.get('file', '')), '')
    return out


def render_artifact(manifest: dict, registry: dict, contents: dict, key: str, plugin_dir: str,
                    record_dir: str, stamp_text: str, stamp_iso: str, links=None) -> str:
    """The artifact's HTML: a complete document for a feature artifact (R5.27), a fragment beginning
    with <title> for the full-progress artifact (R5.29). Same inputs, same bytes (R7.4).

    `links` is None for the committed render, whose links to feature files are relative (R5.30); the
    publish copy passes {feature key: (href, path text)} (R5.31)."""
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
    feature_links = feature_links_of(manifest, links)
    project = str(manifest.get('project', ''))
    meta = content['meta']

    decisions = content.get('decisions') or []
    lede = '<p class="lede">%s</p>\n' % meta['lede'] if meta['lede'] else ''

    sections = []  # (title, inner html) for sections 1..N
    if kind == 'full-progress':
        feature_problems = []
        sections.append(('Feature artifacts', _feature_section(manifest, tasks, contents, feature_problems, feature_links, record_dir)))
        if feature_problems:
            raise ContentError(feature_problems)
    sections += [(s['title'], s['html']) for s in content['sections']]
    if kind == 'feature':
        if decisions:
            sections.append(('Decisions', _decisions(decisions)))
        sections.append(('History', _history(content['history'])))

    all_titles = ['Status and checklist'] + [t for t, _ in sections]
    nav = ''.join('<a href="#s%d"><b>%d</b>%s</a>' % (i, i, esc(t)) for i, t in enumerate(all_titles))
    body = '\n'.join(_section(i, t, inner) for i, (t, inner) in enumerate(sections, 1))
    ref = moment
    timeline = release_timeline(tasks, moment, label) if kind == 'full-progress' else ''

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
        'published': _published_line(manifest, label) if kind == 'feature' else '',
        'lede': lede,
        'glance': _at_a_glance(mine, decisions, moment),
        'tiles': _tiles(mine),
        'key': _key(label),
        'timeline': ('\n' + timeline.rstrip('\n')) if timeline else '',
        'checklist': _checklist(mine, kind, label, ref, feature_links, tasks),
        'sections': body,
        'registry': _registry_script(registry) if kind == 'full-progress' else '',
    }
    out = _fill(template, values)
    return out if out.endswith('\n') else out + '\n'


# ------------------------------------------------------------------ checks on one artifact's HTML (section 14)
def _check_decisions(node, decisions, add) -> None:
    """R5.20 to R5.23 on the Decisions section: order, one card per option, the choice marked, open and replaced."""
    replaced_by = {d['replaces']: d['id'] for d in sorted(decisions, key=_decision_number) if d.get('replaces')}
    want = [d['id'] for d in sorted(decisions, key=_decision_number, reverse=True)]
    blocks = find_all(node, pred=lambda n: 'data-decision' in n.attrs)
    have = [b.attrs['data-decision'] for b in blocks]
    if have != want:
        add('R5.20', 'the decisions must be listed newest first, %s; found %s' % (want, have))
    by_id = {b.attrs['data-decision']: b for b in blocks}
    for decision in decisions:
        block = by_id.get(decision['id'])
        if block is None:
            continue
        did, closed = decision['id'], decision['status'] == 'decided'
        replaced = did in replaced_by
        if replaced:
            summary = find(block, 'summary')
            if block.tag != 'details' or 'open' in block.attrs or summary is None \
                    or 'Replaced by %s' % replaced_by[did] not in text_of(summary):
                add('R5.23', '%s is replaced by %s and must be a closed <details> with a "Replaced by %s" line'
                    % (did, replaced_by[did], replaced_by[did]))
        elif block.tag != 'article':
            add('R5.23', '%s is not replaced and must not be collapsed' % did)
        question = find(block, 'span', 'decision-question')
        if question is None or text_of(question) != decision['question'] or text_of(find(block, 'span', 'decision-id') or block) != did:
            add('R5.21', '%s must show its ID and question' % did)
        cards = find_all(block, 'div', 'decision-option')
        shown = [text_of(find(c, 'span', 'decision-label') or c) for c in cards]
        if shown != [o['label'] for o in decision['options']]:
            add('R5.21', '%s must show one card per option, in order: %s; found %s' % (did, [o['label'] for o in decision['options']], shown))
            continue
        chosen_cards = [c for c in cards if has_class(c, 'decision-chosen')]
        if closed:
            marked = [text_of(find(c, 'span', 'decision-label')) for c in chosen_cards]
            if marked != [decision['chosen']]:
                add('R5.22', '%s must mark only %r as chosen; it marks %s' % (did, decision['chosen'], marked))
            words = [text_of(q) for c in chosen_cards for q in find_all(c, 'blockquote', 'decision-words')]
            if words != ([u'\u201c%s\u201d' % decision['owner_words']] if decision['owner_words'] else []):
                add('R5.22', '%s must quote the owner\'s words on the chosen card, and only there' % did)
        elif chosen_cards:
            add('R5.23', '%s is open and must have no chosen card' % did)
        for card, option in zip(cards, decision['options']):
            chips = [text_of(c) for c in find_all(card, 'span', 'decision-chip')]
            is_chosen = has_class(card, 'decision-chosen')
            want_chip = [] if not closed else (['Chosen by the owner \u00b7 %s' % _fmt_day(decision['decided'])] if is_chosen else ['Not chosen'])
            if chips != want_chip:
                add('R5.22', '%s option %r has the chips %s; it needs %s' % (did, option['label'], chips, want_chip))
            if closed and not is_chosen and not has_class(card, 'decision-muted'):
                add('R5.22', '%s option %r was not chosen and must be muted' % (did, option['label']))
            tags = [text_of(t) for t in find_all(card, 'span', 'decision-tag')]
            if tags != (['Recommended'] if option['recommended'] else []):
                add('R5.22', '%s option %r must carry the Recommended tag exactly when it is recommended' % (did, option['label']))
        needs = find_all(find(block, 'h3') or find(block, 'summary') or block, 'span', 'status-needs-you')
        if (decision['status'] == 'open' and not replaced) != bool(needs):
            add('R5.23', '%s shows the Needs you chip exactly when it is open and not replaced' % did)


def _check_feature_table(s1, manifest: dict, record_dir: str, add, tasks=(), plugin_dir: str = PLUGIN_DIR) -> None:
    """R5.6, R5.39, R5.44: the columns, the sort buttons, a Last updated time and a State per feature and the default order."""
    table = find(s1, 'table', 'feature-list')
    if table is None:
        add('R5.6', 'section 1 must be a table of the feature artifacts')
        return
    heads = find_all(table, 'th')
    if [text_of(th).rstrip(' ↑↓') for th in heads] != ['Feature artifact', 'Last updated', 'Tasks', 'State', 'Where it stands']:
        add('R5.6', 'section 1 must have the columns Feature artifact, Last updated, Tasks, State, Where it stands')
        return
    buttons = [(find(th, 'button', 'sort-header') if i < 2 else None) for i, th in enumerate(heads)]
    for button, name in zip(buttons[:2], ('name', 'updated')):
        if button is None or button.attrs.get('data-sort') != name or button.attrs.get('type') != 'button':
            add('R5.39', 'the %s column header must be a <button type="button" class="sort-header" data-sort="%s">'
                % ('Feature artifact' if name == 'name' else 'Last updated', name))
            return
    if heads[1].attrs.get('aria-sort') != 'descending' or heads[0].attrs.get('aria-sort'):
        add('R5.39', 'the committed table is sorted by Last updated, newest first: that header carries aria-sort="descending"')
    entries = {e.get('title'): e for e in manifest.get('feature_artifacts') or []}
    keys = []
    for row in find_all(table, 'tr'):
        cells = [c for c in row.children if getattr(c, 'tag', None) == 'td']
        if len(cells) != 5:
            continue
        title = text_of(cells[0]).replace('Copy link', '').strip()
        anchor = find(cells[0], 'a')
        title = text_of(anchor) if anchor is not None else title
        time_node = find(cells[1], 'time')
        shown = text_of(cells[1]).strip()
        iso = time_node.attrs.get('datetime', '') if time_node is not None else ''
        entry = entries.get(title)
        want = feature_updated(entry, record_dir) if entry is not None else ''
        if iso != want:
            add('R5.6', 'the Last updated time of %r must be its page\'s stamp %r; it shows %r' % (title, want, iso))
        elif iso and shown != _fmt_stamp(datetime.fromisoformat(iso)):
            add('R5.6', 'the Last updated time of %r must read DD Mon HH:MM; it shows %r' % (title, shown))
        keys.append((not iso, -_utc_minutes(iso) if iso else 0, title.lower()))
        if entry is not None:
            try:
                dec = load_content(record_dir, entry['key'], plugin_dir).get('decisions') or []
            except (ContentError, OSError):
                dec = []
            want_chips = state_chips([t for t in tasks if t.get('owner') == entry['key']], dec)
            have_chips = [([c for c in n.attrs.get('class', '').split() if c.startswith('status-') and c != 'status-chip'], text_of(n))
                          for n in find_all(cells[3], 'span', 'status-chip')]
            if have_chips != [([c], t) for c, t in want_chips]:
                add('R5.44', 'the State of %r must read %s; it shows %s' % (title, [t for _, t in want_chips], [t for _, t in have_chips]))
    if keys != sorted(keys):
        add('R5.39', 'the committed table must list the features by Last updated, newest first, ties by title')


FONT_HOST_RE =re.compile(r'^https://fonts\.(googleapis|gstatic)\.com(/|$)')


def _check_document(html: str, root, kind: str, add) -> None:
    """R5.27 to R5.29: a feature artifact is a complete document that needs nothing but a browser; the
    full-progress artifact is a fragment beginning with <title>."""
    text = html.lstrip('\ufeff')
    if kind == 'full-progress':
        if re.match(r'\s*<!doctype', text, re.I) or any(find(root, tag) is not None for tag in ('html', 'head', 'body')):
            add('R5.29', 'the full-progress artifact is a fragment: no doctype, <html>, <head> or <body>')
        if not text.startswith('<title>'):
            add('R5.29', 'the full-progress artifact must begin with <title>')
        return
    if not re.match(r'\s*<!doctype html>', text, re.I):
        add('R5.27', 'a feature artifact must begin with <!doctype html>')
    html_node, head, body = find(root, 'html'), find(root, 'head'), find(root, 'body')
    if html_node is None or not html_node.attrs.get('lang'):
        add('R5.27', 'a feature artifact needs <html lang="...">')
    if head is None or body is None:
        add('R5.27', 'a feature artifact needs a <head> and a <body>')
    else:
        metas = find_all(head, 'meta')
        if not any(m.attrs.get('charset', '').lower() == 'utf-8' for m in metas):
            add('R5.27', 'the <head> needs <meta charset="utf-8">')
        if not any(m.attrs.get('name') == 'viewport' and 'width=device-width' in m.attrs.get('content', '') for m in metas):
            add('R5.27', 'the <head> needs <meta name="viewport" content="width=device-width, initial-scale=1">')
        if find(head, 'title') is None:
            add('R5.27', 'the <title> belongs in the <head>')
        if find(body, 'main') is None:
            add('R5.27', 'the page (<main>) belongs in the <body>')
    for link in find_all(root, 'link'):
        href, rel = link.attrs.get('href', ''), link.attrs.get('rel', '').lower()
        if rel not in ('preconnect', 'stylesheet') or not FONT_HOST_RE.match(href):
            add('R5.28', 'the only <link> a feature artifact may hold is the Google Fonts link; found rel=%r href=%r' % (rel, href))
        elif rel == 'stylesheet' and not href.startswith('https://fonts.googleapis.com/'):
            add('R5.28', 'the only stylesheet link allowed is on fonts.googleapis.com; found %r' % href)
    for script in find_all(root, 'script'):
        if 'src' in script.attrs:
            add('R5.28', 'a feature artifact loads no external script (<script src=%r>)' % script.attrs['src'])
    for node in elements(root):
        for attr in ('src', 'srcset', 'poster', 'data'):
            value = node.attrs.get(attr)
            if value and node.tag != 'script' and not value.lower().startswith('data:'):
                add('R5.28', 'a feature artifact references no file outside itself (<%s %s=%r>)' % (node.tag, attr, value))
    for style in find_all(root, 'style'):
        css = _strip_comments(''.join(c.text for c in style.children))
        if re.search(r'@import|url\(\s*[\'"]?\s*(https?:|//|file:)', css, re.I):
            add('R5.28', 'the <style> %r imports or loads an external resource' % style.attrs.get('id', '?'))


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
    all_by_id = {t['id']: t for t in all_tasks if 'id' in t}
    feature_files = {e['key']: e.get('file', '') for e in manifest.get('feature_artifacts') or []}
    root = parse_dom(html)
    _check_document(html, root, kind, add)
    decisions = []
    if kind == 'feature':
        try:
            decisions = load_content(record_dir, key, plugin_dir).get('decisions') or []
        except (ContentError, OSError):
            decisions = []       # an invalid content folder is reported by the record checks

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
        parts = [('stamp', find(s0, 'p', 'last-update')), ('at a glance', find(s0, 'div', 'at-a-glance')),
                 ('tiles', find(s0, 'div', 'status-count-tiles')), ('status key', find(s0, 'p', 'note')),
                 ('checklist', find(s0, 'table', 'status-checklist'))]
        lede_node = find(s0, 'p', 'lede')       # optional (R5.7): the session's note
        missing = [name for name, node in parts if node is None]
        if missing:
            add('R5.3', 'section 0 lacks: %s' % ', '.join(missing))
        else:
            wanted_order = parts[:1] + ([('lede', lede_node)] if lede_node is not None else []) + parts[1:]
            positions = [order.index(node) for _, node in wanted_order]
            if positions != sorted(positions):
                add('R5.3', 'section 0 must hold the stamp, the lede (if any), at a glance, tiles, status key and checklist in that order')
        key_node = parts[3][1]
        if key_node is not None and [text_of(c) for c in find_all(key_node, 'span', 'status-chip')] != list(STATUSES):
            add('R5.3', 'the status key must show the eight statuses in order')

    # R5.38 the line under a feature's stamp: when Full Progress was last published
    if s0 is not None:
        want_line = _published_line(manifest, label) if kind == 'feature' else ''
        lines = find_all(s0, 'p', 'full-progress-published')
        stamp_node = find(s0, 'p', 'last-update')
        if want_line:
            want_node = find(parse_dom(want_line), 'p')
            anchor, want_anchor = (find(lines[0], 'a') if lines else None), find(want_node, 'a')
            order_s0 = list(elements(s0))
            if len(lines) != 1 or text_of(lines[0]) != text_of(want_node) \
                    or anchor is None or anchor.attrs.get('href') != want_anchor.attrs.get('href'):
                add('R5.38', 'the line under the stamp must read %r and link to Full Progress\'s URL' % text_of(want_node))
            elif stamp_node is None or order_s0.index(lines[0]) != order_s0.index(stamp_node) + 1 + len(list(elements(stamp_node))):
                add('R5.38', 'the Full Progress published line must come right under the stamp')
        elif lines:
            add('R5.38', 'the Full Progress published line belongs only on a feature artifact, after Full Progress was published')

    # R5.5 stamp
    ref =_parse_iso('2000-01-01T00:00+00:00')
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

    # R5.42, R5.43 the release timeline: present exactly when a release is open, between the key and the checklist
    if kind == 'full-progress' and s0 is not None:
        want_fig = release_timeline(all_tasks, ref, label)
        figs = find_all(s0, 'figure', 'release-timeline')
        if not want_fig:
            if figs:
                add('R5.42', 'the release timeline belongs only when a release is open')
        elif len(figs) != 1:
            add('R5.42', 'section 0 must hold exactly one release timeline while a release is open; it holds %d' % len(figs))
        else:
            want_node = find(parse_dom(want_fig), 'figure')
            svg, want_svg = find(figs[0], 'svg'), find(want_node, 'svg')
            cap, want_cap = find(figs[0], 'figcaption'), find(want_node, 'figcaption')
            if cap is None or text_of(cap) != text_of(want_cap):
                add('R5.42', 'the timeline caption must read %r' % text_of(want_cap))
            if svg is None or svg.attrs.get('role') != 'img' or svg.attrs.get('aria-label') != want_svg.attrs.get('aria-label'):
                add('R5.43', 'the timeline must be an svg with role="img" and the aria-label %r' % want_svg.attrs.get('aria-label'))
            if find(figs[0], 'p', 'timeline-legend') is None or find(figs[0], 'div', 'timeline-scroll') is None:
                add('R5.43', 'the timeline needs its legend and its scrolling box')
            key_p, checklist_t = find(s0, 'p', 'note'), find(s0, 'table', 'status-checklist')
            order_s0 = list(elements(s0))
            if key_p is not None and checklist_t is not None and not (
                    order_s0.index(key_p) < order_s0.index(figs[0]) < order_s0.index(checklist_t)):
                add('R5.42', 'the release timeline must sit between the status key and the checklist')

    # R5.42a a timed release within 24 hours belongs on the time axis, never in a day slot
    if kind == 'full-progress' and s0 is not None:
        figs = find_all(s0, 'figure', 'release-timeline')
        if len(figs) == 1:
            rows = [r for r in (_release_row(t, ref, all_tasks) for t in open_releases(all_tasks)) if r is not None]
            want_slots = sum(1 for r in rows if not r['today']) + sum(
                1 for r in (_other_row(t, ref) for t in all_tasks) if r is not None and not r['today'])
            if len(find_all(figs[0], 'polygon', 'rt-day')) > want_slots:
                add('R5.42a', 'a release with a time within 24 hours of the stamp must be drawn on the time axis, not in a day slot')

    # R5.7 the Needs you group, R5.33 to R5.35 the At a glance block
    glance = find(s0, 'div', 'at-a-glance') if s0 is not None else None
    if glance is not None:
        valid = [t for t in mine if t.get('status') in STATUSES]
        want_groups = glance_groups(valid, decisions, ref)
        have, counts, have_deps = [], {}, {}
        for g in find_all(glance, 'details', 'glance-group'):
            kids = [n for n in g.children if getattr(n, 'tag', None)]
            summ = kids[0] if kids and kids[0].tag == 'summary' else None
            if summ is None or find(summ, 'span', 'glance-label') is None or find(summ, 'span', 'fold-count') is None:
                add('R6.13', 'glance group %r must be a <details> whose first child is a <summary> holding the label and the count' % g.attrs.get('data-glance', ''))
            if ('open' in g.attrs) != glance_open(g.attrs.get('data-glance', '')):
                add('R6.13', 'glance group %r must render %s' % (g.attrs.get('data-glance', ''),
                    'open' if glance_open(g.attrs.get('data-glance', '')) else 'closed (done groups start closed)'))
            tasks_in = [li.attrs.get('data-glance-task') for li in find_all(g, 'li', pred=lambda n: 'data-glance-task' in n.attrs)]
            for li in find_all(g, 'li', pred=lambda n: 'data-glance-task' in n.attrs):
                dep_span = find(li, 'span', 'glance-dep')
                have_deps.setdefault(li.attrs.get('data-glance-task'), {})[g.attrs.get('data-glance', '')] = (
                    text_of(dep_span) if dep_span is not None else '')
            decs_in = [li.attrs.get('data-glance-decision') for li in find_all(g, 'li', pred=lambda n: 'data-glance-decision' in n.attrs)]
            more_li = find(g, 'li', 'glance-more')
            none_p = find(g, 'p', 'glance-none')
            have.append((g.attrs.get('data-glance', ''), tasks_in, decs_in, text_of(more_li) if more_li else '',
                         text_of(none_p) if none_p else ''))
            fold_count = find(summ, 'span', 'fold-count') if summ is not None else None
            counts[g.attrs.get('data-glance', '')] = text_of(fold_count) if fold_count is not None else ''
        wanted_keys = [g[0] for g in want_groups]
        if [h[0] for h in have] != wanted_keys:
            add('R5.33', 'the At a glance groups must be %s in that order; found %s' % (wanted_keys, [h[0] for h in have]))
        by_name = {h[0]: h for h in have}
        for gkey, _label, shown, open_decs, more in want_groups:
            h = by_name.get(gkey)
            if h is None:
                continue
            ids, dec_ids = [t['id'] for t in shown], [d['id'] for d in open_decs]
            total = len(ids) + len(dec_ids) + more
            if h[0] in counts and counts[h[0]] != '%d task%s' % (total, '' if total == 1 else 's'):
                add('R6.13', 'glance group %r shows the count %r; it holds %d' % (gkey, counts[h[0]], total))
            for li_id in [i for i in ids if i in h[1]]:
                task = next(t for t in shown if t['id'] == li_id)
                want_dep = _norm(glance_dependency(task, {t['id']: t for t in valid})) if (
                    gkey in ('you', 'waiting') and task['status'] in ('Waiting', 'On hold', 'Needs you')) else ''
                if want_dep and have_deps.get(li_id, {}).get(gkey) != want_dep:
                    add('R5.34a', 'the %r group row %s must show its dependency %r first; it shows %r'
                        % (gkey, li_id, want_dep, have_deps.get(li_id, {}).get(gkey, '')))
            if gkey == 'you':
                empty_text = 'Nothing needs you.'
                if (h[1], h[2]) != (ids, dec_ids) or (not ids and not dec_ids and h[4] != empty_text) or (ids or dec_ids) and h[4]:
                    add('R5.7', 'the Needs you group must list %s then decisions %s, or read %r when none; it lists %s then %s%s'
                        % (ids, dec_ids, empty_text, h[1], h[2], (' and reads %r' % h[4]) if h[4] else ''))
            else:
                want_more = 'and %d more' % more if more else ''
                if h[1] != ids or h[2] or h[3] != want_more:
                    add('R5.35', 'the %r group must list %s%s; it lists %s%s' % (
                        gkey, ids, (' and "%s"' % want_more) if want_more else '', h[1],
                        (' and "%s"' % h[3]) if h[3] else ''))

    # checklist tables
    tables = find_all(root, 'table', 'status-checklist')
    wanted_cols = _columns(kind, label)
    rows = []
    group_marks = []  # (group key, title) of each group fold, in page order
    table_group = {}  # id(table) -> group key of the fold that holds it
    for fold in find_all(root, 'details', 'status-fold'):
        gkey = fold.attrs.get('data-group', '')
        kids = [n for n in fold.children if getattr(n, 'tag', None)]
        summary = kids[0] if kids and kids[0].tag == 'summary' else None
        strong = find(summary, 'strong') if summary is not None else None
        group_marks.append((gkey, text_of(strong) if strong is not None else ''))
        if summary is None or strong is None:
            add('R6.12', 'group %r must be a <details> whose first child is a <summary> holding the group heading in <strong>' % gkey)
        if ('open' in fold.attrs) != group_open(gkey):
            add('R6.12', 'group %r must render %s' % (gkey, 'open' if group_open(gkey) else 'closed (Live or built always starts closed)'))
        for inner in find_all(fold, 'table', 'status-checklist'):
            table_group[id(inner)] = gkey
    for table_no, table in enumerate(tables):
        folded = has_ancestor(table, lambda n: n.tag == 'details' and has_class(n, 'earlier'))
        cols = [text_of(th) for th in find_all(table, 'th')]
        if cols != wanted_cols:
            add('R6.4', 'checklist columns are %s; this kind needs %s' % (cols, wanted_cols))
        current = table_group.get(id(table), '')
        if not current and (len(tables) > 1 or find_all(table, 'tr', pred=lambda n: has_ancestor(n, lambda a: a.tag == 'tbody'))):
            add('R6.12', 'a checklist table must sit inside a group <details class="status-fold">')
        for tr in find_all(table, 'tr', pred=lambda n: has_ancestor(n, lambda a: a.tag == 'tbody')):
            if has_class(tr, 'status-group'):
                add('R6.12', 'group headings are <summary> elements of collapsible groups, not table rows')
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
            skipped = lambda n: has_class(n, 'task-id') or has_class(n, 'release-name') or has_class(n, 'release-line') or has_class(n, 'no-release-line')
            row['item'] = text_of(item_cell, skip=skipped) if item_cell else ''
            line = find(item_cell, 'span', 'release-line') if item_cell else None
            row['release_line'] = text_of(line) if line else ''
            nline = find(item_cell, 'span', 'no-release-line') if item_cell else None
            row['no_release_line'] = text_of(nline) if nline else ''
            leading = [n for n in find_all(item_cell, 'span', 'release-name')
                       if not has_ancestor(n, lambda a: has_class(a, 'release-line'))] if item_cell else []
            row['release_name'] = ' '.join(text_of(n) for n in leading)
            anchor = find(item_cell, 'a') if item_cell else None
            row['href'] = anchor.attrs.get('href') if anchor else None
            offset = 1 if kind == 'full-progress' else 0
            row['app'] = text_of(cells[2]) if kind == 'full-progress' and len(cells) > 2 else ''
            row['detail'] = text_of(cells[2 + offset]) if len(cells) > 2 + offset else ''
            row['expected'] = (text_of(cells[3 + offset], skip=lambda n: has_class(n, 'expected-basis'))
                               if len(cells) > 3 + offset else '')
            basis = find(cells[3 + offset], 'span', 'expected-basis') if len(cells) > 3 + offset else None
            row['basis'] = text_of(basis) if basis else ''
            rows.append(row)
    if not tables:
        add('R6.4', 'the artifact has no checklist table')

    # R6.1 statuses and chip classes
    for row in rows:
        if row['status'] not in STATUSES:
            add('R6.1', 'task %s has status %r, which is not one of the eight' % (row['id'], row['status']))
        elif row['chip_class'] != [status_class(row['status'])]:
            add('R6.1', 'task %s chip class %s does not match status %r' % (row['id'], row['chip_class'], row['status']))

    # R6.2, R5.46 and R6.3 groups, order and the Earlier fold
    greq = 'R5.46' if kind == 'full-progress' else 'R6.2'
    expected_groups = group_tasks([t for t in mine if t.get('status') in STATUSES], ref, kind)
    group_of_task = {t['id']: gkey for gkey, _, shown, _ in expected_groups for t in shown}
    shown_wanted = [(g, t) for g, t, shown, old in expected_groups if shown or old]
    shown_found = [(m[0], m[1]) for m in group_marks]
    if shown_found != shown_wanted:
        add(greq, 'the checklist groups are %s; the registry needs %s, in that order' % (
            [t for _, t in shown_found], [t for _, t in shown_wanted]))
    for row in rows:
        if row['id'] in group_of_task and not row['folded'] and row['group'] != group_of_task[row['id']]:
            add(greq, 'task %s (%s) is under group %r; it belongs under %r' % (
                row['id'], row['status'], row['group'], group_of_task[row['id']]))
    by_id = {t['id']: t for t in mine if 'id' in t}
    for gkey, _, shown, _ in expected_groups:
        want = [t['id'] for t in shown]
        have = [r['id'] for r in rows if r['group'] == gkey and not r['folded'] and r['id'] in want]
        if have != [i for i in want if i in have]:
            add(greq, 'rows under group %r are in the order %s; they must be %s' % (gkey, have, [i for i in want if i in have]))
    # R5.45, R5.46 the release name of a release row, and the release line of a row that rode one
    shown_line = {t['id'] for gkey, _, shown, old in expected_groups for t in shown if wants_release_line(kind, gkey)}
    shown_line |= {t['id'] for _, _, _, old in expected_groups for t in old}
    for row in rows:
        task = by_id.get(row['id'])
        if task is None:
            continue
        want_name = release_name(task) if is_release(task) else ''
        if row['release_name'] != want_name:
            add('R5.45', 'task %s must show the release name %r at the start of its Item; it shows %r'
                % (row['id'], want_name, row['release_name']))
        target = rode_release(task, all_by_id) if row['id'] in shown_line else None
        want_line = release_name(target) if target is not None else ''
        if row['release_line'] != want_line:
            add('R5.46', 'task %s must show the release line %r under its Item; it shows %r'
                % (row['id'], want_line, row['release_line']))
        want_nr = NO_RELEASE_LINE % no_release_reason(task) if no_release_reason(task) else ''
        if row['no_release_line'] != want_nr:
            add('R5.47a', 'task %s must show the line %r under its Item; it shows %r'
                % (row['id'], want_nr, row['no_release_line']))
    details = find_all(root, 'details', 'earlier')
    folded_wanted = {t['id'] for _, _, _, old in expected_groups for t in old}
    folded_found = {r['id'] for r in rows if r['folded']}
    if kind == 'feature' and details:
        add('R6.3', 'only the full-progress artifact has an Earlier fold')
    if kind == 'full-progress':
        if folded_found != folded_wanted:
            add('R6.3', 'Live rows older than %d days (and only Live rows) belong in Earlier: expected %s, found %s'
                % (EARLIER_DAYS, sorted(folded_wanted), sorted(folded_found)))
        for node in details:
            summary = find(node, 'summary')
            if 'open' in node.attrs or summary is None or text_of(summary) != 'Earlier':
                add('R6.3', 'the Earlier fold must be a closed <details> titled "Earlier"')
            if not has_ancestor(node, lambda n: n.tag == 'details' and has_class(n, 'status-fold') and n.attrs.get('data-group') == 'built'):
                add('R6.3', 'the Earlier fold must sit inside the Live or built group (R6.12)')

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
        pairs = [('status', task.get('status'), row['status']), ('item', _norm(shown_item(task)), row['item']),
                 ('detail', _norm(task.get('detail', '')), row['detail']), ('expected', _norm(task.get('expected', '')), row['expected'])]
        if kind == 'full-progress':
            pairs.append(('app', _norm(task.get('app', '')), row['app']))
        for field, want, have in pairs:
            if want != have:
                add('INV-1', 'task %s %s is %r in the checklist; the registry says %r' % (tid, field, have, want))
        if row['basis'] != (_norm(task.get('expected_basis', '')) if task.get('status') in OPEN_STATUSES else ''):
            add('R6.10', 'task %s shows the basis %r; the registry says %r' % (tid, row['basis'], task.get('expected_basis', '')))
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
    want_tiles = [(tile_label(s, sum(1 for t in mine if t.get('status') == s)), str(sum(1 for t in mine if t.get('status') == s)),
                   [status_class(s)]) for s in STATUSES if any(t.get('status') == s for t in mine)]
    if have_tiles != want_tiles:
        add('R5.8', 'the tiles read %s; the registry needs %s' % (
            [(a, b) for a, b, _ in have_tiles], [(a, b) for a, b, _ in want_tiles]))

    # R6.5 and R5.30 full-progress links: relative, to the feature file
    if kind == 'full-progress':
        for task in mine:
            owner = task.get('owner')
            if owner == 'project' or owner not in feature_files:
                continue
            row = seen.get(task.get('id'), [None])[0]
            if row is None:
                add('R6.5', 'feature task %s is missing from the full-progress artifact' % task.get('id'))
            elif row['href'] is None:
                add('R6.5', 'feature task %s must link to its feature file %s' % (task.get('id'), feature_files[owner]))
            elif row['href'] != feature_files[owner]:
                add('R5.30', 'feature task %s must link to %s, relative to this file; it links to %r'
                    % (task.get('id'), feature_files[owner], row['href']))

    # R5.6 feature list on the full-progress artifact
    if kind == 'full-progress':
        s1 = info[1]['node'] if len(info) > 1 else None
        if s1 is None or info[1]['title'] != 'Feature artifacts':
            add('R5.6', 'section 1 must list the feature artifacts')
        else:
            shown = text_of(s1)
            for e in manifest.get('feature_artifacts') or []:
                anchors = [a for a in find_all(s1, 'a') if text_of(a) == e.get('title')]
                if e.get('title') not in shown or not anchors:
                    add('R5.6', 'section 1 must list %r with its link' % e.get('title'))
                elif not any(a.attrs.get('href') == e.get('file') for a in anchors):
                    add('R5.30', 'section 1 must link %r to %s, relative to this file; it links to %r'
                        % (e.get('title'), e.get('file'), anchors[0].attrs.get('href')))
            _check_feature_table(s1, manifest, record_dir, add, all_tasks, plugin_dir)

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

    # R5.20 to R5.23 Decisions
    decision_sections = [i for i in info if i['title'] == 'Decisions']
    if kind == 'feature' and decisions:
        if len(info) < 3 or info[-2]['title'] != 'Decisions' or len(decision_sections) != 1:
            add('R5.20', 'when decisions.json has decisions, one section named Decisions must come just before History')
        else:
            _check_decisions(info[-2]['node'], decisions, add)
    elif kind == 'feature' and decision_sections:
        add('R5.20', 'a Decisions section may only be drawn from the decisions.json of a feature artifact')

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
