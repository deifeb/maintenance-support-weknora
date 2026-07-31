from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy.orm import Session

from app.core.exceptions import (
    BusinessValidationError,
    NotFoundError,
)
from app.repositories import (
    ConfigurationRepository,
    DemandCalculationRepository,
    EquipmentRepository,
    InventoryRepository,
    ReliabilityRepository,
    SparePartRepository,
)
from app.schemas.demand_calculation import (
    CalculationCreateRequest,
    CalculationPreviewRequest,
)
from app.schemas.scenario_draft import (
    ScenarioDraftEnvelope,
    ScenarioDraftPayload,
)
from app.services.demand_calculation_service import (
    calculation_service,
)
from app.services.inventory_gap_service import (
    inventory_gap_service,
)
from app.services.scenario_draft_service import (
    scenario_draft_service,
)


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def compute_tool_idempotency_key(
    *,
    session_id: int,
    plan_step_id: int | None,
    tool_version: str,
    payload: dict[str, Any],
) -> str:
    material = (
        f"{session_id}:"
        f"{plan_step_id or 0}:"
        f"{tool_version}:"
        f"{canonical_json(payload)}"
    )
    return hashlib.sha256(
        material.encode("utf-8")
    ).hexdigest()


def scenario_draft_card(
    envelope: ScenarioDraftEnvelope,
) -> dict[str, object]:
    return {
        "session_id": envelope.session_id,
        "draft_version": envelope.version,
        "status": (
            "BLOCKED"
            if envelope.blocking_fields
            else "READY"
        ),
        "blocking_fields": envelope.blocking_fields,
        "navigation_url": (
            "/platform/maintenance/scenarios/new"
            f"?session_id={envelope.session_id}"
        ),
    }


def _scenario_draft_session_id(
    data: dict[str, Any],
    context,
) -> int:
    identifier = data.get(
        "session_id",
        context.session_id,
    )
    if identifier is None:
        raise BusinessValidationError(
            "scenario draft session_id is required",
            code="SCENARIO_DRAFT_SESSION_REQUIRED",
        )
    return int(identifier)


def create_scenario_draft(
    session: Session,
    payload,
    context,
) -> dict[str, object]:
    data = payload.model_dump(
        exclude_none=True
    )
    scenario_name = str(
        data.get(
            "scenario_name",
            data.get("title", ""),
        )
    ).strip()
    if not scenario_name:
        raise BusinessValidationError(
            "scenario_name is required",
            code="SCENARIO_DRAFT_NAME_REQUIRED",
        )
    draft = ScenarioDraftPayload.model_validate(
        {
            "scenario_name": scenario_name,
            "current_step": data.get(
                "current_step",
                1,
            ),
            "fields": data.get("fields", {}),
        }
    )
    envelope = scenario_draft_service.create(
        session,
        context.actor,
        title=scenario_name,
        sensitivity_level=(
            data.get(
                "sensitivity_level",
                context.sensitivity_level,
            )
        ),
        origin="AI",
        draft=draft,
    )
    return scenario_draft_card(envelope)


def update_scenario_draft(
    session: Session,
    payload,
    context,
) -> dict[str, object]:
    data = payload.model_dump(
        exclude_none=True
    )
    session_id = _scenario_draft_session_id(
        data,
        context,
    )
    expected_version = data.get(
        "expected_version",
        data.get("draft_version"),
    )
    if expected_version is None:
        raise BusinessValidationError(
            "expected_version is required",
            code="SCENARIO_DRAFT_VERSION_REQUIRED",
        )

    if "draft" in data:
        draft = ScenarioDraftPayload.model_validate(
            data["draft"]
        )
    else:
        current = scenario_draft_service.get(
            session,
            context.actor,
            session_id,
        )
        draft = current.draft.model_copy(deep=True)
        if "scenario_name" in data:
            draft.scenario_name = str(
                data["scenario_name"]
            )
        if "current_step" in data:
            draft.current_step = int(
                data["current_step"]
            )
        if "fields" in data:
            merged = draft.model_dump(
                mode="json"
            )
            merged["fields"].update(
                data["fields"]
            )
            draft = ScenarioDraftPayload.model_validate(
                merged
            )

    envelope = scenario_draft_service.save(
        session,
        context.actor,
        session_id,
        expected_version=int(expected_version),
        draft=draft,
    )
    return scenario_draft_card(envelope)


