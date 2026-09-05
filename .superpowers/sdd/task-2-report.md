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
