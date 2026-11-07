// Number keypad logic (luismc-docs component template). Pure functions, no DOM.
// The buffer is the typed text. A count or a measure is a number; a code keeps its leading zeros.

export type KeypadKind = 'number' | 'code';

export interface KeypadOptions {
  kind?: KeypadKind;
  /** Digits after the decimal point; 0 (default) has no "." key. Ignored for a code. */
  decimals?: number;
  /** Lowest and highest number (kind "number"). */
  min?: number;
  max?: number;
  /** Longest buffer. For a code it is also the exact length Done needs. */
  maxLength?: number;
}

export type KeypadKey = '0' | '1' | '2' | '3' | '4' | '5' | '6' | '7' | '8' | '9' | '.' | 'Backspace' | 'Clear';

/** The keys in grid order, 3 across and 4 down. The "." cell is empty when there are no decimals. */
export function keyLayout(opts: KeypadOptions): (KeypadKey | null)[] {
  const dot = (opts.kind ?? 'number') === 'number' && (opts.decimals ?? 0) > 0;
  return ['1', '2', '3', '4', '5', '6', '7', '8', '9', dot ? '.' : null, '0', 'Backspace'];
}

/**
 * The buffer after one key. A key that would break a limit is refused (the buffer stays as it was):
 * a second ".", a digit past the decimals, past maxLength, or one that takes a number above max
 * (when min is 0 or more, a longer number only grows).
 */
export function pressKey(buffer: string, key: string, opts: KeypadOptions = {}): string {
  const kind = opts.kind ?? 'number';
  const decimals = kind === 'code' ? 0 : Math.max(0, opts.decimals ?? 0);
  if (key === 'Backspace') return buffer.slice(0, -1);
  if (key === 'Clear' || key === 'Delete') return '';
  if (key === '.' || key === ',') {
    if (decimals === 0 || buffer.includes('.')) return buffer;
    return within(buffer === '' ? '0.' : buffer + '.', opts) ? (buffer === '' ? '0.' : buffer + '.') : buffer;
  }
  if (!/^[0-9]$/.test(key)) return buffer;
  const dot = buffer.indexOf('.');
  if (dot !== -1 && buffer.length - dot - 1 >= decimals) return buffer;
  // A number drops a leading zero ("0" then "7" is "7"); a code keeps it.
  const next = kind === 'number' && buffer === '0' ? key : buffer + key;
  return within(next, opts) ? next : buffer;
}

function within(next: string, opts: KeypadOptions): boolean {
  if (opts.maxLength !== undefined && next.length > opts.maxLength) return false;
  if ((opts.kind ?? 'number') === 'number' && opts.max !== undefined && (opts.min ?? 0) >= 0) {
    const n = Number(next);
    if (Number.isFinite(n) && n > opts.max) return false;
  }
  return true;
}

export type CommitResult =
  | { ok: true; value: string }
  | { ok: false; reason: 'empty' | 'below' | 'above' | 'short' };

/** Whether Done may commit the buffer, and the committed text ("12.50" stays as typed; "7." becomes "7"). */
export function commitValue(buffer: string, opts: KeypadOptions = {}): CommitResult {
  const kind = opts.kind ?? 'number';
  if (buffer === '' || buffer === '.') return { ok: false, reason: 'empty' };
  if (kind === 'code') {
    if (opts.maxLength !== undefined && buffer.length < opts.maxLength) return { ok: false, reason: 'short' };
    return { ok: true, value: buffer };
  }
  const value = buffer.endsWith('.') ? buffer.slice(0, -1) : buffer;
  const n = Number(value);
  if (opts.min !== undefined && n < opts.min) return { ok: false, reason: 'below' };
  if (opts.max !== undefined && n > opts.max) return { ok: false, reason: 'above' };
  return { ok: true, value };
}

/** The key index an arrow moves to in the 3 x 4 grid, skipping empty cells; null for another key. */
export function moveInGrid(index: number, key: string, layout: (KeypadKey | null)[]): number | null {
  const delta = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -3, ArrowDown: 3 }[key];
  if (key === 'Home') return layout.findIndex(Boolean);
  if (key === 'End') return layout.length - 1 - [...layout].reverse().findIndex(Boolean);
  if (delta === undefined) return null;
  let i = index + delta;
  while (i >= 0 && i < layout.length) {
    const sameRow = Math.abs(delta) === 1 ? Math.floor(i / 3) === Math.floor(index / 3) : true;
    if (!sameRow) return index;
    if (layout[i]) return i;
    i += delta;
  }
  return index;
}
