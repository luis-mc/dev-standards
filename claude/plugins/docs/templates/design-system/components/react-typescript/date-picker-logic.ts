// Date picker logic (luismc-docs component template). Pure functions, no DOM.
// A date is a plain calendar day { y, m, d } with m 1-12: no time zone, no Date drift.

export interface Day {
  y: number;
  m: number;
  d: number;
}

export type WeekStart = 0 | 1; // 0 Sunday, 1 Monday

export function daysInMonth(y: number, m: number): number {
  return new Date(Date.UTC(y, m, 0)).getUTCDate();
}

export function isValidDay(day: Day): boolean {
  return (
    Number.isInteger(day.y) && Number.isInteger(day.m) && Number.isInteger(day.d) &&
    day.y >= 1 && day.y <= 9999 && day.m >= 1 && day.m <= 12 && day.d >= 1 && day.d <= daysInMonth(day.y, day.m)
  );
}

export function parseIso(text: string | null | undefined): Day | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(text ?? '');
  if (!m) return null;
  const day = { y: Number(m[1]), m: Number(m[2]), d: Number(m[3]) };
  return isValidDay(day) ? day : null;
}

const pad = (n: number, w = 2) => String(n).padStart(w, '0');

export function toIso(day: Day): string {
  return `${pad(day.y, 4)}-${pad(day.m)}-${pad(day.d)}`;
}

export function compare(a: Day, b: Day): number {
  return a.y - b.y || a.m - b.m || a.d - b.d;
}

/** Day of the week, 0 Sunday to 6 Saturday. */
export function weekday(day: Day): number {
  return new Date(Date.UTC(day.y, day.m - 1, day.d)).getUTCDay();
}

export function addDays(day: Day, n: number): Day {
  const t = new Date(Date.UTC(day.y, day.m - 1, day.d + n));
  return { y: t.getUTCFullYear(), m: t.getUTCMonth() + 1, d: t.getUTCDate() };
}

/** Move by whole months; the day is kept, or clamped to the last day of a shorter month. */
export function addMonths(day: Day, n: number): Day {
  const index = day.y * 12 + (day.m - 1) + n;
  const y = Math.floor(index / 12);
  const m = (index % 12) + 1;
  return { y, m, d: Math.min(day.d, daysInMonth(y, m)) };
}

export function clampDay(day: Day, min: Day | null, max: Day | null): Day {
  if (min && compare(day, min) < 0) return min;
  if (max && compare(day, max) > 0) return max;
  return day;
}

export function isOutOfRange(day: Day, min: Day | null, max: Day | null): boolean {
  return Boolean((min && compare(day, min) < 0) || (max && compare(day, max) > 0));
}

/** The weeks of a month, each 7 cells; a cell outside the month is null. */
export function monthGrid(y: number, m: number, weekStart: WeekStart): (Day | null)[][] {
  const lead = (weekday({ y, m, d: 1 }) - weekStart + 7) % 7;
  const cells: (Day | null)[] = Array.from({ length: lead }, () => null);
  for (let d = 1; d <= daysInMonth(y, m); d++) cells.push({ y, m, d });
  while (cells.length % 7) cells.push(null);
  const weeks: (Day | null)[][] = [];
  for (let i = 0; i < cells.length; i += 7) weeks.push(cells.slice(i, i + 7));
  return weeks;
}

export interface GridKey {
  key: string;
  shiftKey?: boolean;
}

/**
 * The day that a key moves the focus to in the day grid (WAI-ARIA APG date picker),
 * clamped to min and max; null for a key the grid does not handle.
 * Arrows: a day or a week. Home/End: start or end of the week. Page Up/Down: a month, with Shift a year.
 */
export function gridKey(
  focus: Day,
  e: GridKey,
  opts: { min?: Day | null; max?: Day | null; weekStart?: WeekStart } = {},
): Day | null {
  const ws = opts.weekStart ?? 1;
  const back = (weekday(focus) - ws + 7) % 7;
  let next: Day;
  switch (e.key) {
    case 'ArrowLeft': next = addDays(focus, -1); break;
    case 'ArrowRight': next = addDays(focus, 1); break;
    case 'ArrowUp': next = addDays(focus, -7); break;
    case 'ArrowDown': next = addDays(focus, 7); break;
    case 'Home': next = addDays(focus, -back); break;
    case 'End': next = addDays(focus, 6 - back); break;
    case 'PageUp': next = addMonths(focus, e.shiftKey ? -12 : -1); break;
    case 'PageDown': next = addMonths(focus, e.shiftKey ? 12 : 1); break;
    default: return null;
  }
  return clampDay(next, opts.min ?? null, opts.max ?? null);
}

