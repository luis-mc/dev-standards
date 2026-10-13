import test from 'node:test'
import assert from 'node:assert/strict'

import type { Change } from '../hooks/fold/change.ts'
import {
  compactCounts, compactRow, cutPieces, diffLine, filesLine, filesWord, piecesText, piecesWidth, toolLabel,
} from '../hooks/fold/summary.ts'
import { DEFAULT_OPTIONS, markerPrefix, normalizeOptions, relativePath } from '../hooks/fold/options.ts'

const change = (over: Partial<Change> = {}): Change => ({
  kind: 'edit', path: '/p/src/a.ts', paths: ['/p/src/a.ts'], files: 1, added: 8, removed: 3, firstLine: 12, cell: '', ...over,
})

test('diffLine: path relative to the root, first line, counts in tones', () => {
  const line = diffLine(change(), '/p', '»')
  assert.equal(piecesText(line), '» src/a.ts:12 (+8 −3)')
  assert.deepEqual(line.map(p => p.tone), ['dim', 'success', 'dim', 'error', 'dim'])
})

test('diffLine: a new file', () => {
  const line = diffLine(change({ kind: 'new', added: 40, removed: 0, firstLine: 1 }), '/p', '»')
  assert.equal(piecesText(line), '» new src/a.ts (+40)')
})

test('diffLine: a notebook names its cell', () => {
  const line = diffLine(change({ kind: 'notebook', path: '/p/n.ipynb', cell: 'cell c1', firstLine: 2 }), '/p', '»')
  assert.equal(piecesText(line), '» n.ipynb cell c1 (+8 −3)')
})

test('diffLine: an empty marker leaves no leading space', () => {
  assert.equal(piecesText(diffLine(change(), '/p', '')), 'src/a.ts:12 (+8 −3)')
  assert.equal(piecesText(diffLine(change(), '/p', '  ')), 'src/a.ts:12 (+8 −3)')
})

test('diffLine: without a first line the path stands alone', () => {
  assert.equal(piecesText(diffLine(change({ firstLine: 0 }), '/p', '»')), '» src/a.ts (+8 −3)')
})

test('filesLine and filesWord', () => {
  assert.equal(piecesText(filesLine({ files: 3, added: 12, removed: 4 }, '»')), '» 3 files (+12 −4)')
  assert.equal(piecesText(filesLine({ files: 1, added: 1, removed: 0 }, '')), '1 file (+1 −0)')
  assert.equal(filesWord(0), '0 files')
})

test('compactCounts: after a label, a new file shows additions only', () => {
  assert.equal(piecesText(compactCounts({ kind: 'edit', added: 2, removed: 1 }, '»')), '» (+2 −1)')
  assert.equal(piecesText(compactCounts({ kind: 'new', added: 9, removed: 0 }, '»')), '» (+9)')
})

test('toolLabel names the tool for a reader', () => {
  assert.equal(toolLabel('Edit', change(), '/p'), 'Update(src/a.ts)')
  assert.equal(toolLabel('Write', change({ kind: 'new' }), '/p'), 'Write(src/a.ts)')
  assert.equal(toolLabel('NotebookEdit', change({ kind: 'notebook', path: '/p/n.ipynb' }), '/p'), 'Edit Notebook(n.ipynb)')
})

test('compactRow: one line when it fits, counts on the next when it does not', () => {
  const counts = compactCounts({ kind: 'edit', added: 2, removed: 1 }, '»')
  const fit = compactRow('Update(a.ts)', counts, 80)
  assert.equal(fit.lines.length, 1)
  assert.equal(piecesText(fit.lines[0] as never), 'Update(a.ts)  » (+2 −1)')
  const tight = compactRow('Update(a-long-name.ts)', counts, 24)
  assert.equal(tight.lines.length, 2)
  assert.equal(piecesText(tight.lines[1] as never), '» (+2 −1)')
  // a label alone wider than the row is cut
  const narrow = compactRow('Update(a-very-long-name.ts)', counts, 10)
  assert.equal(narrow.lines.length, 2)
  assert.ok(piecesWidth(narrow.lines[0] as never) <= 10)
})

test('cutPieces: fits, cuts in the piece it falls in, tiny widths', () => {
  const pieces = [{ text: 'abc', tone: 'dim' as const }, { text: 'defgh', tone: 'error' as const }]
  assert.equal(piecesText(cutPieces(pieces, 8)), 'abcdefgh')
  const cut = cutPieces(pieces, 6)
  assert.equal(piecesText(cut), 'abcde…')
  assert.equal(cut[1]?.tone, 'error')
  assert.equal(piecesText(cutPieces(pieces, 3)), 'ab…')
  assert.equal(piecesText(cutPieces(pieces, 1)), '…')
  assert.deepEqual(cutPieces(pieces, 0), [])
})

test('markerPrefix', () => {
  assert.equal(markerPrefix('»'), '» ')
  assert.equal(markerPrefix(''), '')
})

test('normalizeOptions: defaults, bad values, a marker that is empty', () => {
  assert.deepEqual(normalizeOptions(undefined), DEFAULT_OPTIONS)
  assert.deepEqual(normalizeOptions({}), DEFAULT_OPTIONS)
  assert.deepEqual(normalizeOptions({ foldAbove: 0, marker: '', compactCounts: true }), {
    foldAbove: 0, marker: '', compactCounts: true,
  })
  assert.equal(normalizeOptions({ foldAbove: 7.9 }).foldAbove, 7)
  assert.equal(normalizeOptions({ foldAbove: -2 }).foldAbove, 0)
  assert.equal(normalizeOptions({ foldAbove: 'x' }).foldAbove, 5)
  assert.equal(normalizeOptions({ foldAbove: NaN }).foldAbove, 5)
  assert.equal(normalizeOptions({ marker: 3 }).marker, '»')
  assert.equal(normalizeOptions({ compactCounts: 'yes' }).compactCounts, false)
})

test('relativePath: under the root, outside it, windows paths, the root itself', () => {
  assert.equal(relativePath('/p', '/p/src/a.ts'), 'src/a.ts')
  assert.equal(relativePath('/p/', '/p/src/a.ts'), 'src/a.ts')
  assert.equal(relativePath('/p', '/q/a.ts'), '/q/a.ts')
  assert.equal(relativePath('/p', '/pp/a.ts'), '/pp/a.ts')
  assert.equal(relativePath('C:\\Users\\L\\proj', 'c:\\users\\l\\proj\\src\\a.ts'), 'src/a.ts')
  assert.equal(relativePath('/p', '/p'), '.')
  assert.equal(relativePath('', '/p/a'), '/p/a')
})
