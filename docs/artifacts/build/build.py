"""Build the dev-standards feature artifacts and the full-progress artifact from one task registry,
and write the repo record next to them.

python -I build.py <out-dir> <css-root> <stamp "DD Mon HH:MM"> <iso> [full-progress-url] [--models-url <url>]

<css-root> holds design/default-design.css and templates/project-artifact.css, either directly
(the record's build/ folder) or under claude/plugins/artifacts/ (a dev-standards checkout).

Feature artifacts come from the content_* modules listed in FEATURES; this file keeps the project
tasks, the full-progress content and the rendering. <out-dir> gets the HTML files and record/.
"""
import html as H
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)  # python -I does not add the script folder itself

import content_artifacts  # noqa: E402
import content_models  # noqa: E402

FEATURES = [content_artifacts, content_models]

args = sys.argv[1:]
MODELS_URL = None
if '--models-url' in args:
    i = args.index('--models-url')
    MODELS_URL = args[i + 1]
    del args[i:i + 2]
OUT, CSS_ROOT, STAMP, ISO = args[0:4]
FP_URL = args[4] if len(args) > 4 else ''
if MODELS_URL is not None:
    content_models.URL = MODELS_URL
FP_TITLE = 'Full Progress: dev-standards'
FP_FILE = 'full-progress-dev-standards.html'
PROJECT = 'dev-standards'

if os.path.isfile(os.path.join(CSS_ROOT, 'design', 'default-design.css')):
    CSS_DIR = CSS_ROOT
else:
    CSS_DIR = os.path.join(CSS_ROOT, 'claude', 'plugins', 'artifacts')
DESIGN_CSS = os.path.join(CSS_DIR, 'design', 'default-design.css')
STRUCTURE_CSS = os.path.join(CSS_DIR, 'templates', 'project-artifact.css')


def read_text(path):
    with open(path, encoding='utf-8') as handle:
        return handle.read()


# Tokens first, then the fixed structure that uses them.
CSS = read_text(DESIGN_CSS) + '\n' + read_text(STRUCTURE_CSS)
FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com">\n'
         '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
         '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wdth,wght@75..100,500..800'
         '&family=IBM+Plex+Mono:wght@400;500;600&family=Public+Sans:wght@400;500;600;700&display=swap">')
SCRIPT = """<script>
(function () {
  try {
    var root = document.documentElement;
    var toggle = document.getElementById('theme-toggle');
    if (toggle) {
      toggle.addEventListener('click', function () {
        var dark = root.getAttribute('data-theme') === 'dark' ||
          (!root.getAttribute('data-theme') && window.matchMedia('(prefers-color-scheme: dark)').matches);
        root.setAttribute('data-theme', dark ? 'light' : 'dark');
      });
    }
    var links = Array.prototype.slice.call(document.querySelectorAll('nav.contents a'));
    var sections = links.map(function (link) {
      return document.getElementById(link.getAttribute('href').slice(1));
    });
    function markCurrent() {
      var index = 0;
      for (var i = 0; i < sections.length; i++) {
        if (sections[i] && sections[i].getBoundingClientRect().top <= 120) index = i;
      }
      links.forEach(function (link, i) {
        var isCurrent = i === index;
        link.classList.toggle('current', isCurrent);
        if (isCurrent) link.setAttribute('aria-current', 'location');
        else link.removeAttribute('aria-current');
      });
      var row = document.querySelector('nav.contents .contents-links');
      var current = links[index];
      if (row && current && row.scrollWidth > row.clientWidth && getComputedStyle(row).display === 'flex') {
        row.scrollLeft = current.offsetLeft - row.clientWidth / 2 + current.offsetWidth / 2;
      }
    }
    window.addEventListener('scroll', markCurrent, { passive: true });
    window.addEventListener('resize', markCurrent);
    markCurrent();
  } catch (error) {}
})();
</script>"""
STATUS = [('Live', 'status-live'), ('Done', 'status-done'), ('Running', 'status-running'),
          ('Needs you', 'status-needs-you'), ('Waiting', 'status-waiting'), ('To do', 'status-to-do'),
          ('On hold', 'status-on-hold'), ('Failed', 'status-failed')]
CLS = dict(STATUS)
GROUPS = [
    ('now', 'Running now and next, earliest first', {'Running', 'Waiting', 'To do'}),
    ('you', 'Needs you, failed or on hold', {'Needs you', 'Failed', 'On hold'}),
    ('done', 'Live or done, newest first', {'Live', 'Done'}),
]

