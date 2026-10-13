// The session tally and the band's text. Pure: no engine import, no Node API.

import type { Change } from './change.ts'
import { MINUS, filesWord } from './summary.ts'
import type { Piece } from './summary.ts'

export type Tally = {
  /** Paths touched, each once. */
  files: string[]
  /** Files a shell call changed whose paths were not reported; not de-duplicated. */
  extra: number
  added: number
  removed: number
}

export const EMPTY_TALLY: Tally = { files: [], extra: 0, added: 0, removed: 0 }

/** The tally with one change added: its files once each, its lines in full. */
export function addToTally(tally: Tally, change: Pick<Change, 'paths' | 'files' | 'added' | 'removed'>): Tally {
  const files = tally.files.slice()
  for (const p of change.paths) {
    if (!files.includes(p)) files.push(p)
  }
  const unknown = Math.max(0, change.files - change.paths.length)
  return {
    files,
    extra: tally.extra + unknown,
    added: tally.added + change.added,
    removed: tally.removed + change.removed,
  }
}

export function fileCount(tally: Tally): number {
  return tally.files.length + tally.extra
}

/** True before the first change of the session. */
export function isEmptyTally(tally: Tally): boolean {
  return fileCount(tally) === 0 && tally.added === 0 && tally.removed === 0
}

/** `7 files +120 −34 this session`; '' before the first change. */
export function tallyText(tally: Tally): string {
  if (isEmptyTally(tally)) return ''
  return `${filesWord(fileCount(tally))} +${tally.added} ${MINUS}${tally.removed} this session`
}

export const DIFFS_CHORD = 'ctrl+x d'
export const COMMANDS_CHORD = 'ctrl+x f'

export type BandParts = {
  diffsLabel: string
  commandsLabel: string
  tally: string
}

/** The words of the band: two switch labels and the tally. */
export function bandParts(diffsFolded: boolean, commandsFolded: boolean, tally: Tally): BandParts {
  return {
    diffsLabel: `Diffs ${diffsFolded ? 'folded' : 'shown'} (${DIFFS_CHORD})`,
    commandsLabel: `Commands ${commandsFolded ? 'folded' : 'shown'} (${COMMANDS_CHORD})`,
    tally: tallyText(tally),
  }
}

/** The band as pieces, for tests and plain text: labels, separators, tally. */
export function bandPieces(parts: BandParts): Piece[] {
  const out: Piece[] = [
    { text: parts.diffsLabel, tone: 'dim' },
    { text: ' · ', tone: 'dim' },
    { text: parts.commandsLabel, tone: 'dim' },
  ]
  if (parts.tally !== '') {
    out.push({ text: ' · ', tone: 'dim' }, { text: parts.tally, tone: 'dim' })
  }
  return out
}

/** The one line a toggle answers (toast and slash command). */
export function switchSentence(which: 'diffs' | 'commands', isFolded: boolean): string {
  const name = which === 'diffs' ? 'Diffs' : 'Commands'
  return `${name} ${isFolded ? 'folded' : 'shown in full'}.`
}
