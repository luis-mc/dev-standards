import test from 'node:test'
import assert from 'node:assert/strict'

import type { Change } from '../hooks/fold/change.ts'
import { commandRow, commandText, firstLine, linesWord, planCommand, runningCommand, shellOutcome } from '../hooks/fold/shell.ts'
import { piecesText, piecesWidth } from '../hooks/fold/summary.ts'

const edits: Change = {
  kind: 'bash', path: '', paths: ['/p/a'], files: 2, added: 9, removed: 1, firstLine: 0, cell: '',
}

test('outcome: lines of output, one line, no output', () => {
  assert.deepEqual(shellOutcome({ stdout: 'a\nb\nc\n', stderr: '' }, false), { kind: 'output', text: '3 lines' })
  assert.deepEqual(shellOutcome({ stdout: 'a\n', stderr: '' }, false), { kind: 'output', text: '1 line' })
  assert.deepEqual(shellOutcome({ stdout: '', stderr: '' }, false), { kind: 'empty', text: 'no output' })
  assert.deepEqual(shellOutcome({ stdout: '\n\n', stderr: '  \n' }, false), { kind: 'empty', text: 'no output' })
})

test('outcome: empty and odd records', () => {
  assert.deepEqual(shellOutcome(undefined, false), { kind: 'empty', text: 'no output' })
  assert.deepEqual(shellOutcome('', false), { kind: 'empty', text: 'no output' })
  assert.deepEqual(shellOutcome('x\ny', false), { kind: 'output', text: '2 lines' })
})

test('outcome: stderr only counts the stderr lines', () => {
  assert.deepEqual(shellOutcome({ stdout: '', stderr: 'warn1\nwarn2' }, false), { kind: 'output', text: '2 lines' })
  assert.deepEqual(shellOutcome({ stdout: 'a', stderr: 'b' }, false), { kind: 'output', text: '2 lines' })
})

test('outcome: an error shows its first line only', () => {
  const text = 'Exit code 1\nfatal: not a git repository\nhint: more'
  assert.deepEqual(shellOutcome(text, true), { kind: 'error', text: 'Exit code 1' })
  assert.deepEqual(shellOutcome('\n\n  boom \r\nnext', true), { kind: 'error', text: 'boom' })
})

test('outcome: an error that is only an exit code, or has no text', () => {
  assert.deepEqual(shellOutcome('Exit code 127', true), { kind: 'error', text: 'Exit code 127' })
  assert.deepEqual(shellOutcome('', true), { kind: 'error', text: 'failed' })
  assert.deepEqual(shellOutcome(undefined, true), { kind: 'error', text: 'failed' })
  assert.deepEqual(shellOutcome({ stdout: '', stderr: '' }, true), { kind: 'error', text: 'failed' })
  assert.deepEqual(shellOutcome({ stdout: 'out', stderr: 'bad thing\nmore' }, true), { kind: 'error', text: 'bad thing' })
})

test('firstLine and linesWord', () => {
  assert.equal(firstLine(''), '')
  assert.equal(firstLine('\n  \nx\ny'), 'x')
  assert.equal(linesWord(1), '1 line')
  assert.equal(linesWord(0), '0 lines')
})

const call = (over = {}) => ({ isRunning: false, isErrored: false, isInterrupted: false, output: { stdout: 'x', stderr: '' }, ...over })

test('plan: running keeps the engine row with the command cut', () => {
  assert.equal(planCommand(call({ isRunning: true, output: undefined }), null, true, 5), 'running')
})

test('plan: interrupted and backgrounded calls are never folded', () => {
  assert.equal(planCommand(call({ isInterrupted: true }), null, true, 5), 'engine')
  assert.equal(planCommand(call({ output: { stdout: '', stderr: '', interrupted: true } }), null, true, 5), 'engine')
  assert.equal(planCommand(call({ output: { stdout: '', stderr: '', backgroundTaskId: 'b1' } }), null, true, 5), 'engine')
})

test('plan: a finished call folds, an errored one too', () => {
  assert.equal(planCommand(call(), null, true, 5), 'fold')
  assert.equal(planCommand(call({ isErrored: true, output: 'Exit code 1' }), null, false, 5), 'fold')
})

test('plan: a call that edited files folds only with diffs folded and over the threshold', () => {
  assert.equal(planCommand(call(), edits, true, 5), 'fold')
  assert.equal(planCommand(call(), edits, false, 5), 'engine')
  assert.equal(planCommand(call(), { ...edits, added: 2, removed: 1 }, true, 5), 'engine')
  assert.equal(planCommand(call(), { ...edits, added: 2, removed: 1 }, true, 0), 'fold')
})

test('commandRow: bullet, tool, command, outcome', () => {
  const row = commandRow('Bash', 'git status', { kind: 'output', text: '3 lines' }, null, '»', 120)
  assert.equal(piecesText(row), '● Bash(git status)  ⎿  3 lines')
  assert.equal(row[0]?.tone, 'success')
})

test('commandRow: an error is red in bullet and text', () => {
  const row = commandRow('Bash', 'false', { kind: 'error', text: 'Exit code 1' }, null, '»', 120)
  assert.equal(row[0]?.tone, 'error')
  assert.equal(row[row.length - 1]?.tone, 'error')
})

test('commandRow: edits add the files line', () => {
  const row = commandRow('Bash', 'sed -i x', { kind: 'empty', text: 'no output' }, edits, '»', 120)
  assert.equal(piecesText(row), '● Bash(sed -i x)  ⎿  no output · » 2 files (+9 −1)')
})

test('commandRow: a long multi-line command is cut to the room; the row fits the width', () => {
  const command = 'echo one\n  echo two && echo three && echo four && echo five && echo six'
  const row = commandRow('Bash', command, { kind: 'output', text: '2 lines' }, null, '»', 40)
  assert.equal(piecesWidth(row), 40)
  assert.ok(piecesText(row).includes('…'))
  assert.ok(!piecesText(row).includes('\n'))
})

test('commandRow: tiny widths still give a row within the width', () => {
  const row = commandRow('Bash', 'ls', { kind: 'output', text: '2 lines' }, edits, '»', 6)
  assert.ok(piecesWidth(row) <= 6)
})

test('commandRow: wide characters in the command count as two cells', () => {
  const row = commandRow('Bash', 'echo 日本語日本語日本語', { kind: 'empty', text: 'no output' }, null, '»', 30)
  assert.ok(piecesWidth(row) <= 30)
})

test('commandText and runningCommand cut to one line', () => {
  assert.equal(commandText('a\nb', 10), 'a b')
  assert.equal(commandText('abcdefghij', 5), 'abcd…')
  assert.equal(runningCommand('Bash', 'x\ny', 80), 'x y')
  assert.equal(runningCommand('Bash', 'abcdefghijklmnopqrstuvwxyz', 20), 'abcdefghij…')
  assert.equal(runningCommand('Bash', 'a\nb', 0), 'a b')
})
