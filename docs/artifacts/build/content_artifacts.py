"""Content for Feature: Project artifacts standard (task prefix AR).

The generator imports this module. Section 0 (status and checklist) is generated
from TASKS; SECTIONS hold sections 1..N in order, History last.
"""

KEY = 'artifacts'
TITLE = 'Feature: Project artifacts standard'
SLUG = 'feature-project-artifacts-standard'
PREFIX = 'AR'
APP = 'luismc-artifacts'
URL = 'https://claude.ai/artifact/UUcPLxwLp89kMAQxVYb5hq'
HERO = ('How every project gets the same status artifacts: a feature artifact per feature and one full-progress artifact '
        'for all the work, kept current automatically. Built in dev-standards as the plugin <code>luismc-artifacts</code>.')
EXTRA_CSS = ''

LEDE = ('<p class="lede">The design is agreed and the default design is built (AR14). <strong>Nothing needs you</strong> on this feature. '
        'The build starts at about 13:30 with AR5, the spec, and merges on green at about 17:15. Every task here is also on {fp_link}.</p>')

# status, item, detail, expected. Done/Live newest first, then the rest earliest first.
TASKS = [
    dict(id='AR16', status='Done', item='dev-standards record in docs/artifacts',
         detail='Manifest, registry, HTML and the interim generator committed to main as docs-only commits.',
         expected='10 Oct'),
    dict(id='AR4', status='Done', item='Answer the open decisions',
         detail='Answered: one task registry; branch names start with the task ID; catch-up at session start; each project\'s own design, the plugin\'s default when it has none; an App / service column on the full-progress artifact.',
         expected='10 Oct'),
    dict(id='AR14', status='Done', item='Default design',
         detail='design/default-design.css, DESIGN.md and templates/project-artifact.css on branch AR14-default-design; applied to both dev-standards artifacts.',
         expected='10 Oct'),
    dict(id='AR3', status='Done', item='Moved to dev-standards and rewritten',
         detail='This artifact now belongs to dev-standards and describes the agreed design; Full Progress: dev-standards created.',
         expected='10 Oct'),
    dict(id='AR2', status='Done', item='Proposal reviewed',
         detail='Twelve findings; each one and the change it led to is in section 7.', expected='10 Oct'),
    dict(id='AR5', status='To do', item='ARTIFACTSPEC 1.0.0',
         detail='The standard as a numbered, versioned spec; section 3 is its draft. Must pass spec_check.py.',
         expected='10 Oct ~14:15'),
    dict(id='AR6', status='To do', item='Templates',
         detail='feature-artifact.html and full-progress-artifact.html built on the AR14 stylesheet, plus finding a project\'s own design.',
         expected='10 Oct ~15:30'),
    dict(id='AR7', status='To do', item='project_artifacts.py',
         detail='Task registry, rendering, add-task, set-task-status, stamp, check. Stdlib only; Windows timezone fallback.',
         expected='10 Oct ~15:30'),
    dict(id='AR8', status='To do', item='Hooks',
         detail='After-command, end-of-turn and session-start hooks in hooks/hooks.json.', expected='10 Oct ~16:30'),
    dict(id='AR9', status='To do', item='Tests and CI',
         detail='A fixture per check that proves it fires, hook tests, spec-lint.yml path filters.',
         expected='10 Oct ~16:30'),
    dict(id='AR10', status='To do', item='Skills and rule file',
         detail='The five skills and .claude/rules/project-artifacts.md.', expected='10 Oct ~16:30'),
    dict(id='AR11', status='To do', item='Plugin wiring',
         detail='plugin.json 1.0.0, the marketplace entry, the README section and install line.',
         expected='10 Oct ~16:45'),
    dict(id='AR12', status='To do', item='Integrate and release',
         detail='Full suite once on artifacts/integration, then one ready PR to main: one CI run, one release. Built by Sonnet agents from about 13:30; merged on green.',
         expected='10 Oct ~17:15'),
    dict(id='AR15', status='To do', item='Repo record and recreate',
         detail='Each project keeps its artifacts\' record in docs/artifacts/: manifest, task registry, each artifact\'s content and last published HTML. A deleted artifact is recreated from it without duplicates. Built into project_artifacts.py.',
         expected='10 Oct ~15:30'),
]

