# C2D-C Final Fix Report

Date: 2026-09-05

## Scope and remediation

- Added `source_snapshot` and `database_record` to the recursive metadata
  container denylist. Their `*_json` mappings are now omitted whole from
  ordinary metadata mappings and list elements, without removing safe
  siblings.
- Replaced prefix-only path detection with an embedded-path matcher for
  Windows drive paths, POSIX paths, UNC paths, and `file://` URIs. It applies
  to paths surrounded by prose, parentheses, and newlines.
- Extended the report-detail regression to verify no sensitive container or
  embedded path reaches detail, JSON, Markdown, or DOCX, while safe sibling
  metadata remains visible.
- Removed the extra EOF blank line from the C2D-C implementation plan.

## Test-first record

Before the implementation change, the added API/export regression was run:

```powershell
& 'E:\weknora_projects\maintenance-support-weknora\extensions\maintenance-api\.venv\Scripts\python.exe' -m pytest tests/api/test_report_center_source_provenance_api.py -q
```

Result: `1 failed, 1 passed, 1 warning`. The failure showed that nested
`source_snapshot_json` and `database_record_json` containers reached the
detail response.

After the implementation change, the same focused command passed:

```powershell
& 'E:\weknora_projects\maintenance-support-weknora\extensions\maintenance-api\.venv\Scripts\python.exe' -m pytest tests/api/test_report_center_source_provenance_api.py -q
& 'E:\weknora_projects\maintenance-support-weknora\extensions\maintenance-api\.venv\Scripts\python.exe' -m ruff check app/services/ai_report_service.py tests/api/test_report_center_source_provenance_api.py
```

Result: `2 passed, 1 warning`; Ruff: `All checks passed!`.

## Required final verification

The Task 3 C2D-C matrix was rerun after the final gate-code change:

```powershell
& 'E:\weknora_projects\maintenance-support-weknora\extensions\maintenance-api\.venv\Scripts\python.exe' -m pytest tests/services/test_report_regeneration_source_refs.py tests/exporters/test_ai_report_source_provenance.py tests/api/test_report_center_source_provenance_api.py tests/services/test_report_regeneration_lineage.py tests/api/test_report_center_regenerate_api.py tests/api/test_report_center_lifecycle_api.py tests/api/test_report_center_facade_api.py tests/api/test_report_center_api.py tests/services/test_ai_report_service.py tests/exporters/test_ai_report_exports.py tests/migrations -q
```

Result: `123 passed, 1 warning in 288.18s`.

```powershell
& 'E:\weknora_projects\maintenance-support-weknora\extensions\maintenance-api\.venv\Scripts\python.exe' -m ruff check app tests
git diff --check 1b6a25e32..HEAD
```

Result: Ruff: `All checks passed!`; whitespace check: exit code 0 with no
output.

## Commits and evidence

- `4cbba4ee2766e540f35f13264405fbb4ac7ec5cd`
  `fix(maintenance): close provenance export leaks`
- `47af21a0d2ee275018c06a974b4ab6ab70906c03`
  `docs(maintenance): update c2d-c closure evidence`

`docs/superpowers/sdd/c2d-c-closure.md` records the rerun matrix and scope
audit. No C3, frontend, C2D-B policy/create/list, lifecycle, backfill,
automatic-supersede, or export-filename behavior changed.

## Warning

The only test warning is the existing third-party
`StarletteDeprecationWarning`: `starlette.testclient` imports `httpx` and
recommends `httpx2`. It is not emitted by repository application or test code.
