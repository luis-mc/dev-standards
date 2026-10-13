// Counting changed lines from hunks, new files and notebook cells.
// Pure: no engine import, no Node API.

export type Hunk = {
  oldStart: number
  oldLines: number
  newStart: number
  newLines: number
  lines: readonly string[]
}

export type LineCounts = {
  added: number
  removed: number
  /** Line (in the new file) of the first changed line; 0 when nothing changed. */
  firstLine: number
}

/** Lines in a text: LF or CRLF, a missing final newline counts, "" is 0. */
export function countLines(text: string): number {
  if (text === '') return 0
  const parts = text.split('\n')
  if (parts[parts.length - 1] === '') parts.pop()
  return parts.length
}

function isAdded(line: string): boolean {
  return line.startsWith('+')
}

function isRemoved(line: string): boolean {
  return line.startsWith('-')
}

/**
 * Added and removed lines of a patch, and where the first change lies.
 *
 * A hunk line starts with `+`, `-` or a space; `\ No newline at end of file`
 * and anything else counts for nothing. CR before a line break is of no
 * matter, only the first character is read. The first changed line is found
 * in the first hunk that changes anything: its start plus the context lines
 * before the first `+` or `-` (a removal at the end of the file points at the
 * line where it was).
 */
export function countHunks(hunks: readonly Hunk[]): LineCounts {
  let added = 0
  let removed = 0
  let firstLine = 0
  let found = false
  for (const hunk of hunks) {
    let offset = 0
    let seen = false
    for (const line of hunk.lines) {
      if (isAdded(line)) {
        added += 1
        if (!found && !seen) {
          found = true
          seen = true
          firstLine = Math.max(1, hunk.newStart + offset)
        }
      } else if (isRemoved(line)) {
        removed += 1
        if (!found && !seen) {
          found = true
          seen = true
          firstLine = Math.max(1, hunk.newStart + offset)
        }
      } else if (line.startsWith(' ')) {
        if (!found) offset += 1
      }
    }
  }
  return { added, removed, firstLine }
}

/** A new file: every line of its content is an addition, from line 1. */
export function countNewFile(content: string): LineCounts {
  const added = countLines(content)
  return { added, removed: 0, firstLine: added > 0 ? 1 : 0 }
}

export type CellEdit = {
  mode: string
  oldSource?: string
  newSource?: string
}

function splitLines(text: string): string[] {
  if (text === '') return []
  const parts = text.split('\n').map(l => (l.endsWith('\r') ? l.slice(0, -1) : l))
  if (parts[parts.length - 1] === '') parts.pop()
  return parts
}

/**
 * A notebook cell edit. Insert adds the new source; delete removes the old;
 * replace drops the lines both sources share at the start and the end and
 * counts what is left on each side. Line numbers are cell-relative.
 */
export function countCell(edit: CellEdit): LineCounts {
  const before = splitLines(edit.oldSource ?? '')
  const after = splitLines(edit.newSource ?? '')
  if (edit.mode === 'insert') {
    return { added: after.length, removed: 0, firstLine: after.length > 0 ? 1 : 0 }
  }
  if (edit.mode === 'delete') {
    return { added: 0, removed: before.length, firstLine: before.length > 0 ? 1 : 0 }
  }
  let head = 0
  while (head < before.length && head < after.length && before[head] === after[head]) head += 1
  let tail = 0
  while (
    tail < before.length - head &&
    tail < after.length - head &&
    before[before.length - 1 - tail] === after[after.length - 1 - tail]
  ) {
    tail += 1
  }
  const removed = before.length - head - tail
  const added = after.length - head - tail
  return { added, removed, firstLine: added + removed > 0 ? head + 1 : 0 }
}
