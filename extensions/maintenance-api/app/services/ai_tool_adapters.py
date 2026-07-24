from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.models import (
    ConfigurationVersion,
    DemandCalculation,
    DemandCalculationRun,
    EquipmentModel,
    ReliabilityProfile,
    SparePart,
    WarehouseInventory,
)
from app.schemas.demand_calculation import CalculationCreateRequest, CalculationPreviewRequest
from app.services.demand_calculation_service import calculation_service
from app.services.inventory_gap_service import inventory_gap_service


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
    material = f"{session_id}:{plan_step_id or 0}:{tool_version}:{canonical_json(payload)}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def search_equipment_models(session: Session, payload, context) -> dict[str, Any]:
    del context
    data = payload.model_dump(exclude_none=True)
    query = str(data.get("query", "")).strip()
    stmt = select(EquipmentModel).order_by(EquipmentModel.code)
    rows = list(session.scalars(stmt).all())
    if query:
        lowered = query.lower()
        rows = [row for row in rows if lowered in row.code.lower() or lowered in row.name.lower()]
    return {"items": [{"id": row.id, "code": row.code, "name": row.name} for row in rows[:50]]}


def search_configuration_versions(session: Session, payload, context) -> dict[str, Any]:
    del context
    data = payload.model_dump(exclude_none=True)
    stmt = select(ConfigurationVersion).order_by(ConfigurationVersion.id)
    if data.get("equipment_model_id") is not None:
        stmt = stmt.where(ConfigurationVersion.equipment_model_id == data["equipment_model_id"])
    rows = list(session.scalars(stmt).all())
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


def get_configuration_snapshot(session: Session, payload, context) -> dict[str, Any]:
    del context
    identifier = payload.model_dump().get("configuration_version_id")
    row = session.get(ConfigurationVersion, identifier)
    if row is None:
        raise NotFoundError("configuration_version", identifier)
    return {
        "id": row.id,
        "version_code": row.version_code,
        "version_name": row.version_name,
        "status": row.status.value,
    }


def get_reliability_profiles(session: Session, payload, context) -> dict[str, Any]:
    del context
    spare_part_id = payload.model_dump().get("spare_part_id")
    stmt = select(ReliabilityProfile).order_by(ReliabilityProfile.profile_code)
    if spare_part_id is not None:
        stmt = stmt.where(ReliabilityProfile.spare_part_id == spare_part_id)
    rows = list(session.scalars(stmt).all())
    return {
        "items": [
            {
                "id": row.id,
                "profile_code": row.profile_code,
                "model_type": row.model_type.value,
            }
            for row in rows
        ]
    }


def list_spare_parts(session: Session, payload, context) -> dict[str, Any]:
    del payload, context
    rows = list(session.scalars(select(SparePart).order_by(SparePart.code)).all())
    return {"items": [{"id": row.id, "code": row.code, "name": row.name} for row in rows[:200]]}


def preview_demand_calculation(session: Session, payload, context) -> dict[str, Any]:
    del context
    data = payload.model_dump(exclude_none=True)
    result = calculation_service.preview(session, CalculationPreviewRequest(**data))
    return result.model_dump(mode="json")


def start_demand_calculation(session: Session, payload, context) -> dict[str, Any]:
    data = payload.model_dump(exclude_none=True)
    row = calculation_service.submit(
        session,
        CalculationCreateRequest(**data),
        idempotency_key=context.business_idempotency_key,
        force_async=True,
    )
    if row.status.value == "PENDING":
        from app.workers.executor import demand_task_executor

        demand_task_executor.submit(row.id)
    return {
        "calculation_id": row.id,
        "calculation_code": row.calculation_code,
        "status": row.status.value,
    }


def get_calculation_status(session: Session, payload, context) -> dict[str, Any]:
    del context
    identifier = payload.model_dump().get("calculation_id")
    row = calculation_service.get(session, identifier)
    return {
        "calculation_id": row.id,
        "status": row.status.value,
        "progress_percent": float(row.progress_percent),
        "error_code": row.error_code,
    }


def get_calculation_result(session: Session, payload, context) -> dict[str, Any]:
    del context
    identifier = payload.model_dump().get("calculation_id")
    row = session.get(DemandCalculation, identifier)
    if row is None:
        raise NotFoundError("demand_calculation", identifier)
    runs = list(
        session.scalars(
            select(DemandCalculationRun).where(DemandCalculationRun.calculation_id == identifier)
        ).all()
    )
    return {
        "calculation_id": row.id,
        "status": row.status.value,
        "summary": row.result_summary_json or {},
        "run_ids": [run.id for run in runs],
    }


def cancel_demand_calculation(session: Session, payload, context) -> dict[str, Any]:
    del context
    identifier = payload.model_dump().get("calculation_id")
    row = calculation_service.cancel(session, identifier)
    return {"calculation_id": row.id, "status": row.status.value}


def get_inventory_snapshot(session: Session, payload, context) -> dict[str, Any]:
    del context
    spare_part_id = payload.model_dump().get("spare_part_id")
    stmt = select(WarehouseInventory)
    if spare_part_id is not None:
        stmt = stmt.where(WarehouseInventory.spare_part_id == spare_part_id)
    rows = list(session.scalars(stmt).all())
    return {
        "items": [
            {
                "spare_part_id": row.spare_part_id,
                "warehouse_id": row.warehouse_id,
                "on_hand_quantity": str(row.on_hand_quantity),
                "available_quantity": str(row.available_quantity),
                "in_transit_quantity": str(row.in_transit_quantity),
                "safety_stock": str(row.safety_stock),
            }
            for row in rows
        ]
    }


def calculate_inventory_gap(session: Session, payload, context) -> dict[str, Any]:
    del session, context
    result = inventory_gap_service.calculate(**payload.model_dump())
    return {
        "usable_inventory": str(result.usable_inventory),
        "net_demand_gap": str(result.net_demand_gap),
        "inventory_coverage_rate": result.inventory_coverage_rate,
        "shortage_risk_level": result.shortage_risk_level,
    }


def echo_payload(session: Session, payload, context) -> dict[str, Any]:
    del session, context
    return payload.model_dump(mode="json")


HANDLERS = {
    "search_equipment_models": search_equipment_models,
    "search_configuration_versions": search_configuration_versions,
    "get_configuration_snapshot": get_configuration_snapshot,
    "get_reliability_profiles": get_reliability_profiles,
    "list_spare_parts": list_spare_parts,
    "preview_demand_calculation": preview_demand_calculation,
    "start_demand_calculation": start_demand_calculation,
    "get_calculation_status": get_calculation_status,
    "get_calculation_result": get_calculation_result,
    "cancel_demand_calculation": cancel_demand_calculation,
    "get_inventory_snapshot": get_inventory_snapshot,
    "calculate_inventory_gap": calculate_inventory_gap,
}
