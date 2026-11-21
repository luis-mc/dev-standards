import type { ReactNode } from 'react';

/** The layout roles (UX-66). A page's top level uses these; it never sets its own gap. */
export function PageSections({ children }: { children: ReactNode }) {
  return <main className="ds-page-sections" data-ds-page data-ds-component="page-sections">{children}</main>;
}

export function Section({ children, label }: { children: ReactNode; label: string }) {
  return <section data-ds-section aria-label={label}>{children}</section>;
}

export function CardGrid({ children }: { children: ReactNode }) {
  return <div className="ds-card-grid" data-ds-component="card-grid">{children}</div>;
}

export function FormStack({ children }: { children: ReactNode }) {
  return <div className="ds-form-stack" data-ds-component="form-stack">{children}</div>;
}