MONTHS = {m: n for n, m in enumerate(['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'], 1)}


def date_key(expected):
    """(month, day) of an 'DD Mon' expected value; (0, 0) when it is not a date. Same-year only."""
    parts = expected.split()
    if len(parts) in (2, 3) and parts[0].isdigit() and parts[1] in MONTHS:
        return (MONTHS[parts[1]], int(parts[0]))
    return (0, 0)


# Project tasks: work in dev-standards that belongs to no feature artifact.
# Tasks of the feature artifacts live in their content_* modules.
PROJECT_TASKS = [
    # Live or done, newest first
    dict(id='DS4', status='Live', item='tech-stack-setup 11.2.1',
         detail='Required checks named by job name, not job id. Plugin: luismc-project-setup.', expected='02 Oct'),
    dict(id='DS3', status='Live', item='tech-stack-setup 11.2.0',
         detail='Fewer CI minutes without dropping the STACKSPEC §13.1 gates. Plugin: luismc-project-setup.', expected='02 Oct'),
    dict(id='DS1', status='Live', item='AUTHSPEC 3.1.0',
         detail='Synced passkeys allowed on the admin plane. Plugin: luismc-project-setup.', expected='27 Sep'),
    # Running now and next, earliest first
    dict(id='DS6', status='Running', item='Agent and integration rules',
         detail='17 changes from the 9–10 Oct evidence of a real project’s sessions. Contract committed to DS6-agent-delivery (02535cd): STACKSPEC 6.0.0 and the delivery-scripts contract. Building DS8 to DS11 in parallel; then a test on a real repository, the join, and one ready PR merged on green.',
         expected='10 Oct ~13:45'),
    dict(id='DS8', status='Waiting', item='Branch gate scripts',
         detail='branch_gate, gate_verify, fast_guards, join, agent_setup, gate.json per track, the pre-push hook, a starter guard test per track; tested against throwaway repos (303 checks, 23 mutants). Joined into DS6-agent-delivery at 0b967a3; waiting for release.',
         expected='10 Oct ~13:45', app='luismc-project-setup'),
    dict(id='DS9', status='Waiting', item='CI scripts and workflows',
         detail='ci_watch, ci_skip_check, reach_check; the decide job and gated e2e with a quarantine list in all four ci.yml files. Built: draft PR #6, 33 tests pass. Joined at 0b967a3; waiting for release.',
         expected='10 Oct ~13:45', app='luismc-project-setup'),
    dict(id='DS10', status='Waiting', item='claude-setup rules and profiles',
         detail='The agents-and-integration rule file (replaces model-delegation.md), the docs/ rule, per-skill model and effort, the alias-drift hook. Covers MP3, MP4, MP5 and DS7. Built: draft PR #4. Joined at 0b967a3; waiting for release.',
         expected='10 Oct ~13:45', app='luismc-project-setup'),
    dict(id='DS11', status='Waiting', item='tech-stack-setup wiring',
         detail='Generate and audit paths for STACKSPEC 6.0.0, spec-lint CI steps for the new tests, luismc-project-setup 12.0.0. Built: draft PR #3; also limits spec-lint and secret-scan to main and ready PRs, and fixes the 23 stack-profile references that kept spec-lint red on main since July. Joined at 0b967a3; waiting for release.',
         expected='10 Oct ~13:45', app='luismc-project-setup'),
    dict(id='DS12', status='Waiting', item='Test on a real repository',
         detail='Six scenarios on a local scratch clone of a real repository, nothing pushed: the gate caught a guard violation and blocked the push; lint reported every failing package; gate_verify rejected a stale head and a stale base; join refused a failing branch; the push-CI skip was right on 8 real merges. Four bugs fixed (tests of dependent packages, no-test packages, per-step env, LF for hooks); 322 gate checks pass. Joined at 66c8a58; waiting for release.',
         expected='10 Oct ~13:45', app='luismc-project-setup'),
    dict(id='DS13', status='Running', item='Join and release',
         detail='DS8 to DS12 joined (66c8a58); STACKSPEC §13.2 now gives previews to ready PRs only (2ac740d); every local check passes. Next: DS14, then one ready PR to main, ci_watch on its head, merge on green. Then move the Agents and Integrate sections of the owner’s CLAUDE.md into the rule file.',
         expected='10 Oct ~13:45; your CLAUDE.md ~13:55', app='luismc-project-setup'),
    dict(id='DS14', status='Running', item='Pre-push hook keeps a project’s own check',
         detail='Found in DS12: installing the template pre-push hook replaced a project’s existing one. The existing hook moves to pre-push.local and the template runs it; the agent_setup PATH hint uses Git Bash paths.',
         expected='10 Oct ~13:25', app='luismc-project-setup'),
    dict(id='DS7', status='Waiting', item='docs/ folder rule',
         detail='A project-setup rule: every doc a session creates goes under docs/. Built in DS10.',
         expected='10 Oct ~13:45', app='luismc-project-setup'),
]


