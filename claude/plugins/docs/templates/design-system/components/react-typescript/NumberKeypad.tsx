// NumberKeypad (luismc-docs component template, React + TypeScript).
// For counts, measures and codes only: dates use DatePicker, times and durations use TimePicker.
// An inline 3 x 4 keypad with the value above it, Clear, and optional Cancel and Done. Put it in the
// project's one overlay component (sheet or dialog) when it should float; it builds no overlay of its own.
// Built from design tokens only: the classes are styled in number-keypad.css with var(--ds-*).
// Keyboard: digits, "." and Backspace type from anywhere inside it; arrows move between keys (one tab stop);
// Enter on a key presses it, Enter elsewhere is Done; Escape cancels.
import { useId, useRef, useState, type KeyboardEvent } from 'react';
import { commitValue, keyLayout, moveInGrid, pressKey, type KeypadKind } from './number-keypad-logic';

export interface NumberKeypadLabels {
  backspace: string;
  clear: string;
  cancel: string;
  done: string;
  empty: string;
  /** "{min}" and "{max}" are the limits, "{n}" the code length. */
  below: string;
  above: string;
  short: string;
}

export const DEFAULT_NUMBER_KEYPAD_LABELS: NumberKeypadLabels = {
  backspace: 'Delete last digit',
  clear: 'Clear',
  cancel: 'Cancel',
  done: 'Done',
  empty: 'Type a number.',
  below: 'The lowest is {min}.',
  above: 'The highest is {max}.',
  short: 'Type all {n} digits.',
};

export interface NumberKeypadProps {
  label: string;
  /** The value it opens with, as text ("12", "2.5", "0042"). The first key replaces it. */
  value?: string;
  /** Called with the committed text when Done is pressed (or Enter). */
  onDone: (value: string) => void;
  onCancel?: () => void;
  /** Called on every key with the buffer. */
  onChange?: (buffer: string) => void;
  kind?: KeypadKind;
  decimals?: number;
  min?: number;
  max?: number;
  maxLength?: number;
  /** A unit after the value, such as "kg". */
  unit?: string;
  labels?: Partial<NumberKeypadLabels>;
}

export function NumberKeypad({
  label, value = '', onDone, onCancel, onChange, kind = 'number', decimals = 0, min, max, maxLength, unit, labels,
}: NumberKeypadProps) {
  const words = { ...DEFAULT_NUMBER_KEYPAD_LABELS, ...labels };
  const opts = { kind, decimals, min, max, maxLength };
  const id = useId();
  const [buffer, setBuffer] = useState(value);
  const typed = useRef(false);
  const [focusIndex, setFocusIndex] = useState(0);
  const keyRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const layout = keyLayout(opts);
  const result = commitValue(buffer, opts);

  const press = (key: string) => {
    // The first key after opening replaces a prefilled value, as a native field does.
    const base = typed.current || key === 'Backspace' ? buffer : '';
    typed.current = true;
    const next = pressKey(base, key, opts);
    setBuffer(next);
    onChange?.(next);
  };

  const done = () => {
    if (result.ok) onDone(result.value);
  };

  const onRootKey = (e: KeyboardEvent<HTMLDivElement>) => {
    const target = e.target as HTMLElement;
    const onKey = target.dataset.keypadKey !== undefined;
    if (e.key === 'Escape' && onCancel) {
      e.preventDefault();
      onCancel();
    } else if (e.key === 'Enter') {
      if (onKey) return; // the focused key's own click presses it
      e.preventDefault();
      done();
    } else if (/^[0-9]$/.test(e.key) || e.key === '.' || e.key === ',' || e.key === 'Backspace' || e.key === 'Delete') {
      e.preventDefault();
      press(e.key);
    } else if (onKey) {
      const next = moveInGrid(focusIndex, e.key, layout);
      if (next === null) return;
      e.preventDefault();
      setFocusIndex(next);
      keyRefs.current[next]?.focus();
    }
  };

  const reason = result.ok ? '' : reasonText(result.reason);
  function reasonText(r: 'empty' | 'below' | 'above' | 'short') {
    return words[r].replace('{min}', String(min ?? '')).replace('{max}', String(max ?? '')).replace('{n}', String(maxLength ?? ''));
  }
  const labelId = `${id}-label`;
  const reasonId = `${id}-reason`;

  return (
    <div className="ds-keypad" role="group" aria-labelledby={labelId} onKeyDown={onRootKey}>
      <span id={labelId} className="ds-keypad__label">{label}</span>
      <output className="ds-keypad__display" aria-live="polite" aria-labelledby={labelId} data-kind={kind}>
        <span className="ds-keypad__digits">{buffer === '' ? (kind === 'code' ? '' : '0') : buffer}</span>
        {unit && <span className="ds-keypad__unit">{unit}</span>}
      </output>

      <div className="ds-keypad__keys">
        {layout.map((key, i) =>
          key === null ? (
            <span key={`blank-${i}`} className="ds-keypad__blank" aria-hidden="true" />
          ) : (
            <button
              key={key}
              ref={(el) => { keyRefs.current[i] = el; }}
              type="button"
              data-keypad-key={key}
              className={key === 'Backspace' ? 'ds-keypad__key ds-keypad__key--action' : 'ds-keypad__key'}
              tabIndex={i === focusIndex ? 0 : -1}
              aria-label={key === 'Backspace' ? words.backspace : undefined}
              onFocus={() => setFocusIndex(i)}
              onClick={() => press(key)}
            >
              {key === 'Backspace' ? <span aria-hidden="true">⌫</span> : key}
            </button>
          ),
        )}
      </div>

      <p id={reasonId} className="ds-keypad__reason" aria-live="polite">{reason}</p>

      <div className="ds-keypad__actions">
        <button type="button" className="ds-keypad__action ds-keypad__action--quiet" onClick={() => press('Clear')}>
          {words.clear}
        </button>
        {onCancel && (
          <button type="button" className="ds-keypad__action ds-keypad__action--secondary" onClick={onCancel}>
            {words.cancel}
          </button>
        )}
        <button type="button" className="ds-keypad__action ds-keypad__action--primary"
          disabled={!result.ok} aria-describedby={reason ? reasonId : undefined} onClick={done}>
          {words.done}
        </button>
      </div>
    </div>
  );
}