_CLS = {'Live': 'status-live', 'Done': 'status-done', 'Running': 'status-running', 'Needs you': 'status-needs-you',
        'Waiting': 'status-waiting', 'To do': 'status-to-do', 'On hold': 'status-on-hold', 'Failed': 'status-failed'}


def _chip(status):
    return '<span class="status-chip %s">%s</span>' % (_CLS[status], status)


def _table(head, rows):
    return ('<div class="table-scroll"><table><thead><tr>' + ''.join('<th>%s</th>' % h for h in head) + '</tr></thead><tbody>\n'
            + '\n'.join('<tr>' + ''.join('<td>%s</td>' % c for c in r) + '</tr>' for r in rows) + '\n</tbody></table></div>')


S1 = """<p class="lede">A project builds many things at once. Its owner needs to see, at any moment, what is live, what is running and what needs them, without reading code or chat.</p>
<p>What the owner asked for (9 and 10 October):</p>
<ul>
 <li><strong>Same look and feel</strong> for every artifact within a project, with sections always numbered and section 0 always <strong>Status and checklist</strong>.</li>
 <li><strong>Feature artifacts</strong> (&ldquo;Feature: &lt;name&gt;&rdquo;) describe something to build in one app, several apps or the whole project. They evolve, and log every change in a <strong>History</strong> table as their last section.</li>
 <li>One <strong>full-progress artifact</strong> per project (&ldquo;Full Progress: &lt;project&gt;&rdquo;): the owner&rsquo;s view of <strong>all ongoing work</strong> in the project, across every app and service. It holds every feature task and every other project task; it is not only a summary of the feature artifacts.</li>
 <li>Creating a feature artifact when the project has no full-progress artifact <strong>creates the full-progress artifact too</strong>.</li>
 <li>Status changes update the artifacts <strong>automatically</strong>: a feature task&rsquo;s change updates its feature artifact, and any project task&rsquo;s change updates the full-progress artifact.</li>
 <li>Built in dev-standards as the plugin <code>luismc-artifacts</code>, with <strong>explicit names in the code</strong>: feature artifact and full-progress artifact, never a generic &ldquo;page&rdquo;.</li>
</ul>
<p><strong>Why it matters.</strong> In an earlier project the pages drifted: a feature page still said &ldquo;Needs you&rdquo; for a step finished hours before. The status was typed by hand in two places. This design writes each status once and generates every view of it.</p>"""

