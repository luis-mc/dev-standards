#!/usr/bin/env python3
"""Prove every gating authspec_check.py check fires.

These checks read AUTHSPEC's own structures — §4's entity tables, §19.4's
routes, §23's retention sections, §24.2's configuration reference — so they are
tested by mutating the real document rather than a synthetic one. A minimal
fixture would not exercise the parsing that actually breaks.

Each case introduces exactly one defect and asserts the corresponding check
reports it. This file exists because of what happened without it: `retired` and
`gate-citations` read identifiers (`R27.23`, `§27.2.1`) that were never in the
document, so both sat inside a *blocking* CI gate reporting success for their
entire existence. `erasure` searched §15.4 for entity names and passed on
entities that were only mentioned in nearby prose. `config` asked a question
whose answer was "no" for all 27 rows, so it reported 27 findings
unconditionally and could not have reported anything else.

A check that cannot fail is not a check. Adding one here is the cost of adding
one there.

Run:  python3 tools/test_authspec_check.py
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import authspec_check as AC  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = (ROOT / "claude/plugins/project-setup/skills/auth-setup"
        / "references/authentication.md")
BASE = SPEC.read_text()
ROUTE_MAP = ROOT / "tools" / "route-ratelimit-map.json"


def routes(route_map=ROUTE_MAP):
    """check 8 takes the route map as a second argument, so bind it here."""
    return lambda spec: AC.check_route_buckets(spec, route_map)


def mutate(old: str, new: str) -> str:
    """BASE with one substitution, asserting the anchor exists exactly once.

    Both assertions have already earned their place. If a spec edit moves the
    text a case anchors to, the first fails loudly rather than silently testing
    an unmutated document and "passing" because the real spec is clean.

    The second catches the subtler one: `/.well-known/jwks.json` appears in
    R6.10 as well as in §19.4's route table, so anchoring on the bare path
    mutated a line the check does not read. The case then reported "no findings"
    — indistinguishable, from the output alone, from a check that had stopped
    working. An ambiguous anchor is a test that may not be testing anything.
    """
    count = BASE.count(old)
    assert count == 1, (
        f"anchor appears {count} times in AUTHSPEC, need exactly 1: {old[:60]!r}")
    return BASE.replace(old, new, 1)


# (name, mutated document, check function, substring the finding must contain)
CASES = [
    # -- check 2, retired ---------------------------------------------------
    ("retired: a retired identifier is cited",
     mutate("- **R27.11** — **Retired identifier registry.**",
            "- **R27.11** — **Retired identifier registry.** R4.1."),
     AC.check_retired, "R4.1"),
    ("retired: the registry itself is gone",
     mutate("**Retired identifier registry.**", "**Withdrawn numbers.**"),
     AC.check_retired, "cannot"),

    # -- check 4, attributes ------------------------------------------------
    ("attributes: a column name that is in no §4 table",
     mutate("### 27.1 Audit gate", "### 27.1 Audit gate\n\nSee `bogus_column`."),
     AC.check_attributes, "bogus_column"),

    # -- check 5, enum-values -----------------------------------------------
    ("enum-values: a declared value nothing reads",
     mutate("`enum(cookie, bearer)`", "`enum(cookie, bearer, carrier_pigeon)`"),
     AC.check_enum_values, "carrier_pigeon"),

    # -- check 6, erasure ---------------------------------------------------
    ("erasure: an entity with no disposition row",
     mutate("| `break_glass_activation` | admin |",
            "| break_glass_activation | admin |"),
     AC.check_erasure_coverage, "break_glass_activation"),
    ("erasure: a row naming a table §4 does not declare",
     mutate("| `recovery_code` | user |", "| `recovery_codes` | user |"),
     AC.check_erasure_coverage, "recovery_code"),
    ("erasure: the disposition table is gone",
     mutate("#### 15.4.1 Erasure disposition", "#### Erasure disposition"),
     AC.check_erasure_coverage, "not found"),

    # -- check 7, retention -------------------------------------------------
    ("retention: a growth table with no §23.2 row",
     mutate("| `security_event` | 1 year | Security operations |",
            "| security_event | 1 year | Security operations |"),
     AC.check_retention_jobs, "§23.2 retention row"),
    ("retention: a growth table no §23.3 job prunes",
     mutate("| Attempt/security-event pruner | Daily | Drains `auth_attempt` "
            "and `security_event` per §23.2 |",
            "| Attempt pruner | Daily | Drains `auth_attempt` per §23.2 |"),
     AC.check_retention_jobs, "§23.3 job"),

    # -- check 8, routes ----------------------------------------------------
    # One mutation, both directions: the renamed path has no bucket, and the
    # map's original entry no longer matches anything in §19.4.
    ("routes: a §19.4 route with no bucket",
     mutate("| GET | `/.well-known/jwks.json` | Public verification keys",
            "| GET | `/.well-known/jwks2.json` | Public verification keys"),
     routes(), "/.well-known/jwks2.json has no entry"),
    ("routes: the map buckets a route §19.4 does not declare",
     mutate("| GET | `/.well-known/jwks.json` | Public verification keys",
            "| GET | `/.well-known/jwks2.json` | Public verification keys"),
     routes(), "which is not in §19.4"),
    ("routes: no route map supplied",
     BASE, routes(None), "No route map was supplied"),

    # -- check 9, indexes ---------------------------------------------------
    ("indexes: an entity indexed in §4 with no R22.7 inventory row",
     mutate("| `principal_role` | (`principal_type`, `principal_id`) partial "
            "on active | Permission resolution |",
            "| `principal_roles` | (`principal_type`, `principal_id`) partial "
            "on active | Permission resolution |"),
     AC.check_index_inventory, "principal_role"),

    # -- check 10, gate-citations -------------------------------------------
    ("gate-citations: a release gate cites an undefined requirement",
     mutate("### 27.2", "### 27.2 R99.9 gate"),
     AC.check_citations_in_gates, "R99.9"),

    # -- check 11, config ---------------------------------------------------
    ("config: a default the governing clause contradicts",
     mutate("| `session.user.idle` | 30 d | 30 d | §6.3 |",
            "| `session.user.idle` | 77 d | 30 d | §6.3 |"),
     AC.check_config_keys, "does not state 77"),
    ("config: a row pointing at a clause that does not exist",
     mutate("| `assertion.lifetime` | 120 s | 300 s | §6.4 |",
            "| `assertion.lifetime` | 120 s | 300 s | §6.99 |"),
     AC.check_config_keys, "does not resolve"),
]

# Checks that must report nothing against the real, unmutated document. A fire
# test proves a check *can* fail; this proves it is not failing on everything,
# which is the other way a check becomes noise nobody reads.
CLEAN = [
    ("retired", AC.check_retired),
    ("attributes", AC.check_attributes),
    ("enum-values", AC.check_enum_values),
    ("erasure", AC.check_erasure_coverage),
    ("retention", AC.check_retention_jobs),
    ("routes", routes()),
    ("indexes", AC.check_index_inventory),
    ("gate-citations", AC.check_citations_in_gates),
    ("config", AC.check_config_keys),
]


def main() -> int:
    failures = 0

    for name, text, fn, expected in CASES:
        findings = [f for f in fn(AC.Spec(text)) if f.level != AC.INFO]
        hit = any(expected in f.message for f in findings)
        if hit:
            print(f"PASS  {name:52s} fired")
        else:
            failures += 1
            got = findings[0].message if findings else "no findings at all"
            print(f"FAIL  {name:52s} expected {expected!r}, got: {got}")

    base_spec = AC.Spec(BASE)
    for name, fn in CLEAN:
        noise = [f for f in fn(base_spec) if f.level != AC.INFO]
        if noise:
            failures += 1
            print(f"FAIL  clean: {name:45s} {len(noise)} finding(s) on the "
                  f"real spec: {noise[0].message}")
        else:
            print(f"PASS  clean: {name:45s} silent on the real spec")

    total = len(CASES) + len(CLEAN)
    print(f"\n{total - failures}/{total} cases behaved as specified")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
