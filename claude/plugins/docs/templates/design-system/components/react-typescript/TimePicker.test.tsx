// @vitest-environment jsdom
// TimePicker template tests (luismc-docs): keyboard, value and limits, for h, hm and hms.
import { useState } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { TimePicker, type TimePickerProps } from './TimePicker';
import { formatTime, from12, hourCycleFor, parseTime, spinKey, to12 } from './time-picker-logic';
import { byLabel, click, key, mount, type Mounted } from './test-dom';

let m: Mounted | null = null;
afterEach(() => { m?.unmount(); m = null; });

describe('time logic', () => {
  it('steps and wraps', () => {
    expect(spinKey(23, 'ArrowUp', { max: 23 })).toBe(0);
    expect(spinKey(0, 'ArrowDown', { max: 23 })).toBe(23);
    expect(spinKey(55, 'ArrowUp', { max: 59, step: 5 })).toBe(0);
    expect(spinKey(0, 'ArrowDown', { max: 59, step: 5 })).toBe(55);
  });
  it('snaps a value off the step grid to the next step', () => {
    expect(spinKey(7, 'ArrowUp', { max: 59, step: 5 })).toBe(10);
    expect(spinKey(7, 'ArrowDown', { max: 59, step: 5 })).toBe(5);
  });
  it('Page Up/Down take the big step, Home/End the ends', () => {
    expect(spinKey(10, 'PageUp', { max: 59, step: 1, big: 15 })).toBe(25);
    expect(spinKey(10, 'PageDown', { max: 59, step: 1, big: 15 })).toBe(55);
    expect(spinKey(22, 'PageUp', { max: 23, big: 3 })).toBe(1);
    expect(spinKey(30, 'Home', { max: 59 })).toBe(0);
    expect(spinKey(30, 'End', { max: 59, step: 5 })).toBe(55);
    expect(spinKey(30, 'x', { max: 59 })).toBeNull();
  });
  it('reads and writes each unit set, and refuses impossible times', () => {
    expect(parseTime('07', 'h')).toEqual({ h: 7, m: 0, s: 0 });
    expect(parseTime('18:30', 'hm')).toEqual({ h: 18, m: 30, s: 0 });
    expect(parseTime('00:01:30', 'hms')).toEqual({ h: 0, m: 1, s: 30 });
    expect(parseTime('24:00', 'hm')).toBeNull();
    expect(parseTime('18:30', 'h')).toBeNull();
    expect(formatTime({ h: 7, m: 5, s: 9 }, 'hms')).toBe('07:05:09');
  });
  it('maps the 12-hour clock', () => {
    expect(to12(0)).toEqual({ h: 12, pm: false });
    expect(to12(13)).toEqual({ h: 1, pm: true });
    expect(from12(12, false)).toBe(0);
    expect(from12(12, true)).toBe(12);
    expect(hourCycleFor('en-GB')).toBe('h23');
    expect(hourCycleFor('en-US')).toBe('h12');
  });
});

function Harness(props: Omit<TimePickerProps, 'value' | 'onChange'> & { start: string | null; spy?: (v: string) => void }) {
  const { start, spy, ...rest } = props;
  const [value, setValue] = useState<string | null>(start);
  return <TimePicker {...rest} value={value} onChange={(v) => { setValue(v); spy?.(v); }} />;
}

describe('TimePicker', () => {
  const spins = () => [...m!.container.querySelectorAll('[role="spinbutton"]')] as HTMLElement[];
  /** One spin button by position; fails the test if it is missing. */
  const spin = (i: number): HTMLElement => {
    const el = spins()[i];
    if (!el) throw new Error(`no spin button ${i}`);
    return el;
  };

  it('shows one spin button per unit', () => {
    for (const [units, n] of [['h', 1], ['hm', 2], ['hms', 3]] as const) {
      m = mount(<Harness label="Time" start={null} units={units} hourCycle="h23" />);
      expect(spins()).toHaveLength(n);
      m.unmount(); m = null;
    }
  });

  it('spin buttons carry their value, range and words', () => {
    m = mount(<Harness label="Reminder" start="18:30" units="hm" hourCycle="h23" />);
    const h = spin(0);
    const mins = spin(1);
    expect(h.getAttribute('aria-label')).toBe('Hours');
    expect(h.getAttribute('aria-valuenow')).toBe('18');
    expect(h.getAttribute('aria-valuemin')).toBe('0');
    expect(h.getAttribute('aria-valuemax')).toBe('23');
    expect(mins.getAttribute('aria-valuetext')).toBe('30 minutes');
    expect(h.tabIndex).toBe(0);
  });

  it('arrow keys step by the step, wrap, and Right moves to the next column', () => {
    const spy = vi.fn();
    m = mount(<Harness label="Reminder" start="23:55" units="hm" step={5} hourCycle="h23" spy={spy} />);
    key(spin(1), 'ArrowUp');
    expect(spy).toHaveBeenLastCalledWith('23:00');
    key(spin(0), 'ArrowUp');
    expect(spy).toHaveBeenLastCalledWith('00:00');
    spin(0).focus();
    key(spin(0), 'ArrowRight');
    expect(document.activeElement).toBe(spin(1));
    key(spin(1), 'End');
    expect(spy).toHaveBeenLastCalledWith('00:55');
  });

  it('seconds step and the up and down keys work by pointer', () => {
    const spy = vi.fn();
    m = mount(<Harness label="Rest" start="00:01:30" units="hms" step={15} hourCycle="h23" spy={spy} />);
    click(byLabel(m.container, 'More seconds'));
    expect(spy).toHaveBeenLastCalledWith('00:01:45');
    click(byLabel(m.container, 'Fewer minutes'));
    expect(spy).toHaveBeenLastCalledWith('00:00:45');
  });

  it('a 12-hour clock spins 1 to 12 and switches AM and PM', () => {
    const spy = vi.fn();
    m = mount(<Harness label="Time" start="11:00" units="hm" locale="en-US" spy={spy} />);
    const h = spin(0);
    expect(h.getAttribute('aria-valuemin')).toBe('1');
    expect(h.getAttribute('aria-valuemax')).toBe('12');
    expect(h.getAttribute('aria-valuenow')).toBe('11');
    key(h, 'ArrowUp'); // 11 AM -> 12 AM within the period
    expect(spy).toHaveBeenLastCalledWith('00:00');
    const pm = [...m.container.querySelectorAll('[aria-pressed]')].find((b) => b.textContent === 'PM');
    if (!pm) throw new Error('no PM button');
    click(pm);
    expect(spy).toHaveBeenLastCalledWith('12:00');
  });

  it('a quick pick sets the value and shows as pressed', () => {
    m = mount(<Harness label="Reminder" start="07:00" units="hm" hourCycle="h23"
      quick={[{ value: '07:00' }, { value: '20:00' }]} />);
    const chips = [...m.container.querySelectorAll('[role="group"] [aria-pressed]')] as HTMLElement[];
    expect(chips[0]?.getAttribute('aria-pressed')).toBe('true');
    const second = chips[1];
    if (!second) throw new Error('no second chip');
    click(second);
    expect(spin(0).getAttribute('aria-valuenow')).toBe('20');
  });

  it('Enter is Done and Escape cancels', () => {
    const onDone = vi.fn();
    const onCancel = vi.fn();
    m = mount(<TimePicker label="T" value="06:15" onChange={() => {}} hourCycle="h23" onDone={onDone} onCancel={onCancel} />);
    key(spin(0), 'Enter');
    expect(onDone).toHaveBeenCalledWith('06:15');
    key(spin(1), 'Escape');
    expect(onCancel).toHaveBeenCalledOnce();
  });
});
