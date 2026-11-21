import { t } from './words';

export type FleetState = 'up_to_date' | 'waiting' | 'needs_you';

export interface FleetRow {
  machine: string;
  version: string;
  state: FleetState;
}

const TONE = { up_to_date: 'done', waiting: 'note', needs_you: 'needs-you' } as const;

/** One row per machine: Up to date, Waiting or Needs you. The state is a word, never colour alone (UX-26). */
export function FleetRows({ rows }: { rows: readonly FleetRow[] }) {
  return (
    <ul className="ds-part ds-list" data-ds-part="fleet-rows" aria-label="Machines">
      {rows.map((r) => (
        <li className="ds-list__item" key={r.machine} data-state={r.state}>
          <span className="ds-list__main">{r.machine}<span className="ds-part__hint"> {r.version}</span></span>
          <span className={`ds-tone ds-tone--${TONE[r.state]}`}>{t(`fleet.${r.state}`)}</span>
        </li>
      ))}
    </ul>
  );
}
