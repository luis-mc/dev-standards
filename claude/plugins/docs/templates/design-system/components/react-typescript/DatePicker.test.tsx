// @vitest-environment jsdom
// DatePicker template tests (luismc-docs): keyboard, value and limits.
import { afterEach, describe, expect, it, vi } from 'vitest';
import { DatePicker } from './DatePicker';
import {
  addMonths, gridKey, monthGrid, parseIso, parseTyped, toIso, typedPattern, yearRange,
} from './date-picker-logic';
import { byLabel, choose, click, focus, key, mount, typeInto, type Mounted } from './test-dom';

const d = (iso: string) => parseIso(iso)!;
let m: Mounted | null = null;
afterEach(() => { m?.unmount(); m = null; });

describe('date logic', () => {
  it('moves by day, week, month and year from the keyboard', () => {
    const at = d('2009-03-14'); // a Saturday
    const go = (k: string, shiftKey = false) => toIso(gridKey(at, { key: k, shiftKey })!);
    expect(go('ArrowLeft')).toBe('2009-03-13');
    expect(go('ArrowRight')).toBe('2009-03-15');
    expect(go('ArrowUp')).toBe('2009-03-07');
    expect(go('ArrowDown')).toBe('2009-03-21');
    expect(go('Home')).toBe('2009-03-09'); // Monday
    expect(go('End')).toBe('2009-03-15'); // Sunday
    expect(go('PageUp')).toBe('2009-02-14');
    expect(go('PageDown')).toBe('2009-04-14');
    expect(go('PageUp', true)).toBe('2008-03-14');
    expect(gridKey(at, { key: 'a' })).toBeNull();
  });

  it('Home and End follow a Sunday week start', () => {
    const at = d('2009-03-14');
    expect(toIso(gridKey(at, { key: 'Home' }, { weekStart: 0 })!)).toBe('2009-03-08');
    expect(toIso(gridKey(at, { key: 'End' }, { weekStart: 0 })!)).toBe('2009-03-14');
  });

  it('never leaves min and max', () => {
    const opts = { min: d('2009-03-10'), max: d('2009-03-20') };
    expect(toIso(gridKey(d('2009-03-12'), { key: 'ArrowUp' }, opts)!)).toBe('2009-03-10');
    expect(toIso(gridKey(d('2009-03-18'), { key: 'PageDown' }, opts)!)).toBe('2009-03-20');
  });

  it('clamps the day to a shorter month', () => {
    expect(toIso(addMonths(d('2009-01-31'), 1))).toBe('2009-02-28');
    expect(toIso(addMonths(d('2008-01-31'), 1))).toBe('2008-02-29');
    expect(toIso(addMonths(d('2009-01-15'), -1))).toBe('2008-12-15');
  });

  it('lays a month out in weeks of seven, Monday first', () => {
    const weeks = monthGrid(2009, 3, 1);
    expect(weeks.every((w) => w.length === 7)).toBe(true);
    expect(weeks[0].findIndex(Boolean)).toBe(6); // 1 March 2009 was a Sunday
    expect(weeks.flat().filter(Boolean)).toHaveLength(31);
  });

  it('reads typed dates in the locale order and refuses impossible ones', () => {
    expect(toIso(parseTyped('14/03/2009', 'en-GB')!)).toBe('2009-03-14');
    expect(toIso(parseTyped('03/14/2009', 'en-US')!)).toBe('2009-03-14');
    expect(toIso(parseTyped('14.3.2009', 'de-DE')!)).toBe('2009-03-14');
    expect(toIso(parseTyped('2009-03-14', 'en-US')!)).toBe('2009-03-14');
    expect(parseTyped('31/02/2009', 'en-GB')).toBeNull();
    expect(parseTyped('14/03/09', 'en-GB')).toBeNull();
    expect(parseTyped('soon', 'en-GB')).toBeNull();
    expect(typedPattern('en-GB')).toBe('DD/MM/YYYY');
    expect(typedPattern('en-US')).toBe('MM/DD/YYYY');
  });

  it('offers the years from min to max', () => {
    expect(yearRange(d('2000-01-01'), d('2003-12-31'), d('2026-01-01'))).toEqual([2000, 2001, 2002, 2003]);
  });
});

