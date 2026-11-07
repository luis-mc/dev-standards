// TimePicker (luismc-docs component template, React + TypeScript).
// One spin button per unit: hours only (units="h"), hours and minutes ("hm"), or hours, minutes and seconds ("hms").
// 24-hour by default; a 12-hour locale (or hourCycle="h12") adds an AM/PM switch after the last column (D51).
// Built from design tokens only: the classes are styled in time-picker.css with var(--ds-*).
// Keyboard (WAI-ARIA APG spinbutton): Up/Down step and wrap, Page Up/Down take a bigger step,
// Home/End go to the lowest or highest value, Left/Right move between columns, Enter is Done, Escape cancels.
import { useId, useRef, type KeyboardEvent } from 'react';
import { Chevron } from './PickerIcon';
import {
  dayPeriods, formatTime, from12, hourCycleFor, parseTime, spinKey, to12, UNIT_BIG, UNIT_MAX, unitsOf,
  type HourCycle, type TimeParts, type TimeUnits, type Unit,
} from './time-picker-logic';

export interface TimePickerLabels {
  hours: string;
  minutes: string;
  seconds: string;
  increase: string; // "{unit}" is the unit name
  decrease: string;
  period: string;
  quickPicks: string;
  /** aria-valuetext per unit; "{n}" is the number. */
  hoursText: string;
  minutesText: string;
  secondsText: string;
}

export const DEFAULT_TIME_PICKER_LABELS: TimePickerLabels = {
  hours: 'Hours',
  minutes: 'Minutes',
  seconds: 'Seconds',
  increase: 'More {unit}',
  decrease: 'Fewer {unit}',
  period: 'Morning or afternoon',
  quickPicks: 'Quick picks',
  hoursText: '{n} hours',
  minutesText: '{n} minutes',
  secondsText: '{n} seconds',
};

export interface QuickPick {
  /** The value it sets, in the picker's format ("07:00"). */
  value: string;
  /** The words on the chip. Default: the value. */
  label?: string;
}

export interface TimePickerProps {
  label: string;
  /** "HH", "HH:MM" or "HH:MM:SS" (24-hour) by units, or null (shown as 00). */
  value: string | null;
  onChange: (value: string) => void;
  units?: TimeUnits;
  /** The minute and second step, such as 5. Hours always step by 1. */
  step?: number;
  /** Override the locale's clock. */
  hourCycle?: HourCycle;
  locale?: string;
  quick?: QuickPick[];
  /** Enter. */
  onDone?: (value: string) => void;
  /** Escape. */
  onCancel?: () => void;
  labels?: Partial<TimePickerLabels>;
}

