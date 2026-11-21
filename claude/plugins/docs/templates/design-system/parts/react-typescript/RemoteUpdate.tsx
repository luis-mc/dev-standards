import { t } from './words';

export interface RemoteUpdateProps {
  machine: string;
  from: string;
  to: string;
  state: 'ready' | 'running' | 'done' | 'failed';
  percent?: number;
  onStart?: () => void;
}

/** Start an update on another machine from a phone (360 to 393 px). One column, one primary action. */
export function RemoteUpdate(p: RemoteUpdateProps) {
  return (
    <section className="ds-part ds-remote" data-ds-part="remote-update" data-state={p.state} aria-labelledby="ds-remote-title">
      <h2 className="ds-part__title" id="ds-remote-title">{t('remote.title')}</h2>
      <p className="ds-part__text">{p.machine}</p>
      <p className="ds-part__hint">{p.from} to {p.to}</p>
      {p.state === 'running' && <progress className="ds-progress" max={100} value={p.percent ?? 0} aria-label={t('banner.running')} />}
      {p.state !== 'ready' && <p className="ds-part__text"><span className={`ds-tone ds-tone--${p.state === 'failed' ? 'problem' : p.state === 'done' ? 'done' : 'note'}`}>{t(`banner.${p.state}`)}</span></p>}
      {p.state === 'ready' && <button type="button" className="ds-btn ds-btn--primary" onClick={p.onStart}>{t('remote.start')}</button>}
    </section>
  );
}
