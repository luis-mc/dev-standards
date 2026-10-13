import test from 'node:test'
import assert from 'node:assert/strict'

import { cellWidth, cutToWidth, displayWidth, oneLine } from '../hooks/fold/width.ts'

test('ascii is one cell per character', () => {
  assert.equal(displayWidth('hello'), 5)
  assert.equal(displayWidth(''), 0)
})

test('wide characters count two cells', () => {
  assert.equal(displayWidth('日本語'), 6)
  assert.equal(displayWidth('ａｂ'), 4)
  assert.equal(displayWidth('한글'), 4)
})

test('emoji count two cells, joined sequences and modifiers add nothing', () => {
  assert.equal(displayWidth('😀'), 2)
  assert.equal(displayWidth('a😀b'), 4)
  // man + ZWJ + woman: the joined character adds nothing
  assert.equal(displayWidth('\u{1F468}‍\u{1F469}'), 2)
  // thumbs up + skin tone
  assert.equal(displayWidth('\u{1F44D}\u{1F3FD}'), 2)
})

test('combining marks, variation selectors and control characters are zero', () => {
  assert.equal(displayWidth('é'), 1)
  assert.equal(displayWidth('❤️'), 1)
  assert.equal(displayWidth('\u0007'), 0)
  assert.equal(cellWidth(0x41), 1)
  assert.equal(cellWidth(0x4e00), 2)
})

test('cutToWidth returns text that fits unchanged', () => {
  assert.equal(cutToWidth('abc', 3), 'abc')
  assert.equal(cutToWidth('abc', 10), 'abc')
  assert.equal(cutToWidth('', 3), '')
})

test('cutToWidth marks a cut with an ellipsis that counts in the width', () => {
  assert.equal(cutToWidth('abcdef', 4), 'abc…')
  assert.equal(displayWidth(cutToWidth('abcdef', 4)), 4)
})

test('cutToWidth at tiny widths', () => {
  assert.equal(cutToWidth('abcdef', 1), '…')
  assert.equal(cutToWidth('abcdef', 0), '')
  assert.equal(cutToWidth('abcdef', -3), '')
  assert.equal(cutToWidth('abcdef', 2), 'a…')
})

test('cutToWidth never splits a wide character across the limit', () => {
  // room for 4 cells before the ellipsis would need a 2-cell char to fit at 3
  const cut = cutToWidth('日本語です', 4)
  assert.equal(cut, '日…')
  assert.ok(displayWidth(cut) <= 4)
  assert.equal(cutToWidth('😀😀😀', 3), '😀…')
  assert.equal(cutToWidth('😀😀', 2), '…')
})

test('oneLine folds whitespace and newlines to single spaces', () => {
  assert.equal(oneLine('  a\n  b\t\tc \r\n'), 'a b c')
  assert.equal(oneLine(''), '')
})
