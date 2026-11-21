import { t } from './words';

export type Policy = 'automatic_when_idle' | 'ask_first';

export interface UpdatesCardProps {
  policy: Policy;
  channel: string;
  /** Optional time window, e.g. `{ from: '01:00', to: '05:00' }`. */
  window?: { from: string; to: string };
  waitForRunningWork: boolean;
  lastCheck: string;
  /** When an admin locked the policy: who set it. The controls are then read only. */
  lockedBy?: string;
  onPolicy?: (p: Policy) => void;
  onWait?: (v: boolean) => void;
}

/** The Updates card: two policies, optional window, channel, wait for running work, last check, admin lock. */
export function UpdatesCard(p: UpdatesCardProps) {
  const locked = Boolean(p.lockedBy);
  return (
    <section className="ds-part" data-ds-part="updates-card" data-locked={locked} aria-labelledby="ds-updates-title">
      <h2 className="ds-part__title" id="ds-updates-title">{t('updates.title')}</h2>
      <fieldset className="ds-stack ds-fieldset" disabled={locked}>
        <legend className="ds-part__text">{t('updates.policy')}</legend>
        {(['automatic_when_idle', 'ask_first'] as Policy[]).map((k) => (
          <label className="ds-choice" key={k}>
            <input type="radio" name="policy" checked={p.policy === k} onChange={() => p.onPolicy?.(k)} />
            <span>{t(`policy.${k}`)}</span>
          </label>
        ))}
        <label className="ds-choice">
          <input type="checkbox" checked={p.waitForRunningWork} onChange={(e) => p.onWait?.(e.target.checked)} />
          <span>{t('updates.wait_running')}</span>
        </label>
      </fieldset>
      {p.window && <p className="ds-part__text">{t('updates.window')} {p.window.from} - {p.window.to}</p>}
      <p className="ds-part__text">{t('updates.channel')}: {p.channel}</p>
      <p className="ds-part__hint">{t('updates.last_check')}: {p.lastCheck}</p>
      {locked && <p className="ds-part__hint" role="note">{t('updates.locked_by')} {p.lockedBy}</p>}
    </section>
  );
}
