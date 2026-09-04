# Plan 05 C2D-A Report Source Model Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add durable, tenant-scoped report-source references and Snapshot 1.1 while preserving C2B lineage/provenance and C2C lifecycle contracts.

**Architecture:** `AIReportSourceRef` is the normalized, indexed identity of every source used by a report version. Snapshot 1.1 remains the immutable generation input and public provenance is a safe projection of either 1.0 or 1.1. The create service builds both representations in one transaction; regeneration still copies the persisted snapshot and never resolves current business data.

**Tech Stack:** Python 3.11, SQLAlchemy, Alembic, pytest, Ruff, SQLite migration tests.

## Global Constraints

- Use base `83f3248b181a083d34962846fffc05a801548970`; recheck that `20260830_16` is the unique Alembic head immediately before writing the migration.
- Preserve the three existing `AIReportType` values; report-type expansion belongs to C2D-B.
- Preserve Snapshot 1.0 reads, existing public error contracts, C2B regeneration, and C2C lifecycle/permission behavior.
- Never backfill legacy `AIReportVersion` rows; never query current sources during regeneration.
- Resolve foreign-tenant objects as not found before mutation; public provenance must not expose raw snapshots, tenant IDs, paths, JWTs, or provider secrets.
- Create no frontend files and change no frontend code.
- Do not push, open a PR, merge, or remove a branch/worktree in this phase.

---

## File Structure

| File | Responsibility |
| --- | --- |
| `app/models/enums.py` | Durable source-type enum. |
| `app/models/ai_report.py` | `AIReportSourceRef` persistence model and constraints. |
| `app/models/__init__.py` | Model export for metadata discovery. |
| `alembic/versions/20260904_17_add_ai_report_source_refs.py` | Linear, reversible source-reference schema migration. |
| `app/services/report_source_policy.py` | Converts authorized current source objects to stable source records. |
| `app/services/report_version_provenance.py` | Builds and safely projects Snapshot 1.1 while retaining 1.0 compatibility. |
| `app/repositories/ai_report_repository.py` | Tenant-checked source-reference persistence and ordered reads. |
| `app/services/ai_report_service.py` | Uses the policy during create and persists references with the version. |
| `tests/migrations/test_ai_report_source_ref_migration.py` | Reversible migration contract. |
| `tests/services/test_report_source_policy.py` | Source policy, tenant, ordering, and duplicate behavior. |
| `tests/services/test_report_source_snapshot.py` | Snapshot 1.1 canonical digest and safe 1.0/1.1 projection behavior. |

### Task 1: Source-reference schema and reversible migration

**Files:**

- Create: `extensions/maintenance-api/alembic/versions/20260904_17_add_ai_report_source_refs.py`
- Create: `extensions/maintenance-api/tests/migrations/test_ai_report_source_ref_migration.py`
- Modify: `extensions/maintenance-api/app/models/enums.py:347-350`
- Modify: `extensions/maintenance-api/app/models/ai_report.py:64-110`
- Modify: `extensions/maintenance-api/app/models/__init__.py:10-18, 170-180`

**Interfaces:**

- Produces `AIReportSourceType` with `AI_SESSION`, `SCENARIO_VERSION`, `CALCULATION_RUN`, `CALCULATION_GROUP`, `DEMAND_LIST`, `DEMAND_REVIEW`, `ALLOCATION_PLAN`, and `INVENTORY_STOCKTAKE`.
- Produces `AIReportSourceRef(report_version_id, source_type, source_id, source_version, source_lineage_id, source_digest, ordinal)` with tenant scope.
- Produces linear Alembic revision `20260904_17` whose parent is `20260830_16`.

- [ ] **Step 1: Write the failing migration contract**