def all_tasks():
    """The registry: project tasks, then each feature's tasks. Each task gets owner, app and url."""
    out = []
    for t in PROJECT_TASKS:
        t = dict(t)
        t['owner'] = 'project'
        t.setdefault('app', 'luismc-project-setup')
        t['url'] = ''
        out.append(t)
    for module in FEATURES:
        for t in module.TASKS:
            t = dict(t)
            t['owner'] = module.KEY
            t['app'] = module.APP
            t['url'] = module.URL
            out.append(t)
    return out


TASKS = all_tasks()


def chip(status):
    return '<span class="status-chip %s">%s</span>' % (CLS[status], status)


def checklist(tasks, link_feature, with_app=False):
    rows = []
    for key, title, sts in GROUPS:
        mine = [t for t in tasks if t['status'] in sts]
        if key == 'done':
            mine = sorted(mine, key=lambda t: date_key(t['expected']), reverse=True)  # stable: newest first
        if not mine:
            continue
        rows.append('<tr class="status-group" data-group="%s"><td colspan="%d"><strong>%s</strong></td></tr>' % (key, 5 if with_app else 4, title))
        for t in mine:
            item = '<span class="task-id">%s</span>%s' % (t['id'], H.escape(t['item']))
            if link_feature and t['owner'] != 'project' and t['url']:
                item = '<a href="%s">%s</a>' % (t['url'], item)
            app_cell = ('<td><code>%s</code></td>' % H.escape(t['app'])) if with_app else ''
            rows.append('<tr data-task="%s"><td>%s</td><td>%s</td>%s<td>%s</td><td>%s</td></tr>' % (
                t['id'], chip(t['status']), item, app_cell, H.escape(t['detail']), H.escape(t['expected'])))
    return ('<div class="table-scroll"><table class="status-checklist"><thead><tr><th>Status</th><th>Item</th>'
            + ('<th>App / service</th>' if with_app else '') + '<th>Detail</th>'
            '<th>Expected (Lisbon)</th></tr></thead><tbody>\n' + '\n'.join(rows) + '\n</tbody></table></div>')


def tiles(tasks):
    counts = {}
    for t in tasks:
        counts[t['status']] = counts.get(t['status'], 0) + 1
    return '<div class="status-count-tiles">' + ''.join(
        '<div class="status-count-tile %s"><div class="count">%d</div><div class="label">%s</div></div>' % (c, counts[l], l.lower())
        for l, c in STATUS if l in counts) + '</div>'


KEY = ('<p class="note">Key: ' + ' · '.join(chip(l) for l, _ in STATUS)
       + '. Times are Lisbon time; each estimate names what sets it.</p>')


def section0(tasks, lede, link_feature, with_app=False):
    return ('<section id="s0"><h2><span class="section-number">&sect; 0</span>Status and checklist</h2>'
            '<p class="last-update">Last update: <time datetime="%s">%s</time> (Lisbon)</p>\n%s\n%s\n%s\n%s\n'
            '</section>') % (ISO, STAMP, lede, tiles(tasks), KEY, checklist(tasks, link_feature, with_app))


def page(title, kind, kind_label, hero_p, meta, sections, extra_head='', extra_css=''):
    nav = ''.join('<a href="#s%d"><b>%d</b>%s</a>' % (i, i, lab) for i, (lab, _) in enumerate(sections))
    body = '\n'.join(html for _, html in sections)
    css = CSS + ('\n' + extra_css if extra_css else '')
    return ('<title>%s</title>\n<meta name="artifact-kind" content="%s">\n%s\n<style>%s</style>\n%s'
            '<div class="layout"><nav aria-label="Contents" class="contents"><div class="contents-title">Contents</div>'
            '<div class="contents-links">%s</div><button class="theme-toggle" id="theme-toggle" type="button">Light / dark</button></nav><main>\n'
            '<header class="artifact-header"><div class="artifact-kind">%s</div><h1>%s</h1><p>%s</p><div class="artifact-meta">%s</div></header>\n%s\n</main></div>\n%s\n') % (
        H.escape(title), kind, FONTS, css, extra_head, nav, kind_label, H.escape(title), hero_p, meta, body, SCRIPT)


