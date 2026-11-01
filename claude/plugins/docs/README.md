# luismc-docs

The documentation standard for every project, to **DOCSPEC** (`references/docspec.md`). It is generic: nothing in it belongs to one project.

| Part | What it does |
|---|---|
| `docs-setup` | Lay out `docs/` (overview, features, design-system, architecture, guides, reference, project); move an existing repo with `git mv` and link rewriting (dry run by default); move the artifacts record to `docs/project` |
| `feature-spec-new` | Write `docs/features/<feature>/spec.md` from the template: why / what / how, requirements, visuals, for product and engineering readers |
| `docs-index` | Build `docs/index.html` (offline, search, feature index by app and topic, gaps), `docs/_site/`, `features/index.md`, `decisions.md`, `docs-map.json`, `llms.txt` |
| `docs-check` | Links, `Source:` lines, front matter, version tables, generated files and reference, code-to-doc map, `docs/work` guard, UX rules, freshness |
| `design-system-setup` | Create `docs/design-system/` (README with the order of work, `next-version/` with rules, components, tokens, words, changes and an offline gallery); promote `next-version` to read-only `v1`, `v2` ... only with a recorded owner approval; guard-test templates per stack (DOCSPEC §15) |
| `docs-note` | One-line change notes; the release fold writes one version row per doc per release |
| Hooks | SessionStart hands the agent the docs rule; Stop warns when mapped code changed without docs. Opt-in with `docs/docs.json`; they only warn |

Bundled: `vendor/mermaid.min.js`, Mermaid 11.4.1 from the npm package `mermaid@11.4.1` (MIT, `vendor/LICENSE-mermaid`). `docs_index.py` uses it by default (`--mermaid PATH` and `fetch-mermaid` override).

Scripts (`scripts/`, Python standard library only): `docs_setup.py`, `docs_index.py`, `docs_fold.py`, `docs_check.py`, `docs_work.py`, `design_system.py`, `docs_lib.py`, `hook_stop.py`, `hook_session_start.py`. Tests: `python3 -I -m unittest discover -s claude/plugins/docs/tests`.

Install: `claude plugin install luismc-docs@dev-standards`. First use in a repo: `python3 <plugin>/scripts/docs_setup.py migrate` (plan), then `--apply`, set `apps` and `topics` in `docs/docs.json`, `docs_index.py build`, `docs_check.py`.

Settings live in `docs/docs.json`: `apps`, `topics`, `record_dir` (default `docs/project`), `default_branch`, `stale_days` (90), `binding`, `code_roots`, `generated_reference`.
