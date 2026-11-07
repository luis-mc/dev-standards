// Time picker logic (luismc-docs component template). Pure functions, no DOM.
// The value is always 24-hour: "HH", "HH:MM" or "HH:MM:SS" by units. 12-hour is display only.

export type TimeUnits = 'h' | 'hm' | 'hms';
export type Unit = 'h' | 'm' | 's';
export type HourCycle = 'h23' | 'h12';

export interface TimeParts {
  h: number;
  m: number;
  s: number;
}

export const UNIT_MAX: Record<Unit, number> = { h: 23, m: 59, s: 59 };
/** Page Up/Down step: 3 hours, 15 minutes or 15 seconds. */
export const UNIT_BIG: Record<Unit, number> = { h: 3, m: 15, s: 15 };

export function unitsOf(units: TimeUnits): Unit[] {
  return units.split('') as Unit[];
}

const pad = (n: number) => String(n).padStart(2, '0');

export function parseTime(text: string | null | undefined, units: TimeUnits): TimeParts | null {
  const re = { h: /^(\d{2})$/, hm: /^(\d{2}):(\d{2})$/, hms: /^(\d{2}):(\d{2}):(\d{2})$/ }[units];
  const m = re.exec(text ?? '');
  if (!m) return null;
  const parts = { h: Number(m[1]), m: Number(m[2] ?? 0), s: Number(m[3] ?? 0) };
  if (parts.h > 23 || parts.m > 59 || parts.s > 59) return null;
  return parts;
}

export function formatTime(parts: TimeParts, units: TimeUnits): string {
  return unitsOf(units).map((u) => pad(parts[u])).join(':');
}

/**
 * The next value of one spin button after a key (WAI-ARIA APG spinbutton), or null for a key it does not handle.
 * Up/Down step by `step` and wrap (23 -> 00); a value off the step grid snaps to the next step.
 * Page Up/Down step by `big` and wrap. Home/End go to 0 and the last value on the step grid.
 */
export function spinKey(value: number, key: string, opts: { max: number; step?: number; big?: number }): number | null {
  const step = Math.max(1, opts.step ?? 1);
  const size = opts.max + 1;
  const top = opts.max - (opts.max % step);
  const big = Math.max(step, Math.round((opts.big ?? step) / step) * step);
  const wrap = (n: number) => ((n % size) + size) % size;
  switch (key) {
    case 'ArrowUp': {
      const next = Math.floor(value / step) * step + step;
      return next > top ? 0 : next;
    }
    case 'ArrowDown': {
      const next = Math.ceil(value / step) * step - step;
      return next < 0 ? top : next;
    }
    case 'PageUp': return snap(wrap(value + big), step, top);
    case 'PageDown': return snap(wrap(value - big), step, top);
    case 'Home': return 0;
    case 'End': return top;
    default: return null;
  }
}

function snap(n: number, step: number, top: number): number {
  return Math.min(top, Math.round(n / step) * step);
}

/** 24-hour hour to the 12-hour clock: 0 -> 12 AM, 13 -> 1 PM. */
export function to12(h: number): { h: number; pm: boolean } {
  return { h: h % 12 === 0 ? 12 : h % 12, pm: h >= 12 };
}

export function from12(h12: number, pm: boolean): number {
  return (h12 % 12) + (pm ? 12 : 0);
}

/** 24-hour by default; 12-hour when the locale's clock is 12-hour (D51). */
export function hourCycleFor(locale?: string): HourCycle {
  try {
    const cycle = new Intl.DateTimeFormat(locale, { hour: 'numeric' }).resolvedOptions().hourCycle;
    return cycle === 'h11' || cycle === 'h12' ? 'h12' : 'h23';
  } catch {
    return 'h23';
  }
}

/** Day period words of the locale, such as ["AM", "PM"]. */
export function dayPeriods(locale?: string): [string, string] {
  const f = new Intl.DateTimeFormat(locale, { hour: 'numeric', hourCycle: 'h12', timeZone: 'UTC' });
  const word = (h: number) => f.formatToParts(new Date(Date.UTC(2009, 2, 14, h))).find((p) => p.type === 'dayPeriod')?.value;
  return [word(9) ?? 'AM', word(21) ?? 'PM'];
}
