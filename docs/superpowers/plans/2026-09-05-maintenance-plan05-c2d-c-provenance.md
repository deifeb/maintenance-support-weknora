# Plan 05 C2D-C Provenance Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Preserve exact durable report sources across regeneration and expose a common, safe provenance projection in detail and all export formats.

**Architecture:** Regeneration copies the parent source-ref rows in the same locked transaction that creates its child version. The report serializer remains the sole consumer of the fail-closed public provenance projection; JSON, Markdown, and DOCX render only that serialized data.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy, pytest, python-docx, Ruff.

## Global Constraints

- Base: C2D-B closure head 1b6a25e3297e24d6947fb5341fc791c45f58e27d.
- Regeneration deep-copies parent snapshot, input digest, template version, and all source refs in ordinal order; rows have new child identities.
- Regeneration never reads/replaces/recomputes a current business source and never invokes ReportSourceService.
- Preserve C2B tenant lock, unique report version behavior, and REPORT_REGENERATE_SOURCE_NOT_READY.
- Use public_source_versions() only; raw snapshots/evidence, tenant IDs, paths, internal metadata, JWTs, credentials, and secrets are never public.
- JSON, Markdown, and DOCX use the same safe provenance; filenames remain {report_code}-v{version_number}.{ext}.
- Do not change frontend, report-type policy, creation/list behavior, lifecycle behavior, source backfill, automatic supersede, or C2D-B contracts.

---

## Task 1: Exact source-reference copying during regeneration

**Files:**
- Modify: extensions/maintenance-api/app/services/ai_report_service.py:426-520
- Modify: extensions/maintenance-api/app/repositories/ai_report_repository.py:596-675
- Create: extensions/maintenance-api/tests/services/test_report_regeneration_source_refs.py
- Modify: extensions/maintenance-api/tests/services/test_report_regeneration_lineage.py

**Interfaces:**
- Consumes: AIReportRepository.list_source_refs(session, tenant_id, report_version_id) and create_source_refs(session, tenant_id, report_version_id, records).
- Produces: a child version whose refs have exact parent values and a distinct report_version_id.

- [ ] **Step 1: Write failing drift and copy tests**

~~~
def test_regenerate_copies_exact_source_refs_without_querying_latest(
    service, session, actor, seeded_report, monkeypatch
):
    parent = service.latest_version(session, actor, seeded_report.id)
    parent_refs = repository.list_source_refs(session, actor.tenant_id, parent.id)
    monkeypatch.setattr(
        "app.services.report_source_service.ReportSourceService.resolve_for_create",
        lambda *args, **kwargs: pytest.fail("regeneration queried current source"),
    )
    child = service.regenerate(session, actor, seeded_report.id)
    child_refs = repository.list_source_refs(session, actor.tenant_id, child.id)
    assert [ref.report_version_id for ref in child_refs] == [child.id] * len(parent_refs)
    assert [(r.source_type, r.source_id, r.source_version, r.ordinal, r.evidence_json) for r in child_refs] == [
        (r.source_type, r.source_id, r.source_version, r.ordinal, r.evidence_json) for r in parent_refs
    ]


def test_regeneration_ignores_source_change_after_v1(service, session, actor, report_factory):
    report, source = report_factory.report_with_demand_list()
    parent = service.latest_version(session, actor, report.id)
    source.version += 1
    session.commit()
    child = service.regenerate(session, actor, report.id)
    assert child.input_digest == parent.input_digest
    assert child.source_snapshot_json == parent.source_snapshot_json
    assert child.template_version == parent.template_version
~~~

- [ ] **Step 2: Run the tests and verify failure**

Run:

~~~
& 'E:\weknora_projects\maintenance-support-weknora\extensions\maintenance-api\.venv\Scripts\python.exe' -m pytest tests/services/test_report_regeneration_source_refs.py tests/services/test_report_regeneration_lineage.py -q
~~~

Expected: FAIL because child source refs are not copied.

- [ ] **Step 3: Copy parent refs in the existing regenerate transaction**

After create_version() has returned the child, read the parent refs tenant-scoped, map each one to the repository create_source_refs input shape, and insert them against child.id before the existing commit:

~~~
parent_refs = self.repository.list_source_refs(session, actor.tenant_id, parent.id)
self.repository.create_source_refs(
    session, actor.tenant_id, child.id,
    tuple(
        ReportSourceRecord(
            source_type=row.source_type,
            source_id=row.source_id,
            source_version=row.source_version,
            source_lineage_id=row.source_lineage_id,
            source_digest=row.source_digest,
            evidence=copy.deepcopy(row.evidence_json),
        )
        for row in parent_refs
    ),
)
~~~

Preserve each parent ordinal: extend create_source_refs with an optional ordered-record input only if its current enumeration would otherwise change ordinal. Do not call ReportSourceService or any business repository.

- [ ] **Step 4: Run focused source-copy tests**

~~~
& 'E:\weknora_projects\maintenance-support-weknora\extensions\maintenance-api\.venv\Scripts\python.exe' -m pytest tests/services/test_report_regeneration_source_refs.py tests/services/test_report_regeneration_lineage.py tests/api/test_report_center_regenerate_api.py -q
~~~

Expected: PASS; source changes made after v1 never appear in v2.

- [ ] **Step 5: Commit**

~~~
git add extensions/maintenance-api/app/services/ai_report_service.py extensions/maintenance-api/app/repositories/ai_report_repository.py extensions/maintenance-api/tests/services/test_report_regeneration_source_refs.py extensions/maintenance-api/tests/services/test_report_regeneration_lineage.py
git commit -m "feat(maintenance): copy report source refs on regenerate"
~~~

## Task 2: Single safe provenance projection for API and exports

