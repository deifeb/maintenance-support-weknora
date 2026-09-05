# C2D-B closure evidence

Task 5 adds one regression guard proving that C2D-B regeneration uses the
persisted parent snapshot and does not resolve current sources. No source
implementation change was required.

## Revision and scope

- Base SHA: `4c564d3e78bc72d38ae0f48bd7912bb7106ade71`
- Verification head before the closure commit: `4c564d3e78bc72d38ae0f48bd7912bb7106ade71`
- Completed closure commit/head: `24c4839efe97ff726978e6623ebec110f50a45a0`
- Follow-up correction work is included in the subsequent implementation
  commit `59fc37128` (`fix(maintenance): enforce c2d-b source resolution`).
- Changed test: `extensions/maintenance-api/tests/services/test_report_regeneration_lineage.py`
- Added evidence: this document
- `extensions/maintenance-api/tests/api/test_report_center_regenerate_api.py`: unchanged
- No frontend, exporter, lifecycle, source backfill, or regeneration source-ref-copy code changed.
- C2D-C source-reference copying remains unimplemented and out of scope.

## Verification

Focused regression command:

```text
& 'E:\weknora_projects\maintenance-support-weknora\extensions\maintenance-api\.venv\Scripts\python.exe' -m pytest tests/services/test_report_regeneration_lineage.py -q
```

Result: `19 passed, 1 warning in 12.48s` (baseline closure evidence).

Complete C2D-B gate (the exact Task 5 command):

```text
& 'E:\weknora_projects\maintenance-support-weknora\extensions\maintenance-api\.venv\Scripts\python.exe' -m pytest tests/services/test_ai_report_type_semantics.py tests/services/test_report_template_registry.py tests/services/test_report_source_service.py tests/services/test_report_source_policy.py tests/services/test_report_source_snapshot.py tests/services/test_report_regeneration_lineage.py tests/api/test_report_center_source_refs_api.py tests/api/test_report_center_api.py tests/api/test_report_center_regenerate_api.py tests/api/test_report_center_lifecycle_api.py tests/api/test_report_center_facade_api.py tests/api/test_ai_reports.py tests/exporters/test_ai_report_exports.py tests/exporters/test_report_version_provenance_exports.py tests/migrations -q
& 'E:\weknora_projects\maintenance-support-weknora\extensions\maintenance-api\.venv\Scripts\python.exe' -m ruff check app tests
git diff --check
```

Results:

- Baseline selected tests: `194 passed, 1 warning in 432.64s (0:07:12)`.
- Fresh selected tests after source/API corrections: `194 passed, 1 warning in 387.29s (0:06:27)`.
- Alembic: `20260904_17 (head)`.
- Ruff: `All checks passed!` after formatting the branch-added test and fixing
  the route import order.
- `git diff --check`: no whitespace errors.

The single pytest warning is the existing Starlette deprecation warning for
using httpx with `starlette.testclient`; it does not affect test results.

## Commit

The closure commit `24c4839efe97ff726978e6623ebec110f50a45a0`
(`docs(maintenance): close c2d-b execution`) is complete and staged only the
scoped test and this document. The pre-existing modification to
`.superpowers/sdd/progress.md` was intentionally unstaged.

This document correction is applied in a separate follow-up commit and does
not alter the closure commit or its baseline verification evidence.

## Follow-up source/API corrections

The source-link version comparison now uses the producer-persisted
`DemandList.version`, and explicit `source_refs` plus strict C2D-B report types
are resolved before AI report creation. Legacy management-decision creation
remains unchanged. No regeneration source-reference copying was added.
