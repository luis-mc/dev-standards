# Testing in dev-standards

The shipped agents rule ("Agents test only what they touch") applies here too. How it maps onto this repository:

- **Which case am I?** `python tools/ci_areas.py --branch-advice` reads the branch's diff against `origin/main` and prints `light: test locally only` or `heavy: <areas> -> run ...`.
- **Light** (the `specs` or `profiles` area: specs, skill text, rules): run the touched suites locally.
- **Heavy** (the `delivery` or `artifacts` area): a 1-2 minute local smoke (`-k <scenario>` of what you changed, `--no-mutants`), then `gh workflow run spec-lint.yml --ref <branch> -f areas=<areas>` and watch it with `python claude/plugins/project-setup/skills/tech-stack-setup/assets/tooling/shared/scripts/delivery/ci_watch.py <sha> --workflow spec-lint.yml`.
- **The ready PR** runs only the areas its diff touches, with the mutation passes only when the delivery scripts or their suites change. `nightly.yml` runs every area with mutants on `main`.
- Suites, areas and the path map: `tools/ci_areas.py`. Measurements behind these choices: `docs/artifacts/feature-test-and-validation-cost.html`.
