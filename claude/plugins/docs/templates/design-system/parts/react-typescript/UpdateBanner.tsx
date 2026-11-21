import { t } from './words';

export type BannerState = 'ready' | 'running' | 'done' | 'failed';

export interface UpdateBannerProps {
  state: BannerState;
  version: string;
  /** 0 to 100, for `running`. */
  percent?: number;
  /** The one-line reason, for `failed`. */
  reason?: string;
  onUpdate?: () => void;
  onLater?: () => void;
  onRetry?: () => void;
  onClose?: () => void;
}

/** The update banner: ready, running, done, failed. One primary action per state (UX-4). */
export function UpdateBanner(p: UpdateBannerProps) {
  const tone = p.state === 'failed' ? 'problem' : p.state === 'done' ? 'done' : 'note';
  return (
    <div className={`ds-part ds-banner--${p.state}`} data-ds-part="update-banner" data-state={p.state} role="status">
      <div className="ds-row">
        <span className={`ds-tone ds-tone--${tone}`}>{t(`banner.${p.state}`)}</span>
        <p className="ds-part__text">{p.version}</p>
      </div>
      {p.state === 'running' && <progress className="ds-progress" max={100} value={p.percent ?? 0} aria-label={t('banner.running')} />}
      {p.state === 'failed' && p.reason && <p className="ds-part__hint">{p.reason}</p>}
      <div className="ds-row ds-row--end">
        {p.state === 'ready' && (<>
          <button type="button" className="ds-btn" onClick={p.onLater}>{t('action.later')}</button>
          <button type="button" className="ds-btn ds-btn--primary" onClick={p.onUpdate}>{t('action.update_now')}</button>
        </>)}
        {p.state === 'failed' && (<>
          <button type="button" className="ds-btn" onClick={p.onClose}>{t('action.close')}</button>
          <button type="button" className="ds-btn ds-btn--primary" onClick={p.onRetry}>{t('action.retry')}</button>
        </>)}
        {p.state === 'done' && <button type="button" className="ds-btn ds-btn--primary" onClick={p.onClose}>{t('action.close')}</button>}
        {p.state === 'running' && <button type="button" className="ds-btn" onClick={p.onClose}>{t('action.cancel')}</button>}
      </div>
    </div>
  );
}
