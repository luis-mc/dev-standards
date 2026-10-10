"""Content for Feature: Model and effort profiles (task prefix MP).

The generator imports this module. Section 0 (status and checklist) is generated
from TASKS; SECTIONS hold sections 1..N in order, History last.
"""
from figures_models import FIGURE_CSS, figure_alias, figure_ladders, figure_today

KEY = 'models'
TITLE = 'Feature: Model and effort profiles'
SLUG = 'feature-model-and-effort-profiles'
PREFIX = 'MP'
APP = 'luismc-project-setup'
URL = 'https://claude.ai/artifact/9MMjfeWhPCwH19NV39oBBn'
HERO = ('Which model and which effort every kind of agent and every skill uses, where each setting lives, '
        'and what follows from it. Built into <code>claude-setup</code> in luismc-project-setup.')
EXTRA_CSS = FIGURE_CSS

LEDE = ('<p class="lede">The profiles are decided and the effort question is live (DS5, luismc-project-setup 11.3.0). '
        '<strong>Nothing needs you.</strong> The rest ships with the agent and integration round (DS6): '
        'role rules, per-skill profiles and the alias-drift warning. Every task here is also on {fp_link}.</p>')

# status, item, detail, expected; owner is this feature unless noted. Done/Live newest first.
TASKS = [
    dict(id='DS5', status='Live', item='claude-setup: medium or high effort per model',
         detail='Asked on every run, high preselected for code agents; written to modelSettings and the delegation rule; top-level effortLevel high for cloud agents. luismc-project-setup 11.3.0, PR #2.',
         expected='10 Oct'),
    dict(id='MP2', status='Done', item='Profile decisions',
         detail='Explore and Plan stay on Opus; skills profiled by kind of work; a session-start warning for alias drift. Section 7.',
         expected='10 Oct'),
    dict(id='MP1', status='Done', item='Inventory of models per agent type',
         detail='Checked against the Claude Code docs; corrects the first answer (Explore and Plan run on the main session’s model). Figure 1.',
         expected='10 Oct'),
    dict(id='DS2', status='Live', item='Opus plans, Sonnet codes',
         detail='claude-setup writes model opus and CLAUDE_CODE_SUBAGENT_MODEL sonnet, plus the delegation rule.',
         expected='01 Oct'),
    dict(id='MP3', status='Running', item='Role rules',
         detail='One line per role in the agents-and-integration rule file: orchestrator, code agents, scripts for merges and checks, one Sonnet agent for conflicts a script cannot resolve, Haiku for log triage.',
         expected='today, in DS10'),
    dict(id='MP4', status='Running', item='Per-skill model and effort',
         detail='model and effort in every plugin SKILL.md, by kind of work (section 5), with a test that compares them to the profile table.',
         expected='today, in DS10'),
    dict(id='MP5', status='Running', item='Alias-drift warning',
         detail='A session-start hook that warns when the current Opus or Sonnet ID has no saved effort entry (figure 3).',
         expected='today, in DS10'),
    dict(id='MP6', status='To do', item='Tests and release',
         detail='Profile test, hook test, claude-setup checks; released in the DS6 ready PR.',
         expected='with DS6'),
]


def _table(head, rows):
    return ('<div class="table-scroll"><table><thead><tr>' + ''.join('<th>%s</th>' % h for h in head)
            + '</tr></thead><tbody>\n' + '\n'.join('<tr>' + ''.join('<td>%s</td>' % c for c in r) + '</tr>' for r in rows)
            + '\n</tbody></table></div>')


S1 = """<p class="lede">Which model runs which work is a design decision with a cost, so it is specified, versioned and tracked like any other feature.</p>
<p>The owner&rsquo;s rule (10 October): the definition of which model each agent type uses, and each skill&rsquo;s profile, is always a feature. The 9&ndash;10 October evidence from comics-organizer showed why:</p>
<ul>
 <li>Merging, conflict resolution, lint fixes and running checks were mechanical. Design contracts, scope and judgment calls were the only work that needed the strongest model.</li>
 <li>18 parallel cloud agents used up the 5-hour session limit in about 20 minutes; five at a time finished the same work.</li>
 <li>Effort was set by hand (<code>effortLevel: high</code> in that repo&rsquo;s settings on 10 October), not by the setup every project gets.</li>
</ul>"""

S2 = (figure_today()
      + '<p>Figure 1 corrects the first inventory given in the session: Explore and Plan are not on Sonnet. '
        'They run on the main session&rsquo;s model, so in these projects they run on Opus. '
        'Only <code>general-purpose</code> code agents and plugin agents without a model of their own follow '
        '<code>CLAUDE_CODE_SUBAGENT_MODEL</code>.</p>')

S3 = (figure_ladders()
      + '<p>Two settings carry most of the weight. <code>CLAUDE_CODE_SUBAGENT_MODEL</code> only applies when nothing above it names a model. '
        'Per-model effort (<code>modelSettings</code>) is not documented to reach subagents, which is why DS5 also passes the effort on each Agent call.</p>')

