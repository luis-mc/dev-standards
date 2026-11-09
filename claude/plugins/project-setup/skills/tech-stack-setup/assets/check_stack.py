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

def known_ids() -> dict[str, set[str]]:
    """Every role that names a catalog technology, and its valid ids."""
    languages = load("tech/languages.yaml")
    hosting = load("tech/hosting.yaml")
    data = load("tech/data.yaml")
    frameworks = load("tech/frameworks.yaml")
    services = load("tech/services.yaml")
    return {
        "language": ids(languages, "technologies"),
        "hosting": ids(hosting, "technologies"),
        "db_engine": ids(data, "engines"),
        "db_host": ids(data, "hosts"),
        "web_framework": ids(frameworks, "web"),
        "api_framework": ids(frameworks, "api"),
        "cache": ids(services.get("cache", {}), "technologies"),
        "object_storage": ids(services.get("object_storage", {}), "technologies"),
        "mail": ids(services.get("mail", {}), "technologies"),
        "error_tracking": ids(services.get("error_tracking", {}), "technologies"),
    }


def listed(value) -> list:
    """A role value as a list: a scalar is one entry, a list is each entry."""
    if value is None:
        return []
    return list(value) if isinstance(value, list) else [value]


def component_languages(languages: dict) -> dict[str, dict]:
    """Languages that may be a component beside an API language, by id."""
    return {t["id"]: t for t in languages.get("technologies", [])
            if "component" in (t.get("roles") or []) and t.get("component")}


def normalize_components(value) -> list[dict]:
    """`components` as a list of mappings. A bare id is a component with no detail."""
    out = []
    for c in listed(value):
        out.append(dict(c) if isinstance(c, dict) else {"id": str(c)})
    return out


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

    known = known_ids()

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

    # Every id a host or framework variant names in `conflicts` must exist,
    # or the conflict never matches (a typo makes it silently dead).
    conflict_ok = set().union(*known.values())
    for fw in frameworks.get("web", []):
        for var in fw.get("variants") or []:
            if isinstance(var, dict) and "id" in var:
                conflict_ok.add(var["id"])
    for host in hosting.get("technologies", []):
        for conflict in host.get("conflicts") or []:
            for w in conflict.get("with", []):
                if w not in conflict_ok:
                    errors.append(
                        f"host '{host['id']}' conflicts with unknown id '{w}'")

    # Component parts and pairings must name real things (DS196).
    part_ids: set[str] = set()
    for lang in languages.get("technologies", []):
        comp = lang.get("component")
        if "component" in (lang.get("roles") or []) and not comp:
            errors.append(f"language '{lang['id']}' has role component but no component block")
        for part in (comp or {}).get("parts", []):
            if "id" not in part:
                errors.append(f"language '{lang['id']}' has a component part without id")
            part_ids.add(part.get("id"))
    comp_langs = component_languages(languages)
    for pair in bundles.get("component_pairings") or []:
        if pair.get("component") not in comp_langs:
            errors.append(f"component pairing names unknown component '{pair.get('component')}'")
        for part in listed(pair.get("parts")) + listed(pair.get("part")):
            if part not in part_ids:
                errors.append(f"component pairing names unknown part '{part}'")
        hosts = pair.get("hosts")
        for h in ([] if hosts in (None, "any") else listed(hosts)):
            if h not in host_ids:
                errors.append(f"component pairing names unknown host '{h}'")

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

    # The API language. `api` is the component-aware spelling; `language` still works.
    lang_id = sel.get("api") or sel.get("language")
    engine_id = sel.get("db_engine")

    lang = next((t for t in languages.get("technologies", [])
                 if t["id"] == lang_id), None)
    engine = next((e for e in data.get("engines", [])
                   if e["id"] == engine_id), None)
    hosts = []
    for host_id in listed(sel.get("hosting")):
        host = next((t for t in hosting.get("technologies", [])
                     if t["id"] == host_id), None)
        if host:
            hosts.append(host)

    # Every role that names a catalog technology: each listed id must exist.
    known = known_ids()
    if sel.get("api") and str(sel["api"]) not in known["language"]:
        errors.append(f"unknown api language '{sel['api']}'")
    for role, valid in known.items():
        for v in listed(sel.get(role)):
            if str(v) not in valid:
                errors.append(f"unknown {role} '{v}'")

    # The API framework must belong to the language's track.
    if lang:
        api = next((f for f in load("tech/frameworks.yaml").get("api", [])
                    if f.get("id") == sel.get("api_framework")), None)
        if api and api.get("track") and api["track"] != lang["id"]:
            errors.append(
                f"api_framework '{api['id']}' is for track '{api['track']}', "
                f"not language '{lang['id']}'")

    # The constraint that actually bites: can this language run on this host?
    for host in hosts:
        if not lang:
            break
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

    # Native components (DS196). Not subject to the API host elimination: a
    # component is built in CI and shipped, not run on the host.
    comp_langs = component_languages(languages)
    host_ids_chosen = {h["id"] for h in hosts}
    pairings = load("bundles.yaml").get("component_pairings") or []
    for comp in normalize_components(sel.get("components")):
        cid = comp.get("id")
        spec = comp_langs.get(cid)
        if not spec:
            errors.append(f"component '{cid}' is not a language that can be a component")
            continue
        valid_parts = {p["id"]: p for p in spec["component"].get("parts", [])}
        parts = listed(comp.get("parts"))
        for part in parts:
            if part not in valid_parts:
                errors.append(f"component '{cid}' has unknown part '{part}'")
        if spec["component"].get("requires_reason") and not str(comp.get("reason") or "").strip():
            warnings.append(
                f"{spec['name']} component without a recorded reason: write why it is "
                f"not built in the main language (a written reason is enough)")
        if "library-napi" in parts and not comp.get("build_matrix"):
            warnings.append(
                f"napi addon without a build matrix: list the OS and arch "
                f"each prebuilt binary is built for")
        if comp.get("cross_compile") and not str(comp.get("licence_note") or "").strip():
            warnings.append(
                f"cross-compile target without a licence note: record the licence "
                f"of any SDK the cross tool downloads")
        for pair in pairings:
            if pair.get("component") != cid or not pair.get("warn"):
                continue
            if pair.get("part") not in parts:
                continue
            if pair.get("needs") == "windows_build_option":
                if "windows" in {str(o).lower() for o in listed(comp.get("targets"))} \
                        and not comp.get("cross_compile") and not comp.get("windows_runner"):
                    warnings.append(f"{cid} {pair['part']}: {pair['warn']}")
            elif host_ids_chosen & set(listed(pair.get("hosts"))):
                warnings.append(f"{cid} {pair['part']}: {pair['warn']}")

    # Hard vendor conflicts declared on the host.
    chosen = {str(x) for k, v in sel.items() if k != "components" for x in listed(v)}
    chosen |= {c["id"] for c in normalize_components(sel.get("components"))}
    for host in hosts:
        for conflict in host.get("conflicts") or []:
            hit = set(conflict.get("with", [])) & chosen
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
