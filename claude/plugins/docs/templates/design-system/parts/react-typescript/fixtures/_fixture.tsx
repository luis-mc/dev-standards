import { createRoot } from 'react-dom/client';
import type { ReactNode } from 'react';
import { PageSections, Section, CardGrid } from '../layout';

/** Render a list of labelled states of one part into #root, as the page's sections. */
export function mount(states: ReadonlyArray<readonly [string, ReactNode]>): void {
  createRoot(document.getElementById('root')!).render(
    <PageSections>
      {states.map(([label, node]) => (
        <Section key={label} label={label}><CardGrid>{node}</CardGrid></Section>
      ))}
    </PageSections>,
  );
}