S2 = """<p class="lede">Each task&rsquo;s status is stored once, in a task registry inside the full-progress artifact. One command changes it, regenerates every checklist that shows the task, and a hook makes sure both artifacts are published before the turn ends.</p>
<h3>Two kinds of project artifact</h3>
""" + _table(['Kind', 'Title', 'Holds', 'How many'], [
    ['Feature artifact', '<code>Feature: &lt;name&gt;</code>', 'One feature: why, design, rules, tests, decisions, its tasks, History last.', 'Any number'],
    ['Full-progress artifact', '<code>Full Progress: &lt;project&gt;</code>', 'All ongoing work in the project: every feature task (linked to its feature artifact) and every project task. Embeds the task registry.', 'Exactly one'],
]) + """
<h3>What happens on a status change</h3>
<div class="flow-steps">
 <div class="flow-step"><b>Status event</b><small>PR opened, checks failed, merged, live, blocked, decided</small></div><div class="flow-arrow">&rarr;</div>
 <div class="flow-step key-step"><b>set-task-status AR5 running</b><small>one command, run by the session</small></div><div class="flow-arrow">&rarr;</div>
 <div class="flow-step"><b>Task registry</b><small>the one record, inside the full-progress artifact</small></div><div class="flow-arrow">&rarr;</div>
 <div class="flow-step"><b>Both checklists regenerated</b><small>feature artifact (if the task has one) and full-progress artifact; tiles, groups, stamp</small></div><div class="flow-arrow">&rarr;</div>
 <div class="flow-step"><b>Published</b><small>the end-of-turn hook blocks until it is</small></div>
</div>
<h3>What makes it automatic</h3>
""" + _table(['Layer', 'What it does'], [
    ['Rule file', '<code>.claude/rules/project-artifacts.md</code>, installed in a project when its first project artifact is created. Sessions record every piece of work as a task and run <code>task-status-update</code> at each status event.'],
    ['After-command hook', 'Watches for known events (<code>gh pr create</code>, <code>gh pr merge</code>, deploys, failed checks) on a branch named with a task ID, and queues the status change.'],
    ['End-of-turn hook', 'If a status change is queued or a changed artifact is unpublished, the turn cannot end; it lists what is missing. <strong>This is the guarantee.</strong>'],
    ['Session-start hook', 'Catches changes made between sessions (CI finished, a PR merged on GitHub) and queues them.'],
]) + """
<p class="note">The plugin cannot publish an artifact by itself; only the session&rsquo;s Artifact tool can. The hooks make sure the session does it. All hooks do nothing in a project without the manifest.</p>
<h3>Where things live</h3>
<ul>
 <li><strong>The repo is the record.</strong> Each project keeps <code>docs/artifacts/</code>: <code>manifest.json</code> (each artifact&rsquo;s link), <code>registry.json</code> (the task registry), each artifact&rsquo;s content and its last published HTML. A deleted artifact is recreated from it.</li>
 <li><strong>No duplicates.</strong> An artifact is created only when its manifest link no longer opens and no artifact with the same title exists; the new link is written back to the manifest.</li>
 <li><strong>Status changes commit to the default branch</strong> as docs-only commits. CI ignores <code>docs/**</code>, and hosting skips docs-only deploys.</li>
 <li><strong>Task IDs</strong> are a registered prefix plus a number (<span class="task-id">AR5</span>, <span class="task-id">DS4</span>), unique across the project. Branch names start with one: <code>AR5-artifactspec</code>.</li>
</ul>"""