**Files:**
- Modify only if a failing test proves required: extensions/maintenance-api/app/services/report_version_provenance.py
- Modify: extensions/maintenance-api/app/services/ai_report_service.py:700-750
- Modify: extensions/maintenance-api/app/exporters/ai_report_json.py
- Modify: extensions/maintenance-api/app/exporters/ai_report_markdown.py
- Modify: extensions/maintenance-api/app/exporters/ai_report_docx.py
- Create: extensions/maintenance-api/tests/api/test_report_center_source_provenance_api.py
- Create: extensions/maintenance-api/tests/exporters/test_ai_report_source_provenance.py

**Interfaces:**
- Consumes: public_source_versions(snapshot) -> dict[str, Any].
- Produces: serialized report source_versions and export provenance derived solely from it.

- [ ] **Step 1: Write failing safe-output tests**

~~~
def test_public_provenance_never_exposes_raw_snapshot(client, viewer_headers, report_factory):
    report = report_factory.report_with_sensitive_source_evidence()
    body = client.get(f"/api/v1/reports/{report.id}", headers=viewer_headers).text
    assert "source_snapshot_json" not in body
    assert "tenant_id" not in body
    assert "provider_token" not in body
    assert "sources" in body


def test_json_markdown_docx_include_safe_provenance(report_payload):
    json_export = export_report_json(report_payload)
    markdown_export = export_report_markdown(report_payload)
    docx_export = export_report_docx(report_payload)
    assert json.loads(json_export)["provenance"]["source_versions"] == report_payload["source_versions"]
    assert "## Version provenance" in markdown_export
    assert "Input digest" in document_text(docx_export)
~~~

- [ ] **Step 2: Run and verify failure**

~~~
& 'E:\weknora_projects\maintenance-support-weknora\extensions\maintenance-api\.venv\Scripts\python.exe' -m pytest tests/api/test_report_center_source_provenance_api.py tests/exporters/test_ai_report_source_provenance.py -q
~~~

Expected: FAIL until every format provides the same safe fields.

- [ ] **Step 3: Serialize and render one safe provenance value**

Keep ai_report_service.serialize() as the only point that calls public_source_versions(). JSON adds a provenance object with report_code, report_type, version_number, template_version, generated_at, generation_mode, input_digest, source_versions, and citations. Markdown's existing Version provenance block and DOCX's existing provenance table must use these serialized keys only. Never pass source_snapshot_json, metadata_json, export path, or ORM rows to exporters.

For any malformed snapshot, public_source_versions() returns {} unchanged; exports render safe empty/unavailable fields without trying to recover raw data.

- [ ] **Step 4: Run API and exporter regressions**

~~~
& 'E:\weknora_projects\maintenance-support-weknora\extensions\maintenance-api\.venv\Scripts\python.exe' -m pytest tests/api/test_report_center_source_provenance_api.py tests/exporters/test_ai_report_source_provenance.py tests/exporters/test_ai_report_exports.py tests/exporters/test_report_version_provenance_exports.py -q
~~~

Expected: PASS; no export includes unsafe provenance and filenames remain unchanged.

- [ ] **Step 5: Commit**

~~~
git add extensions/maintenance-api/app/services/report_version_provenance.py extensions/maintenance-api/app/services/ai_report_service.py extensions/maintenance-api/app/exporters/ai_report_json.py extensions/maintenance-api/app/exporters/ai_report_markdown.py extensions/maintenance-api/app/exporters/ai_report_docx.py extensions/maintenance-api/tests/api/test_report_center_source_provenance_api.py extensions/maintenance-api/tests/exporters/test_ai_report_source_provenance.py
git commit -m "feat(maintenance): export safe report provenance"
~~~

## Task 3: C2D-C closure gate

**Files:**
- Create: docs/superpowers/sdd/c2d-c-closure.md

**Interfaces:**
- Consumes: Tasks 1-2.
- Produces: verified evidence that C2D-C preserves C2B/C2C while completing source-copy and provenance coverage.

- [ ] **Step 1: Run complete C2D-C matrix**

~~~
& 'E:\weknora_projects\maintenance-support-weknora\extensions\maintenance-api\.venv\Scripts\python.exe' -m pytest tests/services/test_report_regeneration_source_refs.py tests/exporters/test_ai_report_source_provenance.py tests/api/test_report_center_source_provenance_api.py tests/services/test_report_regeneration_lineage.py tests/api/test_report_center_regenerate_api.py tests/api/test_report_center_lifecycle_api.py tests/api/test_report_center_facade_api.py tests/api/test_report_center_api.py tests/services/test_ai_report_service.py tests/exporters/test_ai_report_exports.py tests/migrations -q
& 'E:\weknora_projects\maintenance-support-weknora\extensions\maintenance-api\.venv\Scripts\python.exe' -m ruff check app tests
git diff --check
~~~

Expected: all selected tests pass, Ruff passes, and diff check has no output.

- [ ] **Step 2: Record evidence and commit**

Write docs/superpowers/sdd/c2d-c-closure.md with base/head SHA, commands, pass counts, Alembic head, accepted warnings, and confirmation that no frontend/current-source regeneration/lifecycle/C2D-B policy work changed.

~~~
git add docs/superpowers/sdd/c2d-c-closure.md
git commit -m "docs(maintenance): close c2d-c execution"
~~~

## Plan self-review

- Task 1 completes the missing durable child source refs and proves no current-source drift.
- Task 2 uses the single fail-closed public projection in detail and every export.
- Task 3 verifies C2B regeneration, C2C lifecycle, migration, export, lint, and whitespace gates.
- No task adds frontend, recomputation, source-policy changes, lifecycle changes, source backfill, or C2D-C idempotency.

