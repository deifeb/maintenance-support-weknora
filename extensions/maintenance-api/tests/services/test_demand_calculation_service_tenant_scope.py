from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from inspect import signature
from typing import Callable

import pytest
from app.core.exceptions import NotFoundError
from app.models import (
    DemandCalculation,
    DemandCalculationRun,
    DemandScenarioTemplate,
    DemandScenarioVersion,
    InventoryBalance,
    ReliabilityProfile,
    RepairProfile,
    SparePart,
    Warehouse,
    WarehouseLocation,
)
from app.models.enums import (
    CalculationExecutionType,
    DataSourceType,
    DemandExecutionMode,
    ReliabilityModelType,
    ScenarioVersionStatus,
)
from app.repositories.demand_calculation_repository import (
    DemandCalculationRunRepository,
)
from app.repositories.reliability_repository import (
    ReliabilityRepository,
)
from app.repositories.repair_repository import (
    RepairRepository,
)
from app.schemas.demand_calculation import (
    CalculationCreateRequest,
    CalculationPreviewRequest,
)
from app.security.actor import ActorContext
from app.services.demand_calculation_service import (
    DemandCalculationService,
    calculation_service,
)
from app.services.inventory_query_service import InventoryQueryService
from sqlalchemy.orm import Session


def add_spare(
    session: Session,
    tenant_id: str,
    suffix: str,
) -> SparePart:
    row = SparePart(
        tenant_id=tenant_id,
        code=f"SP-{suffix}",
        name=f"Spare {suffix}",
        unit="piece",
        is_repairable=True,
    )
    session.add(row)
    session.flush()
    return row


def add_warehouse(
    session: Session,
    tenant_id: str,
    suffix: str,
) -> Warehouse:
    row = Warehouse(
        tenant_id=tenant_id,
        code=f"WH-{suffix}",
        name=f"Warehouse {suffix}",
    )
    session.add(row)
    session.flush()
    return row


def add_calculation(
    session: Session,
    tenant_id: str,
    suffix: str,
) -> DemandCalculation:
    now = datetime.now(timezone.utc)
    row = DemandCalculation(
        tenant_id=tenant_id,
        calculation_code=f"CALC-{suffix}",
        calculation_name=f"Calculation {suffix}",
        execution_type=(
            CalculationExecutionType.SYNCHRONOUS
        ),
        requested_mode=DemandExecutionMode.ANALYTICAL,
        input_snapshot_json={},
        input_snapshot_hash=(suffix * 64)[:64],
        inventory_snapshot_at=now,
        submitted_at=now,
    )
    session.add(row)
    session.flush()
    return row


def temporary_payload(
    spare_part_id: int,
    *,
    code: str = "UNTRUSTED",
    name: str = "Untrusted",
) -> CalculationPreviewRequest:
    return CalculationPreviewRequest(
        temporary_scenario={
            "tenant_id": "tenant-b",
            "stages": [
                {
                    "code": "S1",
                    "name": "Stage",
                    "order": 1,
                    "duration_hours": "1",
                }
            ],
            "items": [
                {
                    "tenant_id": "tenant-b",
                    "spare_part_id": spare_part_id,
                    "spare_part_code": code,
                    "spare_part_name": name,
                    "installed_positions": "1",
                    "replacement_ratio": "1",
                    "is_repairable": False,
                    "reliability": {
                        "model_type": "EXPONENTIAL",
                        "failure_rate": "0.01",
                    },
                    "inventory": {},
                    "nested": {
                        "tenant_id": "tenant-b",
                        "kept": True,
                    },
                }
            ],
        }
    )


def test_calculation_preview_methods_require_actor() -> None:
    for method_name in ("preview", "build_snapshot"):
        assert "actor" in signature(
            getattr(
                DemandCalculationService,
                method_name,
            )
        ).parameters