```python
REVISION = "20260904_17"
PREVIOUS_REVISION = "20260830_16"

def test_source_ref_revision_is_the_only_head() -> None:
    script = ScriptDirectory.from_config(Config("alembic.ini"))
    revision = script.get_revision(REVISION)
    assert revision is not None
    assert revision.down_revision == PREVIOUS_REVISION
    assert script.get_heads() == [REVISION]

def test_source_ref_migration_round_trips(tmp_path, monkeypatch) -> None:
    config, url = _config(tmp_path / "source-ref.db", monkeypatch)
    command.upgrade(config, PREVIOUS_REVISION)
    command.upgrade(config, REVISION)
    inspector = inspect(create_engine(url))
    assert "ai_report_source_refs" in inspector.get_table_names()
    assert {"tenant_id", "report_version_id", "source_type", "source_id", "source_version", "source_lineage_id", "source_digest", "ordinal"} <= {column["name"] for column in inspector.get_columns("ai_report_source_refs")}
    assert any(fk["referred_table"] == "ai_report_versions" for fk in inspector.get_foreign_keys("ai_report_source_refs"))
    assert any(index["column_names"] == ["tenant_id", "source_type", "source_id"] for index in inspector.get_indexes("ai_report_source_refs"))
    assert any(constraint["column_names"] == ["report_version_id", "source_type", "source_id", "source_version"] for constraint in inspector.get_unique_constraints("ai_report_source_refs"))
    command.downgrade(config, PREVIOUS_REVISION)
    assert "ai_report_source_refs" not in inspect(create_engine(url)).get_table_names()
    command.upgrade(config, REVISION)
```

- [ ] **Step 2: Run the migration test to prove RED**

Run: `& $pythonPath -m pytest tests/migrations/test_ai_report_source_ref_migration.py -v`

Expected: FAIL because the `20260904_17` revision and `ai_report_source_refs` table do not exist.

- [ ] **Step 3: Implement enum, model export, and migration**

```python
class AIReportSourceType(StrEnum):
    AI_SESSION = "AI_SESSION"
    SCENARIO_VERSION = "SCENARIO_VERSION"
    CALCULATION_RUN = "CALCULATION_RUN"
    CALCULATION_GROUP = "CALCULATION_GROUP"
    DEMAND_LIST = "DEMAND_LIST"
    DEMAND_REVIEW = "DEMAND_REVIEW"
    ALLOCATION_PLAN = "ALLOCATION_PLAN"
    INVENTORY_STOCKTAKE = "INVENTORY_STOCKTAKE"

class AIReportSourceRef(Base, TenantScopedMixin, TimestampMixin):
    __tablename__ = "ai_report_source_refs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_version_id: Mapped[int] = mapped_column(ForeignKey("ai_report_versions.id", ondelete="CASCADE"), nullable=False)
    source_type: Mapped[AIReportSourceType] = mapped_column(Enum(AIReportSourceType, native_enum=False, length=32), nullable=False)
    source_id: Mapped[str] = mapped_column(String(128), nullable=False)
    source_version: Mapped[str | None] = mapped_column(String(128))
    source_lineage_id: Mapped[str | None] = mapped_column(String(128))
    source_digest: Mapped[str | None] = mapped_column(String(64))
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    __table_args__ = (
        Index("ix_ai_report_source_refs_tenant_source", "tenant_id", "source_type", "source_id"),
        Index("ix_ai_report_source_refs_version_ordinal", "report_version_id", "ordinal"),
        UniqueConstraint("report_version_id", "source_type", "source_id", "source_version", name="uq_ai_report_source_ref_version_source"),
    )
```

Set the migration identifiers to `revision = "20260904_17"` and `down_revision = "20260830_16"`; use `op.create_table`, `op.create_index`, and exactly reversed `op.drop_index`/`op.drop_table` operations. Export `AIReportSourceRef` from `app.models` so Alembic metadata includes it.

- [ ] **Step 4: Run the migration test to prove GREEN**

Run: `& $pythonPath -m pytest tests/migrations/test_ai_report_source_ref_migration.py -v`

Expected: PASS, including upgrade, downgrade, re-upgrade, foreign-key, index, and unique-constraint assertions.

- [ ] **Step 5: Commit the schema task**

```powershell
git add extensions/maintenance-api/app/models/enums.py extensions/maintenance-api/app/models/ai_report.py extensions/maintenance-api/app/models/__init__.py extensions/maintenance-api/alembic/versions/20260904_17_add_ai_report_source_refs.py extensions/maintenance-api/tests/migrations/test_ai_report_source_ref_migration.py
git commit -m "feat(maintenance): add report source references"
```