def sec(n, title, inner):
    return '<section id="s%d"><h2><span class="section-number">&sect; %d</span>%s</h2>\n%s</section>' % (n, n, title, inner)


def table(head, rows):
    return ('<div class="table-scroll"><table><thead><tr>' + ''.join('<th>%s</th>' % h for h in head) + '</tr></thead><tbody>\n'
            + '\n'.join('<tr>' + ''.join('<td>%s</td>' % c for c in r) + '</tr>' for r in rows) + '\n</tbody></table></div>')


fp_link = ('<a href="%s">Full Progress: dev-standards</a>' % FP_URL) if FP_URL else 'Full Progress: dev-standards'


def link_or_text(module):
    if module.URL:
        return '<a href="%s">%s</a>' % (module.URL, H.escape(module.TITLE))
    return H.escape(module.TITLE)


# ---------------------------------------------------------------- feature artifacts
def build_feature(module):
    mine = [t for t in TASKS if t['owner'] == module.KEY]
    sections = [('Status and checklist', section0(mine, module.LEDE.format(fp_link=fp_link), False))]
    for n, (label, inner) in enumerate(module.SECTIONS, 1):
        sections.append((label, sec(n, label, module.history(STAMP) if inner is None else inner)))
    return page(module.TITLE, 'feature-artifact', 'Feature artifact &middot; dev-standards', module.HERO,
                'dev-standards &middot; feature artifact &middot; default design', sections, extra_css=module.EXTRA_CSS)


# ---------------------------------------------------------------- full-progress artifact
p_lede = ('<p class="lede">All ongoing work in dev-standards, across every plugin. <strong>Nothing needs you right now.</strong> '
          'Running: <span class="task-id">DS6</span>, the agent and integration round, with DS8 to DS12 joined; DS14 fixes the pre-push hook before the release at about 13:45. '
          'Live today: <span class="task-id">DS5</span>, the effort question (luismc-project-setup 11.3.0).</p>')

p_s1 = table(['Feature artifact', 'Tasks', 'Where it stands'], [
    [link_or_text(content_artifacts), 'AR1 to AR16',
     'ARTIFACTSPEC 1.0.0 written (AR5); renderer, script and hooks being built; merge on green at about 17:15.'],
    [link_or_text(content_models), 'MP1 to MP6, DS2, DS5',
     'Effort question live; role rules, skill profiles and the alias warning ship with DS6.'],
])

p_s2 = """<p class="lede">Until <code>luismc-artifacts</code> is built, this artifact is kept by hand to the same rules: a status change is written to the feature artifact that holds the task and to this artifact, in the same turn.</p>
<ul>
 <li><strong>Project tasks</strong> (prefix <span class="task-id">DS</span>) are work in dev-standards that belongs to no feature artifact: releases, fixes, CI, spec changes. They include changes to luismc-project-setup, such as DS6 and DS7.</li>
 <li><strong>Feature tasks</strong> link to their feature artifact. Task <span class="task-id">AR</span> belongs to Feature: Project artifacts standard; task <span class="task-id">MP</span> to Feature: Model and effort profiles.</li>
 <li>The task registry below the checklist is the record both artifacts are generated from. Once the plugin lands (AR12), <code>set-task-status</code> writes it and the hooks keep both artifacts published.</li>
 <li>Recent releases are listed from the git history of <code>main</code>; a change merged to <code>main</code> is live through the marketplace&rsquo;s auto-update.</li>
 <li>The record of these artifacts is in <code>docs/artifacts/</code> in this repo. A deleted artifact is recreated from it; see its README.</li>
</ul>"""

registry = {
    'registry': 'draft for ARTIFACTSPEC 1.0.0',
    'project': PROJECT,
    'timezone': 'Europe/Lisbon',
    'updated': ISO,
    'feature_artifacts': [{'title': m.TITLE, 'url': m.URL, 'prefix': m.PREFIX} for m in FEATURES],
    'project_prefixes': ['DS'],
    'tasks': [{'id': t['id'], 'owner': next((m.TITLE for m in FEATURES if m.KEY == t['owner']), 'project'),
               'app': t['app'], 'status': t['status'], 'item': t['item'], 'detail': t['detail'], 'expected': t['expected']} for t in TASKS],
}
REG_JSON = json.dumps(registry, ensure_ascii=False, indent=1)
REG = '<script type="application/json" id="task-registry">%s</script>\n' % REG_JSON.replace('</', '<\\/')

