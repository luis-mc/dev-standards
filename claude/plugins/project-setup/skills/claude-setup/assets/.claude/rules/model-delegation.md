## Model split: Opus plans, Sonnet codes

This session's main loop runs on Opus. Spend it on thinking: understanding the
request, reading enough code to decide, designing the approach, breaking the
work into well-specified tasks, and reviewing what comes back.

Delegate the actual code writing to subagents, which run on Sonnet
(`CLAUDE_CODE_SUBAGENT_MODEL`):

- Any change touching more than a few lines, or more than one file, goes to a
  subagent (`general-purpose` via the Agent tool) with a self-contained brief:
  goal, files, the decided approach, constraints, and how to verify (tests,
  build, lint).
- Independent tasks go to parallel subagents in one message.
- Review each subagent's diff and test output before reporting done. Fix small
  issues directly; send larger rework back to a subagent.
- Do not override a subagent's model to Opus for implementation work. Agents
  whose definition pins a model (e.g. `architect` on Opus for judgment calls)
  keep it.
- Trivial edits (a typo, a one-line config value) may be done directly — a
  subagent round-trip costs more than it saves.
