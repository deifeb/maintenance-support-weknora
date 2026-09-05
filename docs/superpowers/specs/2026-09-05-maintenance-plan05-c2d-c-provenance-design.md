# Plan 05 C2D-C: Regeneration Source Copy and Safe Provenance

**Status:** Approved design; implementation has not started.

**Base:** C2D-B closure head `1b6a25e3297e24d6947fb5341fc791c45f58e27d` on `codex/maintenance-plan05-5-c2d-c`.

## Goal

Finish C2D's immutable-source semantics by copying durable source references during report regeneration, then expose the same fail-closed public provenance in report detail and every export format. The work preserves C2B lineage and C2C lifecycle behavior and does not add frontend functionality.

## Scope

Included:

- exact, ordered copy of parent `AIReportSourceRef` rows into the regenerated child version;
- exact deep copy of the parent source snapshot, input digest, and template version;
- safe public provenance for detail/version output;
- structured JSON, fixed Markdown block, and fixed DOCX table provenance;
- regression coverage for source drift, tenant-safe projection, exports, and C2B/C2C compatibility.

Excluded:

- querying any current business source during regeneration;
- source-policy changes, report-type changes, C2D-B create/list work, and source backfill;
- frontend/C3 work;
- report lifecycle changes, new regeneration idempotency, or automatic superseding;
- export filename changes or absolute export-path exposure.

## Regeneration architecture

`AIReportService.regenerate()` already creates a linear child version under C2B's tenant-scoped lock and unique `(report_job_id, version_number)` protection. C2D-C extends that same transaction after the child version receives an ID:

```text
parent AIReportVersion
  ├─ source_snapshot_json  -> deep-copy -> child source_snapshot_json
  ├─ input_digest          -> exact-copy -> child input_digest
  ├─ template_version      -> exact-copy -> child template_version
  └─ AIReportSourceRef[]   -> exact ordered copy -> child AIReportSourceRef[]
```

The child receives newly inserted source-ref rows with its own `report_version_id`; the copied `tenant_id`, `source_type`, `source_id`, `source_version`, `source_lineage_id`, `source_digest`, `ordinal`, and `evidence_json` values must match the parent exactly. The child may not reuse parent row identities.

No regeneration path may invoke `ReportSourceService`, replace a source from a current demand list/allocation/stocktake/review/calculation, refresh inventory or risk data, or execute a business workflow. The existing second-concurrent-regenerate behavior remains `REPORT_REGENERATE_SOURCE_NOT_READY`; no idempotency layer is added.

## Public provenance

`public_source_versions()` remains the single public projection authority. It accepts only valid legacy 1.0 or authoritative 1.1 snapshots and otherwise returns an empty projection. Version/detail responses expose only:

```json
{
  "source_versions": {
    "capture_mode": "AUTHORITATIVE",
    "provenance_completeness": "AUTHORITATIVE",
    "sources": [
      {
        "type": "ALLOCATION_PLAN",
        "id": "31",
        "version": "4",
        "lineage_id": null,
        "digest": "sha256..."
      }
    ]
  }
}
```

The projection must never disclose a tenant ID, raw snapshot/evidence object, internal metadata key beginning with `_`, filesystem path, JWT, provider credential, secret, or absolute export path. Unknown schema versions, malformed source arrays, unknown types, missing required fields, or invalid digests fail closed to `{}`.

## Export provenance

Exporters consume only the serialized report and its safe `source_versions` projection; they must never read database rows or raw source snapshots.

- JSON contains a structured `provenance` object with report code/type, version, template version, generated time, generation mode, input digest, source versions, and already-safe citations.
- Markdown contains a fixed `## Version provenance` block immediately after its title.
- DOCX contains a fixed provenance table near the document header before report sections.

All three render the same safe fields and omit unsafe values. Existing filenames remain `{report_code}-v{version_number}.{ext}`.

## Error handling and compatibility

The C2B lock, version uniqueness, generation-state guard, and C2C lifecycle permissions are unchanged. A failed child source-ref insertion rolls back the child version transaction; no partial child provenance is committed. Reports created before C2D-A without source refs remain valid: their legacy snapshot can be projected when valid, and regeneration has no invented source rows to copy.

## Tests and acceptance

New tests prove:

- regenerated children receive value-identical but separately persisted parent source refs without querying current sources;
- parent/child source snapshots, input digests, template versions, and public projections remain equal after a source object changes;
- malformed/unsafe provenance never reaches report APIs or exports;
- JSON includes structured provenance, Markdown includes its fixed block, and DOCX includes its fixed table;
- tenant-safe report detail, C2B regenerate, C2C lifecycle, existing exports, migration tests, Ruff, and `git diff --check` remain green.

C2D-C is complete only when these tests pass, the three exports retain their filenames, and no C2D-C code changes frontend, lifecycle, business-source state, or current-source regeneration behavior.
