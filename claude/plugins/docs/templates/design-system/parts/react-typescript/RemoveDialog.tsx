import { useState } from 'react';
import { t } from './words';

export type RemoveChoice = 'keep' | 'purge';

export interface RemoveDialogProps {
  /** Size of the user's data, already formatted (for example `1.4 GB`). */
  size: string;
  /** Where the data lives. */
  path: string;
  initial?: RemoveChoice;
  onRemove?: (choice: RemoveChoice) => void;
  onCancel?: () => void;
}

/** Remove asks every time with no default: Remove stays disabled until a choice is made (lifecycle contract). */
export function RemoveDialog(p: RemoveDialogProps) {
  const [choice, setChoice] = useState<RemoveChoice | undefined>(p.initial);
  return (
    <section className="ds-part" data-ds-part="remove-dialog" role="dialog" aria-labelledby="ds-remove-title">
      <h2 className="ds-part__title" id="ds-remove-title">{t('remove.title')}</h2>
      <p className="ds-part__text">{t('remove.choose')}</p>
      <p className="ds-part__hint">{p.size}, {p.path}</p>
      <fieldset className="ds-stack ds-fieldset">
        {(['keep', 'purge'] as RemoveChoice[]).map((k) => (
          <label className="ds-choice" key={k}>
            <input type="radio" name="remove" checked={choice === k} onChange={() => setChoice(k)} />
            <span>{t(`remove.${k}`)}</span>
          </label>
        ))}
      </fieldset>
      <div className="ds-row ds-row--end">
        <button type="button" className="ds-btn" onClick={p.onCancel}>{t('remove.cancel')}</button>
        <button type="button" className="ds-btn ds-btn--primary" disabled={!choice} onClick={() => choice && p.onRemove?.(choice)}>{t('remove.confirm')}</button>
      </div>
    </section>
  );
}