rules_kinds = [
    ['AS1', 'A project has feature artifacts and <strong>exactly one full-progress artifact</strong>. Creating the first feature artifact creates the full-progress artifact if none exists.'],
    ['AS2', 'A feature artifact is titled <code>Feature: </code> plus the feature name. It covers one app, several, or the whole project, and changes as the feature evolves. Its <strong>last section is History</strong>: <em>Date | Change</em>, newest first.'],
    ['AS3', 'The full-progress artifact is titled <code>Full Progress: </code> plus the project name. It shows <strong>all ongoing work in the project</strong>, across every app and service: every feature task, linked to its feature artifact, and every project task. It has no History; Live or Done rows older than 14 days fold into an &ldquo;Earlier&rdquo; block.'],
    ['AS4', 'Every task has an ID: a prefix registered in the manifest plus a number. IDs are unique across the project and never reused.'],
    ['AS5', 'Each task&rsquo;s state is stored once, in the task registry <code>docs/artifacts/registry.json</code>, committed in the project&rsquo;s repo and embedded in the full-progress artifact. Every checklist and tile count is generated from it; no status row is typed by hand.'],
    ['AS6', 'The manifest <code>docs/artifacts/manifest.json</code> names the project, its timezone, its design, the full-progress artifact, and each feature artifact with its link, task prefix and files.'],
]
rules_look = [
    ['AS7', 'Every artifact of a project uses the shared structure stylesheet unchanged, plus the project&rsquo;s design tokens: taken from the project&rsquo;s own design (design-token files, theme configuration, CSS custom properties or its live site), or the plugin&rsquo;s default design when it has none. Artifact-only drawings may add styles but never change shared ones.'],
    ['AS8', 'Sections are numbered from 0 in order with no gaps; the contents list shows the same numbers. Section 0 is <strong>Status and checklist</strong>: stamp, lede, tiles, key and checklist, in that order.'],
    ['AS9', 'The stamp reads <code>Last update: DD Mon HH:MM (&lt;timezone label&gt;)</code>, with the full ISO time in its <code>datetime</code> attribute, taken from the real clock at the moment of the change.'],
    ['AS10', 'The lede says in plain words what stands and <strong>what needs the owner</strong>, or &ldquo;Nothing needs you&rdquo;.'],
    ['AS11', 'The checklist columns are <strong>Status | Item | Detail | Expected</strong>. Rows are grouped: <em>Running now and next</em> (Running, Waiting, To do), <em>Needs you, failed or on hold</em> (Needs you, Failed, On hold), <em>Live or done</em>, newest first. The full-progress artifact adds an <strong>App / service</strong> column after Item. <strong>Expected</strong> is a date, with a time for work due within a day (<code>10 Oct ~14:15</code>), in the owner&rsquo;s time zone. The zone is set once in the manifest and named in the column header. Never &ldquo;today&rdquo; or &ldquo;soon&rdquo;. When an expected time passes, a new estimate replaces it.'],
    ['AS12', 'Eight statuses with fixed colours and meanings: ' + _chip('Live') + ' released or in production; ' + _chip('Done') + ' finished, nothing to release; ' + _chip('Running') + ' being worked on now; ' + _chip('Needs you') + ' waits on the owner; ' + _chip('Waiting') + ' waits on something else (CI, a dependency, a time); ' + _chip('To do') + ' planned, not started; ' + _chip('On hold') + ' paused by decision; ' + _chip('Failed') + ' broke and needs a fix or a decision.'],
    ['AS13', 'Artifacts work in light and dark themes, and at phone width with a 16 px side gutter and no sideways page scroll; wide tables scroll inside their box.'],
]
rules_current = [
    ['AS14', 'A feature task&rsquo;s status change updates its feature artifact and the full-progress artifact; any other project task&rsquo;s change updates the full-progress artifact. One command does both, and every changed artifact is published in the same turn.'],
    ['AS15', 'Every piece of work a session starts in the project is recorded as a task first: on its feature artifact, or as a project task.'],
    ['AS16', 'Branch names start with the task ID, so hooks can match events to tasks.'],
    ['AS17', 'A turn may not end while a status change is queued or a changed artifact is unpublished.'],
    ['AS18', 'Times are shown in the owner&rsquo;s timezone and labelled with it.'],
    ['AS19', 'A project&rsquo;s artifacts can be recreated from <code>docs/artifacts/</code> alone. A new artifact is created only when the manifest link no longer opens and no artifact with the same title exists.'],
    ['AS20', 'Status changes are committed to the default branch as docs-only commits; CI and hosting skip docs-only changes.'],
]
S3 = ('<p class="lede">The draft of ARTIFACTSPEC 1.0.0. Each rule has an ID so the spec, the checks and reviews can cite it.</p>'
        '<h3>Kinds and tasks</h3>' + _table(['ID', 'Rule'], rules_kinds)
        + '<h3>Look and structure</h3>' + _table(['ID', 'Rule'], rules_look)
        + '<h3>Keeping them current</h3>' + _table(['ID', 'Rule'], rules_current))