def test_calculation_selection_repositories_require_tenant(
) -> None:
    matrix = (
        (
            ReliabilityRepository,
            "list_active_for_selection",
        ),
        (
            RepairRepository,
            "list_active_for_selection",
        ),
        (
            DemandCalculationRunRepository,
            "next_attempt",
        ),
    )

    for repository_type, method_name in matrix:
        method = getattr(
            repository_type,
            method_name,
            None,
        )
        assert method is not None
        assert "tenant_id" in signature(method).parameters

    for method_name in (
        "summary_for_part",
        "summaries_for_parts",
    ):
        assert "actor" in signature(
            getattr(InventoryQueryService, method_name)
        ).parameters


def test_next_attempt_ignores_foreign_runs(
    session: Session,
) -> None:
    calculation = add_calculation(
        session,
        "tenant-a",
        "ATTEMPT",
    )
    session.add_all(
        [
            DemandCalculationRun(
                tenant_id="tenant-a",
                calculation_id=calculation.id,
                run_mode=DemandExecutionMode.ANALYTICAL,
                attempt_number=2,
                engine_version="test",
                formula_version="test",
            ),
            DemandCalculationRun(
                tenant_id="tenant-b",
                calculation_id=calculation.id,
                run_mode=DemandExecutionMode.ANALYTICAL,
                attempt_number=99,
                engine_version="test",
                formula_version="test",
            ),
        ]
    )
    session.commit()

    repository = DemandCalculationRunRepository()

    assert repository.next_attempt(
        session,
        "tenant-a",
        calculation.id,
        DemandExecutionMode.ANALYTICAL,
    ) == 3


def test_temporary_snapshot_rejects_foreign_spare(
    session: Session,
    actor_context: Callable[..., ActorContext],
) -> None:
    actor = actor_context(tenant_id="tenant-a")
    foreign = add_spare(
        session,
        "tenant-b",
        "FOREIGN",
    )
    session.commit()

    with pytest.raises(NotFoundError):
        calculation_service.build_snapshot(
            session,
            actor,
            temporary_payload(foreign.id),
        )


def test_temporary_snapshot_uses_trusted_spare_metadata(
    session: Session,
    actor_context: Callable[..., ActorContext],
) -> None:
    actor = actor_context(tenant_id="tenant-a")
    spare = add_spare(
        session,
        actor.tenant_id,
        "LOCAL",
    )
    session.commit()

    snapshot, warnings = (
        calculation_service.build_snapshot(
            session,
            actor,
            temporary_payload(
                spare.id,
                code="SPOOFED",
                name="Spoofed name",
            ),
        )
    )

    assert warnings == []
    assert "tenant_id" not in snapshot
    item = snapshot["items"][0]
    assert item["spare_part_code"] == spare.code
    assert item["spare_part_name"] == spare.name
    assert "tenant_id" not in item
    assert "tenant_id" not in item["nested"]
    assert item["nested"]["kept"] is True


def test_build_snapshot_rejects_foreign_scenario_version(
    session: Session,
    actor_context: Callable[..., ActorContext],
) -> None:
    actor = actor_context(tenant_id="tenant-a")
    template = DemandScenarioTemplate(
        tenant_id="tenant-b",
        code="FOREIGN",
        name="Foreign",
    )
    session.add(template)
    session.flush()
    version = DemandScenarioVersion(
        tenant_id="tenant-b",
        scenario_template_id=template.id,
        version_code="V1",
        version_name="Version 1",
        status=ScenarioVersionStatus.PUBLISHED,
    )
    session.add(version)
    session.commit()

    with pytest.raises(NotFoundError):
        calculation_service.build_snapshot(
            session,
            actor,
            CalculationPreviewRequest(
                scenario_version_id=version.id,
            ),
        )


