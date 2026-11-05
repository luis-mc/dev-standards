import { describe, expect, it } from 'vitest';
import {
  checkWizard,
  droppedStates,
  judgeAll,
  judgeWizard,
  WIZARD_BEHAVIOUR_TO_FIX,
  WIZARD_STATES,
  type WizardDriver,
  type WizardSnapshot,
  type WizardToFix,
} from './wizard-behaviour.ts';

// Wizard behaviour guard (design system, Enforcement kit).
// 1. DRIVERS: one driver per wizard. `open(state)` renders the wizard in that state and reads a snapshot from
//    the DOM (Testing Library for components; a page script against a stubbed server for script pages).
//    Fill the list below; each new wizard adds a driver in the same change.
// 2. The table `WIZARD_BEHAVIOUR_TO_FIX` (wizard-behaviour.ts) lists today's breaches and only shrinks.
// The rest of this file is the harness's own self-test: it plants each breach and expects it to be found.
const DRIVERS: WizardDriver[] = [];

describe('wizard behaviour', () => {
  it('every wizard is clean in every state, except the listed breaches (the table only shrinks)', async () => {
    expect(await judgeAll(DRIVERS)).toEqual([]);
  });

  it('every row of the table names its task', () => {
    for (const r of WIZARD_BEHAVIOUR_TO_FIX) expect(r.task, `${r.wizard}: task`).toMatch(/\S/);
  });

  describe('the rules themselves', () => {
    const good: WizardSnapshot = {
      state: 'running',
      steps: [
        { name: 'Choose', standing: 'done', pressable: true },
        { name: 'Run', standing: 'now', pressable: true },
        { name: 'Done', standing: 'later', pressable: false },
      ],
      buttons: [
        { label: 'Start', primary: true, disabled: true, reason: 'Running', requestOpen: true },
        { label: 'Stop', primary: false, disabled: false, role: 'stop' },
        { label: 'Pause', primary: false, disabled: false, role: 'pause' },
      ],
      job: { canStop: true, canPause: true },
    };
    const rules = (s: WizardSnapshot): string[] => checkWizard(s).map((p) => p.rule);

    it('passes a good wizard', () => expect(rules(good)).toEqual([]));
    it('finds a later step that can be pressed', () => {
      const s = { ...good, steps: [...good.steps.slice(0, 2), { name: 'Done', standing: 'later' as const, pressable: true }] };
      expect(rules(s)).toEqual(['later-step-pressable']);
    });
    it('wants exactly one primary', () => {
      expect(rules({ ...good, buttons: good.buttons.map((b) => ({ ...b, primary: false })) })).toContain('primary-count');
      expect(rules({ ...good, buttons: good.buttons.map((b) => ({ ...b, primary: true })) })).toContain('primary-count');
    });
    it('wants a reason on a disabled primary', () => {
      const b = good.buttons.map((x, i) => (i === 0 ? { ...x, reason: '' } : x));
      expect(rules({ ...good, buttons: b })).toEqual(['disabled-primary-no-reason']);
    });
    it('wants Stop and Pause when the job can', () => {
      const b = good.buttons.filter((x) => x.role === undefined);
      expect(rules({ ...good, buttons: b })).toEqual(['stop-missing', 'pause-missing']);
    });
    it('wants a Done that is not empty', () => {
      const done: WizardSnapshot = { ...good, state: 'done', job: { canStop: false, canPause: false }, buttons: [{ label: 'Start again', primary: true, disabled: false }] };
      expect(rules(done)).toEqual(['done-empty']);
      expect(rules({ ...done, done: { text: '12 files renamed', counts: 12 } })).toEqual([]);
    });
    it('wants a busy button disabled', () => {
      const b = good.buttons.map((x, i) => (i === 0 ? { ...x, disabled: false } : x));
      expect(rules({ ...good, buttons: b })).toContain('busy-not-disabled');
    });
  });

  describe('the nine required states', () => {
    const clean = (state: string): WizardSnapshot => ({
      state,
      steps: [],
      buttons: [{ label: 'Go', primary: true, disabled: false }],
      job: { canStop: false, canPause: false },
      done: { text: 'ok', counts: 1 },
    });
    it('are exactly the nine of the owner list', () => {
      expect([...WIZARD_STATES]).toEqual([
        'first-run', 'planning', 'ready-to-review', 'running', 'paused', 'stopped', 'failed', 'done', 'done-after-reload',
      ]);
    });
    it('a driver that lists fewer states fails and names the dropped ones', async () => {
      const driver: WizardDriver = { id: 'w', states: ['first-run', 'done'], open: (s) => Promise.resolve(clean(s)) };
      expect(droppedStates(driver)).toHaveLength(7);
      const lines = await judgeAll([driver], []);
      expect(lines).toHaveLength(7);
      expect(lines[0]).toContain('never drop one');
    });
    it('a driver may add a state and is then driven through ten', async () => {
      const seen: string[] = [];
      const driver: WizardDriver = {
        id: 'w',
        states: [...WIZARD_STATES, 'needs-login'],
        open: (s) => {
          seen.push(s);
          return Promise.resolve(clean(s));
        },
      };
      expect(await judgeAll([driver], [])).toEqual([]);
      expect(seen).toHaveLength(10);
    });
    it('a driver with no states list runs all nine', async () => {
      const seen: string[] = [];
      const driver: WizardDriver = { id: 'w', open: (s) => { seen.push(s); return Promise.resolve(clean(s)); } };
      expect(await judgeAll([driver], [])).toEqual([]);
      expect(seen).toHaveLength(9);
    });
  });

  describe('the ratchet', () => {
    const problem = [{ rule: 'stop-missing' as const, text: 't' }];
    const row: WizardToFix = { wizard: 'w', state: 'running', rule: 'stop-missing', task: 'T1' };
    it('fails a problem not on the table', () => {
      expect(judgeWizard('w', 'running', problem, []).unknown).toHaveLength(1);
    });
    it('accepts a listed problem and fails a listed row that is gone', () => {
      expect(judgeWizard('w', 'running', problem, [row])).toEqual({ unknown: [], stale: [] });
      expect(judgeWizard('w', 'running', [], [row]).stale).toHaveLength(1);
    });
    it('a star row covers every state and goes stale when no state has the problem', async () => {
      const clean = (state: (typeof WIZARD_STATES)[number]): WizardSnapshot => ({
        state,
        steps: [],
        buttons: [{ label: 'Go', primary: true, disabled: false }],
        job: { canStop: false, canPause: false },
        done: { text: 'ok', counts: 1 },
      });
      const driver: WizardDriver = { id: 'w', open: (s) => Promise.resolve(clean(s)) };
      const star: WizardToFix = { wizard: 'w', state: '*', rule: 'stop-missing', task: 'T1' };
      const lines = await judgeAll([driver], [star]);
      expect(lines).toHaveLength(1);
      expect(lines[0]).toContain('no longer happens in any state');
    });
  });
});
