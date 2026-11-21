# Design-system guards (DS234) and lifecycle guards (LC-22 to LC-30)

Node scripts, no build step. Each prints one line per problem and exits 1 on any. Rendered guards need Playwright (`DS_NODE_MODULES` points at the folder that has it).

| Guard | Script | Proves |
|---|---|---|
| A | `design-guards/rendered-layout.mjs <page.html>...` | no box overlaps a neighbour at 360, 393, 1300 and 1800 px, counting focus outline, glow and shadow; section gap equals the section token |
| B | `design-guards/spacing-tokens.mjs <dir>` | no fixed px or rem in margin, padding or gap outside token files |
| C | `design-guards/layout-roles.mjs <root>` | one component per layout role; no plain gap at a page's top level |
| D | `design-guards/none-yet.mjs <ux-rules.md>` | `none yet (YYYY-MM-DD)` expires after `none_yet_days` (default 30, `tools/design-guards.json`) |
| E | `design-guards/citation-test.mjs <root>` | a spec that cites a UX or CORE rule names a test file that exists |
| LC-22, LC-30 | `lifecycle/tray-modal.mjs <dir>` | the tray never opens a modal, one notice per event per 24 h; no fixed-size window |
| LC-23 | `lifecycle/parts-tokens.mjs <parts-dir>` | parts use the shared class and tokens only |
| LC-24, LC-30 | `lifecycle/states-render.mjs <page.html>...` | every state renders without clipping or overlap at 100 to 200% and 360 px |

The starter rules still say bare `none yet`. A project dates each one when it adopts guard D.
