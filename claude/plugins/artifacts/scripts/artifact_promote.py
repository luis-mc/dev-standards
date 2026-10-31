"""Promote a feature artifact's decided content into a feature spec (DOCSPEC R4.10, R10.4).

Pure functions used by `project_artifacts.py promote-to-spec`; nothing here touches the record. The output follows
luismc-docs' `templates/feature-spec.md` (front matter of R4.2; sections mapped by heading, see `classify`). Standard library only.
"""
import difflib
import html
import json
import re
from html.parser import HTMLParser

TITLE_RE = re.compile(r'^\s*<!--\s*title:\s*(.*?)\s*-->[ \t]*\n?', re.S)
SECTION_RE = re.compile(r'^\d+-.*\.html$')


class _MD(HTMLParser):
    BLOCK = {'p', 'div', 'section', 'ul', 'ol', 'pre', 'table', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'blockquote'}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out = []
        self.lists = []
        self.skip = 0
        self.pre = False
        self.href = []
        self.row = None
        self.cell = None
        self.rows = []

    def _w(self, s):
        if self.cell is not None:
            self.cell.append(s)
        else:
            self.out.append(s)

    def _gap(self):
        if self.out and not ''.join(self.out[-2:]).endswith('\n\n'):
            self.out.append('\n\n' if not ''.join(self.out[-1:]).endswith('\n') else '\n')

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ('script', 'style'):
            self.skip += 1
        elif tag in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
            self._gap()
            self.out.append('#' * min(int(tag[1]) + 2, 6) + ' ')   # h2 of a section -> ####; keeps the spec's own levels
        elif tag in ('p', 'div', 'section', 'blockquote'):
            self._gap()
        elif tag in ('ul', 'ol'):
            self._gap()
            self.lists.append([tag, 0])
        elif tag == 'li' and self.lists:
            self.lists[-1][1] += 1
            mark = '- ' if self.lists[-1][0] == 'ul' else '%d. ' % self.lists[-1][1]
            self.out.append('\n' + '  ' * (len(self.lists) - 1) + mark)
        elif tag == 'pre':
            self._gap()
            self.out.append('```\n')
            self.pre = True
        elif tag == 'code' and not self.pre:
            self._w('`')
        elif tag in ('strong', 'b'):
            self._w('**')
        elif tag in ('em', 'i'):
            self._w('*')
        elif tag == 'a':
            self.href.append(a.get('href') or '')
            self._w('[')
        elif tag == 'br':
            self._w('\n')
        elif tag == 'img':
            self._w('![%s](%s)' % (a.get('alt') or '', a.get('src') or ''))
        elif tag == 'tr':
            self.row = []
        elif tag in ('td', 'th') and self.row is not None:
            self.cell = []

    def handle_endtag(self, tag):
        if tag in ('script', 'style'):
            self.skip = max(0, self.skip - 1)
        elif tag in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'div', 'section', 'blockquote'):
            self.out.append('\n\n')
        elif tag in ('ul', 'ol'):
            if self.lists:
                self.lists.pop()
            self.out.append('\n\n' if not self.lists else '')
        elif tag == 'pre':
            self.out.append('\n```\n\n')
            self.pre = False
        elif tag == 'code' and not self.pre:
            self._w('`')
        elif tag in ('strong', 'b'):
            self._w('**')
        elif tag in ('em', 'i'):
            self._w('*')
        elif tag == 'a' and self.href:
            self._w('](%s)' % self.href.pop())
        elif tag in ('td', 'th') and self.cell is not None and self.row is not None:
            self.row.append(' '.join(''.join(self.cell).split()).replace('|', '\\|'))
            self.cell = None
        elif tag == 'tr' and self.row is not None:
            self.rows.append(self.row)
            self.row = None
        elif tag == 'table':
            if self.rows:
                w = max(len(r) for r in self.rows)
                rows = [r + [''] * (w - len(r)) for r in self.rows]
                lines = ['| ' + ' | '.join(rows[0]) + ' |', '|' + '---|' * w] + ['| ' + ' | '.join(r) + ' |' for r in rows[1:]]
                self._gap()
                self.out.append('\n'.join(lines) + '\n\n')
            self.rows = []

    def handle_data(self, data):
        if self.skip:
            return
        self._w(data if self.pre else re.sub(r'\s+', ' ', data))


