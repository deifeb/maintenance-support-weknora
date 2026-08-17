from __future__ import annotations

import importlib
import inspect
from decimal import Decimal

import pytest
from app.models import (
    CalculationGroup,
    DemandList,
    DemandListEvent,
    DemandScenarioTemplate,
    DemandScenarioVersion,
    SparePart,
)
from app.models.enums import (
    CalculationGroupStatus,
    DemandListEventType,
    DemandListStatus,
)
from app.repositories.demand_list_repository import DemandListRepository
from app.schemas.inventory_ledger import InventorySummaryRead
from app.services.inventory_query_service import InventoryQueryService
from app.services.snapshot_service import snapshot_service
from pydantic import ValidationError
from sqlalchemy.orm import Session

FEATURE_MARKER = "PLAN05_4C_TASK2_FEATURE_MISSING"
SCHEMA_MODULE = "app.schemas.demand_review"
SNAPSHOT_MODULE = "app.services.demand_review_snapshot"


def _future(module_name: str):
    try:
        return importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        if exc.name == module_name:
            pytest.fail(
                f"{FEATURE_MARKER}: {module_name}",
                pytrace=False,
            )
        raise


def _create_source(
    session: Session,
    tenant_id: str,
    suffix: str,
) -> tuple[DemandList, list]:
    template = DemandScenarioTemplate(
        tenant_id=tenant_id,
        code=f"SC-SNAPSHOT-{suffix}",
        name=f"Scenario {suffix}",
    )
    session.add(template)
    session.flush()
    version = DemandScenarioVersion(
        tenant_id=tenant_id,
        scenario_template_id=template.id,
        version_code=f"V-SNAPSHOT-{suffix}",
        version_name=f"Version {suffix}",
    )
    session.add(version)
    session.flush()
    group = CalculationGroup(
        tenant_id=tenant_id,
        scenario_version_id=version.id,
        status=CalculationGroupStatus.COMPLETED,
        primary_candidate_key="WEIBULL:ANALYTICAL",
        recommendation_snapshot_json={},
        parameter_snapshot_json={},
        created_by_user_id=f"user-{suffix}",
        created_by_request_id=f"request-{suffix}",
    )
    session.add(group)
    session.flush()
    source = DemandListRepository().create_version(
        session,
        tenant_id,
        {
            "name": f"Snapshot source {suffix}",
            "scenario_version_id": version.id,
            "calculation_group_id": group.id,
            "status": DemandListStatus.PUBLISHED,
            "is_current": True,
            "created_by_user_id": f"user-{suffix}",
            "created_by_request_id": f"request-{suffix}",
        },
    )
    source.status = DemandListStatus.PUBLISHED
    source.is_current = True
    spares = [
        SparePart(
            tenant_id=tenant_id,
            code=f"SP-SNAPSHOT-{suffix}-{index}",
            name=f"Spare {suffix} {index}",
            unit="EA",
            is_critical=index == 1,
        )
        for index in (1, 2)
    ]
    session.add_all(spares)
    session.flush()
    items = [
        DemandListRepository().add_item(
            session,
            tenant_id,
            demand_list_id=source.id,
            spare_part_id=spare.id,
            original_quantity=Decimal(f"{index}.000000"),
            final_quantity=Decimal(f"{index}.000000"),
            source_snapshot={"index": index},
            spare_part_code_snapshot=spare.code,
            spare_part_name_snapshot=spare.name,
            spare_part_unit_snapshot=spare.unit,
            parameter_snapshot_json={"index": index},
            decision_snapshot_json={"decision": index},
        )
        for index, spare in enumerate(spares, start=1)
    ]
    session.flush()
    return source, items


def _summary(
    *,
    warehouse_id: int,
    spare_part_id: int,
    on_hand: str,
) -> InventorySummaryRead:
    return InventorySummaryRead(
        warehouse_id=warehouse_id,
        spare_part_id=spare_part_id,
        on_hand_quantity=Decimal(on_hand),
        reserved_quantity=Decimal("0.0000"),
        damaged_quantity=Decimal("0.0000"),
        quarantined_quantity=Decimal("0.0000"),
        in_transit_quantity=Decimal("0.0000"),
        safety_stock=Decimal("0.0000"),
        reorder_point=Decimal("0.0000"),
        maximum_stock=None,
    )


def test_formal_run_schema_is_frozen_and_rejects_client_authority() -> None:
    schema = _future(SCHEMA_MODULE)
    request_type = schema.DemandReviewRunRequest
    assert set(request_type.model_fields) == {"expected_source_version"}

    with pytest.raises(ValidationError):
        request_type.model_validate(
            {
                "expected_source_version": 1,
                "tenant_id": "tenant-b",
            }
        )
    with pytest.raises(ValidationError):
        request_type.model_validate(
            {
                "expected_source_version": 1,
                "items": [{"spare_part_id": 1}],
                "evidence": [{"kind": "client"}],
            }
        )

    snapshot = schema.DemandReviewSnapshot(
        schema_version="1",
        captured_at="2026-08-17T00:00:00+00:00",
        request={
            "command": "RUN",
            "demand_list_id": 1,
            "expected_source_version": 1,
        },
        source_demand_list={},
        source_items=(),
        source_events=(),
        current_inventory=(),
        master_data_evidence={},
        rule_set_version="DEMAND-REVIEW-1",
        input_hash="a" * 64,
    )
    with pytest.raises(ValidationError):
        snapshot.input_hash = "b" * 64


