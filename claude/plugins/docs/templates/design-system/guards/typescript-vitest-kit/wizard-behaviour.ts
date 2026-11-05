/**
 * The wizard behaviour harness (design system, Enforcement kit). A wizard is a page with steps and one job. The
 * look is the shared UI package's; the BEHAVIOUR (which step can be pressed, which button is primary, when Stop
 * shows, what Done says, what a busy button does) must be the same for every wizard, so this harness asks each
 * wizard the same questions in each of its states and judges the answers. No screenshots.
 *
 * Pattern:
 *  1. For each wizard, write a driver: `open(state)` renders the wizard in that state (a component test with
 *     Testing Library, or a page script run against a stubbed server) and returns a `WizardSnapshot` read from
 *     the DOM: steps, buttons, what the job can do, what Done shows.
 *  2. `checkWizard(snapshot)` returns the problems (pure; the self-test plants each breach).
 *  3. `judgeWizard(id, state, problems, WIZARD_BEHAVIOUR_TO_FIX)` is the ratchet: a problem not on the table
 *     fails; a table row that no longer happens fails; so the table only shrinks to empty.
 */
/** The ten states every wizard MUST be driven through (owner decisions D237 and D244). A project may add states, never drop one. */
export const WIZARD_STATES = [
  'loading',
  'first-run',
  'planning',
  'ready-to-review',
  'running',
  'paused',
  'stopped',
  'failed',
  'done',
  'done-after-reload',
] as const;
export type RequiredWizardState = (typeof WIZARD_STATES)[number];
/** A required state, or a state the project added to a driver's `states`. */
export type WizardState = RequiredWizardState | (string & {});

export type WizardRule =
  | 'later-step-pressable'
  | 'primary-count'
  | 'disabled-primary-no-reason'
  | 'stop-missing'
  | 'pause-missing'
  | 'done-empty'
  | 'busy-not-disabled'
  | 'loading-action-hidden'
  | 'loading-action-live'
  | 'loading-wait-not-once'
  | 'loading-back-missing'
  | 'loading-done-shown';

export interface WizardStep {
  readonly name: string;
  /** done = finished, now = the current step, later = not reached yet. */
  readonly standing: 'done' | 'now' | 'later';
  /** The step can be pressed (not disabled, not aria-disabled). */
  readonly pressable: boolean;
}

export interface WizardButton {
  readonly label: string;
  readonly primary: boolean;
  readonly disabled: boolean;
  /** The text that says why a disabled button is disabled (a hint next to it, or its description). */
  readonly reason?: string;
  /** Its request is open right now (the driver clicked it and the stubbed server has not answered). */
  readonly requestOpen?: boolean;
  readonly role?: 'stop' | 'pause' | 'back' | 'other';
}

export interface WizardSnapshot {
  readonly state: WizardState;
  readonly steps: readonly WizardStep[];
  readonly buttons: readonly WizardButton[];
  /** What the job can do in this state (from the job reading, not from the page). */
  readonly job: { readonly canStop: boolean; readonly canPause: boolean };
  /** What the Done step shows; only read in the done states. */
  readonly done?: { readonly text: string; readonly counts: number };
  /** How many lines say the step data is still being read (read in the loading state: exactly one wanted). */
  readonly waitLines?: number;
}

export interface WizardProblem {
  readonly rule: WizardRule;
  readonly text: string;
}

const DONE_STATES: readonly WizardState[] = ['done', 'done-after-reload'];

