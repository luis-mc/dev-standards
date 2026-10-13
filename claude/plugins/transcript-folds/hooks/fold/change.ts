// What a finished tool call changed, read from the tool's result record.
// Pure: no engine import, no Node API. The record is read defensively: a
// shape that is not the one expected is "no change", never an error.

import { countCell, countHunks, countNewFile } from './lines.ts'
import type { Hunk, LineCounts } from './lines.ts'

export type ChangeKind = 'edit' | 'new' | 'notebook' | 'bash'

export type Change = {
  kind: ChangeKind
  /** File path as the tool reported it (absolute); '' for a shell call. */
  path: string
  /** Every file the call changed, as far as the record names them. */
  paths: string[]
  /** How many files: 1 for a file tool; for a shell call all it reports. */
  files: number
  added: number
  removed: number
  /** Line of the first change; 0 when unknown (a shell call). */
  firstLine: number
  /** Notebook cell, named for a reader; '' otherwise. */
  cell: string
}

export const EDIT_TOOLS: readonly string[] = ['Edit', 'Write', 'MultiEdit', 'NotebookEdit']
export const SHELL_TOOLS: readonly string[] = ['Bash', 'PowerShell']

type Rec = Record<string, unknown>

function isRec(value: unknown): value is Rec {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function str(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

function num(value: unknown): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : 0
}

function hunksOf(value: unknown): Hunk[] {
  if (!Array.isArray(value)) return []
  const out: Hunk[] = []
  for (const h of value) {
    if (!isRec(h) || !Array.isArray(h.lines)) continue
    out.push({
      oldStart: num(h.oldStart),
      oldLines: num(h.oldLines),
      newStart: num(h.newStart),
      newLines: num(h.newLines),
      lines: h.lines.filter((l): l is string => typeof l === 'string'),
    })
  }
  return out
}

function make(kind: ChangeKind, path: string, counts: LineCounts, extra: Partial<Change> = {}): Change {
  return {
    kind,
    path,
    paths: path === '' ? [] : [path],
    files: 1,
    added: counts.added,
    removed: counts.removed,
    firstLine: counts.firstLine,
    cell: '',
    ...extra,
  }
}

function fromFileEdit(output: Rec): Change | null {
  if (output.staged === true) return null
  const path = str(output.filePath)
  if (path === '') return null
  const hunks = hunksOf(output.structuredPatch)
  if (hunks.length === 0) return null
  return make('edit', path, countHunks(hunks))
}

function fromWrite(output: Rec): Change | null {
  if (output.staged === true) return null
  const path = str(output.filePath)
  if (path === '') return null
  if (output.type === 'create') {
    return make('new', path, countNewFile(str(output.content)))
  }
  const hunks = hunksOf(output.structuredPatch)
  if (hunks.length === 0) return null
  return make('edit', path, countHunks(hunks))
}

function fromNotebook(output: Rec): Change | null {
  if (str(output.error) !== '') return null
  const path = str(output.notebook_path)
  if (path === '') return null
  const mode = str(output.edit_mode) || 'replace'
  const counts = countCell({
    mode,
    oldSource: str(output.old_source),
    newSource: str(output.new_source),
  })
  const id = str(output.cell_id)
  const cell = id !== '' ? `cell ${id}` : mode === 'insert' ? 'new cell' : 'cell'
  return make('notebook', path, counts, { cell })
}

function fromShell(output: Rec): Change | null {
  const diff = output.bashEditDiff
  if (!isRec(diff) || diff.unavailable === true || diff.skipped === true) return null
  const list = Array.isArray(diff.files) ? diff.files : []
  const more = Math.max(0, Math.floor(num(diff.moreFiles)))
  let added = 0
  let removed = 0
  const paths: string[] = []
  for (const f of list) {
    if (!isRec(f)) continue
    const counts = countHunks(hunksOf(f.hunks))
    added += counts.added
    removed += counts.removed
    const p = str(f.filePath)
    if (p !== '' && !paths.includes(p)) paths.push(p)
  }
  if (Array.isArray(diff.changedFiles)) {
    for (const p of diff.changedFiles) {
      if (typeof p === 'string' && p !== '' && !paths.includes(p)) paths.push(p)
    }
  }
  const files = list.length + more
  if (files === 0) return null
  return {
    kind: 'bash',
    path: '',
    paths,
    files,
    added,
    removed,
    firstLine: 0,
    cell: '',
  }
}

/**
 * The change a finished call made, or null when it made none we can count
 * (another tool, an unreadable record, an edit held for review).
 */
export function changeOf(tool: string, output: unknown): Change | null {
  if (!isRec(output)) return null
  switch (tool) {
    case 'Edit':
    case 'MultiEdit':
      return fromFileEdit(output)
    case 'Write':
      return fromWrite(output)
    case 'NotebookEdit':
      return fromNotebook(output)
    case 'Bash':
      return fromShell(output)
    default:
      return null
  }
}

/** Added plus removed lines. */
export function changedLines(change: Pick<Change, 'added' | 'removed'>): number {
  return change.added + change.removed
}

/**
 * Whether a change is drawn folded: its changed lines exceed the threshold.
 * A threshold of 0 folds every diff that changes anything.
 */
export function isOverThreshold(change: Pick<Change, 'added' | 'removed'>, foldAbove: number): boolean {
  const n = changedLines(change)
  return n > 0 && n > foldAbove
}
