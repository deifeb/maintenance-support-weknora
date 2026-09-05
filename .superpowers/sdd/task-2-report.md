# C2D-C Task 2 — Safe Report Provenance Exports

## Status

Complete. The report serializer remains the only production caller of
`public_source_versions()`. JSON now emits an explicit, allowlisted
`provenance` object; JSON export itself allows only serialized report fields.
Markdown and DOCX render authoritative Snapshot 1.1 source lists from the
already-projected `source_versions` value, while retaining legacy formatting.

## Tests

- The initial red run of the new API/exporter tests failed as expected because
  JSON had no `provenance` object.
- Focused regression command passed: `9 passed, 1 warning`.
- Ruff over the changed production and test files passed.
- `git diff --check` passed.

The accepted warning is FastAPI/Starlette's pre-existing TestClient deprecation
warning about its `httpx` dependency.

## Coverage

- API detail returns only the fail-closed public source projection; raw
  snapshot evidence, tenant identifiers, and credentials are absent.
- JSON, Markdown, and DOCX render the safe authoritative source list and do
  not render raw snapshot, internal-metadata, credential, or path values.
- Malformed/empty public source projections render unavailable provenance
  without reconstructing a raw snapshot.
- JSON, Markdown, and DOCX filenames remain
  `{report_code}-v{version_number}.{ext}`.

## Scope Review

No regeneration copying, source policy, frontend, lifecycle, C2D-B
creation/list contracts, or absolute export-path behavior changed.

## Follow-up Security Remediation

A review identified two detail/export leak paths. The serializer now projects
citations through an explicit allowlist and never includes
`database_record_json`. Metadata is recursively projected from JSON-safe
scalars, lists, and mappings only; underscore-prefixed, tenant, internal,
credential, token, secret, evidence, and path/directory fields are omitted at
every nesting level. Path-like string values are also omitted.

The regression begins with a red API-detail test that exposed both the raw
citation record and unsafe metadata. It now verifies detail plus JSON,
Markdown, and DOCX exports against nested citation evidence/provider-token,
metadata tenant/internal/nested-token, and path probes. The fresh focused
verification completed with `9 passed, 1 warning`; Ruff and `git diff --check`
passed. The warning remains the existing FastAPI/Starlette TestClient
deprecation warning.

## Second-Round Review Remediation: Section Payloads

The second review found that `_section_tables` and `_section_citations` were
read from private metadata and copied directly into serialized sections. This
bypassed the metadata projection and could expose nested tenant, internal,
token, evidence, snapshot, or database-record values.

Implementation commit: `de10c8017 fix(maintenance): sanitize report section exports`.

- Section tables now project only `title`, `columns`, and `rows`; unsupported,
  nested, path-like, and sensitive values are omitted or safely blanked.
- Section citations now project only non-path string citation IDs.
- The API regression seeds a section table with nested tenant/internal/token,
  evidence/credential, source-snapshot, and database-record probes plus an
  unsafe structured section citation. It verifies detail, JSON, Markdown, and
  DOCX retain safe table/citation content and expose none of those probes.

Fresh verification command:

```powershell
& 'E:\weknora_projects\maintenance-support-weknora\extensions\maintenance-api\.venv\Scripts\python.exe' -m pytest tests/api/test_report_center_source_provenance_api.py tests/exporters/test_ai_report_source_provenance.py tests/exporters/test_ai_report_exports.py tests/exporters/test_report_version_provenance_exports.py -q
& 'E:\weknora_projects\maintenance-support-weknora\extensions\maintenance-api\.venv\Scripts\python.exe' -m ruff check app/services/ai_report_service.py app/exporters/ai_report_json.py app/exporters/ai_report_markdown.py app/exporters/ai_report_docx.py tests/api/test_report_center_source_provenance_api.py tests/exporters/test_ai_report_source_provenance.py
git diff --check HEAD^ HEAD
```