S4 = """<p class="lede">A new plugin, <strong><code>luismc-artifacts</code></strong>, beside <code>luismc-specs</code>. One script does the work; the skills and hooks call it.</p>
<h3>Layout</h3>
<pre><code>claude/plugins/artifacts/
  .claude-plugin/plugin.json            name luismc-artifacts, version 1.0.0
  design/default-design.css             the default design tokens (AR14)
  design/DESIGN.md                      how a project's own design is found; the token contract
  references/ARTIFACTSPEC.md            the standard (section 3 here), versioned like STACKSPEC and AUTHSPEC
  scripts/project_artifacts.py          registry, rendering, add-task, set-task-status, stamp, check (stdlib only)
  scripts/hook_after_command.py         queues status changes from git, gh and deploy commands
  scripts/hook_end_of_turn.py           blocks the turn while anything is queued or unpublished
  scripts/hook_session_start.py         queues changes made between sessions
  hooks/hooks.json
  templates/feature-artifact.html
  templates/full-progress-artifact.html
  templates/project-artifact.css        the fixed structure stylesheet
  rules/project-artifacts.md            installed into a project by the first creation skill
  skills/feature-artifact-new/SKILL.md
  skills/full-progress-artifact-new/SKILL.md
  skills/task-add/SKILL.md
  skills/task-status-update/SKILL.md
  skills/project-artifact-check/SKILL.md
.claude-plugin/marketplace.json         add the luismc-artifacts entry
README.md                               a luismc-artifacts section and the install line
tools/test_project_artifacts_check.py   a fixture per check, proving it fires
tools/test_project_artifacts_hooks.py   sample events in, queue and exit codes out
.github/workflows/spec-lint.yml         path filters and steps for the above</code></pre>
<h3>The five skills</h3>
""" + _table(['Skill', 'What it does'], [
    ['<code>/luismc-artifacts:feature-artifact-new</code>', 'Asks the feature name and the apps it covers, writes a feature artifact with section 0 started and a first History row, registers it in the manifest, and adds its tasks to the registry. Creates the full-progress artifact first if the project has none.'],
    ['<code>/luismc-artifacts:full-progress-artifact-new</code>', 'Writes the project&rsquo;s one full-progress artifact with an empty task registry; refuses if one exists. For a project with ongoing work but no feature artifact yet.'],
    ['<code>/luismc-artifacts:task-add</code>', 'Records new work as a task, asking which artifact owns it (a feature artifact, or the project), and gives it the next ID.'],
    ['<code>/luismc-artifacts:task-status-update</code>', 'Reads the artifacts, runs <code>set-task-status</code>, runs the check, and publishes every artifact that changed. Retries after a publish conflict.'],
    ['<code>/luismc-artifacts:project-artifact-check</code>', 'Checks a project&rsquo;s artifacts against ARTIFACTSPEC. Exit 0 clean, 1 findings, 2 unreadable, like <code>spec_check.py</code>.'],
]) + """
<p class="note">The default design is in <code>design/default-design.css</code> and <code>templates/project-artifact.css</code> on branch AR14-default-design; these two artifacts use it.</p>"""

