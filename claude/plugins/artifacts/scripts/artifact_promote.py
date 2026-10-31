"""Promote a feature artifact's decided content into a feature spec (DOCSPEC R4.10, R10.4).

Pure functions used by `project_artifacts.py promote-to-spec`; nothing here touches the record. The output follows
luismc-docs' `templates/feature-spec.md` (front matter of R4.2, sections 1, 2, 3 and 10). Standard library only.
"""
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


def build_spec(feature_id, title, apps, artifact_file, lede, secs, decs):
    """The text of docs/features/<feature_id>/spec.md. `version` starts at 0.1.0; only the release fold writes it (R4.3)."""
    fm = ['---', 'id: %s' % feature_id, 'title: %s' % title, 'apps: [%s]' % ', '.join(apps), 'topics: []',
          'status: proposed', 'version: 0.1.0', 'owner: owner', 'type: explanation', 'code: []',
          'artifact: %s' % artifact_file, '---']
    body = ['# %s' % title, '',
            '<!-- Promoted from the feature artifact by project_artifacts.py promote-to-spec. Review it against '
            'luismc-docs templates/feature-spec.md: move the sections into the template order, add the requirements '
            '(R5.x, R6.x), the code map and the diagram, delete what does not apply. -->', '']
    lede_md = html_to_md(lede) if lede and '<' in lede else (lede or '').strip()
    first = secs[0] if secs else None
    body += ['## 1. In one paragraph', '', lede_md or '<what it does and for whom, in plain words>', '']
    if first:
        body += ['## 2. Why', '', first[1], '']
    rest = secs[1:]
    if rest:
        body += ['## 3. How it works', '']
        for t, md in rest:
            body += ['### %s' % t, '', md, '']
    if decs:
        body += ['## 10. Decisions', '', '| ID | Question | Chosen | Date |', '|---|---|---|---|']
        body += ['| %s | %s | %s | %s |' % (_cell(d.get('id')), _cell(d.get('question')), _cell(d.get('chosen')), _cell(d.get('decided')))
                 for d in decs]
        body += ['']
    body += ['## Versions', '']
    return '\n'.join(fm + body)
