"""Inline SVG figures for Feature: Model and effort profiles.

Each figure is a <figure> with role="img" SVG and a caption. Colours come from
page CSS classes (dg-*) that use the design tokens, so both themes work.
"""

FIGURE_CSS = """
figure.diagram{margin:1.2em 0;border:1px solid var(--rule);background:var(--surface)}
figure.diagram .diagram-scroll{overflow-x:auto;padding:.8em}
figure.diagram svg{display:block;width:100%;max-width:100%;height:auto;min-width:40rem}
figure.diagram figcaption{font-size:.86rem;color:var(--ink-muted);padding:.6em .9em;border-top:1px solid var(--rule)}
figure.diagram figcaption b{color:var(--ink)}
.dg text{fill:var(--ink);font-family:var(--font-body);font-size:12.5px}
.dg .dg-title{font-family:var(--font-display);font-stretch:var(--font-display-stretch);font-weight:700;font-size:14px}
.dg .dg-mono{font-family:var(--font-mono);font-size:11.5px}
.dg .dg-head{font-family:var(--font-mono);font-size:11px;letter-spacing:.06em;fill:var(--ink-muted)}
.dg .dg-muted{fill:var(--ink-muted)}
.dg .dg-set{fill:var(--signal);font-family:var(--font-mono);font-size:11px;font-weight:600}
.dg .dg-gap{fill:var(--running-mark);font-weight:600}
.dg .dg-box{fill:var(--surface);stroke:var(--rule-strong);stroke-width:1}
.dg .dg-main{fill:var(--surface-2);stroke:var(--ink);stroke-width:1.5}
.dg .dg-key{fill:var(--surface);stroke:var(--signal);stroke-width:2}
.dg .dg-warn{fill:var(--running-bg);stroke:var(--running-mark);stroke-width:1.5;stroke-dasharray:5 4}
.dg .dg-line{stroke:var(--ink-muted);stroke-width:1.5;fill:none}
.dg .dg-arrowhead{fill:var(--ink-muted)}
"""


def _arrow_defs(fid):
    return ('<defs><marker id="%s-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
            'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" class="dg-arrowhead"/></marker></defs>') % fid


def _figure(fid, viewbox, label, body, caption):
    return ('<figure class="diagram"><div class="diagram-scroll">'
            '<svg class="dg" viewBox="%s" role="img" aria-label="%s" xmlns="http://www.w3.org/2000/svg">%s%s</svg>'
            '</div><figcaption>%s</figcaption></figure>') % (viewbox, label, _arrow_defs(fid), body, caption)