progress = page(FP_TITLE, 'full-progress-artifact', 'Full-progress artifact &middot; dev-standards',
                'All ongoing work in dev-standards, across every plugin: every feature task, linked to its feature artifact, and every project task. Check here first for what is live, what is running and what needs you.',
                'dev-standards &middot; full progress, every plugin &middot; default design',
                [('Status and checklist', section0(TASKS, p_lede, True, True)),
                 ('Feature artifacts', sec(1, 'Feature artifacts', p_s1)),
                 ('How it stays current', sec(2, 'How it stays current', p_s2))],
                extra_head=REG)


# ---------------------------------------------------------------- write the HTML and the record
def write_text(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8', newline='\n') as handle:
        handle.write(text)


def copy_file(src, dst):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if os.path.abspath(src) != os.path.abspath(dst):
        shutil.copyfile(src, dst)


README = """# Artifact record: dev-standards

This folder is the record of the dev-standards project artifacts: the repo record is the
source, and the published artifacts are generated from it. It holds:

- `manifest.json`: the project, its timezone and design, the full-progress artifact and each
  feature artifact with its link, task prefix, app and file.
- `registry.json`: the task registry, the same one embedded in the full-progress artifact.
- the last published HTML of every artifact.
- `build/`: the generator (`build.py`, the content modules, `check.py`) and the two stylesheets
  it needs under `build/design/` and `build/templates/`.

## Rebuild

    python -I build/build.py <out> <dir containing design/ and templates/> "<DD Mon HH:MM>" <iso> <fp-url> --models-url <url>

`build/` itself contains `design/` and `templates/`, so it can be its own CSS root:

    python -I build/build.py out build "10 Oct 12:00" 2026-10-10T12:00+01:00 <fp-url> --models-url <url>

`<out>` gets the HTML files and a fresh `record/`. Run `python -I build/check.py <out>` to check them.

## Recreate a deleted artifact without duplicates

1. Try to open the link in `manifest.json`. If it opens, republish the HTML to that link.
2. If it no longer opens, list your artifacts and look for one with the same title. If you find
   one, write its link to the manifest.
3. Only if none exists, publish the HTML as a new artifact and write the new link to the manifest.
4. Commit the manifest to the default branch as a docs-only commit.

This manual procedure is replaced by the luismc-artifacts plugin (AR7, AR15) once it is built.
"""


def write_outputs():
    os.makedirs(OUT, exist_ok=True)
    pages = [(m.SLUG + '.html', build_feature(m)) for m in FEATURES] + [(FP_FILE, progress)]
    for name, text in pages:
        write_text(os.path.join(OUT, name), text)
    rec = os.path.join(OUT, 'record')
    manifest = {
        'project': PROJECT,
        'timezone': 'Europe/Lisbon',
        'design': 'default',
        'full_progress_artifact': {'title': FP_TITLE, 'url': FP_URL, 'file': FP_FILE},
        'feature_artifacts': [{'key': m.KEY, 'title': m.TITLE, 'url': m.URL, 'prefix': m.PREFIX, 'app': m.APP,
                               'file': m.SLUG + '.html'} for m in FEATURES],
        'project_prefixes': ['DS'],
        'updated': ISO,
    }
    write_text(os.path.join(rec, 'manifest.json'), json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    write_text(os.path.join(rec, 'registry.json'), REG_JSON + '\n')
    for name, text in pages:
        write_text(os.path.join(rec, name), text)
    for name in ['build.py', 'content_artifacts.py', 'content_models.py', 'figures_models.py', 'check.py']:
        copy_file(os.path.join(HERE, name), os.path.join(rec, 'build', name))
    copy_file(DESIGN_CSS, os.path.join(rec, 'build', 'design', 'default-design.css'))
    copy_file(STRUCTURE_CSS, os.path.join(rec, 'build', 'templates', 'project-artifact.css'))
    write_text(os.path.join(rec, 'README.md'), README)
    return pages


pages = write_outputs()
print(', '.join('%s %d' % (n, len(t)) for n, t in pages), '| fp_url', FP_URL or '(none)',
      '| models_url', content_models.URL or '(none)')
