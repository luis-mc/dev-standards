// The outcome of a finished shell call and the one row a folded call draws.
// Pure: no engine import, no Node API.

import type { Change } from './change.ts'
import { isOverThreshold } from './change.ts'
import { countLines } from './lines.ts'
import { cutPieces, filesLine, piecesWidth } from './summary.ts'
import type { Piece } from './summary.ts'
import { cutToWidth, displayWidth, oneLine } from './width.ts'

export type Outcome = {
  kind: 'output' | 'empty' | 'error'
  /** `3 lines`, `no output`, or the first line of the error. */
  text: string
}

type Rec = Record<string, unknown>

function isRec(value: unknown): value is Rec {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function str(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

export function linesWord(n: number): string {
  return n === 1 ? '1 line' : `${n} lines`
}

/** The first line of a text that has any characters; '' for none. */
export function firstLine(text: string): string {
  for (const raw of text.split('\n')) {
    const line = raw.replace(/\r$/, '').trim()
    if (line !== '') return line
  }
  return ''
}

/**
 * What a finished shell call came to. An errored call is the first line of
 * its error (the whole record is a string, or an object with stderr then
 * stdout), `failed` when there is no text at all; a call that went well is the
 * number of lines it printed on either stream, or `no output`.
 */
export function shellOutcome(output: unknown, isErrored: boolean): Outcome {
  if (isErrored) {
    const text = typeof output === 'string' ? output : isRec(output) ? str(output.stderr) || str(output.stdout) : ''
    const line = firstLine(text)
    return { kind: 'error', text: line === '' ? 'failed' : line }
  }
  if (!isRec(output)) {
    const text = typeof output === 'string' ? output.trimEnd() : ''
    return text === '' ? { kind: 'empty', text: 'no output' } : { kind: 'output', text: linesWord(countLines(text)) }
  }
  const stdout = str(output.stdout).trimEnd()
  const stderr = str(output.stderr).trimEnd()
  const n = countLines(stdout) + countLines(stderr)
  if (n === 0) return { kind: 'empty', text: 'no output' }
  return { kind: 'output', text: linesWord(n) }
}

export type OutputLine = { text: string; isStderr: boolean }

export type OutputView = { lines: OutputLine[]; more: number }

/**
 * A shell call's own output as lines (stdout, then stderr), at most `max`
 * of them; `more` counts those left out. Used where a call that edited files
 * is drawn with its output but without the per-file diff.
 */
export function outputView(output: unknown, max: number): OutputView {
  if (!isRec(output)) return { lines: [], more: 0 }
  const all: OutputLine[] = []
  for (const [key, isStderr] of [['stdout', false], ['stderr', true]] as const) {
    const text = str(output[key]).trimEnd()
    if (text === '') continue
    for (const raw of text.split('\n')) all.push({ text: raw.replace(/\r$/, ''), isStderr })
  }
  const keep = Math.max(0, Math.floor(max))
  return { lines: all.slice(0, keep), more: Math.max(0, all.length - keep) }
}

export type CommandCall = {
  isRunning: boolean
  isErrored: boolean
  isInterrupted: boolean
  output: unknown
}

export type CommandPlan = 'engine' | 'running' | 'fold'

/**
 * What to draw for a shell call. A running call keeps the engine's row (with
 * its command cut); an interrupted or backgrounded one is left alone; a call
 * that edited files folds only while the diffs switch is on and the change is
 * over the threshold, so a diff that would show is never hidden by the row.
 */
export function planCommand(
  call: CommandCall,
  edits: Change | null,
  diffsFolded: boolean,
  foldAbove: number,
): CommandPlan {
  if (call.isRunning) return 'running'
  if (call.isInterrupted) return 'engine'
  if (isRec(call.output)) {
    if (call.output.interrupted === true) return 'engine'
    if (typeof call.output.backgroundTaskId === 'string' && call.output.backgroundTaskId !== '') return 'engine'
  }
  if (edits !== null) {
    if (!diffsFolded || !isOverThreshold(edits, foldAbove)) return 'engine'
  }
  return 'fold'
}

/** A command on one line, cut to `room` cells. */
export function commandText(command: string, room: number): string {
  return cutToWidth(oneLine(command), room)
}

/**
 * The row of a folded call: `● Bash(git status)  ⎿  3 lines · » 2 files (+4 −1)`.
 * The command takes the room the rest leaves; the whole row is cut to `columns`.
 */
export function commandRow(
  tool: string,
  command: string,
  outcome: Outcome,
  edits: Change | null,
  marker: string,
  columns: number,
): Piece[] {
  const bullet: Piece = { text: '●', tone: outcome.kind === 'error' ? 'error' : 'success' }
  const joint: Piece = { text: '  ⎿  ', tone: 'dim' }
  const result: Piece = { text: outcome.text, tone: outcome.kind === 'error' ? 'error' : 'dim' }
  const tail: Piece[] = edits === null ? [] : [{ text: ' · ', tone: 'dim' }, ...filesLine(edits, marker)]
  const open: Piece = { text: ` ${tool}(`, tone: 'plain' }
  const close: Piece = { text: ')', tone: 'plain' }
  const fixed = piecesWidth([bullet, open, close, joint, result, ...tail])
  const room = columns > 0 ? Math.max(1, columns - fixed) : displayWidth(oneLine(command))
  const cmd: Piece = { text: commandText(command, room), tone: 'plain' }
  const row = [bullet, open, cmd, close, joint, result, ...tail]
  return columns > 0 ? cutPieces(row, columns) : row
}

/** A running call's command, cut so the engine's own row stays on one line. */
export function runningCommand(tool: string, command: string, columns: number): string {
  const one = oneLine(command)
  if (columns <= 0) return one
  // The engine's row: bullet, space, `Tool(`, the command, `)`.
  return cutToWidth(one, Math.max(1, columns - displayWidth(tool) - 5))
}
