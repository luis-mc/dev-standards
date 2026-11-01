# Tokens

> **Starter.** Every item in this file is a starter item. Keep, change or delete each one before v1 is approved.

Use tokens and nothing else: no raw colour, size or font in a screen. The values are given here and nowhere else.

**Prefix:** `--ds-`

## How themes work

- The light values are the default.
- The dark values apply under `@media (prefers-color-scheme: dark)` and under `[data-theme=dark]`. The attribute wins over the system setting.
- A token has the same name in every theme. Only its value changes.
- Text and its background meet WCAG 2.2 AA contrast in every theme (UX-17): at least 4.5:1 for text, 3:1 for large text and for borders of controls.

```css
:root { --ds-color-page: #f6f7f9; }
@media (prefers-color-scheme: dark) {
  :root:not([data-theme=light]) { --ds-color-page: #14171a; }
}
[data-theme=dark] { --ds-color-page: #14171a; }
```

## Colour

| Token | Light | Dark | Use |
|---|---|---|---|
| `--ds-color-page` | `#f6f7f9` | `#14171a` | page background |
| `--ds-color-surface` | `#ffffff` | `#1c2024` | cards, dialogs, inputs |
| `--ds-color-text` | `#1b1f24` | `#e8ebee` | body text |
| `--ds-color-text-muted` | `#4f5a66` | `#a4aeb9` | secondary text, hints |
| `--ds-color-border` | `#7a8590` | `#6b7681` | borders of controls |
| `--ds-color-divider` | `#d4d9de` | `#32383f` | lines between sections |
| `--ds-color-primary` | `#0b57d0` | `#8ab4f8` | the primary action, links in text |
| `--ds-color-on-primary` | `#ffffff` | `#0b1b33` | text on the primary action |
| `--ds-color-done` | `#146c2e` | `#7fd99b` | the Done tone |
| `--ds-color-done-bg` | `#e6f4ea` | `#14301f` | background of Done |
| `--ds-color-note` | `#1f5fa8` | `#8dc1f5` | the Note tone |
| `--ds-color-note-bg` | `#e8f1fb` | `#15283c` | background of Note |
| `--ds-color-needs-you` | `#8a5300` | `#f2c46d` | the Needs you tone |
| `--ds-color-needs-you-bg` | `#fff4dc` | `#3a2c0f` | background of Needs you |
| `--ds-color-problem` | `#b3261e` | `#f5a29b` | the Problem tone |
| `--ds-color-problem-bg` | `#fdecea` | `#3d1815` | background of Problem |
| `--ds-color-focus` | `#0b57d0` | `#8ab4f8` | the focus ring |

A tone is never shown by colour alone (UX-26). It always has a word or an icon too.

## Type families

System font stacks only. Nothing is bundled and nothing is loaded from the network.

| Token | Value | Use |
|---|---|---|
| `--ds-font-body` | `system-ui, -apple-system, "Segoe UI", sans-serif` | all text |
| `--ds-font-mono` | `ui-monospace, "SF Mono", Menlo, Consolas, monospace` | code |

## Type scale

| Token | Value | Use |
|---|---|---|
| `--ds-size-1` | `0.75rem` | badge |
| `--ds-size-2` | `0.875rem` | hint, secondary text |
| `--ds-size-3` | `1rem` | body, label, button |
| `--ds-size-4` | `1.125rem` | subtitle |
| `--ds-size-5` | `1.25rem` | section title |
| `--ds-size-6` | `1.75rem` | page title |
| `--ds-line-height` | `1.5` | body text |
| `--ds-line-height-tight` | `1.25` | titles |

## Type roles

| Role | Size | Weight | Family |
|---|---|---|---|
| Page title | `--ds-size-6` | 700 | `--ds-font-body` |
| Section title | `--ds-size-5` | 600 | `--ds-font-body` |
| Subtitle | `--ds-size-4` | 400 | `--ds-font-body` |
| Body | `--ds-size-3` | 400 | `--ds-font-body` |
| Label | `--ds-size-3` | 600 | `--ds-font-body` |
| Button | `--ds-size-3` | 600 | `--ds-font-body` |
| Secondary | `--ds-size-2` | 400 | `--ds-font-body` |
| Hint | `--ds-size-2` | 400 | `--ds-font-body` |
| Badge | `--ds-size-1` | 600 | `--ds-font-body` |
| Code | `--ds-size-2` | 400 | `--ds-font-mono` |

## Spacing

| Token | Value | Use |
|---|---|---|
| `--ds-space-0` | `0` | none |
| `--ds-space-1` | `4px` | tight gaps |
| `--ds-space-2` | `8px` | gap inside a control |
| `--ds-space-3` | `12px` | gap between related items |
| `--ds-space-4` | `16px` | default gap, page gutter on a phone |
| `--ds-space-5` | `24px` | gap between cards |
| `--ds-space-6` | `32px` | gap between sections |
| `--ds-space-7` | `48px` | page padding on wide screens |
| `--ds-target-min` | `44px` | smallest touch target (UX-16) |

## Radius

| Token | Value | Use |
|---|---|---|
| `--ds-radius-1` | `4px` | inputs, badges |
| `--ds-radius-2` | `8px` | buttons, cards |
| `--ds-radius-3` | `16px` | dialogs, sheets |
| `--ds-radius-round` | `999px` | chips, switches |