/** The order of day, month and year in the locale's numeric date, such as ['d', 'm', 'y']. */
export function fieldOrder(locale?: string): ('d' | 'm' | 'y')[] {
  const parts = new Intl.DateTimeFormat(locale, { day: '2-digit', month: '2-digit', year: 'numeric', timeZone: 'UTC' })
    .formatToParts(new Date(Date.UTC(2009, 2, 14)));
  const order: ('d' | 'm' | 'y')[] = [];
  for (const p of parts) {
    if (p.type === 'day') order.push('d');
    if (p.type === 'month') order.push('m');
    if (p.type === 'year') order.push('y');
  }
  return order.length === 3 ? order : ['d', 'm', 'y'];
}

/** The typed-entry hint for the locale, such as "DD/MM/YYYY". */
export function typedPattern(locale?: string): string {
  const word = { d: 'DD', m: 'MM', y: 'YYYY' } as const;
  const sep = fieldOrder(locale)[0] === 'y' ? '-' : '/';
  return fieldOrder(locale).map((k) => word[k]).join(sep);
}

/**
 * Read a typed date: ISO "2009-03-14", or three numbers in the locale's order separated by
 * "/", ".", "-" or a space ("14/03/2009", "3.14.2009"). A two-digit year is refused. Null when not a real day.
 */
export function parseTyped(text: string, locale?: string): Day | null {
  const t = text.trim();
  const iso = parseIso(t);
  if (iso) return iso;
  const bits = t.split(/[\s./-]+/).filter(Boolean);
  if (bits.length !== 3 || bits.some((b) => !/^\d+$/.test(b))) return null;
  const order = fieldOrder(locale);
  const got: Record<string, string> = {};
  order.forEach((k, i) => (got[k] = bits[i] ?? ''));
  if (got['y']?.length !== 4) return null;
  const day = { y: Number(got['y']), m: Number(got['m']), d: Number(got['d']) };
  return isValidDay(day) ? day : null;
}

export function formatLong(day: Day, locale?: string): string {
  return new Intl.DateTimeFormat(locale, { day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC' })
    .format(new Date(Date.UTC(day.y, day.m - 1, day.d)));
}

export function formatTyped(day: Day, locale?: string): string {
  const val = { d: pad(day.d), m: pad(day.m), y: pad(day.y, 4) } as const;
  const order = fieldOrder(locale);
  return order.map((k) => val[k]).join(order[0] === 'y' ? '-' : '/');
}

export function monthNames(locale?: string): string[] {
  const f = new Intl.DateTimeFormat(locale, { month: 'long', timeZone: 'UTC' });
  return Array.from({ length: 12 }, (_, i) => f.format(new Date(Date.UTC(2009, i, 1))));
}

/** Short and long weekday names in grid order. */
export function weekdayNames(locale: string | undefined, weekStart: WeekStart): { short: string; long: string }[] {
  const s = new Intl.DateTimeFormat(locale, { weekday: 'short', timeZone: 'UTC' });
  const l = new Intl.DateTimeFormat(locale, { weekday: 'long', timeZone: 'UTC' });
  // 2009-03-01 was a Sunday.
  return Array.from({ length: 7 }, (_, i) => {
    const t = new Date(Date.UTC(2009, 2, 1 + ((i + weekStart) % 7)));
    return { short: s.format(t), long: l.format(t) };
  });
}

/** The years the year select offers: min to max, or a default window around today. */
export function yearRange(min: Day | null, max: Day | null, today: Day): number[] {
  const from = min?.y ?? today.y - 120;
  const to = max?.y ?? today.y + 10;
  return Array.from({ length: Math.max(0, to - from + 1) }, (_, i) => from + i);
}

export function todayDay(now: Date = new Date()): Day {
  return { y: now.getFullYear(), m: now.getMonth() + 1, d: now.getDate() };
}
