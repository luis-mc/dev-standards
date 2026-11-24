# DL409 report

Files:
- claude/plugins/delivery/templates/shared/scripts/delivery/test_guardrails.py (Cypress G1/G3/G4, Selenium G1/G4, kind_of, *.cy.* as test files)
- claude/plugins/delivery/templates/shared/scripts/delivery/stack.py (KNOWN: cypress, selenium)
- claude/plugins/delivery/tests/test_dl409_guardrails_cypress_selenium.py (new, 11 tests)
- claude/plugins/delivery/tests/test_dl406_stack.py (four tests used cypress/selenium as the "unchecked" example; now gradle, and selenium is known)
- docs/features/delivery/spec.md (R5.67; R5.67 was free), change notes DL409

time.sleep was already caught by G4 for test files; driver.sleep and cy.wait(N) added.

Tests (all OK): test_dl409_guardrails_cypress_selenium, test_dl376_test_guardrails, test_dl379_templates_guardrails, test_dl406_stack.
docs_check: M1 for delivery-speed spec cleared by `Docs: none` in the commit message (see below for final run).