def test_selection_candidates_ignore_foreign_rows(
    session: Session,
    actor_context: Callable[..., ActorContext],
) -> None:
    actor = actor_context(tenant_id="tenant-a")
    spare = add_spare(
        session,
        actor.tenant_id,
        "SELECT",
    )
    local_warehouse = add_warehouse(
        session,
        actor.tenant_id,
        "LOCAL",
    )
    foreign_warehouse = add_warehouse(
        session,
        "tenant-b",
        "FOREIGN",
    )
    local_location = WarehouseLocation(
        tenant_id=actor.tenant_id,
        warehouse_id=local_warehouse.id,
        code="LOCAL",
        name="Local",
        location_type="SHELF",
    )
    foreign_location = WarehouseLocation(
        tenant_id="tenant-b",
        warehouse_id=foreign_warehouse.id,
        code="FOREIGN",
        name="Foreign",
        location_type="SHELF",
    )
    session.add_all((local_location, foreign_location))
    session.flush()
    local_inventory = InventoryBalance(
        tenant_id=actor.tenant_id,
        warehouse_id=local_warehouse.id,
        location_id=local_location.id,
        spare_part_id=spare.id,
        on_hand_quantity=Decimal("10"),
    )
    foreign_inventory = InventoryBalance(
        tenant_id="tenant-b",
        warehouse_id=foreign_warehouse.id,
        location_id=foreign_location.id,
        spare_part_id=spare.id,
        on_hand_quantity=Decimal("999"),
    )
    local_reliability = ReliabilityProfile(
        tenant_id=actor.tenant_id,
        profile_code="REL-LOCAL",
        spare_part_id=spare.id,
        model_type=ReliabilityModelType.EXPONENTIAL,
        failure_rate=Decimal("0.01"),
        data_source_type=DataSourceType.MANUAL_ESTIMATE,
    )
    foreign_reliability = ReliabilityProfile(
        tenant_id="tenant-b",
        profile_code="REL-FOREIGN",
        spare_part_id=spare.id,
        model_type=ReliabilityModelType.EXPONENTIAL,
        failure_rate=Decimal("0.99"),
        data_source_type=DataSourceType.MAINTENANCE_RECORD,
    )
    local_repair = RepairProfile(
        tenant_id=actor.tenant_id,
        profile_code="REP-LOCAL",
        profile_name="Local repair",
        spare_part_id=spare.id,
        repair_success_rate=Decimal("0.8"),
        condemnation_rate=Decimal("0.1"),
        repair_turnaround_hours=Decimal("24"),
    )
    foreign_repair = RepairProfile(
        tenant_id="tenant-b",
        profile_code="REP-FOREIGN",
        profile_name="Foreign repair",
        spare_part_id=spare.id,
        repair_success_rate=Decimal("0.9"),
        condemnation_rate=Decimal("0.05"),
        repair_turnaround_hours=Decimal("12"),
    )
    session.add_all(
        [
            local_inventory,
            foreign_inventory,
            local_reliability,
            foreign_reliability,
            local_repair,
            foreign_repair,
        ]
    )
    session.commit()

    inventories = calculation_service.inventory_query_service.summary_for_part(
        session,
        actor,
        spare.id,
    )
    reliability = (
        calculation_service._select_reliability(
            session,
            actor,
            spare.id,
            999,
            date.today(),
        )
    )
    repair = calculation_service._select_repair(
        session,
        actor,
        spare.id,
        999,
        None,
        date.today(),
    )

    assert [row.warehouse_id for row in inventories] == [
        local_warehouse.id
    ]
    assert inventories[0].on_hand_quantity == Decimal("10")
    assert reliability is not None
    assert reliability.id == local_reliability.id
    assert repair is not None
    assert repair.id == local_repair.id

# TASK_73C2_EXECUTION_TESTS


