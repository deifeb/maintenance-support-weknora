# C2D-C Closure Evidence

Date: 2026-09-05

## Revision evidence

- Base SHA (C2D-C planning baseline): `649a249b582ef45b272249b8e9dfc4aa5572bcb6`
- Head SHA verified: `9f07ab9fe340222f4e92452f30fe2a7ea1042294`
- Branch: `codex/maintenance-plan05-5-c2d-c`
- Alembic head: `20260904_17 (head)`

## Complete matrix

Executed from `extensions/maintenance-api`:

```powershell
& 'E:\weknora_projects\maintenance-support-weknora\extensions\maintenance-api\.venv\Scripts\python.exe' -m pytest tests/services/test_report_regeneration_source_refs.py tests/exporters/test_ai_report_source_provenance.py tests/api/test_report_center_source_provenance_api.py tests/services/test_report_regeneration_lineage.py tests/api/test_report_center_regenerate_api.py tests/api/test_report_center_lifecycle_api.py tests/api/test_report_center_facade_api.py tests/api/test_report_center_api.py tests/services/test_ai_report_service.py tests/exporters/test_ai_report_exports.py tests/migrations -q
```

Result: `123 passed, 1 warning in 347.69s`.

```powershell
& 'E:\weknora_projects\maintenance-support-weknora\extensions\maintenance-api\.venv\Scripts\python.exe' -m ruff check app tests
```

Result: `All checks passed!`

Executed from the repository root:

```powershell
git diff --check
```

Result: exit code 0; no whitespace errors.

## Accepted warnings

- Pytest reported one third-party `StarletteDeprecationWarning`: `starlette.testclient` imports `httpx`, and recommends `httpx2`. It does not originate in this repository's application or test code.
- `git diff --check` emitted one Git CRLF conversion warning for the pre-existing unstaged `.superpowers/sdd/progress.md`; its exit code was 0 and it reported no whitespace error.

## Scope audit

The C2D-C range (`649a249b..9f07ab9f`) changes only report provenance implementation/tests and its Task 2 report. It contains no `frontend/` files, migrations, lifecycle API/service changes, C2D-B source-policy/create/list work, current-business-source regeneration, source backfill, automatic supersede behavior, C3 work, or export filename changes. The regeneration coverage in the matrix confirms persisted child source references are copied rather than re-derived from current sources.

The closure task itself adds documentation evidence only; it changes no business implementation, tests, or frontend files.