def validate_scenario_draft(
    session: Session,
    payload,
    context,
) -> dict[str, object]:
    data = payload.model_dump(
        exclude_none=True
    )
    envelope = scenario_draft_service.validate(
        session,
        context.actor,
        _scenario_draft_session_id(
            data,
            context,
        ),
    )
    return scenario_draft_card(envelope)


def get_scenario_preview(
    session: Session,
    payload,
    context,
) -> dict[str, object]:
    return validate_scenario_draft(
        session,
        payload,
        context,
    )


def search_equipment_models(
    session: Session,
    payload,
    context,
) -> dict[str, Any]:
    data = payload.model_dump(
        exclude_none=True
    )
    query = str(
        data.get("query", "")
    ).strip()
    rows, _ = EquipmentRepository().list_page(
        session,
        context.tenant_id,
        page=1,
        page_size=50,
        keyword=query or None,
        keyword_fields=("code", "name"),
        include_inactive=True,
        sort_by="code",
    )
    return {
        "items": [
            {
                "id": row.id,
                "code": row.code,
                "name": row.name,
            }
            for row in rows
        ]
    }


def search_configuration_versions(
    session: Session,
    payload,
    context,
) -> dict[str, Any]:
    data = payload.model_dump(
        exclude_none=True
    )
    filters = {}
    if data.get(
        "equipment_model_id"
    ) is not None:
        filters["equipment_model_id"] = data[
            "equipment_model_id"
        ]
    rows, _ = (
        ConfigurationRepository().list_page(
            session,
            context.tenant_id,
            page=1,
            page_size=200,
            filters=filters,
            include_inactive=True,
            sort_by="id",
        )
    )
    return {
        "items": [
            {
                "id": row.id,
                "version_code": row.version_code,
                "version_name": row.version_name,
                "status": row.status.value,
            }
            for row in rows
        ]
    }


def get_configuration_snapshot(
    session: Session,
    payload,
    context,
) -> dict[str, Any]:
    identifier = payload.model_dump().get(
        "configuration_version_id"
    )
    row = ConfigurationRepository().get_by_id(
        session,
        context.tenant_id,
        identifier,
    )
    if row is None:
        raise NotFoundError(
            "configuration_version",
            identifier,
        )
    return {
        "id": row.id,
        "version_code": row.version_code,
        "version_name": row.version_name,
        "status": row.status.value,
    }


def get_reliability_profiles(
    session: Session,
    payload,
    context,
) -> dict[str, Any]:
    spare_part_id = payload.model_dump().get(
        "spare_part_id"
    )
    filters = {}
    if spare_part_id is not None:
        filters["spare_part_id"] = spare_part_id
    rows, _ = ReliabilityRepository().list_page(
        session,
        context.tenant_id,
        page=1,
        page_size=200,
        filters=filters,
        include_inactive=True,
        sort_by="profile_code",
    )
    return {
        "items": [
            {
                "id": row.id,
                "profile_code": row.profile_code,
                "model_type": (
                    row.model_type.value
                ),
            }
            for row in rows
        ]
    }


def list_spare_parts(
    session: Session,
    payload,
    context,
) -> dict[str, Any]:
    del payload
    rows, _ = SparePartRepository().list_page(
        session,
        context.tenant_id,
        page=1,
        page_size=200,
        include_inactive=True,
        sort_by="code",
    )
    return {
        "items": [
            {
                "id": row.id,
                "code": row.code,
                "name": row.name,
            }
            for row in rows
        ]
    }


def preview_demand_calculation(
    session: Session,
    payload,
    context,
) -> dict[str, Any]:
    data = payload.model_dump(
        exclude_none=True
    )
    result = calculation_service.preview(
        session,
        context.actor,
        CalculationPreviewRequest(**data),
    )
    return result.model_dump(mode="json")


def start_demand_calculation(
    session: Session,
    payload,
    context,
) -> dict[str, Any]:
    data = payload.model_dump(
        exclude_none=True
    )
    row = calculation_service.submit(
        session,
        context.actor,
        CalculationCreateRequest(**data),
        idempotency_key=(
            context.business_idempotency_key
        ),
        force_async=True,
    )
    if row.status.value == "PENDING":
        from app.workers.executor import (
            demand_task_executor,
        )

        demand_task_executor.submit(
            context.tenant_id,
            row.id,
        )
    return {
        "calculation_id": row.id,
        "calculation_code": row.calculation_code,
        "status": row.status.value,
    }


