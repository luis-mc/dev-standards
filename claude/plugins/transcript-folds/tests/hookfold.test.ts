import test from 'node:test'
import assert from 'node:assert/strict'

import {
  EMPTY_DIAG, diagSentence, hookLine, noteSeen, parseHookMessage, planHookFold, wordCount,
} from '../hooks/fold/hookfold.ts'
import { normalizeOptions } from '../hooks/fold/options.ts'
import { piecesText } from '../hooks/fold/summary.ts'
import { displayWidth } from '../hooks/fold/width.ts'

const words = (n: number) => Array.from({ length: n }, (_, i) => `w${i}`).join(' ')
const LONG = `Stop says: DL-63 row is still open. ${words(410)}`

test('a long hook message folds to event, first sentence and words', () => {
  const message = planHookFold(LONG, true, 40)
  assert.notEqual(message, null)
  assert.equal(message?.event, 'Stop')
  const line = piecesText(hookLine(message!, wordCount(LONG), 0))
  assert.equal(line, 'Stop says: DL-63 row is still open. (+410 words)')
})

test('a matcher name stays in the event: PreToolUse:Bash hook error', () => {
  const text = `PreToolUse:Bash hook error: blocked the call.\n${words(100)}`
  const message = planHookFold(text, true, 40)
  assert.equal(message?.event, 'PreToolUse:Bash')
  assert.match(piecesText(hookLine(message!, wordCount(text), 0)), /^PreToolUse:Bash hook error: blocked the call\. \(\+\d+ words\)$/)
  assert.equal(parseHookMessage(`SessionStart hook feedback: ${words(3)}`)?.event, 'SessionStart')
})

test('a short hook message is drawn whole', () => {
  assert.equal(planHookFold(`Stop says: ${words(20)}`, true, 40), null)
})

test('the threshold: exactly foldAbove words is whole, one more folds', () => {
  const at = `Stop says: ${words(38)}`
  assert.equal(wordCount(at), 40)
  assert.equal(planHookFold(at, true, 40), null)
  assert.notEqual(planHookFold(`${at} more`, true, 40), null)
  assert.notEqual(planHookFold('Stop says: hi', true, 0), null)
})

test('a long message that is not hook output is never folded', () => {
  assert.equal(planHookFold(words(300), true, 40), null)
  assert.equal(planHookFold(`Please review this. Stop says: ${words(100)}`, true, 40), null)
  assert.equal(planHookFold(`<system-reminder>\nStop says: ${words(100)}\n</system-reminder>`, true, 40), null)
  assert.equal(planHookFold(`Stop saying: ${words(100)}`, true, 40), null)
})

test('the switch off draws every hook message whole', () => {
  assert.equal(planHookFold(LONG, false, 40), null)
})

test('the line is cut to the width and keeps its word count', () => {
  const message = planHookFold(`Stop says: ${'x'.repeat(200)}. ${words(100)}`, true, 40)
  const line = piecesText(hookLine(message!, 101, 60))
  assert.ok(displayWidth(line) <= 60, line)
  assert.match(line, /^Stop says: x+… \(\+\d+ words\)$/)
})

test('foldHooksAbove: default 40, bad values fall back, a fraction rounds down', () => {
  assert.equal(normalizeOptions(undefined).foldHooksAbove, 40)
  assert.equal(normalizeOptions({ foldHooksAbove: 'x' }).foldHooksAbove, 40)
  assert.equal(normalizeOptions({ foldHooksAbove: -3 }).foldHooksAbove, 0)
  assert.equal(normalizeOptions({ foldHooksAbove: 12.9 }).foldHooksAbove, 12)
})

test('diag keeps the last five of each list and skips short non-matches', () => {
  let diag = EMPTY_DIAG
  for (let i = 0; i < 7; i += 1) diag = noteSeen(diag, 'UserMessage', `Stop says: n${i} ${words(5)}`, true)
  assert.equal(diag.matched.length, 5)
  assert.equal(diag.matched[0]?.head.startsWith('Stop says: n2'), true)
  const same = noteSeen(diag, 'UserMessage', `Stop says: n6 ${words(5)}`, true)
  assert.equal(same, diag)
  assert.equal(noteSeen(diag, 'InfoNotice', words(30), false), diag)
  const missed = noteSeen(diag, 'InfoNotice', words(90), false)
  assert.equal(missed.missed.length, 1)
  assert.equal(missed.missed[0]?.head.length, 40)
  assert.equal(missed.missed[0]?.words, 90)
  assert.match(diagSentence(missed), /^Matched \(last 5\): .* \| Long, not matched \(last 5\): InfoNotice "w0 w1/)
  assert.match(diagSentence(EMPTY_DIAG), /none \| .*none$/)
})