### Task 2: Source policy and Snapshot 1.1 compatibility

**Files:**

- Create: `extensions/maintenance-api/app/services/report_source_policy.py`
- Create: `extensions/maintenance-api/tests/services/test_report_source_policy.py`
- Create: `extensions/maintenance-api/tests/services/test_report_source_snapshot.py`
- Modify: `extensions/maintenance-api/app/services/report_version_provenance.py:14-27, 74-260`

**Interfaces:**

- Consumes authorized `AISession`, `DemandScenarioVersion`, `DemandCalculationRun`, `DemandCalculation`, and `AIReviewRun` records from `AIReportRepository.load_create_sources_owned()`.
- Produces immutable `ReportSourceRecord(source_type: AIReportSourceType, source_id: str, source_version: str, source_lineage_id: str | None, source_digest: str | None, evidence: dict[str, Any])` values ordered by policy declaration.
- Produces `build_authoritative_source_snapshot(report_type: str, template_version: str, metadata: dict[str, Any] | None, source_records: Sequence[ReportSourceRecord]) -> dict[str, Any]` with `schema_version == "1.1"`.

- [ ] **Step 1: Write failing policy and snapshot tests**

```python
def test_current_report_sources_become_stable_ordered_records() -> None:
    records = build_source_records(ai_session=ai_session, scenario_version=scenario, calculation_run=run, calculation=calculation, review_run=review)
    assert [record.source_type.value for record in records] == ["AI_SESSION", "SCENARIO_VERSION", "CALCULATION_RUN", "DEMAND_REVIEW"]
    assert all(record.source_version for record in records)
    assert list(enumerate(records))[-1][0] == 3

def test_snapshot_11_digest_is_canonical() -> None:
    left = {"schema_version": "1.1", "sources": [{"type": "AI_SESSION", "id": 7, "version": "2", "lineage_id": None, "digest": None}]}
    right = {"sources": [{"version": "2", "id": 7, "digest": None, "type": "AI_SESSION", "lineage_id": None}], "schema_version": "1.1"}
    assert source_snapshot_digest(left) == source_snapshot_digest(right)

def test_public_source_versions_supports_10_and_11() -> None:
    assert public_source_versions({"schema_version": "1.0", "capture_mode": "AUTHORITATIVE_CREATE", "sources": {"session": {"id": 7, "version": 2}}})["sources"]["session"]["id"] == 7
    assert public_source_versions({"schema_version": "1.1", "capture_mode": "AUTHORITATIVE_CREATE", "sources": [{"type": "AI_SESSION", "id": 7, "version": "2", "lineage_id": None, "digest": None}]})["sources"][0]["type"] == "AI_SESSION"
```

- [ ] **Step 2: Run focused tests to prove RED**

Run: `& $pythonPath -m pytest tests/services/test_report_source_policy.py tests/services/test_report_source_snapshot.py -v`

Expected: FAIL because `report_source_policy` and Snapshot 1.1 behavior are absent.

- [ ] **Step 3: Implement the source-policy boundary and safe snapshot projection**

```python
@dataclass(frozen=True)
class ReportSourceRecord:
    source_type: AIReportSourceType
    source_id: str
    source_version: str
    source_lineage_id: str | None
    source_digest: str | None
    evidence: dict[str, Any]

def build_source_records(
    *,
    ai_session: AISession | None = None,
    scenario_version: DemandScenarioVersion | None = None,
    calculation_run: DemandCalculationRun | None = None,
    calculation: DemandCalculation | None = None,
    review_run: AIReviewRun | None = None,
) -> Sequence[ReportSourceRecord]:
    candidates = (
        (AIReportSourceType.AI_SESSION, ai_session, lambda row: str(row.version), lambda row: {"id": row.id, "version": row.version, "session_code": row.session_code}),
        (AIReportSourceType.SCENARIO_VERSION, scenario_version, lambda row: str(row.version), lambda row: {"id": row.id, "version": row.version, "version_code": row.version_code, "formula_version": row.formula_version}),
        (AIReportSourceType.CALCULATION_RUN, calculation_run, lambda row: str(row.attempt_number), lambda row: {"id": row.id, "version": row.attempt_number, "calculation_id": row.calculation_id, "engine_version": row.engine_version, "input_snapshot_hash": calculation.input_snapshot_hash if calculation is not None else None}),
        (AIReportSourceType.DEMAND_REVIEW, review_run, lambda row: str(row.version), lambda row: {"id": row.id, "version": row.version, "rule_set_version": row.rule_set_version, "scenario_version_id": row.scenario_version_id, "calculation_run_id": row.calculation_run_id}),
    )
    return tuple(
        ReportSourceRecord(
            source_type=source_type,
            source_id=str(row.id),
            source_version=version_for(row),
            source_lineage_id=None,
            source_digest=source_snapshot_digest(evidence_for(row)),
            evidence=evidence_for(row),
        )
        for source_type, row, version_for, evidence_for in candidates
        if row is not None
    )
```

