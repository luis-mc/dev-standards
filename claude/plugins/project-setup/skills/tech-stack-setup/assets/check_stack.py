#!/usr/bin/env python3
"""Validate a stack selection against the catalog, and the catalog against itself.

Two modes, because they fail differently and both failures are expensive:

  --catalog        Check the catalog files parse and are internally consistent.
                   Run this after editing any YAML under assets/catalog/.

  --selection F    Check one product's selections. F is a YAML or JSON mapping
                   of role -> technology id, which is what the wizard produces
                   at the end of Phase 3 and what the Stack Profile records.

The point of the selection mode is that consistency is MECHANICAL rather than
remembered. A wizard that reasons its way to "Go on Vercel" in a long session is
exactly the failure this script exists to make impossible.

Exit codes:
    0  everything checked passed
    1  at least one error
    2  bad arguments, or PyYAML missing
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("BLOCKED: PyYAML is required.\n\n  pip install pyyaml", file=sys.stderr)
    sys.exit(2)

CATALOG = Path(__file__).parent / "catalog"

# Hosting scores that mean "do not put an API deployable here".
UNUSABLE = {"none", "degraded"}


def load(name: str) -> dict:
    path = CATALOG / name
    if not path.exists():
        raise FileNotFoundError(f"catalog file missing: {path}")
    return yaml.safe_load(path.read_text()) or {}


def ids(node: dict, key: str) -> set[str]:
    """Every `id` under node[key], tolerating the several shapes the files use."""
    section = node.get(key) or []
    if isinstance(section, dict):
        section = section.get("technologies", [])
    return {e["id"] for e in section if isinstance(e, dict) and "id" in e}


# ---------------------------------------------------------------------------
# Catalog self-check
# ---------------------------------------------------------------------------

def check_catalog() -> list[str]:
    errors: list[str] = []

    roles = load("roles.yaml")
    languages = load("tech/languages.yaml")
    hosting = load("tech/hosting.yaml")
    data = load("tech/data.yaml")
    frameworks = load("tech/frameworks.yaml")
    services = load("tech/services.yaml")
    bundles = load("bundles.yaml")

    lang_ids = ids(languages, "technologies")
    host_ids = ids(hosting, "technologies")
    engine_ids = ids(data, "engines")
    dbhost_ids = ids(data, "hosts")
    web_ids = ids(frameworks, "web")
    api_ids = ids(frameworks, "api")

    known = {
        "language": lang_ids,
        "hosting": host_ids,
        "db_engine": engine_ids,
        "db_host": dbhost_ids,
        "web_framework": web_ids,
        "api_framework": api_ids,
        "cache": ids(services.get("cache", {}), "technologies"),
        "object_storage": ids(services.get("object_storage", {}), "technologies"),
        "mail": ids(services.get("mail", {}), "technologies"),
        "error_tracking": ids(services.get("error_tracking", {}), "technologies"),
    }

    # Every language must score every hosting class it could meet.
    for lang in languages.get("technologies", []):
        scores = lang.get("hosting") or {}
        if not scores:
            errors.append(f"language '{lang['id']}' scores no hosting classes")

    # Framework tracks must name a real language.
    for section in ("web", "api"):
        for fw in frameworks.get(section, []):
            track = fw.get("track")
            if track and track not in lang_ids:
                errors.append(
                    f"{section} framework '{fw['id']}' declares unknown track '{track}'")

    # A db host must name engines that exist.
    for host in data.get("hosts", []):
        engines = host.get("engine")
        engines = engines if isinstance(engines, list) else [engines]
        for e in engines:
            if e and e not in engine_ids:
                errors.append(
                    f"db host '{host['id']}' declares unknown engine '{e}'")

    # Every engine must answer every declared capability.
    declared = set(data.get("capability_definitions", {}))
    for engine in data.get("engines", []):
        answered = set(engine.get("capabilities") or {})
        for missing in sorted(declared - answered):
            errors.append(
                f"engine '{engine['id']}' does not answer capability '{missing}'")

    # Bundle selections must reference real technologies.
    for bundle in bundles.get("bundles", []):
        for role, value in (bundle.get("selections") or {}).items():
            if role not in known:
                continue  # derived roles carry prose values, not ids
            for v in (value if isinstance(value, list) else [value]):
                if v not in known[role]:
                    errors.append(
                        f"bundle '{bundle['id']}' selects unknown {role} '{v}'")

    # Roles referenced by the entry paths must exist.
    role_ids = {r["id"] for r in roles.get("roles", [])}
    for path_id, path in (roles.get("entry_paths") or {}).items():
        for role in path.get("order", []):
            if role != "derived" and role not in role_ids:
                errors.append(
                    f"entry path '{path_id}' orders unknown role '{role}'")

    return errors


# ---------------------------------------------------------------------------
# Selection check
# ---------------------------------------------------------------------------

def check_selection(path: Path) -> tuple[list[str], list[str]]:
    """Returns (errors, warnings) for one product's role assignments."""
    text = path.read_text()
    sel = json.loads(text) if path.suffix == ".json" else yaml.safe_load(text)
    if not isinstance(sel, dict):
        return ([f"{path}: expected a mapping of role -> technology id"], [])

    errors: list[str] = []
    warnings: list[str] = []

    languages = load("tech/languages.yaml")
    hosting = load("tech/hosting.yaml")
    data = load("tech/data.yaml")

    lang_id = sel.get("language")
    host_id = sel.get("hosting")
    engine_id = sel.get("db_engine")

    lang = next((t for t in languages.get("technologies", [])
                 if t["id"] == lang_id), None)
    host = next((t for t in hosting.get("technologies", [])
                 if t["id"] == host_id), None)
    engine = next((e for e in data.get("engines", [])
                   if e["id"] == engine_id), None)

    if lang_id and not lang:
        errors.append(f"unknown language '{lang_id}'")
    if host_id and not host:
        errors.append(f"unknown hosting '{host_id}'")
    if engine_id and not engine:
        errors.append(f"unknown db_engine '{engine_id}'")

    # The constraint that actually bites: can this language run on this host?
    if lang and host:
        score = (host.get("languages") or {}).get(lang["id"])
        if score is None:
            warnings.append(
                f"host '{host['id']}' does not score language '{lang['id']}'")
        elif score in UNUSABLE:
            note = host.get("language_note", "")
            errors.append(
                f"'{lang['name']}' on '{host['name']}' is '{score}' — not a place "
                f"for an API deployable. {note}".strip())

    # Capability gaps that STACKSPEC requires to be recorded, not silently held.
    if engine:
        caps = engine.get("capabilities") or {}
        if caps.get("transactional_enqueue") is not True:
            warnings.append(
                f"engine '{engine['id']}' gives transactional_enqueue = "
                f"{caps.get('transactional_enqueue')!r}: §7.2 requires an outbox "
                f"with a relay, recorded as a §18 item 14 capability gap")
        for cap in ("multi_statement_transactions", "referential_constraints",
                    "statement_timeout", "pitr"):
            if caps.get(cap) is False:
                clause = (data.get("capability_definitions", {})
                          .get(cap, {}).get("clause", "?"))
                warnings.append(
                    f"engine '{engine['id']}' lacks {cap} ({clause}): a "
                    f"compensating control must be recorded in the Stack Profile")

    # Hard vendor conflicts declared on the host.
    if host:
        for conflict in host.get("conflicts") or []:
            hit = set(conflict.get("with", [])) & set(
                str(v) for v in sel.values())
            if hit:
                errors.append(
                    f"'{host['name']}' conflicts with {sorted(hit)}: "
                    f"{conflict.get('why', '')}")

    return errors, warnings


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Validate a stack selection against the catalog.")
    ap.add_argument("--catalog", action="store_true",
                    help="check the catalog files parse and agree with each other")
    ap.add_argument("--selection", metavar="FILE", type=Path,
                    help="check one product's role assignments")
    args = ap.parse_args()

    if not args.catalog and not args.selection:
        print("preflight: nothing was checked. Pass --catalog or --selection; a "
              "checker that examined nothing must not report the same success "
              "as one that examined something.", file=sys.stderr)
        return 2

    failed = False

    if args.catalog:
        errors = check_catalog()
        if errors:
            failed = True
            print(f"catalog: {len(errors)} error(s)")
            for e in errors:
                print(f"  ERROR  {e}")
        else:
            print("catalog: clean")

    if args.selection:
        errors, warnings = check_selection(args.selection)
        for w in warnings:
            print(f"  WARN   {w}")
        for e in errors:
            print(f"  ERROR  {e}")
        if errors:
            failed = True
            print(f"selection: {len(errors)} error(s), {len(warnings)} warning(s)")
        else:
            print(f"selection: viable, {len(warnings)} warning(s) to record")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
