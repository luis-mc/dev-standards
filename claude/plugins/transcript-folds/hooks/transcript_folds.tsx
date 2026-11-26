// luismc-transcript-folds: folds long diffs and finished shell commands to one
// line in the transcript. This file is glue: every decision (what counts as a
// change, what folds, the words of each line) is a call into ./fold/*.ts,
// which has no engine import and is tested with node:test.

import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import { EDIT_TOOLS, SHELL_TOOLS, changeOf, foldedFileChange, isOverThreshold } from './fold/change.ts'
import { normalizeOptions } from './fold/options.ts'
import { commandRow, outputView, planCommand, runningCommand, shellOutcome } from './fold/shell.ts'
import { compactCounts, compactRow, cutPieces, diffLine, filesLine, toolLabel } from './fold/summary.ts'
import type { Piece, Tone } from './fold/summary.ts'
import { EMPTY_TALLY, addToTally, bandParts, switchSentence } from './fold/tally.ts'
import type { Tally } from './fold/tally.ts'

// Session state. Its contract is types/state.d.ts. The two switches start
// folded in every session.
const diffsFolded = atom({ plugin: 'luismc-transcript-folds', key: 'diffsFolded' } as const, true)
const commandsFolded = atom({ plugin: 'luismc-transcript-folds', key: 'commandsFolded' } as const, true)
const tally = atom({ plugin: 'luismc-transcript-folds', key: 'tally' } as const, EMPTY_TALLY as Tally)
const root = atom({ plugin: 'luismc-transcript-folds', key: 'root' } as const, '')
const COUNTS = { plugin: 'luismc-transcript-folds', key: 'counts' } as const
const OUTCOMES = { plugin: 'luismc-transcript-folds', key: 'outcomes' } as const

type Which = 'diffs' | 'commands'

// Flips a switch for this session and answers its new state.
async function flip($: Pick<EngineInterface, 'state'>, which: Which): Promise<boolean> {
  // The scan reads update's source by name, so each switch has its own call.
  const isFolded =
    which === 'diffs'
      ? await update($, diffsFolded, value => !value)
      : await update($, commandsFolded, value => !value)
  return isFolded
}

function toneProps(tone: Tone): Record<string, string | boolean> {
  if (tone === 'dim') return { dimColor: true }
  if (tone === 'success') return { color: 'success' }
  if (tone === 'error') return { color: 'error' }
  return {}
}

// One row of pieces, each in its tone, cut to the row.
function row(Text: any, pieces: readonly Piece[]) {
  return (
    <Text wrap="truncate">
      {pieces.map(piece => (
        <Text {...toneProps(piece.tone)}>{piece.text}</Text>
      ))}
    </Text>
  )
}

function inputCommand(input: unknown): string {
  if (typeof input === 'object' && input !== null && 'command' in input) {
    const command = (input as { command?: unknown }).command
    if (typeof command === 'string') return command
  }
  return ''
}

