// Hook messages: the long feedback text a hook adds to the transcript. Pure:
// no engine import, no Node API.
//
// The engine names no render component for a hook message and the render
// input carries no hook marker. So the matcher works on the text alone and
// folds only a message whose first line has the shape of hook output:
// `Stop says: ...`, `PreToolUse:Bash hook error: ...`, `X hook feedback: ...`.
// A message that has any other shape, a `<system-reminder>` block included, is
// never folded.

import type { Piece } from './summary.ts'
import { ELLIPSIS, cutToWidth, displayWidth } from './width.ts'

/** The engine's own components a hook message can arrive in (non-assistant rows). */
export const HOOK_COMPONENTS = ['UserMessage', 'InfoNotice'] as const

export const HOOKS_CHORD = 'ctrl+x h'
export const HOOKS_ACTION = 'settings:sortByTokens'
export const DEFAULT_FOLD_HOOKS_ABOVE = 40
export const LONG_WORDS = 80
export const DIAG_KEEP = 5
export const DIAG_HEAD = 40

// `Stop says:`, `PreToolUse:Bash hook error:`, `SessionStart hook feedback:`.
const HEAD = /^([A-Za-z]+(?::[A-Za-z0-9_.*|-]+)?) (says|hook error|hook feedback)(:?)/

export type HookMessage = {
  /** The hook event name, with its matcher when it has one (`PreToolUse:Bash`). */
  event: string
  /** The words that open the message, colon included (`Stop says:`). */
  header: string
  /** What follows the header, white space collapsed. */
  rest: string
}

export function wordCount(text: string): number {
  const t = text.trim()
  return t === '' ? 0 : t.split(/\s+/).length
}

/** The message as hook output, or null when it is not sure to be. */
export function parseHookMessage(text: string): HookMessage | null {
  if (typeof text !== 'string') return null
  const body = text.replace(/^\s+/, '')
  if (body.startsWith('<system-reminder>')) return null
  const found = HEAD.exec(body.split('\n', 1)[0] ?? '')
  if (found === null) return null
  const verb = found[2] as string
  return {
    event: found[1] as string,
    header: `${found[1]} ${verb}:`,
    rest: body.slice(found[0].length).replace(/\s+/g, ' ').trim(),
  }
}

/** The text up to the first sentence end, or all of it. */
export function firstSentence(text: string): string {
  const end = /[.!?](?=\s|$)/.exec(text)
  return end === null ? text : text.slice(0, end.index + 1)
}

/** A hook message to fold, or null: not hook output, too short, or the switch off. */
export function planHookFold(text: string, isFolded: boolean, foldAbove: number): HookMessage | null {
  if (!isFolded) return null
  const message = parseHookMessage(text)
  if (message === null) return null
  return wordCount(text) > foldAbove ? message : null
}

/**
 * The folded line: header, the first sentence cut to fit, then the words it
 * hides, `Stop says: DL-63 row ... (+412 words)`. A width of 0 means no cut.
 */
export function hookLine(message: HookMessage, totalWords: number, columns: number): Piece[] {
  const hidden = Math.max(0, totalWords - wordCount(`${message.header} ${firstSentence(message.rest)}`))
  const tail = ` (+${hidden} words)`
  const lead = `${message.header} `
  let sentence = firstSentence(message.rest)
  if (columns > 0) {
    const room = columns - displayWidth(lead) - displayWidth(tail) - 1
    if (displayWidth(sentence) > room) sentence = room > 1 ? cutToWidth(sentence, room) : ELLIPSIS
  }
  return [{ text: `${lead}${sentence}${tail}`, tone: 'dim' }]
}

export type DiagEntry = { component: string; head: string; words: number }

export type Diag = { matched: DiagEntry[]; missed: DiagEntry[] }

export const EMPTY_DIAG: Diag = { matched: [], missed: [] }

/** What the diagnostic records of one message: the component, 40 characters, the words. */
export function diagEntry(component: string, text: string): DiagEntry {
  return { component, head: text.replace(/\s+/g, ' ').trim().slice(0, DIAG_HEAD), words: wordCount(text) }
}

/**
 * The diagnostic with one message seen: a message that matched joins `matched`
 * (any length); one that did not joins `missed` only when over 80 words. The
 * last five of each are kept. The same object comes back when nothing is new.
 */
export function noteSeen(diag: Diag, component: string, text: string, isMatch: boolean): Diag {
  const entry = diagEntry(component, text)
  if (!isMatch && entry.words <= LONG_WORDS) return diag
  const list = isMatch ? diag.matched : diag.missed
  if (list.some(item => item.component === entry.component && item.head === entry.head && item.words === entry.words)) {
    return diag
  }
  const next = [...list, entry].slice(-DIAG_KEEP)
  return isMatch ? { matched: next, missed: diag.missed } : { matched: diag.matched, missed: next }
}

function diagList(list: readonly DiagEntry[]): string {
  if (list.length === 0) return 'none'
  return list.map(item => `${item.component} "${item.head}" ${item.words}w`).join('; ')
}

/** The one line `/fold-hooks diag` prints. */
export function diagSentence(diag: Diag): string {
  return `Matched (last ${DIAG_KEEP}): ${diagList(diag.matched)} | Long, not matched (last ${DIAG_KEEP}): ${diagList(diag.missed)}`
}