describe('DatePicker', () => {
  const grid = () => m!.container.querySelector('[role="grid"]')!;
  const focused = () => grid().querySelector('button[tabindex="0"]')!;

  it('is a labelled group with one tab stop in the grid and the chosen day selected', () => {
    m = mount(<DatePicker label="Date of birth" value="2009-03-14" onChange={() => {}} locale="en-GB" />);
    const group = m.container.querySelector('[role="group"]')!;
    expect(group.getAttribute('aria-labelledby')).toBeTruthy();
    expect(grid().querySelectorAll('button[tabindex="0"]')).toHaveLength(1);
    expect(focused().textContent).toBe('14');
    expect(grid().querySelector('[aria-selected="true"] button')!.textContent).toBe('14');
    expect(byLabel(m.container, 'Month')).toBeTruthy();
    expect(byLabel(m.container, 'Year')).toBeTruthy();
    expect(m.container.querySelector('label')!.textContent).toBe('Or type the date');
  });

  it('arrow keys move the focus, Page Down changes the month, Enter picks', () => {
    const onChange = vi.fn();
    m = mount(<DatePicker label="Day" value="2009-03-14" onChange={onChange} locale="en-GB" />);
    focus(focused());
    key(focused(), 'ArrowRight');
    expect(focused().textContent).toBe('15');
    expect(document.activeElement).toBe(focused());
    key(focused(), 'PageDown');
    expect((byLabel(m.container, 'Month') as HTMLSelectElement).value).toBe('4');
    click(focused()); // Enter and Space on a button fire its click
    expect(onChange).toHaveBeenCalledWith('2009-04-15');
  });

  it('disables days outside min and max and never picks them', () => {
    const onChange = vi.fn();
    m = mount(<DatePicker label="Start" value={null} initialFocus="2026-11-10" min="2026-11-07" max="2026-11-20"
      onChange={onChange} locale="en-GB" />);
    const day6 = [...grid().querySelectorAll('button')].find((b) => b.textContent === '6')!;
    expect(day6.getAttribute('aria-disabled')).toBe('true');
    click(day6);
    expect(onChange).not.toHaveBeenCalled();
    expect((byLabel(m.container, 'Previous month') as HTMLButtonElement).disabled).toBe(true);
    expect((byLabel(m.container, 'Next month') as HTMLButtonElement).disabled).toBe(true);
    key(focused(), 'ArrowUp');
    expect(focused().textContent).toBe('7');
  });

  it('the month and year selects move the view', () => {
    m = mount(<DatePicker label="Day" value="2009-03-14" onChange={() => {}} locale="en-GB" />);
    const year = byLabel(m.container, 'Year') as HTMLSelectElement;
    choose(year, '2010');
    expect(m.container.querySelector('caption')!.textContent).toBe('March 2010');
  });

  it('accepts a typed date and says why it refuses one', () => {
    const onChange = vi.fn();
    m = mount(<DatePicker label="Day" value={null} min="2000-01-01" max="2010-12-31" initialFocus="2009-01-01"
      onChange={onChange} locale="en-GB" />);
    const input = m.container.querySelector('input')!;
    typeInto(input, '31/02/2009');
    key(input, 'Enter');
    expect(m.container.querySelector('[role="alert"]')!.textContent).toBe('Type the date as DD/MM/YYYY.');
    expect(input.getAttribute('aria-invalid')).toBe('true');
    typeInto(input, '01/01/2020');
    key(input, 'Enter');
    expect(m.container.querySelector('[role="alert"]')!.textContent).toContain('Pick a date from 1 January 2000');
    typeInto(input, '14/03/2009');
    key(input, 'Enter');
    expect(onChange).toHaveBeenCalledWith('2009-03-14');
    expect(m.container.querySelector('[role="alert"]')).toBeNull();
  });

  it('shows the value through the project formatter when one is given', () => {
    m = mount(<DatePicker label="Day" value="2009-03-14" onChange={() => {}} formatValue={(iso) => `on ${iso}`} />);
    expect(m.container.querySelector('.ds-datepicker__value')!.textContent).toBe('on 2009-03-14');
  });

  it('Escape cancels', () => {
    const onCancel = vi.fn();
    m = mount(<DatePicker label="Day" value="2009-03-14" onChange={() => {}} onCancel={onCancel} />);
    key(focused(), 'Escape');
    expect(onCancel).toHaveBeenCalledOnce();
  });
});