S4 = (figure_alias()
      + _table(['Situation', 'What happens', 'Handled by'], [
          ['An Agent call names a model', 'It beats the agent file and the environment default.', 'Role rules: name a model only for a role that needs it (MP3)'],
          ['<code>CLAUDE_CODE_EFFORT_LEVEL</code> is set', 'It overrides every saved effort, for every model.', 'claude-setup reports it as a conflict (DS5)'],
          ['A project&rsquo;s settings set an effort', 'It shadows your user setting in that repo, for everyone who clones it.', 'Personal overrides go in <code>.claude/settings.local.json</code>'],
          ['Explore and Plan inherit Opus', 'Searches and plans cost Opus tokens.', 'Decided on 10 Oct: keep them on Opus'],
          ['A fork', 'Always runs on the main session&rsquo;s model and effort.', 'By design: a fork continues the main reasoning'],
          ['A skill sets <code>model</code>', 'Applies for the rest of the turn; the session model resumes on your next prompt. Whether a skill&rsquo;s <code>effort</code> reverts is not documented.', 'MP4 sets both; MP6 tests the revert'],
          ['An alias moves to a newer model', 'The saved effort stops applying (figure 3).', 'Session-start warning (MP5)'],
          ['A session whose model has no entry, such as a cloud agent', 'It uses the top-level <code>effortLevel</code>.', 'Top-level high (DS5)'],
      ]))

S5 = ('<h3>Per agent type</h3>'
      + _table(['Who', 'Does', 'Model', 'Effort', 'Set by'], [
          ['Main session', 'Plans, writes contracts, decides, reviews risky diffs. Nothing mechanical.', 'Opus 5.5', 'asked on every setup', '<code>model</code>, <code>modelSettings</code>'],
          ['Code agents', 'Write code, fix lint, resolve conflicts a script cannot.', 'Sonnet 5.5', 'high (preselected)', '<code>CLAUDE_CODE_SUBAGENT_MODEL</code>, Agent call <code>effort</code>'],
          ['Merges and checks', 'Join branches, run gates.', 'none: scripts', '&mdash;', 'DS6 scripts'],
          ['Log triage', 'Read CI and gate logs, name the failure.', 'Haiku 5.5', 'model default', 'Agent call <code>model: haiku</code>'],
          ['luismc-agents:architect', 'Hard design calls, audit review.', 'Opus 5.5', 'main session&rsquo;s', '<code>architect.md</code>'],
          ['Explore, Plan', 'Search, plan.', 'Opus 5.5', 'main session&rsquo;s', 'built in; kept'],
          ['fork', 'Continues the main reasoning.', 'Opus 5.5', 'main session&rsquo;s', 'built in'],
          ['claude-code-guide', 'Claude Code questions.', 'Haiku', 'built in', 'built in'],
          ['Cloud agents, routines', 'Unattended work.', 'settings model', 'high', 'top-level <code>effortLevel</code>'],
      ])
      + '<h3>Per skill</h3>'
      + _table(['Skills', 'Kind of work', 'Model', 'Effort'], [
          ['spec-new, security-audit, performance-audit, compliance-audit, tech-stack-setup, auth-setup', 'judgment', 'Opus', 'high'],
          ['spec-check, project-artifact-check, task-add, task-status-update', 'mechanical', 'Sonnet', 'medium'],
          ['claude-setup', 'setup', 'Sonnet', 'high'],
      ])
      + '<p class="note">A skill&rsquo;s <code>model</code> and <code>effort</code> go in its SKILL.md frontmatter. '
        'The model applies for the rest of the turn that runs the skill; the session model resumes on the next prompt. '
        'Skills of luismc-artifacts not listed here get their profile when that plugin is built (AR10).</p>')

S6 = _table(['ID', 'Requirement', 'Test that proves it'], [
    ['R1', 'Every plugin SKILL.md declares the model and effort of its kind (section 5).', 'A test reads every SKILL.md frontmatter and compares it with the profile table; a missing or different value fails.'],
    ['R2', 'claude-setup writes both <code>modelSettings</code> entries and the delegation rule with the chosen subagent effort.', 'The claude-setup checks (DS5): canonical IDs, medium or high, no placeholder left.'],
    ['R3', 'The rule file has one line per role.', 'The rule-file test finds each role line.'],
    ['R4', 'The session-start hook warns when the current Opus or Sonnet ID has no effort entry.', 'Hook test: settings with an entry for an older ID produce the warning; settings with the current ID do not.'],
    ['R5', 'Explore and Plan are not overridden.', 'No plugin ships an agent named Explore or Plan.'],
    ['R6', 'Whether a skill&rsquo;s effort reverts after its turn is known.', 'A manual check, recorded in History: run a skill with effort high, then check the next turn&rsquo;s effort.'],
])

S7 = _table(['#', 'Question', 'Decision (10 Oct)'], [
    ['1', 'Effort for each model of the split?', 'Asked on every setup, <strong>high preselected for code agents</strong>; top-level <code>effortLevel</code> high for cloud agents.'],
    ['2', 'Where do the role rules live?', 'In a plugin-owned rule file, <code>.claude/rules/agents-and-integration.md</code>, replaced on every run.'],
    ['3', 'Override Explore and Plan?', '<strong>No</strong>; both stay on the main session&rsquo;s model (Opus).'],
    ['4', 'Per-skill profiles?', '<strong>By kind of work</strong>: judgment on Opus high, mechanical on Sonnet medium, claude-setup on Sonnet high.'],
    ['5', 'Saved effort when an alias moves?', '<strong>Warn at session start</strong> and ask to re-run claude-setup; aliases keep following new models.'],
])


def history(stamp):
    return _table(['Date', 'Change'], [
        [stamp, 'Created. The owner made model and effort profiles a feature of their own. DS2 and DS5 moved here from the project tasks; MP1 to MP6 added; three figures (who runs on what, where settings come from, alias drift); the decisions of 10 October.'],
    ]).replace('<table>', '<table class="history-table">')


SECTIONS = [
    ('What and why', S1),
    ('Today', S2),
    ('Where model and effort come from', S3),
    ('Consequences', S4),
    ('The profiles', S5),
    ('Requirements and tests', S6),
    ('Decisions', S7),
    ('History', None),  # rendered by history(stamp)
]
