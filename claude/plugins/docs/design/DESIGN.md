# Design for project artifacts

Every project's artifacts follow that project's own design. A project without a design uses the default design in this folder.

## Finding a project's design

The plugin looks for the project's design by scanning, in this order:

1. Design-token files.
2. Tailwind or theme configuration.
3. CSS custom properties in the app.
4. The project's live site, if the manifest names a URL.

It shows what it found and asks before using it. If nothing is found, or the answer is no, it uses the default.

## The default design

`default-design.css` holds the default tokens: fonts, light colours, and dark colours. Its layout concept is a spec sheet: a contents rail on the left, numbered sections, the status checklist first.

The fonts are plain, legible and built for scanning status. Archivo (semi-condensed) is for headings, Public Sans for text, and IBM Plex Mono for IDs, times and labels.

## The token contract

Any project design must supply these token names, with its own values. A project design is the same names as the default with different values. Light values go on `:root`. Dark values go under `@media (prefers-color-scheme: dark)` with `:root:not([data-theme="light"])`, and again under `:root[data-theme="dark"]`.

- Fonts: `--font-display`, `--font-display-stretch`, `--font-body`, `--font-mono`
- Surfaces and text: `--paper`, `--surface`, `--surface-2`, `--ink`, `--ink-muted`
- Lines: `--rule`, `--rule-strong`
- Accent: `--signal`, `--on-signal`, `--focus`
- Status colours: `--live`, `--on-live`, `--done-bg`, `--running-bg`, `--running-mark`, `--waiting-bg`, `--failed`, `--on-failed`

## The structure stylesheet

`../templates/project-artifact.css` is the fixed structure. It uses the tokens above and never holds a colour. Every project's artifacts use it unchanged, so only the tokens differ between projects.