reqs = [
    ['R1', 'Titles start with &ldquo;Feature: &rdquo; or &ldquo;Full Progress: &rdquo; (AS2, AS3).', 'A feature artifact titled &ldquo;Manga&rdquo; fails; &ldquo;Feature: Manga&rdquo; passes.'],
    ['R2', 'Exactly one full-progress artifact, created with the first feature artifact (AS1).', 'Project with none: feature-artifact-new creates both. Project with one: no second is created. Manifest with two: fails.'],
    ['R3', 'Section 0 first and named &ldquo;Status and checklist&rdquo; (AS8).', 'Section 0 named &ldquo;Status&rdquo; fails.'],
    ['R4', 'Sections numbered from 0, in order, no gaps (AS8).', 'A gap, a repeat and an unnumbered section each fail with their line.'],
    ['R5', 'Stamp format, ISO attribute and timezone label (AS9, AS18).', '&ldquo;Last update: 9/10 7am&rdquo; fails; a stamp without <code>datetime</code> or label fails.'],
    ['R6', 'Checklist columns: Status | Item | Detail | Expected on a feature artifact; Status | Item | App / service | Detail | Expected on the full-progress artifact (AS11).', 'A fifth column, or reordered columns, fails. An Expected value on an open row that is not a date (<code>today</code>, <code>soon</code>) fails.'],
    ['R7', 'Only the eight statuses (AS12).', '&ldquo;Merged&rdquo; as a status fails and names the nearest allowed word.'],
    ['R8', 'Every row sits in its status&rsquo;s group (AS11).', 'A Live row under &ldquo;Running now and next&rdquo; fails.'],
    ['R9', 'Checklists and tiles equal the registry (AS5).', 'A hand-edited row, or a tile saying 3 Live over 2, fails.'],
    ['R10', 'Every feature task is on the full-progress artifact, linked to its feature artifact (AS3).', 'A feature task missing from the full-progress artifact fails.'],
    ['R11', 'Task IDs unique and their prefixes registered (AS4).', 'Two tasks named AR5, or an unregistered prefix, fail.'],
    ['R12', 'History is the last section of a feature artifact, Date | Change (AS2).', 'No History, or History not last, fails.'],
    ['R13', 'Structure stylesheet unchanged; theme tokens free (AS7).', 'A changed structure rule fails; a changed theme colour passes.'],
    ['R14', 'One command updates every artifact that shows the task (AS14).', 'set-task-status AR5 running: both artifacts show Running with new stamps.'],
    ['R15', 'Hooks queue and block (AS16, AS17).', '<code>gh pr merge</code> on branch AR5-x queues AR5; the end-of-turn hook blocks with a queue and passes without one; no manifest, no effect.'],
    ['R16', 'Phone width and both themes (AS13).', 'A fixture artifact at 360 px wide has no sideways scroll in light and dark (manual check listed in the skill).'],
    ['R17', 'Recreate without duplicates (AS19).', 'Manifest link deleted: one new artifact, manifest updated. Link alive: nothing created. Same title exists: no new artifact, manifest repaired.'],
]
S5 = _table(['ID', 'Requirement', 'Test that proves it'], reqs)

S6 = _table(['#', 'Question', 'Decision (10 Oct)'], [
    ['1', 'How is a task&rsquo;s status stored so both artifacts update automatically?', '<strong>One task registry</strong> inside the full-progress artifact; both checklists are generated from it.'],
    ['2', 'Do branch names start with the task ID?', '<strong>Yes</strong> (<code>AR5-artifactspec</code>), so hooks can match events to tasks.'],
    ['3', 'How do changes made outside a session reach the artifacts?', '<strong>At the next session start</strong>, through the session-start hook. No cloud routine in 1.0.'],
    ['4', 'What look do artifacts get?', '<strong>The project&rsquo;s own design</strong>, found by scanning its design files, theme configuration, CSS custom properties or live site. A project with no design gets the plugin&rsquo;s <strong>default design</strong>. dev-standards uses the default.'],
    ['5', 'An App / service column on the full-progress artifact?', '<strong>Yes</strong>, on the full-progress artifact only.'],
    ['6', 'Where is the record kept?', '<strong>In the repo</strong>, <code>docs/artifacts/</code>, committed to the default branch as docs-only commits; a deleted artifact is recreated from it without duplicates. Replaces the first answer that the published artifact is the record.'],
    ['7', 'How does a project get the plugin?', '<strong>luismc-project-setup installs it</strong> in every project it sets up; it can also be installed on its own in any project. No artifact is created until the first feature artifact.'],
    ['8', 'Which clock do Expected times use?', '<strong>The owner&rsquo;s time zone, per project</strong>, set in the manifest and named in the column header.'],
    ['9', 'Does dev-standards move other projects onto the plugin?', '<strong>No.</strong> dev-standards ships the plugin and names or changes no other project; each project adopts it in its own sessions.'],
])

