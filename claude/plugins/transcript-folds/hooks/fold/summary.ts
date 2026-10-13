// The text of a folded diff, as pieces with a tone each, and cutting pieces to
// a width. Pure: no engine import, no Node API.

import type { Change } from './change.ts'
import { displayWidth, cutToWidth, ELLIPSIS } from './width.ts'
import { markerPrefix, relativePath } from './options.ts'

export type Tone = 'dim' | 'success' | 'error' | 'plain'

export type Piece = { text: string; tone: Tone }

/** The minus sign used for removed counts (U+2212). */
export const MINUS = '−'

export function piecesText(pieces: readonly Piece[]): string {
  return pieces.map(p => p.text).join('')
}

export function piecesWidth(pieces: readonly Piece[]): number {
  return displayWidth(piecesText(pieces))
}

/** Pieces cut to at most `max` cells; the cut ends in an ellipsis in the piece it falls in. */
export function cutPieces(pieces: readonly Piece[], max: number): Piece[] {
  if (!(max > 0)) return []
  if (piecesWidth(pieces) <= max) return pieces.slice()
  const out: Piece[] = []
  let left = max
  for (let i = 0; i < pieces.length; i += 1) {
    const piece = pieces[i] as Piece
    const w = displayWidth(piece.text)
    const isLast = i === pieces.length - 1
    // Leave one cell for the ellipsis wherever the text will end.
    if (w < left || (isLast && w <= left)) {
      out.push(piece)
      left -= w
      continue
    }
    // The piece does not fit whole with the rest still to come: it ends in
    // the ellipsis (asking for one more character forces the cut).
    out.push({ text: cutToWidth(piece.text + ELLIPSIS, left), tone: piece.tone })
    return out.filter(p => p.text !== '')
  }
  return out
}

function added(n: number): Piece {
  return { text: `+${n}`, tone: 'success' }
}

function removed(n: number): Piece {
  return { text: `${MINUS}${n}`, tone: 'error' }
}

/** `(+a −r)` as pieces, with the leading text that goes before the bracket. */
export function countPieces(lead: string, addedLines: number, removedLines: number, withRemoved: boolean): Piece[] {
  const out: Piece[] = [{ text: `${lead}(`, tone: 'dim' }, added(addedLines)]
  if (withRemoved) {
    out.push({ text: ' ', tone: 'dim' }, removed(removedLines))
  }
  out.push({ text: ')', tone: 'dim' })
  return out
}

export function filesWord(n: number): string {
  return n === 1 ? '1 file' : `${n} files`
}

/**
 * The one dim line a folded file diff draws:
 * `» path:12 (+8 −3)`, `» new path (+40)`, `» nb.ipynb cell abc (+2 −1)`.
 */
export function diffLine(change: Change, root: string, marker: string): Piece[] {
  const path = relativePath(root, change.path)
  const lead = markerPrefix(marker)
  if (change.kind === 'new') {
    return countPieces(`${lead}new ${path} `, change.added, 0, false)
  }
  if (change.kind === 'notebook') {
    return countPieces(`${lead}${path} ${change.cell} `, change.added, change.removed, true)
  }
  const where = change.firstLine > 0 ? `${path}:${change.firstLine}` : path
  return countPieces(`${lead}${where} `, change.added, change.removed, true)
}

/** `» 3 files (+12 −4)`: what a shell call that edited files adds to its line. */
export function filesLine(change: Pick<Change, 'files' | 'added' | 'removed'>, marker: string): Piece[] {
  return countPieces(`${markerPrefix(marker)}${filesWord(change.files)} `, change.added, change.removed, true)
}

/** `» (+8 −3)`: the counts that follow a tool row's label in compact mode. */
export function compactCounts(change: Pick<Change, 'added' | 'removed' | 'kind'>, marker: string): Piece[] {
  return countPieces(markerPrefix(marker), change.added, change.removed, change.kind !== 'new')
}

const LABELS: Readonly<Record<string, string>> = {
  Edit: 'Update',
  MultiEdit: 'Update',
  Write: 'Write',
  NotebookEdit: 'Edit Notebook',
}

/** A file tool row's label: `Update(src/a.ts)`. */
export function toolLabel(tool: string, change: Pick<Change, 'path' | 'kind'>, root: string): string {
  const name = change.kind === 'new' ? 'Write' : (LABELS[tool] ?? tool)
  return `${name}(${relativePath(root, change.path)})`
}

export type CompactRow = { lines: Piece[][] }

/**
 * A file tool row in compact mode: the label and the counts on one line when
 * they fit `columns`, else the counts on the next line.
 */
export function compactRow(label: string, counts: readonly Piece[], columns: number): CompactRow {
  const head: Piece = { text: label, tone: 'plain' }
  const gap: Piece = { text: '  ', tone: 'dim' }
  const one = [head, gap, ...counts]
  if (columns <= 0 || piecesWidth(one) <= columns) return { lines: [one] }
  return {
    lines: [cutPieces([head], columns), cutPieces(counts, columns)],
  }
}