Complete result: `9 passed, 1 warning in 10.09s`; Ruff reported `All checks
passed!`; `git diff --check HEAD^ HEAD` had no output. The one warning is the
existing FastAPI/Starlette TestClient deprecation warning.

## Fourth-Round Review Remediation: Compact JWT Values

The fourth review found that a standard compact JWT has no `jwt` keyword and
could therefore pass the sensitive-string marker filter when used as a section
table title, column, cell, or section citation.

Implementation commit: `a3dcec529 fix(maintenance): block compact JWT section values`.

- Section scalar projection now detects compact base64url JWT candidates and
  validates that their decoded header is a JSON object with an `alg` field.
  This blocks both standalone and embedded complete JWT values without relying
  on a literal `jwt` marker.
- A regression uses a real three-segment JWT in the title, a column, a cell,
  and a section citation. Detail, JSON, Markdown, and DOCX are all asserted to
  omit it while preserving safe section content.

Fresh verification command:

```powershell
& 'E:\weknora_projects\maintenance-support-weknora\extensions\maintenance-api\.venv\Scripts\python.exe' -m pytest tests/api/test_report_center_source_provenance_api.py tests/exporters/test_ai_report_source_provenance.py tests/exporters/test_ai_report_exports.py tests/exporters/test_report_version_provenance_exports.py -q
& 'E:\weknora_projects\maintenance-support-weknora\extensions\maintenance-api\.venv\Scripts\python.exe' -m ruff check app/services/ai_report_service.py app/exporters/ai_report_json.py app/exporters/ai_report_markdown.py app/exporters/ai_report_docx.py tests/api/test_report_center_source_provenance_api.py tests/exporters/test_ai_report_source_provenance.py
git diff --check HEAD^ HEAD
```

Complete result: `9 passed, 1 warning in 8.65s`; Ruff reported `All checks
passed!`; `git diff --check HEAD^ HEAD` had no output. The one warning is the
existing FastAPI/Starlette TestClient deprecation warning.

## Third-Round Review Remediation: Sensitive Section Scalars

The third review found that section title, column, cell, and citation strings
still reused a metadata helper that only rejected path-like values. This could
return tenant IDs, JWTs, tokens, credentials, or secrets when they appeared as
otherwise allowed scalar values.

Implementation commit: `de72a1703 fix(maintenance): redact sensitive section scalars`.

- Section scalar values now use an independent strict rule: only primitive
  values are accepted, and strings containing tenant, JWT, token, credential,
  secret, password, authorization, bearer, API/access/private/client-key,
  database-record, or source-snapshot markers (and path-like values) are
  rejected.
- Rejected table scalars become empty cells, preserving safe table shape
  without returning the source value. Rejected section citation strings are
  omitted.
- The API regression injects sensitive scalar values into otherwise allowed
  column names, table cells, and section citations, and verifies detail, JSON,
  Markdown, and DOCX keep safe values but contain none of the probes.

Fresh verification command:

```powershell
& 'E:\weknora_projects\maintenance-support-weknora\extensions\maintenance-api\.venv\Scripts\python.exe' -m pytest tests/api/test_report_center_source_provenance_api.py tests/exporters/test_ai_report_source_provenance.py tests/exporters/test_ai_report_exports.py tests/exporters/test_report_version_provenance_exports.py -q
& 'E:\weknora_projects\maintenance-support-weknora\extensions\maintenance-api\.venv\Scripts\python.exe' -m ruff check app/services/ai_report_service.py app/exporters/ai_report_json.py app/exporters/ai_report_markdown.py app/exporters/ai_report_docx.py tests/api/test_report_center_source_provenance_api.py tests/exporters/test_ai_report_source_provenance.py
git diff --check HEAD^ HEAD
```

Complete result: `9 passed, 1 warning in 8.85s`; Ruff reported `All checks
passed!`; `git diff --check HEAD^ HEAD` had no output. The one warning is the
existing FastAPI/Starlette TestClient deprecation warning.