Change `SOURCE_SNAPSHOT_SCHEMA_VERSION` to `"1.1"` only for authoritative creation. Keep `build_legacy_source_snapshot()` at `"1.0"`. In `public_source_versions()`, construct an allowlisted projection for 1.1 source-list fields `type`, `id`, `version`, `lineage_id`, and `digest`; retain the current 1.0 keyed projection. Do not return `generation_seed` or unrecognized keys.

- [ ] **Step 4: Run focused tests to prove GREEN**

Run: `& $pythonPath -m pytest tests/services/test_report_source_policy.py tests/services/test_report_source_snapshot.py tests/services/test_report_regeneration_lineage.py -v`

Expected: PASS, including canonical digest, ordered 1.1 projection, legacy 1.0 projection, and unchanged regeneration snapshot/digest tests.

- [ ] **Step 5: Commit the policy and compatibility task**

```powershell
git add extensions/maintenance-api/app/services/report_source_policy.py extensions/maintenance-api/app/services/report_version_provenance.py extensions/maintenance-api/tests/services/test_report_source_policy.py extensions/maintenance-api/tests/services/test_report_source_snapshot.py
git commit -m "feat(maintenance): define report source policy"
```

### Task 3: Persist source references during report creation

**Files:**

- Modify: `extensions/maintenance-api/app/repositories/ai_report_repository.py:455-552`
- Modify: `extensions/maintenance-api/app/services/ai_report_service.py:157-231`
- Modify: `extensions/maintenance-api/tests/services/test_report_source_policy.py`

**Interfaces:**

- Consumes `Sequence[ReportSourceRecord]` from `build_source_records()` and a newly persisted `AIReportVersion`.
- Produces `AIReportRepository.create_source_refs(session, tenant_id, report_version_id, records) -> list[AIReportSourceRef]` and `list_source_refs(session, tenant_id, report_version_id) -> list[AIReportSourceRef]` ordered by `ordinal`.
- Preserves `AIReportService.create(session, actor, payload) -> AIReportJob` and all existing create payloads.

- [ ] **Step 1: Write failing persistence and tenant-isolation tests**

```python
def test_create_persists_source_refs_with_the_snapshot(session, actor_context) -> None:
    actor = actor_context(tenant_id="tenant-a", user_id="author", role=MaintenanceRole.CONTRIBUTOR)
    job = ai_report_service.create(session, actor, _create_payload_with_owned_sources())
    version = ai_report_service.latest_version(session, actor, job.id)
    refs = ai_report_repository.list_source_refs(session, actor.tenant_id, version.id)
    assert [(ref.source_type.value, ref.source_id, ref.ordinal) for ref in refs] == [("AI_SESSION", "1", 0)]
    assert version.source_snapshot_json["schema_version"] == "1.1"

def test_source_ref_requires_tenant_scoped_version(session, actor_context) -> None:
    foreign = actor_context(tenant_id="tenant-b", user_id="foreign", role=MaintenanceRole.CONTRIBUTOR)
    foreign_version = _create_version_for(session, foreign)
    with pytest.raises(LookupError):
        ai_report_repository.create_source_refs(session, "tenant-a", foreign_version.id, (_record(),))

def test_source_ref_unique_within_report_version(session, actor_context) -> None:
    actor = actor_context(tenant_id="tenant-a", user_id="author", role=MaintenanceRole.CONTRIBUTOR)
    version = _create_version_for(session, actor)
    ai_report_repository.create_source_refs(session, actor.tenant_id, version.id, (_record(),))
    with pytest.raises(IntegrityError):
        ai_report_repository.create_source_refs(session, actor.tenant_id, version.id, (_record(),))
```