# ---------------------------------------------------------------- figure 1: who runs on what today
def figure_today():
    fid = 'f1'
    out = []
    # main session box, vertically centred on the trunk (rows span 16..440)
    out.append('<rect class="dg-main" x="16" y="175" width="220" height="106"/>')
    out.append('<text class="dg-title" x="30" y="201">Main session</text>')
    out.append('<text x="30" y="222">Claude Opus 5.5</text>')
    out.append('<text class="dg-mono dg-muted" x="30" y="243">model &#8592; settings: opus</text>')
    out.append('<text class="dg-mono dg-muted" x="30" y="264">effort &#8592; modelSettings</text>')
    out.append('<line class="dg-line" x1="236" y1="228" x2="300" y2="228"/>')
    out.append('<text class="dg-head" x="246" y="220">SPAWNS</text>')
    out.append('<line class="dg-line" x1="300" y1="52" x2="300" y2="404"/>')
    rows = [
        (16, 'dg-key', 'Code agents (general-purpose)', 'Sonnet 5.5 &#8592; CLAUDE_CODE_SUBAGENT_MODEL',
         'effort: high, passed on each Agent call (DS5)', 'dg-set'),
        (104, 'dg-box', 'Explore, Plan', 'Opus 5.5 &#8592; the main session&#8217;s model',
         'effort: the main session&#8217;s', 'dg-muted'),
        (192, 'dg-box', 'luismc-agents:architect', 'Opus 5.5 &#8592; model: opus in architect.md',
         'effort: the main session&#8217;s', 'dg-muted'),
        (280, 'dg-box', 'fork', 'Opus 5.5 &#8592; always the main session&#8217;s',
         'effort: the main session&#8217;s', 'dg-muted'),
        (368, 'dg-box', 'Other built-in and plugin agents', 'guide: Haiku &#183; statusline: Sonnet (built in)',
         'plugin agents with no model: Sonnet (env default)', 'dg-muted'),
    ]
    for y, cls, title, model, effort, ecls in rows:
        cy = y + 36
        out.append('<line class="dg-line" x1="300" y1="%d" x2="424" y2="%d" marker-end="url(#%s-arrow)"/>' % (cy, cy, fid))
        out.append('<rect class="%s" x="430" y="%d" width="314" height="72"/>' % (cls, y))
        out.append('<text class="dg-title" x="444" y="%d">%s</text>' % (y + 22, title))
        out.append('<text class="dg-mono" x="444" y="%d">%s</text>' % (y + 42, model))
        out.append('<text class="%s" x="444" y="%d">%s</text>' % (ecls, y + 61, effort))
    caption = ('<b>Who runs on what today.</b> The main session runs on Opus and spawns every other agent; '
               'each agent&#8217;s model comes from the source after the arrow. Only code agents run on Sonnet: '
               'Explore, Plan, the architect and forks all run on Opus. Since DS5, code agents get their effort '
               'explicitly (blue box); the others take the main session&#8217;s.')
    return _figure(fid, '0 0 760 456',
                   'The main session on Opus spawns code agents on Sonnet at high effort; Explore, Plan, the architect and forks run on Opus at the main session effort; claude-code-guide runs on Haiku.',
                   ''.join(out), caption)


# ---------------------------------------------------------------- figure 2: precedence ladders
def figure_ladders():
    fid = 'f2'
    out = []
    cols = [
        (10, 'SUBAGENT MODEL', [
            ('1', 'Agent call: model', None),
            ('2', 'agent file: model', 'architect &#8594; opus'),
            ('3', 'CLAUDE_CODE_SUBAGENT_MODEL', 'claude-setup: sonnet'),
            ('4', 'the main session&#8217;s model', None),
        ]),
        (260, 'SUBAGENT EFFORT', [
            ('1', 'CLAUDE_CODE_EFFORT_LEVEL', None),
            ('2', 'Agent call: effort', 'DS5 rule: high'),
            ('3', 'agent file: effort', None),
            ('4', 'the session&#8217;s effort', None),
        ]),
        (510, 'MAIN SESSION EFFORT', [
            ('1', 'CLAUDE_CODE_EFFORT_LEVEL', None),
            ('2', '--effort or /effort', None),
            ('3', 'modelSettings[model ID]', 'claude-setup: asked'),
            ('4', 'top-level effortLevel', 'claude-setup: high'),
            ('5', 'model default: medium', None),
        ]),
    ]
    for x, head, steps in cols:
        out.append('<text class="dg-head" x="%d" y="28">%s</text>' % (x, head))
        for i, (n, label, setby) in enumerate(steps):
            y = 44 + i * 56
            cls = 'dg-key' if setby else 'dg-box'
            out.append('<rect class="%s" x="%d" y="%d" width="240" height="40"/>' % (cls, x, y))
            out.append('<text class="dg-mono dg-muted" x="%d" y="%d">%s</text>' % (x + 10, y + 25, n))
            if setby:
                out.append('<text class="dg-mono" x="%d" y="%d">%s</text>' % (x + 26, y + 17, label))
                out.append('<text class="dg-set" x="%d" y="%d">%s</text>' % (x + 26, y + 33, setby))
            else:
                out.append('<text class="dg-mono" x="%d" y="%d">%s</text>' % (x + 26, y + 25, label))
            if i < len(steps) - 1:
                out.append('<line class="dg-line" x1="%d" y1="%d" x2="%d" y2="%d" marker-end="url(#%s-arrow)"/>'
                           % (x + 120, y + 40, x + 120, y + 55, fid))
    out.append('<text class="dg-muted" x="10" y="326">Read each column top down: the first source that is set wins; an arrow means &#8220;if not set&#8221;.</text>')
    caption = ('<b>Where a model and an effort come from.</b> Blue boxes are the sources this feature writes. '
               'Anything above a blue box overrides it: an Agent call that names a model, or '
               '<code>CLAUDE_CODE_EFFORT_LEVEL</code> in the environment, which beats every saved effort for every model.')
    return _figure(fid, '0 0 760 336',
                   'Three precedence ladders: subagent model, subagent effort and main-session effort; the first source that is set wins, and the sources claude-setup writes are highlighted.',
                   ''.join(out), caption)


