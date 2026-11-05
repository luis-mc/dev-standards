import { test } from '@playwright/test';
import { expectDomLayout, type KnownLayoutBreach } from './dom-layout.ts';

// Example Playwright spec for the DOM layout checker. Copy it per app, list the app's screens, and keep the
// known list next to it (a screen that breaks a rule today, with the task that fixes it; the list only shrinks).
// Run it with the project's e2e command. It uses the DOM only: no screenshots, no baseline images.
const KNOWN: KnownLayoutBreach[] = [];

const SCREENS: { name: string; path: string; primary?: string }[] = [
  { name: 'home', path: '/' },
  // { name: 'import wizard', path: '/import', primary: '[data-primary]' },
];

for (const screen of SCREENS) {
  test(`layout: ${screen.name}`, async ({ page }) => {
    await page.goto(screen.path);
    await page.waitForLoadState('networkidle');
    await expectDomLayout(page, screen.name, { known: KNOWN, primary: screen.primary });
  });
}
