# Plan 05 Task 8 Full Workflow and AI-Degraded Integration Design

## Goal

Add two deterministic maintenance-API integration tests that prove the
completed Plan 05 workflows compose correctly: one full allocation-to-report
workflow and one provider-disabled, `RULE_FALLBACK` workflow.

## Scope

`tests/integration/test_plan05_full_workflow.py` will exercise existing
tenant-scoped service and persistence paths in this order: seed master data
and inventory; materialize a scenario; calculate; publish a demand list;
review and derive demand; create and execute an allocation plan; create an
`ALLOCATION_PLAN` report; generate, validate, finalize, and DOCX export it.

The test will assert tenant isolation, published-demand immutability, ledger
balance, reservation integrity, exact allocation-plan source version,
immutable report source snapshots, and FINAL-report mutation rejection.

`tests/integration/test_plan05_ai_disabled.py` will disable every remote and
local AI provider in the test runtime. It will prove the structured scenario,
deterministic calculation, published demand, deterministic review,
`DEMAND_REVIEW` report, `RULE_FALLBACK` generation, validation, finalization,
and export remain operational. It will assert current report job/version
states, never the obsolete generic `COMPLETED` state.

## Test Architecture

Both tests will compose existing integration fixtures and service/API helpers
instead of duplicating business rules. Fixture data remains isolated per test
and uses no production tenant IDs, provider credentials, or absolute file
paths. Assertions target externally visible persisted results and typed error
codes, not private implementation details.

The task may adjust `tests/conftest.py` only when a missing reusable fixture
prevents deterministic setup. It will not alter application behavior. A
failing assertion that identifies an application defect is a stop condition:
record the evidence and create a separate bounded repair plan rather than
expanding Task 8.

## Verification

The closure gate runs the two new tests, the complete maintenance API pytest
suite, and Ruff. Test reports record commands, counts, accepted third-party
warnings, and confirmation that the phase added verification only.
