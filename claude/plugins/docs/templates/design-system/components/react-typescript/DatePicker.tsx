// DatePicker (luismc-docs component template, React + TypeScript).
// A month grid with month and year selects, previous and next month buttons, and a typed entry.
// Built from design tokens only: the classes are styled in date-picker.css with var(--ds-*).
// Keyboard (WAI-ARIA APG date picker): the grid is one tab stop; arrows move a day or a week,
// Home/End go to the start or end of the week, Page Up/Down change the month (with Shift the year),
// Enter or Space picks the focused day, Escape cancels.
import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent } from 'react';
import {
  clampDay, compare, formatLong, formatTyped, gridKey, isOutOfRange, monthGrid, monthNames, parseIso,
  parseTyped, todayDay, toIso, typedPattern, weekdayNames, yearRange, type Day, type WeekStart,
} from './date-picker-logic';
import { Chevron } from './PickerIcon';

export interface DatePickerLabels {
  previousMonth: string;
  nextMonth: string;
  month: string;
  year: string;
  typed: string;
  /** Shown when the typed text is not a date. {pattern} is the locale's pattern. */
  notADate: string;
  /** Shown when the typed date is outside min and max. {min} and {max} are long dates. */
  outOfRange: string;
}

export const DEFAULT_DATE_PICKER_LABELS: DatePickerLabels = {
  previousMonth: 'Previous month',
  nextMonth: 'Next month',
  month: 'Month',
  year: 'Year',
  typed: 'Or type the date',
  notADate: 'Type the date as {pattern}.',
  outOfRange: 'Pick a date from {min} to {max}.',
};

export interface DatePickerProps {
  /** The field name, shown above the picker and used as its accessible name. */
  label: string;
  /** The chosen day as ISO "YYYY-MM-DD", or null. */
  value: string | null;
  /** Called with the ISO day when a day is picked or a valid date is typed. */
  onChange: (iso: string) => void;
  /** Called on Escape. */
  onCancel?: () => void;
  /** Earliest and latest day, ISO. Days outside are disabled; keys and typing never leave the range. */
  min?: string;
  max?: string;
  /** BCP 47 locale for names, order and the typed pattern. Default: the runtime's. */
  locale?: string;
  /** 1 Monday (default), 0 Sunday. */
  weekStart?: WeekStart;
  /** The day shown and focused when there is no value. Default: today. */
  initialFocus?: string;
  /** How the chosen day is shown in the header. Default: the locale's long date ("14 March 2009").
   * Pass the project's one date formatter here so the picker matches every other screen. */
  formatValue?: (iso: string) => string;
  labels?: Partial<DatePickerLabels>;
}

