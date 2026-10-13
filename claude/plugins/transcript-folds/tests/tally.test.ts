import test from 'node:test'
import assert from 'node:assert/strict'

import {
  EMPTY_TALLY, addToTally, bandParts, bandPieces, fileCount, isEmptyTally, switchSentence, tallyText,
} from '../hooks/fold/tally.ts'
import { piecesText } from '../hooks/fold/summary.ts'

const one = (path: string, added: number, removed: number) => ({ paths: [path], files: 1, added, removed })

test('an empty tally says nothing', () => {
  assert.equal(isEmptyTally(EMPTY_TALLY), true)
  assert.equal(tallyText(EMPTY_TALLY), '')
  assert.equal(fileCount(EMPTY_TALLY), 0)
})

test('the same file twice counts once, its lines twice', () => {
  let t = addToTally(EMPTY_TALLY, one('/p/a', 3, 1))
  t = addToTally(t, one('/p/a', 2, 2))
  assert.equal(fileCount(t), 1)
  assert.deepEqual([t.added, t.removed], [5, 3])
  assert.equal(tallyText(t), '1 file +5 −3 this session')
})

test('addToTally does not change the tally it was given', () => {
  const before = addToTally(EMPTY_TALLY, one('/p/a', 1, 0))
  const copy = JSON.stringify(before)
  addToTally(before, one('/p/b', 4, 4))
  assert.equal(JSON.stringify(before), copy)
  assert.equal(EMPTY_TALLY.files.length, 0)
})

test('a shell call adds its paths, and files it did not name by count', () => {
  const t = addToTally(EMPTY_TALLY, { paths: ['/p/a', '/p/b'], files: 5, added: 10, removed: 2 })
  assert.equal(fileCount(t), 5)
  assert.equal(tallyText(t), '5 files +10 −2 this session')
  const again = addToTally(t, one('/p/a', 1, 1))
  assert.equal(fileCount(again), 5)
})

test('a change of no lines still counts its file', () => {
  const t = addToTally(EMPTY_TALLY, one('/p/a', 0, 0))
  assert.equal(isEmptyTally(t), false)
  assert.equal(tallyText(t), '1 file +0 −0 this session')
})

test('the band: labels with chords, no tally before the first change', () => {
  const parts = bandParts(true, true, EMPTY_TALLY)
  assert.equal(piecesText(bandPieces(parts)), 'Diffs folded (ctrl+x d) · Commands folded (ctrl+x f)')
})

test('the band: states shown, and the tally once there is one', () => {
  let t = EMPTY_TALLY
  for (let i = 0; i < 7; i += 1) t = addToTally(t, one(`/p/f${i}`, i === 0 ? 120 : 0, i === 0 ? 34 : 0))
  const parts = bandParts(false, true, t)
  assert.equal(
    piecesText(bandPieces(parts)),
    'Diffs shown (ctrl+x d) · Commands folded (ctrl+x f) · 7 files +120 −34 this session',
  )
})

test('switchSentence says the new state in one line', () => {
  assert.equal(switchSentence('diffs', true), 'Diffs folded.')
  assert.equal(switchSentence('diffs', false), 'Diffs shown in full.')
  assert.equal(switchSentence('commands', true), 'Commands folded.')
  assert.equal(switchSentence('commands', false), 'Commands shown in full.')
})