export const register: Register = (on, options) => {
  const opts = normalizeOptions(options)

  on('session.start', async ($, e, next) => {
    const held = await $.state.get({ plugin: 'luismc-transcript-folds', key: 'root' })
    if (held.value === undefined || held.value === '') {
      await $.state.set({ plugin: 'luismc-transcript-folds', key: 'root' }, e.cwd)
    }
    // Every session starts with diffs and commands folded (owner, 16 Oct): a
    // toggle holds for this session only, so a stray ctrl+x f never carries over.
    await $.command.register({ name: 'fold-diffs', description: 'Fold or show long diffs in the transcript' })
    await $.command.register({ name: 'fold-commands', description: 'Fold or show finished shell commands in the transcript' })
    return next(e)
  })

  on('command.run', { command: 'fold-diffs' }, async $ => {
    const isFolded = await flip($, 'diffs')
    return { text: switchSentence('diffs', isFolded) }
  })

  on('command.run', { command: 'fold-commands' }, async $ => {
    const isFolded = await flip($, 'commands')
    return { text: switchSentence('commands', isFolded) }
  })

  // The tally and the per-call records. The result is the engine's own and is
  // handed back untouched.
  on('tool.call', async ($, e, next) => {
    const done = await next(e)
    if (done.deny !== undefined || done.isError === true) return done
    const tool = String(e.tool)
    const isEdit = EDIT_TOOLS.includes(tool)
    const isShell = SHELL_TOOLS.includes(tool)
    if (!isEdit && !isShell) return done
    try {
      const id = e.tool_use_id
      if (isShell) {
        await $.state.set({ ...OUTCOMES, id }, shellOutcome(done.result, false))
      }
      const change = changeOf(tool, done.result)
      if (change !== null) {
        await $.state.set({ ...COUNTS, id }, change)
        await update($, tally, current => addToTally(current, change))
      }
    } catch {
      // A record that cannot be kept never costs the call.
    }
    return done
  }).catch(($, e, next) => next(e))

  on('ui.render', { component: 'ToolResult' }, async ($, e, next) => {
    const { tool, output, isErrored } = e.props
    const isEdit = EDIT_TOOLS.includes(tool)
    const isShell = SHELL_TOOLS.includes(tool)
    if (!isEdit && !isShell) return next(e)
    const diffs = await read($, diffsFolded)
    const columns = e.viewport?.columns ?? 0

    if (isEdit) {
      const change = foldedFileChange(tool, output, isErrored, diffs, opts.foldAbove)
      if (change === null) return next(e)
      const { Box, Text } = $.ui.resolve(e)
      // Compact mode: the counts ride the tool row; nothing is drawn here.
      if (opts.compactCounts) return <Box display="none" />
      const dir = await read($, root)
      const pieces: Piece[] = [{ text: '  ⎿  ', tone: 'dim' }, ...diffLine(change, dir, opts.marker)]
      return <Box>{row(Text, columns > 0 ? cutPieces(pieces, columns) : pieces)}</Box>
    }

    const commands = await read($, commandsFolded)
    const change = changeOf(tool, output)
    const plan = planCommand({ isRunning: false, isErrored, isInterrupted: false, output }, change, diffs, opts.foldAbove)
    const { Box, Text } = $.ui.resolve(e)
    if (commands && plan === 'fold') return <Box display="none" />

    // A call that edited files: its own output, then one line for the files,
    // in place of the engine's per-file diff.
    if (diffs && !isErrored && plan === 'fold' && change !== null && isOverThreshold(change, opts.foldAbove)) {
      const view = outputView(output, 20)
      const nodes = view.lines.map(line => (line.isStderr ? <Text color="error">{line.text}</Text> : <Text>{line.text}</Text>))
      if (view.more > 0) nodes.push(<Text dimColor>{`… +${view.more} lines`}</Text>)
      nodes.push(row(Text, filesLine(change, opts.marker)))
      return <Box flexDirection="column">{nodes}</Box>
    }
    return next(e)
  })

  on('ui.render', { component: 'ToolUse' }, async ($, e, next) => {
    const props = e.props
    const isEdit = EDIT_TOOLS.includes(props.tool)
    const isShell = SHELL_TOOLS.includes(props.tool)
    if (!isEdit && !isShell) return next(e)
    const columns = e.viewport?.columns ?? 0

    if (isEdit) {
      if (!opts.compactCounts || props.isRunning) return next(e)
      const diffs = await read($, diffsFolded)
      const change = foldedFileChange(props.tool, props.output, props.isErrored, diffs, opts.foldAbove)
      if (change === null) return next(e)
      const dir = await read($, root)
      const { Box, Text } = $.ui.resolve(e)
      const layout = compactRow(toolLabel(props.tool, change, dir), compactCounts(change, opts.marker), Math.max(0, columns - 2))
      const lines = layout.lines.map((pieces, index) => {
        const lead: Piece[] = index === 0 ? [{ text: '● ', tone: 'success' }] : [{ text: '  ', tone: 'plain' }]
        return row(Text, [...lead, ...pieces])
      })
      return <Box flexDirection="column">{lines}</Box>
    }

    const commands = await read($, commandsFolded)
    if (!commands) return next(e)
    const command = inputCommand(props.input)
    if (command === '') return next(e)
    const diffs = await read($, diffsFolded)
    const change = changeOf(props.tool, props.output)
    const plan = planCommand(
      { isRunning: props.isRunning, isErrored: props.isErrored, isInterrupted: props.isInterrupted, output: props.output },
      change,
      diffs,
      opts.foldAbove,
    )
    if (plan === 'engine') return next(e)
    if (plan === 'running') {
      const cut = runningCommand(props.tool, command, columns)
      if (cut === command) return next(e)
      const input = { ...(props.input as Record<string, unknown>), command: cut }
      return next({ ...e, props: { ...props, input } })
    }
    const { Box, Text } = $.ui.resolve(e)
    const outcome = shellOutcome(props.output, props.isErrored)
    return <Box>{row(Text, commandRow(props.tool, command, outcome, change, opts.marker, columns))}</Box>
  })

  // With the diffs switch off every diff must show, so a run of calls the
  // engine would fold into one count line is drawn expanded.
  on('ui.render', { component: 'ToolGroup' }, async ($, e, next) => {
    if (e.props.isExpanded || !e.props.calls.some(call => EDIT_TOOLS.includes(call.tool))) return next(e)
    if (await read($, diffsFolded)) return next(e)
    return next({ ...e, props: { ...e.props, isExpanded: true } })
  })

  // The band above the prompt: two buttons, each pressed by the chord the
  // person gave its engine action, and the session's tally.
  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    if (e.props.hasSurvey) return next(e)
    const parts = bandParts(await read($, diffsFolded), await read($, commandsFolded), await read($, tally))
    const { Box, Button, Text } = $.ui.resolve(e)
    // The tally is absent before the first change.
    const tail = parts.tally === '' ? [] : [<Text dimColor>{` · ${parts.tally}`}</Text>]
    return (
      <Box>
        <Button
          key="diffs"
          label={parts.diffsLabel}
          plain
          dimColor
          action="theme:toggleSyntaxHighlighting"
          onPress={async () => {
            $.ui.toast(switchSentence('diffs', await flip($, 'diffs')))
          }}
        />
        <Text dimColor>{' · '}</Text>
        <Button
          key="commands"
          label={parts.commandsLabel}
          plain
          dimColor
          action="theme:editCustom"
          onPress={async () => {
            $.ui.toast(switchSentence('commands', await flip($, 'commands')))
          }}
        />
        {tail}
      </Box>
    )
  })
}