# ---------------------------------------------------------------- figure 3: alias drift
def figure_alias():
    fid = 'f3'
    out = []
    heads = [(10, 'ALIAS IN SETTINGS'), (190, 'MODEL IT RESOLVES TO'), (420, 'modelSettings ENTRY'), (640, 'EFFORT USED')]
    for x, h in heads:
        out.append('<text class="dg-head" x="%d" y="22">%s</text>' % (x, h))
    rows = [
        (40, 'Today', 'claude-sonnet-5-5', 'dg-box', 'claude-sonnet-5-5: high', 'dg-key', 'high', ''),
        (132, 'After &#8220;sonnet&#8221; points to a newer model', 'a newer Sonnet ID', 'dg-box',
         'no entry for this ID', 'dg-warn', 'medium', 'model default'),
    ]
    for y, label, model, mcls, entry, ecls, effort, note in rows:
        out.append('<text class="dg-muted" x="10" y="%d">%s</text>' % (y - 6, label))
        out.append('<rect class="dg-box" x="10" y="%d" width="120" height="44"/>' % y)
        out.append('<text class="dg-mono" x="70" y="%d" text-anchor="middle">sonnet</text>' % (y + 27))
        out.append('<line class="dg-line" x1="130" y1="%d" x2="184" y2="%d" marker-end="url(#%s-arrow)"/>' % (y + 22, y + 22, fid))
        out.append('<rect class="%s" x="190" y="%d" width="170" height="44"/>' % (mcls, y))
        out.append('<text class="dg-mono" x="275" y="%d" text-anchor="middle">%s</text>' % (y + 27, model))
        out.append('<line class="dg-line" x1="360" y1="%d" x2="414" y2="%d" marker-end="url(#%s-arrow)"/>' % (y + 22, y + 22, fid))
        out.append('<rect class="%s" x="420" y="%d" width="180" height="44"/>' % (ecls, y))
        out.append('<text class="dg-mono" x="510" y="%d" text-anchor="middle">%s</text>' % (y + 27, entry))
        out.append('<line class="dg-line" x1="600" y1="%d" x2="634" y2="%d" marker-end="url(#%s-arrow)"/>' % (y + 22, y + 22, fid))
        out.append('<rect class="dg-box" x="640" y="%d" width="110" height="44"/>' % y)
        if note:
            out.append('<text class="dg-title" x="695" y="%d" text-anchor="middle">%s</text>' % (y + 20, effort))
            out.append('<text class="dg-muted" x="695" y="%d" text-anchor="middle" font-size="11">%s</text>' % (y + 36, note))
        else:
            out.append('<text class="dg-title" x="695" y="%d" text-anchor="middle">%s</text>' % (y + 27, effort))
    caption = ('<b>Why a saved effort can silently stop applying.</b> Effort is saved under the full model ID, '
               'while the model is chosen by alias. When the alias moves to a newer model, nothing matches the saved '
               'entry and that model runs at its default until claude-setup runs again. MP5 decides how to prevent this.')
    return _figure(fid, '0 0 760 190',
                   'Today the sonnet alias resolves to claude-sonnet-5-5, which has a saved high effort; after the alias moves to a newer model, no entry matches and the model runs at its default medium effort.',
                   ''.join(out), caption)