def temporary_create_payload(
    spare_part_id: int,
    *,
    execution_preference: str = "SYNC",
    selected_reliability_profile_id: int | None = None,
    selected_repair_profile_id: int | None = None,
) -> CalculationCreateRequest:
    item = {
        "spare_part_id": spare_part_id,
        "spare_part_code": "UNTRUSTED",
        "spare_part_name": "Untrusted",
        "installed_positions": "10",
        "replacement_ratio": "1",
        "is_repairable": False,
        "failure_process_mode": "SINGLE_FAILURE",
        "target_service_level": "0.95",
        "reliability": {
            "model_type": "EXPONENTIAL",
            "failure_rate": "0.01",
        },
        "inventory": {
            "on_hand_quantity": "0",
            "available_quantity": "0",
            "in_transit_quantity": "0",
            "safety_stock": "0",
        },
    }
    if selected_reliability_profile_id is not None:
        item["selected_reliability_profile_id"] = (
            selected_reliability_profile_id
        )
    if selected_repair_profile_id is not None:
        item["selected_repair_profile_id"] = (
            selected_repair_profile_id
        )

    return CalculationCreateRequest(
        calculation_name="Tenant-safe calculation",
        requested_mode=DemandExecutionMode.ANALYTICAL,
        execution_preference=execution_preference,
        random_seed=42,
        temporary_scenario={
            "calculation_code": "TEMP-TENANT",
            "stages": [
                {
                    "code": "S1",
                    "name": "Stage 1",
                    "order": 1,
                    "duration_hours": "100",
                    "utilization_rate": "1",
                }
            ],
            "items": [item],
            "simulation": {
                "min_runs": 100,
                "max_runs": 200,
                "batch_size": 100,
                "quantiles": [
                    "0.5",
                    "0.8",
                    "0.9",
                    "0.95",
                    "0.99",
                ],
            },
        },
    )


def test_calculation_execution_methods_require_actor(
) -> None:
    for method_name in (
        "submit",
        "run",
        "get",
        "cancel",
    ):
        assert "actor" in signature(
            getattr(
                DemandCalculationService,
                method_name,
            )
        ).parameters

    internal_parameters = signature(
        DemandCalculationService.run_internal
    ).parameters
    assert "tenant_id" in internal_parameters
    assert "actor" not in internal_parameters


def test_idempotency_key_is_scoped_per_tenant(
    session: Session,
    actor_context: Callable[..., ActorContext],
) -> None:
    actor_a = actor_context(tenant_id="tenant-a")
    actor_b = actor_context(tenant_id="tenant-b")
    spare_a = add_spare(
        session,
        actor_a.tenant_id,
        "IDEMP-A",
    )
    spare_b = add_spare(
        session,
        actor_b.tenant_id,
        "IDEMP-B",
    )
    session.commit()

    key = "shared-idempotency-key"
    calculation_a = calculation_service.submit(
        session,
        actor_a,
        temporary_create_payload(
            spare_a.id,
            execution_preference="ASYNC",
        ),
        idempotency_key=key,
        force_async=True,
    )
    calculation_b = calculation_service.submit(
        session,
        actor_b,
        temporary_create_payload(
            spare_b.id,
            execution_preference="ASYNC",
        ),
        idempotency_key=key,
        force_async=True,
    )

    assert calculation_a.id != calculation_b.id
    assert calculation_a.tenant_id == "tenant-a"
    assert calculation_b.tenant_id == "tenant-b"


def test_cross_tenant_calculation_operations_are_not_found(
    session: Session,
    actor_context: Callable[..., ActorContext],
) -> None:
    actor = actor_context(tenant_id="tenant-a")
    foreign = add_calculation(
        session,
        "tenant-b",
        "FOREIGN-ROOT",
    )
    session.commit()

    with pytest.raises(NotFoundError):
        calculation_service.get(
            session,
            actor,
            foreign.id,
        )
    with pytest.raises(NotFoundError):
        calculation_service.cancel(
            session,
            actor,
            foreign.id,
        )
    with pytest.raises(NotFoundError):
        calculation_service.run(
            session,
            actor,
            foreign.id,
        )


def test_synchronous_result_tree_uses_actor_tenant(
    session: Session,
    actor_context: Callable[..., ActorContext],
) -> None:
    actor = actor_context(tenant_id="tenant-a")
    spare = add_spare(
        session,
        actor.tenant_id,
        "RESULT",
    )
    session.commit()

    calculation = calculation_service.submit(
        session,
        actor,
        temporary_create_payload(spare.id),
    )

    full = (
        calculation_service.calculation_repository
        .get_full(
            session,
            actor.tenant_id,
            calculation.id,
        )
    )

    assert full is not None
    assert full.status.value == "SUCCEEDED"
    assert full.tenant_id == actor.tenant_id
    assert full.runs
    assert {
        run.tenant_id
        for run in full.runs
    } == {actor.tenant_id}
    assert {
        item.tenant_id
        for run in full.runs
        for item in run.item_results
    } == {actor.tenant_id}
    assert {
        contribution.tenant_id
        for run in full.runs
        for contribution in run.contributions
    } == {actor.tenant_id}


