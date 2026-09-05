# C2D-B closure evidence

Task 5 adds one regression guard proving that C2D-B regeneration uses the
persisted parent snapshot and does not resolve current sources. No source
implementation change was required.

## Revision and scope

- Base SHA: `4c564d3e78bc72d38ae0f48bd7912bb7106ade71`
- Head SHA before the closure commit: `4c564d3e78bc72d38ae0f48bd7912bb7106ade71`
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

Result: `19 passed, 1 warning in 12.48s`.

Complete C2D-B gate (the exact Task 5 command):

```text
& 'E:\weknora_projects\maintenance-support-weknora\extensions\maintenance-api\.venv\Scripts\python.exe' -m pytest tests/services/test_ai_report_type_semantics.py tests/services/test_report_template_registry.py tests/services/test_report_source_service.py tests/services/test_report_source_policy.py tests/services/test_report_source_snapshot.py tests/services/test_report_regeneration_lineage.py tests/api/test_report_center_source_refs_api.py tests/api/test_report_center_api.py tests/api/test_report_center_regenerate_api.py tests/api/test_report_center_lifecycle_api.py tests/api/test_report_center_facade_api.py tests/api/test_ai_reports.py tests/exporters/test_ai_report_exports.py tests/exporters/test_report_version_provenance_exports.py tests/migrations -q
& 'E:\weknora_projects\maintenance-support-weknora\extensions\maintenance-api\.venv\Scripts\python.exe' -m ruff check app tests
git diff --check
```

Results:

- Selected tests: `194 passed, 1 warning in 432.64s (0:07:12)`.
- Alembic: `20260904_17 (head)`.
- Ruff: one pre-existing `I001` import-order violation in
  `tests/services/test_ai_report_type_semantics.py`; this file is outside the
  Task 5 scope and was not modified.
- `git diff --check`: no whitespace errors.

The single pytest warning is the existing Starlette deprecation warning for
using httpx with `starlette.testclient`; it does not affect test results.

## Commit

The closure commit is recorded by the supervising agent after staging only the
scoped test and this document. The pre-existing modification to
`.superpowers/sdd/progress.md` is intentionally unstaged.
