import { t } from './words';

/** One audit event: who did what, when, with what result. */
export interface AuditEvent {
  at: string;
  actor: string;
  action: string;
  result: 'ok' | 'failed' | 'skipped';
}

const TONE = { ok: 'done', failed: 'problem', skipped: 'needs-you' } as const;

export function UpdateHistory({ events }: { events: readonly AuditEvent[] }) {
  return (
    <section className="ds-part" data-ds-part="update-history" aria-labelledby="ds-history-title">
      <h2 className="ds-part__title" id="ds-history-title">{t('history.title')}</h2>
      {events.length === 0 ? <p className="ds-part__hint">{t('history.empty')}</p> : (
        <ul className="ds-list">
          {events.map((e, i) => (
            <li className="ds-list__item" key={i}>
              <span className="ds-list__main">{e.action}<span className="ds-part__hint"> {e.actor}, {e.at}</span></span>
              <span className={`ds-tone ds-tone--${TONE[e.result]}`}>{e.result}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