def test_failed_run_reloads_with_trusted_tenant(
    session: Session,
    actor_context: Callable[..., ActorContext],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actor = actor_context(tenant_id="tenant-a")
    spare = add_spare(
        session,
        actor.tenant_id,
        "FAIL",
    )
    session.commit()

    calculation = calculation_service.submit(
        session,
        actor,
        temporary_create_payload(
            spare.id,
            execution_preference="ASYNC",
        ),
        force_async=True,
    )

    def fail_calculation(*args, **kwargs):
        raise RuntimeError("deterministic engine failure")

    monkeypatch.setattr(
        "app.services.demand_calculation_service."
        "DemandCalculationEngine.calculate",
        fail_calculation,
    )

    with pytest.raises(
        RuntimeError,
        match="deterministic engine failure",
    ):
        calculation_service.run(
            session,
            actor,
            calculation.id,
        )

    failed = (
        calculation_service.calculation_repository
        .get_by_id(
            session,
            actor.tenant_id,
            calculation.id,
        )
    )
    assert failed is not None
    assert failed.status.value == "FAILED"
    assert failed.error_code == "RUNTIMEERROR"

    foreign_actor = actor_context(
        tenant_id="tenant-b"
    )
    with pytest.raises(NotFoundError):
        calculation_service.get(
            session,
            foreign_actor,
            calculation.id,
        )


def test_temporary_snapshot_strips_untrusted_profile_ids(
    session: Session,
    actor_context: Callable[..., ActorContext],
) -> None:
    actor = actor_context(tenant_id="tenant-a")
    local_spare = add_spare(
        session,
        actor.tenant_id,
        "PROFILE-LOCAL",
    )
    foreign_spare = add_spare(
        session,
        "tenant-b",
        "PROFILE-FOREIGN",
    )
    foreign_reliability = ReliabilityProfile(
        tenant_id="tenant-b",
        profile_code="REL-FOREIGN-TEMP",
        spare_part_id=foreign_spare.id,
        model_type=ReliabilityModelType.EXPONENTIAL,
        failure_rate=Decimal("0.99"),
        data_source_type=DataSourceType.MANUAL_ESTIMATE,
    )
    foreign_repair = RepairProfile(
        tenant_id="tenant-b",
        profile_code="REP-FOREIGN-TEMP",
        profile_name="Foreign temporary repair",
        spare_part_id=foreign_spare.id,
        repair_success_rate=Decimal("0.8"),
        condemnation_rate=Decimal("0.1"),
        repair_turnaround_hours=Decimal("24"),
    )
    session.add_all(
        [foreign_reliability, foreign_repair]
    )
    session.commit()

    payload = temporary_create_payload(
        local_spare.id,
        selected_reliability_profile_id=(
            foreign_reliability.id
        ),
        selected_repair_profile_id=(
            foreign_repair.id
        ),
    )

    snapshot, _ = (
        calculation_service.build_snapshot(
            session,
            actor,
            payload,
        )
    )
    item = snapshot["items"][0]

    assert (
        "selected_reliability_profile_id"
        not in item
    )
    assert "selected_repair_profile_id" not in item



# TASK_073_REVIEW_FIXES


def test_cancel_requested_is_bound_and_tenant_scoped(
    session: Session,
    actor_context: Callable[..., ActorContext],
) -> None:
    actor = actor_context(tenant_id="tenant-a")
    calculation = add_calculation(
        session,
        actor.tenant_id,
        "CANCEL-CHECK",
    )
    calculation.cancel_requested = True
    session.commit()

    assert calculation_service._cancel_requested(
        session,
        actor.tenant_id,
        calculation.id,
    ) is True
    assert calculation_service._cancel_requested(
        session,
        "tenant-b",
        calculation.id,
    ) is False
