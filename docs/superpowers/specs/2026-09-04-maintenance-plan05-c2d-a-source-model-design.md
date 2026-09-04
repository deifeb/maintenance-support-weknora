# Plan 05 C2D-A Report Source Model Design

**Date:** 2026-09-04

**Status:** Approved design; implementation plan pending review

## Goal

Introduce durable, tenant-scoped report-source references and the Snapshot 1.1 format without widening the public report-type enum, changing Report Center lifecycle behavior, or altering the frontend.

## Existing Contract to Preserve

- One `AIReportJob` represents one report lineage; regeneration appends a child `AIReportVersion` with a linear parent chain.
- Generation and regeneration use immutable snapshots. Regeneration must not query latest business data.
- `input_digest` remains the SHA-256 digest of canonical source-snapshot JSON.
- C2C lifecycle states, permissions, error contracts, and tenant-first 404 behavior are unchanged.
- Existing Snapshot 1.0 rows remain readable and are never fake-backfilled.
- `MANAGEMENT_DECISION` stays supported. C2D-A does not add the other report types; that is C2D-B work.

## Selected Approach

Use complementary representations:

```text
AIReportSourceRef       durable query and audit identity
source_snapshot_json    immutable historical generation truth
```

Using JSON alone would not provide indexed, constrained source lookup. Per-source-type association tables would duplicate schema and query paths without a current need. A single normalized source-reference model keeps the source contract uniform while the snapshot preserves the exact inputs used at generation time.

## Data Model

Add `AIReportSourceType` with these values:

```text
AI_SESSION
SCENARIO_VERSION
CALCULATION_RUN
CALCULATION_GROUP
DEMAND_LIST
DEMAND_REVIEW
ALLOCATION_PLAN
INVENTORY_STOCKTAKE
```

Add tenant-scoped `AIReportSourceRef`:

| Field | Purpose |
| --- | --- |
| `id` | Surrogate primary key. |
| `tenant_id` | Tenant scope copied only after validating the referenced report version's tenant. |
| `report_version_id` | Required foreign key to `ai_report_versions.id`. |
| `source_type` | Required `AIReportSourceType`. |
| `source_id` | Required stable business-source identity. |
| `source_version` | Stable observed version token; null only for a policy that explicitly permits it. |
| `source_lineage_id` | Optional source lineage identity. |
| `source_digest` | Optional 64-character SHA-256 canonical digest of the source evidence. |
| `ordinal` | Required, stable position in the source list. |

Database guarantees:

- index `(tenant_id, source_type, source_id)` for tenant-scoped source lookup;
- index `(report_version_id, ordinal)` for ordered provenance retrieval;
- unique `(report_version_id, source_type, source_id, source_version)`;
- a service/repository tenant check before insert, because the single-column foreign key cannot prove that both rows have the same tenant.

The source policy must emit a non-null stable version token for every initially supported authoritative source. This makes the unique constraint effective on all new C2D-A source references and leaves any future null-token exception explicit and testable.

## Source Policy Boundary

`report_source_policy.py` is the single authority for translating a supported business object into a source record. The record contains its type, stable ID, version token, optional lineage ID, optional canonical digest, and safe structured evidence for the snapshot.

Report creation uses the policy to validate tenant scope and build both `AIReportSourceRef` rows and a Snapshot 1.1 source list in the same transaction. The policy does not mutate a business source. C2D-A supports the source-model foundation only; mapping additional report types and templates is deferred to C2D-B/C2D-C.

No `SPARE_PART_RISK` source type is introduced because no durable risk entity exists.

## Snapshot 1.1 and Compatibility

New authoritative creates use the following shape:

```json
{
  "schema_version": "1.1",
  "capture_mode": "AUTHORITATIVE_CREATE",
  "provenance_completeness": "AUTHORITATIVE",
  "report_type": "ALLOCATION_PLAN",
  "template_version": "1.0",
  "sources": [
    {
      "type": "ALLOCATION_PLAN",
      "id": 31,
      "version": "4",
      "lineage_id": null,
      "digest": "sha256-hex"
    }
  ],
  "generation_seed": {}
}
```

Canonical JSON serialization remains sorted-key JSON with UTF-8 encoding and `default=str`, then SHA-256. The persisted snapshot is the regeneration input, so a child version copies the parent's snapshot and digest rather than resolving present-day source objects.

`public_source_versions()` accepts both Snapshot 1.0's keyed `sources` object and Snapshot 1.1's ordered `sources` list. Its public projection preserves stable source order and may expose only capture mode, provenance completeness, source type, ID, version, lineage ID, and digest. It must not expose tenant IDs, raw snapshot JSON, internal filesystem paths, JWTs, provider credentials, or generation seed internals.

## Migration

Create linear revision `20260904_17_add_ai_report_source_refs` with `down_revision = "20260830_16"`. It creates the enum-backed source-reference table, foreign key, indexes, and unique constraint. Upgrade and downgrade operate only on the new table and leave every pre-existing `AIReportVersion` row unchanged.

The revision is valid only while `20260830_16` remains the unique migration head. The preflight on 2026-09-04 confirmed that head; the implementation gate must recheck it immediately before migration creation.

## Error Handling and Security

- Foreign-tenant report-version access resolves as not found before a source-reference mutation is attempted.
- A report version from another tenant cannot receive a source reference, even if its numeric ID is known.
- Duplicate sources for one version fail deterministically at validation and remain backed by the database uniqueness rule.
- Malformed, unsupported, or unsafe snapshot structures are not published through public provenance.
- AI availability is irrelevant to this source-model phase and must not be required to persist or read source references.

## Tests and Acceptance Criteria

The phase begins with failing tests for:

- tenant-scoped report-version enforcement;
- duplicate source-reference rejection;
- canonical Snapshot 1.1 digest;
- public compatibility for Snapshot 1.0 and 1.1;
- no fake backfill of legacy rows;
- migration `base -> head -> base -> head`, including table, foreign key, indexes, unique constraint, and untouched legacy data.

The GREEN gate additionally reruns C2B lineage/regeneration, C2C lifecycle, provenance export, migration, and Ruff coverage. No frontend files, public report-type expansion, lifecycle transition, automatic validation/finalization, or business-source mutation is in scope.

## Non-Goals

- C2D-B report-type expansion and source adapters;
- C2D-C template registry and type-specific generation;
- Report Center frontend work;
- latest-state regeneration, automatic supersede, and source-table backfill;
- branch/worktree cleanup.

## Design Self-Review

- The model separates durable lookup identity from immutable historical truth.
- The migration parent, scope, and reversibility are explicit.
- The security boundary covers cross-tenant writes and public provenance redaction.
- Snapshot compatibility is explicit for both existing 1.0 data and new 1.1 data.
- No requirement relies on a later phase or introduces an unapproved public behavior change.