export function TimePicker({
  label, value, onChange, units = 'hm', step = 1, hourCycle, locale, quick, onDone, onCancel, labels,
}: TimePickerProps) {
  const words = { ...DEFAULT_TIME_PICKER_LABELS, ...labels };
  const id = useId();
  const cycle = hourCycle ?? hourCycleFor(locale);
  const parts: TimeParts = parseTime(value, units) ?? { h: 0, m: 0, s: 0 };
  const current = formatTime(parts, units);
  const cols = unitsOf(units);
  const refs = useRef<(HTMLDivElement | null)[]>([]);
  const [am, pm] = dayPeriods(locale);
  const isPm = parts.h >= 12;

  const set = (next: TimeParts) => {
    const v = formatTime(next, units);
    if (v !== current) onChange(v);
  };

  const unitName = (u: Unit) => ({ h: words.hours, m: words.minutes, s: words.seconds })[u];
  const unitStep = (u: Unit) => (u === 'h' ? 1 : step);

  // The hour column on a 12-hour clock spins 1..12 within the chosen period.
  const spin = (u: Unit, key: string): number | null => {
    if (u === 'h' && cycle === 'h12') {
      const k = to12(parts.h).h; // 1..12
      const r = spinKey(k - 1, key, { max: 11, step: 1, big: UNIT_BIG.h });
      return r === null ? null : from12((r + 1) % 12, isPm);
    }
    return spinKey(parts[u], key, { max: UNIT_MAX[u], step: unitStep(u), big: UNIT_BIG[u] });
  };

  const onSpinKey = (u: Unit, i: number) => (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
      const j = i + (e.key === 'ArrowLeft' ? -1 : 1);
      if (j >= 0 && j < cols.length) {
        e.preventDefault();
        refs.current[j]?.focus();
      }
      return;
    }
    const n = spin(u, e.key);
    if (n === null) return;
    e.preventDefault();
    set({ ...parts, [u]: n });
  };

  const onRootKey = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key === 'Escape' && onCancel) {
      e.preventDefault();
      onCancel();
    } else if (e.key === 'Enter' && onDone && (e.target as HTMLElement).getAttribute('role') === 'spinbutton') {
      e.preventDefault();
      onDone(current);
    }
  };

  const shown = (u: Unit) => (u === 'h' && cycle === 'h12' ? to12(parts.h).h : parts[u]);
  const valueText = (u: Unit) =>
    ({ h: words.hoursText, m: words.minutesText, s: words.secondsText })[u].replace('{n}', String(shown(u)));
  const labelId = `${id}-label`;

  return (
    <div className="ds-timepicker" role="group" aria-labelledby={labelId} onKeyDown={onRootKey}>
      <div className="ds-timepicker__header">
        <span id={labelId} className="ds-timepicker__label">{label}</span>
        <span className="ds-timepicker__value" aria-live="polite">
          {cycle === 'h12' ? `${pad2(to12(parts.h).h)}${current.slice(2)} ${isPm ? pm : am}` : current}
        </span>
      </div>

      <div className="ds-timepicker__columns">
        {cols.map((u, i) => (
          <div key={u} className="ds-timepicker__column">
            {i > 0 && <span className="ds-timepicker__sep" aria-hidden="true">:</span>}
            <div className="ds-timepicker__spin">
              <button type="button" tabIndex={-1} className="ds-timepicker__key"
                aria-label={words.increase.replace('{unit}', unitName(u).toLowerCase())}
                onClick={() => { const n = spin(u, 'ArrowUp'); if (n !== null) set({ ...parts, [u]: n }); }}>
                <Chevron dir="up" />
              </button>
              <div
                ref={(el) => { refs.current[i] = el; }}
                role="spinbutton"
                tabIndex={0}
                className="ds-timepicker__number"
                aria-label={unitName(u)}
                aria-valuenow={shown(u)}
                aria-valuemin={u === 'h' && cycle === 'h12' ? 1 : 0}
                aria-valuemax={u === 'h' && cycle === 'h12' ? 12 : UNIT_MAX[u]}
                aria-valuetext={valueText(u)}
                onKeyDown={onSpinKey(u, i)}
              >
                {pad2(shown(u))}
              </div>
              <button type="button" tabIndex={-1} className="ds-timepicker__key"
                aria-label={words.decrease.replace('{unit}', unitName(u).toLowerCase())}
                onClick={() => { const n = spin(u, 'ArrowDown'); if (n !== null) set({ ...parts, [u]: n }); }}>
                <Chevron dir="down" />
              </button>
            </div>
          </div>
        ))}
        {cycle === 'h12' && (
          <div className="ds-timepicker__period" role="group" aria-label={words.period}>
            {[false, true].map((p) => (
              <button key={String(p)} type="button" className="ds-timepicker__period-option" aria-pressed={isPm === p}
                onClick={() => set({ ...parts, h: from12(to12(parts.h).h % 12, p) })}>
                {p ? pm : am}
              </button>
            ))}
          </div>
        )}
      </div>

      {quick && quick.length > 0 && (
        <div className="ds-timepicker__quick" role="group" aria-label={words.quickPicks}>
          {quick.map((q) => {
            const qp = parseTime(q.value, units);
            return (
              <button key={q.value} type="button" className="ds-timepicker__chip" disabled={!qp}
                aria-pressed={q.value === current} onClick={() => qp && set(qp)}>
                {q.label ?? q.value}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

function pad2(n: number) {
  return String(n).padStart(2, '0');
}