def test_snapshot_builder_signature_has_no_client_evidence_parameters() -> None:
    module = _future(SNAPSHOT_MODULE)
    parameters = list(
        inspect.signature(
            module.DemandReviewSnapshotBuilder.build
        ).parameters
    )
    assert parameters == [
        "self",
        "session",
        "actor",
        "source",
        "items",
        "events",
    ]


def test_snapshot_uses_one_inventory_query_call_and_canonical_order(
    session: Session,
    actor_context,
    monkeypatch,
) -> None:
    module = _future(SNAPSHOT_MODULE)
    source, items = _create_source(session, "tenant-a", "ORDER")
    actor = actor_context(tenant_id="tenant-a")
    events = [
        DemandListEvent(
            tenant_id="tenant-a",
            demand_list_id=source.id,
            event_type=DemandListEventType.PUBLISHED,
            actor_user_id="admin-a",
            actor_roles_json=["admin"],
            request_id="request-published",
            after_summary_json={"status": "PUBLISHED"},
        ),
        DemandListEvent(
            tenant_id="tenant-a",
            demand_list_id=source.id,
            event_type=DemandListEventType.CREATED,
            actor_user_id="user-a",
            actor_roles_json=["contributor"],
            request_id="request-created",
            after_summary_json={"status": "DRAFT"},
        ),
    ]
    session.add_all(events)
    session.flush()

    calls: list[tuple[object, object, list[int]]] = []

    def summaries_for_parts(
        self,
        session_arg,
        actor_arg,
        spare_part_ids,
    ):
        del self
        calls.append(
            (
                session_arg,
                actor_arg,
                list(spare_part_ids),
            )
        )
        return [
            _summary(
                warehouse_id=2,
                spare_part_id=items[1].spare_part_id,
                on_hand="2.0000",
            ),
            _summary(
                warehouse_id=1,
                spare_part_id=items[0].spare_part_id,
                on_hand="1.0000",
            ),
        ]

    monkeypatch.setattr(
        InventoryQueryService,
        "summaries_for_parts",
        summaries_for_parts,
    )

    snapshot = module.DemandReviewSnapshotBuilder().build(
        session,
        actor,
        source,
        list(reversed(items)),
        list(reversed(events)),
    )

    assert len(calls) == 1
    assert calls[0][0] is session
    assert calls[0][1] is actor
    assert calls[0][2] == [
        item.spare_part_id
        for item in reversed(items)
    ]
    assert [
        row["id"]
        for row in snapshot.source_items
    ] == sorted(item.id for item in items)
    assert [
        (
            row["warehouse_id"],
            row["spare_part_id"],
        )
        for row in snapshot.current_inventory
    ] == sorted(
        (
            row["warehouse_id"],
            row["spare_part_id"],
        )
        for row in snapshot.current_inventory
    )


def test_snapshot_master_data_is_tenant_scoped_and_fail_closed(
    session: Session,
    actor_context,
    monkeypatch,
) -> None:
    module = _future(SNAPSHOT_MODULE)
    source, items = _create_source(session, "tenant-a", "AUTH")
    hidden = SparePart(
        tenant_id="tenant-b",
        code="SP-HIDDEN-TENANT-B",
        name="Hidden tenant B",
        unit="EA",
    )
    session.add(hidden)
    session.flush()

    def summaries_for_parts(
        self,
        session_arg,
        actor_arg,
        spare_part_ids,
    ):
        del self, session_arg, actor_arg, spare_part_ids
        return []

    monkeypatch.setattr(
        InventoryQueryService,
        "summaries_for_parts",
        summaries_for_parts,
    )

    snapshot = module.DemandReviewSnapshotBuilder().build(
        session,
        actor_context(tenant_id="tenant-a"),
        source,
        items,
        [],
    )
    evidence = snapshot.master_data_evidence

    assert set(evidence) >= {
        "parts_by_id",
        "spare_parts_by_id",
        "reliability_profiles_by_id",
        "configuration_versions_by_id",
        "configuration_items_by_id",
        "substitution_evidence",
        "kit_evidence",
    }
    assert "SP-HIDDEN-TENANT-B" not in snapshot_service.canonical_json(
        evidence
    )
    for key in (
        "parts_by_id",
        "spare_parts_by_id",
        "reliability_profiles_by_id",
        "configuration_versions_by_id",
        "configuration_items_by_id",
    ):
        assert list(evidence[key]) == sorted(
            evidence[key],
            key=str,
        )
    for key in ("substitution_evidence", "kit_evidence"):
        assert evidence[key] == {
            "status": "UNAVAILABLE",
            "records": [],
            "reason": "NO_AUTHORITATIVE_RELATION",
        }


def test_input_hash_covers_canonical_snapshot_except_itself(
    session: Session,
    actor_context,
    monkeypatch,
) -> None:
    module = _future(SNAPSHOT_MODULE)
    source, items = _create_source(session, "tenant-a", "HASH")

    monkeypatch.setattr(
        InventoryQueryService,
        "summaries_for_parts",
        lambda self, session_arg, actor_arg, spare_part_ids: [],
    )
    snapshot = module.DemandReviewSnapshotBuilder().build(
        session,
        actor_context(tenant_id="tenant-a"),
        source,
        items,
        [],
    )
    payload = snapshot.model_dump(mode="python")
    input_hash = payload.pop("input_hash")
    assert input_hash == snapshot_service.canonical_hash(payload)
