# C2D-A Final Fix Report

## Scope

- `public_source_versions()` now accepts only Snapshot 1.0 and 1.1,
  projects each through a schema-specific scalar-only allowlist, and fails
  closed for malformed or unsupported snapshots.
- New authoritative Snapshot 1.1 records include
  `provenance_completeness: "AUTHORITATIVE"`.
- Duplicate source references are rejected before database flush with a
  deterministic `ValueError`; the database uniqueness constraint remains the
  concurrency backstop.
- The migration contract now independently verifies the
  `(report_version_id, ordinal)` index.

## TDD Evidence

### RED

Command:

```powershell
& E:\weknora_projects\maintenance-support-weknora\extensions\maintenance-api\.venv\Scripts\python.exe -m pytest tests/services/test_report_source_snapshot.py tests/services/test_report_source_policy.py tests/services/test_report_regeneration_lineage.py -q
```

Result: `5 failed, 22 passed, 1 warning in 10.29s`.

Expected failures demonstrated the missing authoritative completeness field on
direct construction and report creation, an `AttributeError` for malformed
non-mapping snapshots, and raw legacy source fields leaking through the 1.0
projection.

Command:

```powershell
& E:\weknora_projects\maintenance-support-weknora\extensions\maintenance-api\.venv\Scripts\python.exe -m pytest tests/services/test_report_source_policy.py::test_source_ref_unique_within_report_version -q
```

Result: failed with the expected database `IntegrityError`, demonstrating that
duplicate source references had no deterministic validation path.

### GREEN

Focused projection, creation, and regeneration command:

```powershell
& E:\weknora_projects\maintenance-support-weknora\extensions\maintenance-api\.venv\Scripts\python.exe -m pytest tests/services/test_report_source_snapshot.py tests/services/test_report_source_policy.py tests/services/test_report_regeneration_lineage.py -q
```

Result: `27 passed, 1 warning in 9.31s`.

Duplicate-source validation command:

```powershell
& E:\weknora_projects\maintenance-support-weknora\extensions\maintenance-api\.venv\Scripts\python.exe -m pytest tests/services/test_report_source_policy.py::test_source_ref_unique_within_report_version -q
```

Result: `1 passed, 1 warning in 6.93s`.

## Regression and Quality Evidence

- Source, lineage, service, and migration suite: `47 passed, 1 warning in 13.19s`.
- Report API and report-center API suite: `18 passed, 1 warning in 14.43s`.
- Report-center facade and regeneration API suite: `16 passed, 1 warning in 20.44s`.
- Report-center lifecycle API suite: `11 passed, 1 warning in 25.40s`.
- Ruff on changed files: passed.
- `git diff --check`: passed.
- Full `ruff check app tests` remains blocked by the pre-existing import-sort
  error in `tests/migrations/test_report_version_lineage_migration.py`; that
  unrelated file was not changed.

## Minor-Finding Disposition

- Addressed: the migration test independently checks the ordered-provenance
  index, and duplicate references now fail deterministically before flush.
- Left unchanged: there is no new migration test which seeds a legacy
  `AIReportVersion` and asserts no source-ref backfill. The migration only
  creates/drops `ai_report_source_refs` and contains no legacy-row update or
  insert, so no production change was warranted in this focused fix.

## Follow-up Final-Review Fix

### Scope

- Snapshot 1.0 now preserves every originally supported semantic legacy field
  through per-source scalar allowlists: session, scenario, calculation-run,
  review-run, and inventory fields. Unknown, secret-like, and nested values
  are still omitted.
- Snapshot 1.1 now requires `AUTHORITATIVE_CREATE`,
  `provenance_completeness: "AUTHORITATIVE"`, valid required source fields,
  valid source-type discriminators, and a lowercase SHA-256 digest when one
  is present. Invalid input returns `{}`.
- Source-reference batches are immutable after the first nonempty batch,
  preventing duplicate ordinals from a distinct second batch.
- The migration test now seeds a legacy report version and proves it survives
  upgrade/re-upgrade without a fabricated source-reference row.

### TDD Evidence

RED command:

```powershell
& E:\weknora_projects\maintenance-support-weknora\extensions\maintenance-api\.venv\Scripts\python.exe -m pytest tests/services/test_report_source_snapshot.py tests/services/test_report_source_policy.py tests/migrations/test_ai_report_source_ref_migration.py -q
```

Result: `11 failed, 12 passed, 1 warning in 13.68s`. The failures covered
dropped safe 1.0 calculation/inventory semantics, missing or invalid required
1.1 discriminators and fields, invalid digest handling, and acceptance of a
second distinct source batch.

GREEN command:

```powershell
& E:\weknora_projects\maintenance-support-weknora\extensions\maintenance-api\.venv\Scripts\python.exe -m pytest tests/services/test_report_source_snapshot.py tests/services/test_report_source_policy.py tests/migrations/test_ai_report_source_ref_migration.py -q
```

Result: `23 passed, 1 warning in 12.79s`.

### Regression and Quality Evidence

- Source, migration, lineage, and report service suite: `59 passed, 1 warning in 15.71s`.
- Report API and report-center API suite: `18 passed, 1 warning in 15.77s`.
- Ruff on changed files: passed.
- `git diff --check`: pending final staged verification.

### Remaining Minor Items

- None from the final-review follow-up. The seeded migration test now covers
  legacy-row preservation and zero source-ref backfill on both upgrade paths.