/** The rules, applied to one wizard in one state. Pure. */
export function checkWizard(s: WizardSnapshot): WizardProblem[] {
  const out: WizardProblem[] = [];
  const add = (rule: WizardRule, text: string): void => {
    out.push({ rule, text });
  };
  for (const step of s.steps)
    if (step.standing === 'later' && step.pressable) add('later-step-pressable', `step "${step.name}" is not reached yet but can be pressed`);
  const primaries = s.buttons.filter((b) => b.primary);
  if (primaries.length !== 1) add('primary-count', `${primaries.length} primary buttons (exactly one wanted)`);
  for (const b of primaries)
    if (b.disabled && !(b.reason ?? '').trim()) add('disabled-primary-no-reason', `the primary "${b.label}" is disabled and does not say why`);
  if (s.job.canStop && !s.buttons.some((b) => b.role === 'stop' && !b.disabled)) add('stop-missing', 'the job can stop but there is no Stop button');
  if (s.job.canPause && !s.buttons.some((b) => b.role === 'pause' && !b.disabled)) add('pause-missing', 'the job can pause but there is no Pause button');
  if (DONE_STATES.includes(s.state) && (!s.done || !s.done.text.trim() || s.done.counts <= 0))
    add('done-empty', 'Done shows no result (text and counts are needed)');
  for (const b of s.buttons)
    if (b.requestOpen && !b.disabled) add('busy-not-disabled', `"${b.label}" starts a request and is still pressable while it runs`);
  if (s.state === 'loading') {
    // The step own data is still being read: actions stay, locked; one wait line; Back free; no Done text.
    if (primaries.length === 0) add('loading-action-hidden', 'the primary action is hidden while loading (it must be shown, locked)');
    for (const b of s.buttons)
      if (b.role !== 'back' && !b.disabled) add('loading-action-live', `"${b.label}" is pressable while the data of the step is still loading (lock it)`);
    if (s.waitLines !== 1) add('loading-wait-not-once', `the wait is said ${s.waitLines ?? 0} times (exactly one line wanted)`);
    if (!s.buttons.some((b) => b.role === 'back' && !b.disabled)) add('loading-back-missing', 'Back is missing or locked while loading');
    if (s.done?.text.trim()) add('loading-done-shown', 'Done text shows while the step is still loading');
  }
  return out;
}

/** One known breach: the wizard, the state ('*' for every state), the rule and the task that removes it. */
export interface WizardToFix {
  readonly wizard: string;
  readonly state: WizardState | '*';
  readonly rule: WizardRule;
  readonly task: string;
}

/** The shrinking table (ratchet): remove a row when its breach is fixed; never add a row to pass. */
export const WIZARD_BEHAVIOUR_TO_FIX: readonly WizardToFix[] = [];

/** Split the problems of one wizard in one state into unknown ones (fail) and stale rows (fail). */
export function judgeWizard(
  wizard: string,
  state: WizardState,
  problems: readonly WizardProblem[],
  table: readonly WizardToFix[] = WIZARD_BEHAVIOUR_TO_FIX,
): { unknown: string[]; stale: string[] } {
  const mine = table.filter((r) => r.wizard === wizard && (r.state === '*' || r.state === state));
  const unknown = problems
    .filter((p) => !mine.some((r) => r.rule === p.rule))
    .map((p) => `${wizard} [${state}] ${p.rule}: ${p.text}`);
  // A '*' row is stale only when the rule never happens in any state: the caller passes every state through
  // `judgeAll`; a per-state row is stale when it does not happen in its own state.
  const stale = mine
    .filter((r) => r.state === state && !problems.some((p) => p.rule === r.rule))
    .map((r) => `${wizard} [${state}]: known ${r.rule} (${r.task}) no longer happens: remove it from WIZARD_BEHAVIOUR_TO_FIX`);
  return { unknown, stale };
}

/** A wizard driver: renders the wizard in a state and reads a snapshot from the DOM. */
export interface WizardDriver {
  readonly id: string;
  /** States the project ADDS to the ten required ones. Listing fewer than the ten is a failure, not a shortcut. */
  readonly states?: readonly WizardState[];
  open(state: WizardState): Promise<WizardSnapshot>;
}

/** The required states a driver's own `states` list leaves out (empty when it lists none: all ten run). */
export function droppedStates(d: WizardDriver): string[] {
  if (!d.states) return [];
  return WIZARD_STATES.filter((s) => !d.states?.includes(s));
}

/** Run every driver through the ten required states and the ones it adds; every problem and stale row, as lines. Empty means green. */
export async function judgeAll(
  drivers: readonly WizardDriver[],
  table: readonly WizardToFix[] = WIZARD_BEHAVIOUR_TO_FIX,
): Promise<string[]> {
  const lines: string[] = [];
  for (const d of drivers) {
    const seenStar = new Set<WizardRule>();
    for (const dropped of droppedStates(d)) lines.push(`${d.id}: required state "${dropped}" is missing from the driver's states: a project may add states, never drop one`);
    const states = [...WIZARD_STATES, ...(d.states ?? []).filter((s) => !(WIZARD_STATES as readonly string[]).includes(s))];
    for (const state of states) {
      const problems = checkWizard(await d.open(state));
      const r = judgeWizard(d.id, state, problems, table);
      lines.push(...r.unknown, ...r.stale);
      for (const p of problems) seenStar.add(p.rule);
    }
    for (const row of table)
      if (row.wizard === d.id && row.state === '*' && !seenStar.has(row.rule))
        lines.push(`${d.id}: known ${row.rule} (${row.task}) no longer happens in any state: remove it from WIZARD_BEHAVIOUR_TO_FIX`);
  }
  return lines;
}
