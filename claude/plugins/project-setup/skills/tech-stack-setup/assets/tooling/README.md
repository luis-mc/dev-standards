# Tooling assets

Working implementations of `STACKSPEC §13.1`'s twelve required gates, one set
per track, plus what is genuinely language-agnostic.

Copy in Phase 7 step 1 — before any module exists, so the first commit is
already gated.

```
tooling/
├── shared/     copied for every product, whatever the track
│   ├── .gitleaks.toml
│   └── .githooks/pre-commit
├── ts/         TypeScript / Node
├── go/         Go
├── rust/       Rust
└── dotnet/     .NET
```

`shared/` is separate because gitleaks does not care what language the secret
was committed in. Duplicating it four times would mean four places to add an
allowlist entry and three of them going stale.

## The twelve gates, per track

| `§13.1` gate | ts | go | rust | dotnet |
|---|---|---|---|---|
| 1. Frozen install | `pnpm install --frozen-lockfile` | `go mod download` + `verify` + tidy-diff | `cargo fetch --locked` | `dotnet restore --locked-mode` |
| 2. Codegen drift | `turbo codegen` + `git diff` | `go generate` + `git diff` | codegen bin + `git diff` | codegen project + `git diff` |
| 3. Lint | ESLint | golangci-lint | clippy | Roslyn analyzers |
| 4. Format | Prettier | `gofmt -l` | `cargo fmt --check` | `dotnet format --verify-no-changes` |
| 5. Typecheck | `tsc` | `go build` | `cargo check` | `dotnet build` |
| 6. Unit tests | Vitest `unit` | `go test -short` | `cargo test --lib` | `Category=Unit` |
| 7. Integration | Vitest `integration` | `TestIntegration` | `--test integration` | `Category=Integration` |
| 8. Contract | Vitest `contract` | `TestContract` | `--test contract` | `Category=Contract` |
| 9. Route coverage | Vitest `authz` | `TestRouteCoverage` | `--test route_coverage` | `Category=RouteCoverage` |
| 10. Dependency scan | `pnpm audit --prod` | govulncheck | `cargo deny check advisories` | `dotnet list package --vulnerable` |
| 11. Secret scan | gitleaks, `fetch-depth: 0` | same | same | same |
| 12. Boundaries | dependency-cruiser | depguard in golangci-lint | `cargo deny check bans` | NetArchTest |

**The tool names are this generator's choice, not the spec's.** `§13.1` requires
the gates to run and fail the build; it names nothing. `§20` makes naming a
vendor in the spec a defect. Record the tools in `docs/specs/stack-profile.md`
section 2, and treat a product satisfying the same gates with different tools as
conforming.

## Gates that fail loudly by construction

Four places exist specifically so an absent check cannot masquerade as a passing
one. Preserve these when adapting any track:

- **`fetch-depth: 0` on the secret scan.** gitleaks scans history. At the
  default clone depth it silently examines one commit and reports clean.
- **Codegen drift regenerates, then diffs.** Checking only that generated files
  exist would let a stale committed artifact pass.
- **A suite finding zero tests fails** (`§11.3`). The TS config sets
  `passWithNoTests: false`; the other tracks fail on an empty filter by default,
  but verify it after changing any test filter.
- **The .NET dependency scan greps its own output.** `dotnet list package
  --vulnerable` exits 0 even when it finds vulnerabilities, so a bare invocation
  is a gate that can never fail — worse than no gate, because it reports success.

## Adapting a track

Two things to change before first use:

1. **Module and project paths.** `go/.golangci.yml` has `<module>` placeholders;
   the .NET and Rust workflows assume `src/Db`, `tools/Codegen` and a `codegen`
   binary.
2. **The database service image**, if the engine is not Postgres. `§5.5` requires
   an ephemeral real instance of *whatever engine was chosen* — not a substitute,
   and not an in-memory stand-in for a different engine.

## What is not here

**E2E tests.** `§11.2` makes them `SHOULD`, not gated. The TS track carries a
Playwright config as a starting point; no track gates on it. Where E2E is not
automated, `§11.2` requires the release checklist to name the manual journeys
verified before each release.

**Mobile CI.** `§13.3` needs macOS runners for iOS and its own path filters.
Generated per-product, because signing material and store configuration are
product-specific.
