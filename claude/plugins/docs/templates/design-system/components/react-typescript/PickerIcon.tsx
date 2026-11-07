// The chevron the picker templates share (luismc-docs component template). Decoration only: the button names the action.
export function Chevron({ dir }: { dir: 'left' | 'right' | 'up' | 'down' }) {
  return (
    <svg className="ds-picker-icon" data-dir={dir} viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <path d="M9 5l7 7-7 7" fill="none" stroke="currentColor" strokeWidth="2.5" />
    </svg>
  );
}
