# DL406 report

## Files
- new claude/plugins/delivery/templates/shared/scripts/delivery/stack.py (detect_tools, declared, problems, resolve, KNOWN, PRESETS)
- claude/plugins/delivery/references/config-schema.json (`stack` block, closed field list, additionalProperties false)
- claude/plugins/delivery/scripts/delivery_doctor.py (check_stack, registered as "stack"; rows id `stack.tools`)
- new claude/plugins/delivery/tests/test_dl406_stack.py (12 tests)
- claude/plugins/delivery/tests/test_doctor.py (line 56: expected check set now includes "stack")
- docs/features/delivery/spec.md: new R5.66 (R5.65 is cited in code but absent from the spec, so I skipped it)
- CONTRACT.md (stack section), commands/delivery-ci-setup.md (stack section)
- change notes: docs/architecture/changes/DL406-declared-stack.md, docs/features/delivery/changes/DL406.md

## Tests
- python3 -m unittest test_dl406_stack test_doctor test_config (in claude/plugins/delivery/tests): 53 OK
- also test_dl188_doctor_tools, test_dl184_pool_doctor_agree, test_ds202_rust_doctor, test_dl212_doctor_same_content: OK
- ci_areas --branch-advice: "light: test locally only"

## docs_check
Only error: W1 for docs/work/DL406/REPORT.md (expected; reports stay on the branch). No other findings.

## Branch head (code commit)
f0f3d7fca03b8b7c69029b55671ab0d61af6dedf (the report commit follows it)

## Notes / questions for the owner
- The validator in delivery_config.py (not mine) only warns on unknown keys; the closed list is enforced by the schema flag plus `stack.problems()`, which the doctor check fails on.
- KNOWN is listed from test_guardrails.py and delivery_common.py. selenium, cypress, yarn, npm, gradle, maven, bundler, composer are unchecked.
- A ts-track project with yarn.lock or package-lock.json now fails until it declares package_manager. Intended? npm in particular is common.
- Detection reads two folder levels deep, skipping node_modules, target, build folders.
- stack.py ships under templates; the doctor loads it from the plugin copy.

READY
