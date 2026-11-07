// @vitest-environment jsdom
// NumberKeypad template tests (luismc-docs): keyboard, value and limits, for numbers and codes.
import { afterEach, describe, expect, it, vi } from 'vitest';
import { NumberKeypad } from './NumberKeypad';
import { commitValue, keyLayout, moveInGrid, pressKey } from './number-keypad-logic';
import { byLabel, click, focus, key, mount, type Mounted } from './test-dom';

let m: Mounted | null = null;
afterEach(() => { m?.unmount(); m = null; });
const typeAll = (keys: string, opts = {}) => [...keys].reduce((b, k) => pressKey(b, k, opts), '');

describe('keypad logic', () => {
  it('types digits, drops a leading zero for a number and keeps it for a code', () => {
    expect(typeAll('012')).toBe('12');
    expect(typeAll('0042', { kind: 'code', maxLength: 6 })).toBe('0042');
  });
  it('caps decimals and refuses a second point', () => {
    expect(typeAll('2.555', { decimals: 2 })).toBe('2.55');
    expect(typeAll('2..5', { decimals: 1 })).toBe('2.5');
    expect(typeAll('.5', { decimals: 1 })).toBe('0.5');
    expect(typeAll('2.5', { decimals: 0 })).toBe('25');
  });
  it('refuses a digit past max or maxLength', () => {
    expect(typeAll('1234', { max: 300 })).toBe('123');
    expect(typeAll('1234567', { kind: 'code', maxLength: 6 })).toBe('123456');
  });
  it('commits within the limits and says why not otherwise', () => {
    expect(commitValue('', {})).toEqual({ ok: false, reason: 'empty' });
    expect(commitValue('3', { min: 5 })).toEqual({ ok: false, reason: 'below' });
    expect(commitValue('7.', { decimals: 1 })).toEqual({ ok: true, value: '7' });
    expect(commitValue('123', { kind: 'code', maxLength: 6 })).toEqual({ ok: false, reason: 'short' });
    expect(commitValue('004211', { kind: 'code', maxLength: 6 })).toEqual({ ok: true, value: '004211' });
  });
  it('arrows move in the 3 x 4 grid and skip the empty cell', () => {
    const layout = keyLayout({});
    expect(layout[9]).toBeNull();
    expect(moveInGrid(0, 'ArrowRight', layout)).toBe(1);
    expect(moveInGrid(2, 'ArrowRight', layout)).toBe(2); // the row ends
    expect(moveInGrid(6, 'ArrowDown', layout)).toBe(6); // the cell below is empty and the grid ends
    expect(moveInGrid(10, 'ArrowLeft', layout)).toBe(10);
    expect(moveInGrid(4, 'ArrowUp', layout)).toBe(1);
    expect(moveInGrid(4, 'End', layout)).toBe(11);
    expect(moveInGrid(4, 'x', layout)).toBeNull();
  });
});

describe('NumberKeypad', () => {
  const keyBtn = (k: string) => m!.container.querySelector<HTMLButtonElement>(`[data-keypad-key="${k}"]`)!;
  const shown = () => m!.container.querySelector('.ds-keypad__digits')!.textContent;
  const doneBtn = () => [...m!.container.querySelectorAll('button')].find((b) => b.textContent === 'Done')!;

  it('is a labelled group with one tab stop, and the keys are 0-9 and Delete last digit', () => {
    m = mount(<NumberKeypad label="Reps" onDone={() => {}} />);
    expect(m.container.querySelector('[role="group"]')!.getAttribute('aria-labelledby')).toBeTruthy();
    expect(m.container.querySelectorAll('.ds-keypad__keys button[tabindex="0"]')).toHaveLength(1);
    expect(byLabel(m.container, 'Delete last digit')).toBeTruthy();
    expect(keyBtn('.')).toBeNull();
  });

  it('the first key replaces a prefilled value; digits and Backspace type from the keyboard', () => {
    const onChange = vi.fn();
    m = mount(<NumberKeypad label="Reps" value="12" onDone={() => {}} onChange={onChange} />);
    key(keyBtn('1'), '8');
    expect(shown()).toBe('8');
    key(keyBtn('1'), '5');
    key(keyBtn('1'), 'Backspace');
    expect(shown()).toBe('8');
    expect(onChange).toHaveBeenLastCalledWith('8');
  });

  it('Done is disabled with its reason outside the limits, and commits inside them', () => {
    const onDone = vi.fn();
    m = mount(<NumberKeypad label="Weight" unit="kg" min={20} max={300} decimals={1} onDone={onDone} />);
    expect(doneBtn().disabled).toBe(true);
    expect(m.container.querySelector('.ds-keypad__reason')!.textContent).toBe('Type a number.');
    click(keyBtn('5'));
    expect(doneBtn().disabled).toBe(true);
    expect(m.container.querySelector('.ds-keypad__reason')!.textContent).toBe('The lowest is 20.');
    click(keyBtn('2'));
    click(keyBtn('.'));
    click(keyBtn('5'));
    expect(shown()).toBe('52.5');
    click(doneBtn());
    expect(onDone).toHaveBeenCalledWith('52.5');
  });

  it('a code needs every digit', () => {
    const onDone = vi.fn();
    m = mount(<NumberKeypad label="Code" kind="code" maxLength={4} onDone={onDone} />);
    for (const k of '0071') key(keyBtn('1'), k);
    expect(shown()).toBe('0071');
    key(keyBtn('1'), '9'); // past maxLength: refused
    expect(shown()).toBe('0071');
    key(m.container.querySelector('output')!, 'Enter');
    expect(onDone).toHaveBeenCalledWith('0071');
  });

  it('arrow keys move the focus between keys; Enter on a key presses it; Escape cancels', () => {
    const onCancel = vi.fn();
    const onDone = vi.fn();
    m = mount(<NumberKeypad label="Sets" onDone={onDone} onCancel={onCancel} />);
    focus(keyBtn('1'));
    key(keyBtn('1'), 'ArrowRight');
    expect(document.activeElement).toBe(keyBtn('2'));
    key(keyBtn('2'), 'ArrowDown');
    expect(document.activeElement).toBe(keyBtn('5'));
    expect(keyBtn('5').tabIndex).toBe(0);
    key(keyBtn('5'), 'Enter');
    expect(onDone).not.toHaveBeenCalled();
    key(keyBtn('5'), 'Escape');
    expect(onCancel).toHaveBeenCalledOnce();
  });
});
