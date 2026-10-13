import test from 'node:test'
import assert from 'node:assert/strict'

import { countCell, countHunks, countLines, countNewFile } from '../hooks/fold/lines.ts'

test('countLines: LF, CRLF, missing final newline, empty', () => {
  assert.equal(countLines(''), 0)
  assert.equal(countLines('a'), 1)
  assert.equal(countLines('a\n'), 1)
  assert.equal(countLines('a\nb'), 2)
  assert.equal(countLines('a\r\nb\r\n'), 2)
  assert.equal(countLines('\n'), 1)
  assert.equal(countLines('a\n\nb\n'), 3)
})

test('countHunks: one hunk, first line is after the leading context', () => {
  const r = countHunks([
    { oldStart: 10, oldLines: 5, newStart: 10, newLines: 6, lines: [' a', ' b', '-c', '+C', '+D', ' e'] },
  ])
  assert.deepEqual(r, { added: 2, removed: 1, firstLine: 12 })
})

test('countHunks: several hunks add up, the first hunk gives the first line', () => {
  const r = countHunks([
    { oldStart: 3, oldLines: 2, newStart: 3, newLines: 3, lines: ['+x', ' y', ' z'] },
    { oldStart: 40, oldLines: 3, newStart: 41, newLines: 2, lines: [' p', '-q', ' r'] },
  ])
  assert.deepEqual(r, { added: 1, removed: 1, firstLine: 3 })
})

test('countHunks: a first hunk with no change is skipped for the first line', () => {
  const r = countHunks([
    { oldStart: 1, oldLines: 2, newStart: 1, newLines: 2, lines: [' a', ' b'] },
    { oldStart: 20, oldLines: 2, newStart: 20, newLines: 2, lines: [' a', '-b', '+c'] },
  ])
  assert.deepEqual(r, { added: 1, removed: 1, firstLine: 21 })
})

test('countHunks: CRLF lines and the no-newline marker', () => {
  const r = countHunks([
    {
      oldStart: 1,
      oldLines: 2,
      newStart: 1,
      newLines: 2,
      lines: ['-old\r', '\\ No newline at end of file', '+new\r', '\\ No newline at end of file'],
    },
  ])
  assert.deepEqual(r, { added: 1, removed: 1, firstLine: 1 })
})

test('countHunks: nothing changed, and no hunks', () => {
  assert.deepEqual(countHunks([]), { added: 0, removed: 0, firstLine: 0 })
  assert.deepEqual(
    countHunks([{ oldStart: 1, oldLines: 1, newStart: 1, newLines: 1, lines: [' a'] }]),
    { added: 0, removed: 0, firstLine: 0 },
  )
})

test('countNewFile counts every line as added from line 1', () => {
  assert.deepEqual(countNewFile('a\nb\nc\n'), { added: 3, removed: 0, firstLine: 1 })
  assert.deepEqual(countNewFile('one'), { added: 1, removed: 0, firstLine: 1 })
  assert.deepEqual(countNewFile(''), { added: 0, removed: 0, firstLine: 0 })
  assert.deepEqual(countNewFile('a\r\nb'), { added: 2, removed: 0, firstLine: 1 })
})

test('countCell: a cell added', () => {
  assert.deepEqual(countCell({ mode: 'insert', newSource: 'a\nb' }), { added: 2, removed: 0, firstLine: 1 })
})

test('countCell: a cell removed', () => {
  assert.deepEqual(countCell({ mode: 'delete', oldSource: 'a\nb\nc' }), { added: 0, removed: 3, firstLine: 1 })
})

test('countCell: a cell changed counts only the lines that differ', () => {
  const r = countCell({ mode: 'replace', oldSource: 'a\nb\nc\nd', newSource: 'a\nB\nC\nd' })
  assert.deepEqual(r, { added: 2, removed: 2, firstLine: 2 })
})

test('countCell: replace with identical source changes nothing; CRLF is ignored', () => {
  assert.deepEqual(countCell({ mode: 'replace', oldSource: 'a\r\nb', newSource: 'a\nb' }), {
    added: 0,
    removed: 0,
    firstLine: 0,
  })
})

test('countCell: replace of an empty cell is a pure addition', () => {
  assert.deepEqual(countCell({ mode: 'replace', oldSource: '', newSource: 'x\ny' }), {
    added: 2,
    removed: 0,
    firstLine: 1,
  })
})