export function DatePicker({
  label, value, onChange, onCancel, min, max, locale, weekStart = 1, initialFocus, formatValue, labels,
}: DatePickerProps) {
  const words = { ...DEFAULT_DATE_PICKER_LABELS, ...labels };
  const id = useId();
  const minDay = parseIso(min);
  const maxDay = parseIso(max);
  const selected = parseIso(value);
  const today = useMemo(() => todayDay(), []);
  const start = clampDay(selected ?? parseIso(initialFocus) ?? today, minDay, maxDay);

  const [focus, setFocus] = useState<Day>(start);
  const [text, setText] = useState(selected ? formatTyped(selected, locale) : '');
  const [error, setError] = useState<string | null>(null);
  const moveFocus = useRef(false);
  const gridRef = useRef<HTMLTableElement>(null);

  // A new value from outside moves the view and the typed text with it.
  useEffect(() => {
    const day = parseIso(value);
    if (day) {
      setFocus(clampDay(day, minDay, maxDay));
      setText(formatTyped(day, locale));
      setError(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);

  useEffect(() => {
    if (!moveFocus.current) return;
    moveFocus.current = false;
    gridRef.current?.querySelector<HTMLButtonElement>('button[tabindex="0"]')?.focus();
  }, [focus]);

  const months = monthNames(locale);
  const years = yearRange(minDay, maxDay, today);
  const days = weekdayNames(locale, weekStart);
  const weeks = monthGrid(focus.y, focus.m, weekStart);
  const firstOfView: Day = { y: focus.y, m: focus.m, d: 1 };
  const lastOfView: Day = { y: focus.y, m: focus.m, d: weeks.flat().filter(Boolean).length };
  const prevDisabled = Boolean(minDay && compare(firstOfView, minDay) <= 0);
  const nextDisabled = Boolean(maxDay && compare(lastOfView, maxDay) >= 0);

  const pick = (day: Day) => {
    if (isOutOfRange(day, minDay, maxDay)) return;
    setFocus(day);
    setText(formatTyped(day, locale));
    setError(null);
    onChange(toIso(day));
  };

  const showMonth = (y: number, m: number) => {
    setFocus(clampDay({ y, m, d: Math.min(focus.d, new Date(Date.UTC(y, m, 0)).getUTCDate()) }, minDay, maxDay));
  };

  const onGridKey = (e: KeyboardEvent<HTMLTableElement>) => {
    const next = gridKey(focus, { key: e.key, shiftKey: e.shiftKey }, { min: minDay, max: maxDay, weekStart });
    if (!next) return;
    e.preventDefault();
    moveFocus.current = true;
    setFocus(next);
  };

  const commitText = () => {
    if (text.trim() === '') {
      setError(null);
      return;
    }
    const day = parseTyped(text, locale);
    if (!day) {
      setError(words.notADate.replace('{pattern}', typedPattern(locale)));
      return;
    }
    if (isOutOfRange(day, minDay, maxDay)) {
      setError(words.outOfRange
        .replace('{min}', minDay ? formatLong(minDay, locale) : '')
        .replace('{max}', maxDay ? formatLong(maxDay, locale) : ''));
      return;
    }
    pick(day);
  };

  const onRootKey = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key === 'Escape' && onCancel) {
      e.preventDefault();
      onCancel();
    }
  };

  const labelId = `${id}-label`;
  const captionId = `${id}-caption`;
  const typedId = `${id}-typed`;
  const errorId = `${id}-error`;
  const hintId = `${id}-hint`;
  const selectedDay = selected;

  return (
    <div className="ds-datepicker" role="group" aria-labelledby={labelId} onKeyDown={onRootKey}>
      <div className="ds-datepicker__header">
        <span id={labelId} className="ds-datepicker__label">{label}</span>
        <span className="ds-datepicker__value" aria-live="polite">{selectedDay ? (formatValue ? formatValue(toIso(selectedDay)) : formatLong(selectedDay, locale)) : ''}</span>
      </div>

      <div className="ds-datepicker__nav">
        <button type="button" className="ds-datepicker__step" aria-label={words.previousMonth}
          disabled={prevDisabled} onClick={() => showMonth(...ym(focus.y, focus.m - 1))}>
          <Chevron dir="left" />
        </button>
        <select className="ds-datepicker__select" aria-label={words.month} value={focus.m}
          onChange={(e) => showMonth(focus.y, Number(e.target.value))}>
          {months.map((name, i) => (
            <option key={name} value={i + 1}
              disabled={monthOut(focus.y, i + 1, minDay, maxDay)}>{name}</option>
          ))}
        </select>
        <select className="ds-datepicker__select" aria-label={words.year} value={focus.y}
          onChange={(e) => showMonth(Number(e.target.value), focus.m)}>
          {years.map((y) => <option key={y} value={y}>{y}</option>)}
        </select>
        <button type="button" className="ds-datepicker__step" aria-label={words.nextMonth}
          disabled={nextDisabled} onClick={() => showMonth(...ym(focus.y, focus.m + 1))}>
          <Chevron dir="right" />
        </button>
      </div>

      <table className="ds-datepicker__grid" role="grid" aria-labelledby={captionId} ref={gridRef} onKeyDown={onGridKey}>
        <caption id={captionId} className="ds-datepicker__caption">{`${months[focus.m - 1]} ${focus.y}`}</caption>
        <thead>
          <tr>
            {days.map((d) => <th key={d.long} scope="col" abbr={d.long}>{d.short}</th>)}
          </tr>
        </thead>
        <tbody>
          {weeks.map((week, wi) => (
            <tr key={wi}>
              {week.map((day, di) => {
                if (!day) return <td key={di} className="ds-datepicker__blank" />;
                const isFocus = compare(day, focus) === 0;
                const isSelected = Boolean(selectedDay && compare(day, selectedDay) === 0);
                const out = isOutOfRange(day, minDay, maxDay);
                return (
                  <td key={di} role="gridcell" aria-selected={isSelected}>
                    <button
                      type="button"
                      className="ds-datepicker__day"
                      tabIndex={isFocus ? 0 : -1}
                      aria-label={`${days[di].long} ${formatLong(day, locale)}`}
                      aria-current={compare(day, today) === 0 ? 'date' : undefined}
                      aria-disabled={out || undefined}
                      data-selected={isSelected || undefined}
                      onClick={() => pick(day)}
                      onFocus={() => { if (!isFocus) setFocus(day); }}
                    >
                      {day.d}
                    </button>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>

      <div className="ds-datepicker__typed">
        <label htmlFor={typedId} className="ds-datepicker__typed-label">{words.typed}</label>
        <span id={hintId} className="ds-datepicker__hint">{typedPattern(locale)}</span>
        <input
          id={typedId}
          className="ds-datepicker__input"
          type="text"
          inputMode="numeric"
          autoComplete="off"
          value={text}
          aria-describedby={error ? `${hintId} ${errorId}` : hintId}
          aria-invalid={error ? true : undefined}
          onChange={(e) => setText(e.target.value)}
          onBlur={commitText}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault();
              commitText();
            }
          }}
        />
        {error && <p id={errorId} className="ds-datepicker__error" role="alert">{error}</p>}
      </div>
    </div>
  );
}

function ym(y: number, m: number): [number, number] {
  const i = y * 12 + (m - 1);
  return [Math.floor(i / 12), (i % 12) + 1];
}

function monthOut(y: number, m: number, min: Day | null, max: Day | null): boolean {
  const last = new Date(Date.UTC(y, m, 0)).getUTCDate();
  return Boolean((min && compare({ y, m, d: last }, min) < 0) || (max && compare({ y, m, d: 1 }, max) > 0));
}