def get_calculation_status(
    session: Session,
    payload,
    context,
) -> dict[str, Any]:
    identifier = payload.model_dump().get(
        "calculation_id"
    )
    row = calculation_service.get(
        session,
        context.actor,
        identifier,
    )
    return {
        "calculation_id": row.id,
        "status": row.status.value,
        "progress_percent": float(
            row.progress_percent
        ),
        "error_code": row.error_code,
    }


def get_calculation_result(
    session: Session,
    payload,
    context,
) -> dict[str, Any]:
    identifier = payload.model_dump().get(
        "calculation_id"
    )
    row = DemandCalculationRepository().get_full(
        session,
        context.tenant_id,
        identifier,
    )
    if row is None:
        raise NotFoundError(
            "demand_calculation",
            identifier,
        )
    return {
        "calculation_id": row.id,
        "status": row.status.value,
        "summary": row.result_summary_json or {},
        "run_ids": [
            run.id
            for run in row.runs
            if run.tenant_id
            == context.tenant_id
        ],
    }


def cancel_demand_calculation(
    session: Session,
    payload,
    context,
) -> dict[str, Any]:
    identifier = payload.model_dump().get(
        "calculation_id"
    )
    row = calculation_service.cancel(
        session,
        context.actor,
        identifier,
    )
    return {
        "calculation_id": row.id,
        "status": row.status.value,
    }


def get_inventory_snapshot(
    session: Session,
    payload,
    context,
) -> dict[str, Any]:
    spare_part_id = payload.model_dump().get(
        "spare_part_id"
    )
    filters = {}
    if spare_part_id is not None:
        filters["spare_part_id"] = (
            spare_part_id
        )
    rows, _ = InventoryRepository().list_page(
        session,
        context.tenant_id,
        page=1,
        page_size=500,
        filters=filters,
        include_inactive=True,
        sort_by="id",
    )
    return {
        "items": [
            {
                "spare_part_id": (
                    row.spare_part_id
                ),
                "warehouse_id": row.warehouse_id,
                "on_hand_quantity": str(
                    row.on_hand_quantity
                ),
                "available_quantity": str(
                    row.available_quantity
                ),
                "in_transit_quantity": str(
                    row.in_transit_quantity
                ),
                "safety_stock": str(
                    row.safety_stock
                ),
            }
            for row in rows
        ]
    }


def calculate_inventory_gap(
    session: Session,
    payload,
    context,
) -> dict[str, Any]:
    del session, context
    result = inventory_gap_service.calculate(
        **payload.model_dump()
    )
    return {
        "usable_inventory": str(
            result.usable_inventory
        ),
        "net_demand_gap": str(
            result.net_demand_gap
        ),
        "inventory_coverage_rate": (
            result.inventory_coverage_rate
        ),
        "shortage_risk_level": (
            result.shortage_risk_level
        ),
    }


def echo_payload(
    session: Session,
    payload,
    context,
) -> dict[str, Any]:
    del session, context
    return payload.model_dump(mode="json")


HANDLERS = {
    "create_scenario_draft": (
        create_scenario_draft
    ),
    "update_scenario_draft": (
        update_scenario_draft
    ),
    "validate_scenario_draft": (
        validate_scenario_draft
    ),
    "get_scenario_preview": (
        get_scenario_preview
    ),
    "search_equipment_models": (
        search_equipment_models
    ),
    "search_configuration_versions": (
        search_configuration_versions
    ),
    "get_configuration_snapshot": (
        get_configuration_snapshot
    ),
    "get_reliability_profiles": (
        get_reliability_profiles
    ),
    "list_spare_parts": list_spare_parts,
    "preview_demand_calculation": (
        preview_demand_calculation
    ),
    "start_demand_calculation": (
        start_demand_calculation
    ),
    "get_calculation_status": (
        get_calculation_status
    ),
    "get_calculation_result": (
        get_calculation_result
    ),
    "cancel_demand_calculation": (
        cancel_demand_calculation
    ),
    "get_inventory_snapshot": (
        get_inventory_snapshot
    ),
    "calculate_inventory_gap": (
        calculate_inventory_gap
    ),
}