## Shadows

| Token | Light | Dark | Use |
|---|---|---|---|
| `--ds-shadow-1` | `0 1px 2px rgba(0, 0, 0, 0.12)` | `0 1px 2px rgba(0, 0, 0, 0.5)` | cards |
| `--ds-shadow-2` | `0 4px 12px rgba(0, 0, 0, 0.16)` | `0 4px 12px rgba(0, 0, 0, 0.6)` | sticky bars, menus |
| `--ds-shadow-3` | `0 12px 32px rgba(0, 0, 0, 0.24)` | `0 12px 32px rgba(0, 0, 0, 0.7)` | dialogs, sheets |

## Breakpoints

A screen works from 360 px up (UX-16). Write layouts mobile first.

| Token | Value | Use |
|---|---|---|
| `--ds-bp-min` | `360px` | the smallest supported width |
| `--ds-bp-sm` | `600px` | phone to tablet |
| `--ds-bp-md` | `900px` | tablet to desktop |
| `--ds-bp-lg` | `1200px` | wide screens |
| `--ds-bp-xl` | `1600px` | very wide screens |

CSS cannot read a custom property inside a media query. Write these values in the query itself.

## Layout

| Token | Value | Use |
|---|---|---|
| `--ds-card-min` | `280px` | smallest card width in a card grid (UX-10) |
| `--ds-width-field-short` | `8rem` | short box (UX-23) |
| `--ds-width-field-medium` | `20rem` | medium box (UX-23) |
| `--ds-width-field-full` | `100%` | full box (UX-23) |

## Motion

| Token | Value | Use |
|---|---|---|
| `--ds-duration-fast` | `100ms` | hover, press |
| `--ds-duration-base` | `200ms` | open and close |
| `--ds-duration-slow` | `400ms` | sheets, page changes |
| `--ds-duration-loop` | `1200ms` | one turn of a looping bar or spinner |
| `--ds-ease` | `cubic-bezier(0.2, 0, 0, 1)` | all movement |
| `--ds-ease-in-out` | `cubic-bezier(0.42, 0, 0.58, 1)` | movement that starts and ends at rest |

Motion has a purpose: it shows where something came from or went to (UX-36).

Under `prefers-reduced-motion: reduce` every duration is `0ms` and nothing animates, except a progress bar of unknown total, which shows a static striped fill (UX-17, UX-29).

## Row heights

Starter values. Change to fit.

| Token | Value | Use |
|---|---|---|
| `--ds-row` | `56px` | a list row without a picture (UX-25) |
| `--ds-row-picture` | `88px` | a list row with a picture |
| `--ds-hairline` | `1px` | a thin quiet edge or rule between rows |
| `--ds-icon-size` | `16px` | a small icon beside text |

## Tone shapes

A tone is also told by the shape of its edge, so it never rests on colour alone (UX-26). Starter values. Change to fit.

| Tone | Edge |
|---|---|
| Done | `3px solid` |
| Note | `2px solid` |
| Needs you | `3px dashed` |
| Problem | `6px double` |

| Token | Value | Use |
|---|---|---|
| `--ds-tone-bar` | `12px` | the bar down the left of a message |

## Focus

| Token | Value | Use |
|---|---|---|
| `--ds-focus-width` | `3px` | width of the focus ring |
| `--ds-focus-offset` | `2px` | gap between a control and its ring |

- Every control shows the ring on `:focus-visible`, in `--ds-color-focus` (UX-17).
- Under `forced-colors: active` the ring uses the system colour `Highlight`.

## Z-order

One scale. A screen never writes a raw `z-index` (UX-1).

| Token | Value | Use |
|---|---|---|
| `--ds-z-base` | `0` | page content |
| `--ds-z-sticky` | `100` | sticky bars and docked headers |
| `--ds-z-menu` | `200` | menus and pop-overs |
| `--ds-z-overlay` | `300` | the dimmed page behind a dialog |
| `--ds-z-dialog` | `400` | dialogs and sheets |
| `--ds-z-toast` | `500` | the one app-wide banner when it floats |

## Density

A project may offer a compact density. It changes only these tokens. The touch target stays `--ds-target-min` (UX-16).

| Token | Comfortable | Compact | Use |
|---|---|---|---|
| `--ds-row` | `56px` | `44px` | list row height |
| `--ds-space-3` | `12px` | `8px` | gap between related items |
| `--ds-space-5` | `24px` | `16px` | gap between cards |

## Use your own font

1. Add a family token, for example `--ds-font-brand`, with the font and then the system stack as fallback.
2. Point the role you want to change at it (for example, the page title) in this file.
3. Load the font file from the project's own files. Never from another site.
4. Check the contrast and the line length again.
5. Add a `CHANGES.md` entry.

## Add a named theme

1. Choose a name, for example `high-contrast`.
2. Give every colour token a value under `[data-theme=high-contrast]`. A theme never leaves a token out.
3. Check WCAG 2.2 AA contrast for each pair (UX-17).
4. Add a way to pick the theme in the settings.
5. Add a `CHANGES.md` entry.