- [ ] **Step 2: Run persistence tests to prove RED**

Run: `& $pythonPath -m pytest tests/services/test_report_source_policy.py::test_create_persists_source_refs_with_the_snapshot tests/services/test_report_source_policy.py::test_source_ref_requires_tenant_scoped_version tests/services/test_report_source_policy.py::test_source_ref_unique_within_report_version -v`

Expected: FAIL because source-reference repository methods and Snapshot 1.1 create integration are absent.

- [ ] **Step 3: Implement tenant-checked persistence and create integration**

```python
def create_source_refs(self, session: Session, tenant_id: str, report_version_id: int, records: Sequence[ReportSourceRecord]) -> list[AIReportSourceRef]:
    _require_owned(session, tenant_id, AIReportVersion, report_version_id)
    rows = [AIReportSourceRef(tenant_id=tenant_id, report_version_id=report_version_id, source_type=record.source_type, source_id=record.source_id, source_version=record.source_version, source_lineage_id=record.source_lineage_id, source_digest=record.source_digest, ordinal=ordinal) for ordinal, record in enumerate(records)]
    session.add_all(rows)
    session.flush()
    return rows
```

In `AIReportService.create`, keep the existing owned-source lookup first. Build records from the returned objects, create the Snapshot 1.1 from those records, create the version, and call `create_source_refs()` before the existing `session.commit()`. Catch `LookupError` through the current `NotFoundError("ai_report_source", "linked")` path. Do not touch `regenerate()`; it must continue copying the parent snapshot and input digest.

- [ ] **Step 4: Run persistence plus inherited regressions to prove GREEN**

Run: `& $pythonPath -m pytest tests/services/test_report_source_policy.py tests/services/test_report_source_snapshot.py tests/services/test_report_regeneration_lineage.py tests/api/test_report_center_lifecycle_api.py tests/api/test_report_center_regenerate_api.py tests/exporters/test_report_version_provenance_exports.py tests/migrations/test_ai_report_source_ref_migration.py -v`

Expected: PASS with all existing C2B/C2C behavior unchanged and new references written only for new report versions.

- [ ] **Step 5: Run exact static checks**

Run: `& $pythonPath -m ruff check app/models/enums.py app/models/ai_report.py app/models/__init__.py app/repositories/ai_report_repository.py app/services/ai_report_service.py app/services/report_source_policy.py app/services/report_version_provenance.py tests/migrations/test_ai_report_source_ref_migration.py tests/services/test_report_source_policy.py tests/services/test_report_source_snapshot.py`

Expected: exit code `0`.

- [ ] **Step 6: Commit the integration task**

```powershell
git add extensions/maintenance-api/app/repositories/ai_report_repository.py extensions/maintenance-api/app/services/ai_report_service.py extensions/maintenance-api/tests/services/test_report_source_policy.py
git commit -m "feat(maintenance): persist report source provenance"
git diff --check HEAD~3..HEAD
git status --short
```

## Plan Self-Review

**Spec coverage:** Task 1 implements the enum, durable source model, constraints, and reversible migration. Task 2 implements policy ownership, canonical Snapshot 1.1, 1.0 readability, safe provenance projection, and no risk source. Task 3 persists only tenant-authorized source references at creation and preserves regeneration/lifecycle behavior.

**Scope correction:** The source document's original file inventory omits `app/services/ai_report_service.py`, but its approved requirement that report creation build references and the snapshot in one transaction cannot be met without this existing create orchestration file. The plan changes only that method and retains its public API.

**Placeholder scan:** No incomplete task, deferred implementation marker, or undefined interface remains.

**Type consistency:** `ReportSourceRecord` is created by the policy, consumed by `build_authoritative_source_snapshot()` and `create_source_refs()`, and persisted as `AIReportSourceRef`; all version IDs remain `int`, source identities/versions are stored as strings, and ordered source-record positions are persisted as `ordinal`.
