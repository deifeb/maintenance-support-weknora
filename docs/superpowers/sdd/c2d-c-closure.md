# C2D-C Closure Evidence

Date: 2026-09-05

## Revision evidence

- Base SHA (C2D-C planning baseline): `649a249b582ef45b272249b8e9dfc4aa5572bcb6`
- Head SHA verified: `dcc0588c335408a7bb0bddfdd6db35ae58382154`
- Branch: `codex/maintenance-plan05-5-c2d-c`
- Alembic head: `20260904_17 (head)`

## Complete matrix

Executed from `extensions/maintenance-api`:

```powershell
& 'E:\weknora_projects\maintenance-support-weknora\extensions\maintenance-api\.venv\Scripts\python.exe' -m pytest tests/services/test_report_regeneration_source_refs.py tests/exporters/test_ai_report_source_provenance.py tests/api/test_report_center_source_provenance_api.py tests/services/test_report_regeneration_lineage.py tests/api/test_report_center_regenerate_api.py tests/api/test_report_center_lifecycle_api.py tests/api/test_report_center_facade_api.py tests/api/test_report_center_api.py tests/services/test_ai_report_service.py tests/exporters/test_ai_report_exports.py tests/migrations -q
```

Result: `123 passed, 1 warning in 348.99s`.

```powershell
& 'E:\weknora_projects\maintenance-support-weknora\extensions\maintenance-api\.venv\Scripts\python.exe' -m ruff check app tests
```

Result: `All checks passed!`

Executed from the repository root:

```powershell
git diff --check 1b6a25e32..HEAD
```

Result: exit code 0; no whitespace errors.

## Accepted warnings

- Pytest reported one third-party `StarletteDeprecationWarning`: `starlette.testclient` imports `httpx`, and recommends `httpx2`. It does not originate in this repository's application or test code.
- `git diff --check 1b6a25e32..HEAD` emitted no output and reported no whitespace errors.

## Scope audit

The C2D-C range (`1b6a25e32..dcc0588c3`) changes only report provenance implementation/tests and its Task 2 report. It contains no `frontend/` files, migrations, lifecycle API/service changes, C2D-B source-policy/create/list work, current-business-source regeneration, source backfill, automatic supersede behavior, C3 work, or export filename changes. The regeneration coverage in the matrix confirms persisted child source references are copied rather than re-derived from current sources.

## Final provenance security remediation

The final review identified two fail-open cases in the recursive public metadata
projection. Metadata mappings and list entries named `source_snapshot_json` or
`database_record_json` now have their entire containers omitted at every depth,
while safe sibling values continue to serialize. Path detection now rejects
Windows, POSIX, UNC, and `file://` paths wherever they occur in a string,
including surrounding prose, parentheses, and newlines. The API regression
asserts both detail and all three export formats omit these values and retain
safe sibling metadata.

The final plan EOF blank line was removed. The complete matrix above was
rerun after this gate-code change, followed by `ruff check app tests` and
`git diff --check 1b6a25e32..HEAD`; all completed successfully.

## Root-level POSIX path remediation

Final review found that the POSIX matcher accepted a single root-level file
only when it ended the string. It now detects `/report.json` at a safe
non-alphanumeric boundary regardless of trailing explanatory text, closing
punctuation, or newline. The regression places those three forms under
ordinary metadata keys, section content, and a citation source name, so the
metadata-key denylist cannot mask the value-filter check. Detail, JSON,
Markdown, and DOCX omit all probes while keeping safe sibling content.

The complete matrix, `ruff check app tests`, and the baseline whitespace gate
were rerun after this production-path and final-regression change.

The closure task itself adds documentation evidence only; it changes no business implementation, tests, or frontend files.