def html_to_md(fragment):
    p = _MD()
    p.feed(fragment)
    p.close()
    text = ''.join(p.out)
    text = re.sub(r'[ \t]+\n', '\n', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def sections(files):
    """[(title, markdown)] for the NN-*.html files of a content folder ({name: bytes}), in order."""
    out = []
    for name in sorted(n for n in files if SECTION_RE.match(n)):
        text = files[name].decode('utf-8')
        m = TITLE_RE.match(text)
        title = m.group(1) if m else name
        out.append((html.unescape(title), html_to_md(text[m.end():] if m else text)))
    return out


def decided(files):
    """(decided decisions, open decisions) from decisions.json, in file order."""
    raw = files.get('decisions.json')
    if not raw:
        return [], []
    items = json.loads(raw.decode('utf-8')).get('decisions', [])
    return [d for d in items if d.get('status') == 'decided'], [d for d in items if d.get('status') != 'decided']


def _cell(s):
    return ' '.join(str(s or '').split()).replace('|', '\\|')


SLOTS = {1: 'In one paragraph', 2: 'Why', 3: 'How it works', 4: 'Screens and states', 5: 'Functional requirements',
         6: 'Non-functional requirements', 7: 'Design', 8: 'Failure modes', 9: 'How it is proven', 10: 'Decisions',
         11: 'Not built yet', 12: 'Code map'}

# First match wins; order matters ("non-functional" before "functional", "for developers" before plain words).
_RULES = [
    (10, r'\bdecisions?\b'),
    (12, r'\bcode map\b|\bsource files?\b|\bwhere the code\b'),
    (11, r'not (yet )?built|not implemented|\bbacklog\b|\broadmap\b|\bfuture work\b|\bleft to do\b'),
    (9, r'how (it is|it.s) (proven|tested)|\btests?\b|\bverification\b|\bproof\b|\bacceptance tests?\b'),
    (8, r'\bfailure modes?\b|\bfailures?\b|\bwhen it fails\b|\bfallbacks?\b|\berror handling\b'),
    (6, r'non[- ]?functional|\bnfrs?\b|\bperformance\b|\bsecurity\b|\bprivacy\b|\baccessibility\b|\blimits?\b|\bbudgets?\b'),
    (5, r'functional requirements?|\bfrs?\b|\brequirements?\b|\bacceptance criteria\b|\bmust have\b'),
    (7, r'for (developers?|engineers?)|\bdevelopers?\b|\bengineers?\b|\bdata model\b|\binterfaces?\b|\bimplementation\b|\barchitecture\b|\bdesign\b|\bapi\b'),
    (4, r'\bscreens?\b|\bvisuals?\b|\bmock-?ups?\b|\bwireframes?\b|\bstates\b|\bui\b|\bscreenshots?\b|\blayouts?\b'),
    (3, r'for (users?|everyone|readers?)|\buser guide\b|\bhow it works\b|\bhow\b|\bflow\b|\bsteps\b|\bbehaviou?r\b|\bworkflow\b'),
    (2, r'\bwhy\b|\bproblems?\b|\bgoals?\b|\bnon-goals?\b|\bmotivation\b|\bbackground\b|\bcontext\b|\bwho (it is|for)\b'),
    (1, r'\bwhat\b|\bsummary\b|\boverview\b|\bin one paragraph\b|\bat a glance\b'),
]


def classify(title):
    """The feature-spec template slot (1..12) a page section belongs to, from its heading; None when no rule
    matches (the section then goes under 3 How it works with its own heading and is reported)."""
    t = ' '.join(re.sub(r'^\d+[.)-]?\s*', '', html.unescape(title or '')).lower().split())
    for slot, rx in _RULES:
        if re.search(rx, t):
            return slot
    return None


def _norm(s):
    return ' '.join(str(s or '').lower().replace('-', ' ').split())


def _is_slot_name(title, slot):
    t = _norm(re.sub(r'^\d+[.)-]?\s*', '', title))
    return t == _norm(SLOTS[slot]) or (slot == 2 and t in ('why', 'what and why')) or (slot == 3 and t == 'how')


def topics_from(lede, secs, meta_topics, allowed):
    """Topics the page names: meta.json `topics` first, else docs.json topics found as whole words in the lede and
    headings. Only values in `allowed` when docs.json lists any (DOCSPEC R4.4)."""
    found = [t for t in (meta_topics or []) if isinstance(t, str)]
    text = ' ' + _norm(' '.join([re.sub(r'<[^>]+>', ' ', lede or '')] + [t for t, _ in secs])) + ' '
    for a in allowed or []:
        if (' %s ' % _norm(a)) in text and a not in found:
            found.append(a)
    if allowed:
        found = [t for t in found if t in allowed]
    return found


def slots_for(lede, secs, decs):
    """({slot: [(subheading or None, markdown)]}, [titles that matched no rule]). The lede is always section 1."""
    lede_md = html_to_md(lede) if lede and '<' in lede else (lede or '').strip()
    out = {1: [(None, lede_md)] if lede_md else []}
    unmapped = []
    for title, md in secs:
        slot = classify(title)
        if slot is None:
            slot = 3
            unmapped.append(title)
        if slot == 10:   # the decisions table comes from decisions.json; prose about decisions stays beside it
            slot = 3
        out.setdefault(slot, []).append((None if _is_slot_name(title, slot) else title, md))
    return out, unmapped


def decision_rows(decs):
    return [(str(d.get('id') or ''), '| %s | %s | %s | %s |' % (_cell(d.get('id')), _cell(d.get('question')), _cell(d.get('chosen')), _cell(d.get('decided'))))
            for d in decs]


DEC_HEAD = ['| ID | Question | Chosen | Date |', '|---|---|---|---|']


def _piece_text(pieces):
    out = []
    for t, md in pieces:
        out += (['### %s' % t, ''] if t else []) + [md, '']
    return '\n'.join(out).rstrip()


def _front_matter(fid, title, apps, artifact_file, topics):
    return ['---', 'id: %s' % fid, 'title: %s' % title, 'apps: [%s]' % ', '.join(apps), 'topics: [%s]' % ', '.join(topics),
            'status: proposed', 'version: 0.1.0', 'owner: owner', 'type: explanation', 'code: []',
            'artifact: %s' % artifact_file, '---']


NEW_NOTE = ('<!-- Promoted from the feature artifact by project_artifacts.py promote-to-spec; sections are placed by '
            'heading. Review it against luismc-docs templates/feature-spec.md: add the requirements (R5.x, R6.x), '
            'the code map and the diagram, delete what does not apply. -->')
PLACEHOLDER = '<what it does and for whom, in plain words>'


def build_spec(feature_id, title, apps, artifact_file, lede, secs, decs, topics=()):
    """The text of a new docs/features/<feature_id>/spec.md. `version` starts at 0.1.0; only the release fold writes it (R4.3)."""
    slots, _ = slots_for(lede, secs, decs)
    body = ['# %s' % title, '', NEW_NOTE, '']
    for n in range(1, 13):
        if n == 10:
            if decs:
                body += ['## 10. Decisions', ''] + DEC_HEAD + [r for _, r in decision_rows(decs)] + ['']
            continue
        pieces = slots.get(n)
        if n == 1 and not pieces:
            pieces = [(None, PLACEHOLDER)]
        if pieces:
            body += ['## %d. %s' % (n, SLOTS[n]), '', _piece_text(pieces), '']
    body += ['## Versions', '']
    return '\n'.join(_front_matter(feature_id, title, apps, artifact_file, topics) + body)


# --- merging into a spec that exists -------------------------------------------------------------------------

_PLACEHOLDER_LINES = {'what it does and for whom, in plain words.', 'problem, users, goals, non-goals.', PLACEHOLDER}
MERGE_MARK = '<!-- promoted from the feature page -->'


def _is_placeholder(body):
    lines = [l.strip() for l in re.sub(r'<!--.*?-->', '', body, flags=re.S).splitlines() if l.strip()]
    return all(l.lower() in _PLACEHOLDER_LINES or re.fullmatch(r'<[^<>]+>', l) for l in lines)


def _split_spec(text):
    """(front matter lines or None, preamble lines, [[heading, body lines]])."""
    lines = text.split('\n')
    fm = None
    if lines and lines[0].strip() == '---':
        for i in range(1, len(lines)):
            if lines[i].strip() == '---':
                fm, lines = lines[:i + 1], lines[i + 1:]
                break
    pre, secs = [], []
    for l in lines:
        if l.startswith('## '):
            secs.append([l, []])
        elif secs:
            secs[-1][1].append(l)
        else:
            pre.append(l)
    return fm, pre, secs


def _slot_of(heading):
    h = heading[3:].strip()
    m = re.match(r'(\d+)\.\s', h)
    if m and 1 <= int(m.group(1)) <= 12:
        return int(m.group(1))
    if h.lower() == 'versions':
        return None
    return classify(h)


def _fm_value(fm, key):
    for l in fm:
        if l.startswith(key + ':'):
            return l.split(':', 1)[1].split('#')[0].strip()
    return None


def merge_spec(existing, feature_id, title, apps, artifact_file, lede, secs, decs, topics=()):
    """Merge the page into an existing spec, section by section. Returns (new text, [change lines]).
    Nothing the spec already says is removed: a section is appended to (under a marker comment), a missing section is
    inserted in order, a template placeholder is replaced (said in the change list), a decision already in the table
    is kept as it is. Front matter keys keep their values; empty `apps`, `topics`, `artifact` are filled."""
    slots, _ = slots_for(lede, secs, decs)
    fm, pre, sec = _split_spec(existing)
    changes = []
    if fm is not None:
        for key, val in (('apps', '[%s]' % ', '.join(apps) if apps else ''), ('topics', '[%s]' % ', '.join(topics) if topics else ''),
                         ('artifact', artifact_file or '')):
            cur = _fm_value(fm, key)
            if val and cur in (None, '', '[]'):
                if cur is None:
                    fm.insert(len(fm) - 1, '%s: %s' % (key, val))
                else:
                    fm[:] = ['%s: %s' % (key, val) if l.startswith(key + ':') else l for l in fm]
                changes.append('front matter: set %s to %s (it was empty)' % (key, val))
    where = {}
    for i, (h, _) in enumerate(sec):
        n = _slot_of(h)
        if n and n not in where:
            where[n] = i
    for n in range(1, 13):
        if n == 10:
            if not decs:
                continue
            rows = decision_rows(decs)
            if n in where:
                body = sec[where[n]][1]
                have = {}
                for l in body:
                    cells = [c.strip() for c in l.strip().strip('|').split('|')]
                    if l.strip().startswith('|') and cells and cells[0] and cells[0] not in ('ID', '---', '') and not set(cells[0]) <= set('-:'):
                        have[cells[0]] = cells
                add = [r for i, r in rows if i not in have]
                for i, r in rows:
                    if i in have:
                        new = [c.strip() for c in r.strip().strip('|').split('|')]
                        if have[i][:3] != new[:3]:
                            changes.append('section 10: kept your row for %s; the page says "%s" (not applied)' % (i, new[2]))
                if add:
                    last = max([k for k, l in enumerate(body) if l.strip().startswith('|')] or [-1])
                    if last < 0:
                        body[:] = [x for x in body if x.strip()] + [''] + DEC_HEAD + add + ['']
                    else:
                        body[last + 1:last + 1] = add
                    changes.append('section 10: added %s' % ', '.join(i for i, _ in rows if i not in have))
            else:
                sec.insert(_insert_at(sec, n), ['## 10. Decisions', [''] + DEC_HEAD + [r for _, r in rows] + ['']])
                changes.append('section 10: inserted with %d decision(s)' % len(rows))
                where = _reindex(sec)
            continue
        pieces = slots.get(n)
        if not pieces:
            continue
        if n not in where:
            sec.insert(_insert_at(sec, n), ['## %d. %s' % (n, SLOTS[n]), [''] + _piece_text(pieces).split('\n') + ['']])
            changes.append('section %d %s: inserted' % (n, SLOTS[n]))
            where = _reindex(sec)
            continue
        h, body = sec[where[n]]
        cur = '\n'.join(body)
        if _is_placeholder(cur):
            body[:] = [''] + _piece_text(pieces).split('\n') + ['']
            changes.append('section %d %s: replaced the template placeholder' % (n, SLOTS[n]))
            continue
        have = _norm(re.sub(r'<!--.*?-->', '', cur, flags=re.S))
        new = [(t, md) for t, md in pieces if _norm(md) not in have]
        if new:
            while body and not body[-1].strip():
                body.pop()
            body += ['', MERGE_MARK] + _piece_text(new).split('\n') + ['']
            changes.append('section %d %s: appended %d part(s) from the page, your text kept' % (n, SLOTS[n], len(new)))
    out = (fm or []) + pre
    for h, body in sec:
        out += [h] + body
    return '\n'.join(out), changes


def _insert_at(sec, n):
    for i, (h, _) in enumerate(sec):
        k = _slot_of(h)
        if k and k > n:
            return i
        if h[3:].strip().lower() == 'versions':
            return i
    return len(sec)


def _reindex(sec):
    where = {}
    for i, (h, _) in enumerate(sec):
        k = _slot_of(h)
        if k and k not in where:
            where[k] = i
    return where


def diff(old, new, name):
    return ''.join(difflib.unified_diff(old.splitlines(True), new.splitlines(True), 'a/' + name, 'b/' + name))