S7 = ('<p class="lede">The review of the first proposal on 10 October found twelve problems. Each one changed the design above.</p>'
        + _table(['Finding', 'Change'], [
            ['A status was typed by hand in two places, the cause of the drift.', 'One task registry; one command regenerates every checklist (AS5, AS14).'],
            ['The discipline was a sentence in CLAUDE.md, the form that already failed.', 'Hooks queue status changes and block the turn until artifacts are published (AS17).'],
            ['No source of truth and no list of a project&rsquo;s pages.', 'The repo record in <code>docs/artifacts/</code> is the source; the manifest lists every artifact, and a deleted one is recreated from it (AS5, AS6, AS19).'],
            ['Per-project look contradicted the byte-identical stylesheet check.', 'Structure stylesheet fixed, theme tokens free (AS7, R13).'],
            ['A project name and &ldquo;Lisbon&rdquo; hard-coded; old and duplicate CSS rules.', 'Project name and timezone come from the manifest; the stylesheet is rebuilt clean (AR6).'],
            ['Spec and code disagreed on the groups and the History columns.', 'One definition each (AS2, AS11).'],
            ['HTML parsed with regular expressions; it left broken CSS on this artifact.', 'The script uses Python&rsquo;s built-in HTML parser.'],
            ['Python&rsquo;s zoneinfo has no timezone data on Windows without the tzdata package.', 'Fallback to the machine&rsquo;s local time, with a warning.'],
            ['The stamp had no year and nothing a program could compare.', 'ISO time in the <code>datetime</code> attribute (AS9).'],
            ['The rule would have gone into every project&rsquo;s CLAUDE.md.', 'A rule file installed only where project artifacts are used.'],
            ['The progress page would grow forever.', 'Live or Done rows older than 14 days fold into &ldquo;Earlier&rdquo; (AS3).'],
            ['Generic names: &ldquo;page&rdquo;, <code>luismc-pages</code>, <code>.st</code>.', 'Feature artifact and full-progress artifact throughout; plugin <code>luismc-artifacts</code>; readable class names in AR6.'],
        ]))




def history(stamp):
    return _table(['Date', 'Change'], [
        [stamp, 'Expected times are now a date and a time on the owner&rsquo;s clock (AS11, R6). Decisions 7 to 9: luismc-project-setup installs the plugin, which also installs on its own; the owner&rsquo;s time zone per project; dev-standards names and changes no other project, so AR1 and AR13 are out of this list. The build runs from about 13:30 and merges on green.'],
        ['10 Oct 11:07', 'The repo becomes the record: docs/artifacts/ holds the manifest, the task registry, each artifact&rsquo;s content and last published HTML, committed to the default branch as docs-only commits; a deleted artifact is recreated from it without duplicates (AS19, AS20, AR15). dev-standards&rsquo; record saved (AR16). Model and effort profiles split into their own feature artifact.'],
        ['10 Oct 09:47', 'Decisions answered (AR4): one task registry, task-ID branch names, catch-up at session start, an App / service column on the full-progress artifact. The look now comes from each project&rsquo;s own design, with a plugin default for projects without one; dev-standards uses the default design (AR14), applied to this artifact.'],
        ['10 Oct 09:24', 'Moved to dev-standards, where it is built. Rewritten to the agreed design: plugin <code>luismc-artifacts</code>; explicit names (feature artifact, full-progress artifact); the full-progress artifact shows all project work and is created with the first feature artifact; one task registry with automatic updates and hooks; task IDs AR1 to AR13; the review findings (section 7); five open decisions. Full Progress: dev-standards created.'],
        ['09 Oct 06:48', 'Created as a proposal, after the owner asked for one template, numbered sections, Feature and Full Progress pages, and a dev-standards version.'],
    ]).replace('<table>', '<table class="history-table">')


SECTIONS = [
    ('What and why', S1),
    ('The design', S2),
    ('The rules', S3),
    ('In dev-standards', S4),
    ('Requirements and tests', S5),
    ('Decisions', S6),
    ('What the review changed', S7),
    ('History', None),  # rendered by history(stamp)
]
