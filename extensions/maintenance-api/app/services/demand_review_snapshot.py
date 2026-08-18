from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    ConfigurationItem,
    ConfigurationVersion,
    Part,
    ReliabilityProfile,
    SparePart,
)
from app.models.demand_list import (
    DemandList,
    DemandListEvent,
    DemandListItem,
)
from app.schemas.demand_review import DemandReviewSnapshot
from app.security.actor import ActorContext
from app.services.inventory_query_service import InventoryQueryService
from app.services.snapshot_service import snapshot_service

SCHEMA_VERSION = "1"
RULE_SET_VERSION = "DEMAND-REVIEW-1"


def _enum_value(value: Any) -> Any:
    return value.value if hasattr(value, "value") else value


def _decimal_string(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value, "f")


def _normalize(value: Any) -> Any:
    return snapshot_service.normalize(value)


def _map_by_id(rows: Sequence[Any], serializer) -> dict[str, Any]:
    return {
        str(row.id): serializer(row)
        for row in sorted(rows, key=lambda current: str(current.id))
    }


def _unavailable_relation() -> dict[str, Any]:
    return {
        "status": "UNAVAILABLE",
        "records": [],
        "reason": "NO_AUTHORITATIVE_RELATION",
    }


class DemandReviewSnapshotBuilder:
    def __init__(
        self,
        inventory_query_service: InventoryQueryService | None = None,
    ) -> None:
        self.inventory_query_service = (
            inventory_query_service
            if inventory_query_service is not None
            else InventoryQueryService()
        )

    def build(
        self,
        session: Session,
        actor: ActorContext,
        source: DemandList,
        items: Sequence[DemandListItem],
        events: Sequence[DemandListEvent],
    ) -> DemandReviewSnapshot:
        summary_rows = self.inventory_query_service.summaries_for_parts(
            session,
            actor,
            [item.spare_part_id for item in items],
        )

        payload: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "captured_at": datetime.now(UTC),
            "request": {
                "command": "RUN",
                "demand_list_id": source.id,
                "expected_source_version": source.version,
            },
            "source_demand_list": self._source_demand_list(source),
            "source_items": tuple(
                self._source_item(item)
                for item in sorted(items, key=lambda current: current.id)
            ),
            "source_events": tuple(
                self._source_event(event)
                for event in sorted(
                    events,
                    key=lambda current: (
                        current.occurred_at,
                        current.id,
                    ),
                )
            ),
            "current_inventory": tuple(
                self._inventory_summary(row)
                for row in sorted(
                    summary_rows,
                    key=lambda current: (
                        current.warehouse_id,
                        current.spare_part_id,
                    ),
                )
            ),
            "master_data_evidence": self._master_data_evidence(
                session,
                actor,
                items,
            ),
            "rule_set_version": RULE_SET_VERSION,
        }
        normalized = _normalize(payload)
        input_hash = snapshot_service.canonical_hash(normalized)
        return DemandReviewSnapshot(
            **normalized,
            input_hash=input_hash,
        )

    @staticmethod
    def _source_demand_list(source: DemandList) -> dict[str, Any]:
        return _normalize(
            {
                "id": source.id,
                "lineage_id": source.lineage_id,
                "version_number": source.version_number,
                "version": source.version,
                "status": _enum_value(source.status),
                "is_current": source.is_current,
                "scenario_version_id": source.scenario_version_id,
                "calculation_group_id": source.calculation_group_id,
                "created_by_user_id": source.created_by_user_id,
                "created_by_request_id": source.created_by_request_id,
                "created_at": source.created_at,
                "published_by_user_id": source.published_by_user_id,
                "published_by_request_id": source.published_by_request_id,
                "published_at": source.published_at,
            }
        )

    @staticmethod
    def _source_item(item: DemandListItem) -> dict[str, Any]:
        return _normalize(
            {
                "id": item.id,
                "spare_part_id": item.spare_part_id,
                "spare_part_code_snapshot": item.spare_part_code_snapshot,
                "spare_part_name_snapshot": item.spare_part_name_snapshot,
                "spare_part_unit_snapshot": item.spare_part_unit_snapshot,
                "criticality_level_snapshot": item.criticality_level_snapshot,
                "source_calculation_group_id": item.source_calculation_group_id,
                "source_group_child_id": item.source_group_child_id,
                "source_calculation_id": item.source_calculation_id,
                "source_calculation_run_id": item.source_calculation_run_id,
                "source_result_id": item.source_result_id,
                "reliability_model": _enum_value(item.reliability_model),
                "execution_mode": _enum_value(item.execution_mode),
                "original_quantity": _decimal_string(item.original_quantity),
                "final_quantity": _decimal_string(item.final_quantity),
                "decision_type": _enum_value(item.decision_type),
                "decision_reason": item.decision_reason,
                "decision_risk": item.decision_risk,
                "requires_admin_confirmation": (
                    item.requires_admin_confirmation
                ),
                "confirmed_by_admin": item.confirmed_by_admin,
                "risk_rule_version": item.risk_rule_version,
                "source_snapshot_json": item.source_snapshot_json,
                "decision_snapshot_json": item.decision_snapshot_json,
                "interval_snapshot_json": item.interval_snapshot_json,
                "parameter_snapshot_json": item.parameter_snapshot_json,
                "warning_snapshot_json": item.warning_snapshot_json,
                "inventory_snapshot_json": item.inventory_snapshot_json,
                "version": item.version,
            }
        )

    @staticmethod
    def _source_event(event: DemandListEvent) -> dict[str, Any]:
        return _normalize(
            {
                "id": event.id,
                "event_type": _enum_value(event.event_type),
                "actor_user_id": event.actor_user_id,
                "actor_roles": event.actor_roles_json,
                "request_id": event.request_id,
                "before_summary": event.before_summary_json,
                "after_summary": event.after_summary_json,
                "occurred_at": event.occurred_at,
            }
        )

    @staticmethod
    def _inventory_summary(row: Any) -> dict[str, Any]:
        return _normalize(
            {
                "warehouse_id": row.warehouse_id,
                "spare_part_id": row.spare_part_id,
                "on_hand_quantity": _decimal_string(row.on_hand_quantity),
                "reserved_quantity": _decimal_string(row.reserved_quantity),
                "damaged_quantity": _decimal_string(row.damaged_quantity),
                "quarantined_quantity": _decimal_string(
                    row.quarantined_quantity
                ),
                "in_transit_quantity": _decimal_string(
                    row.in_transit_quantity
                ),
                "safety_stock": _decimal_string(row.safety_stock),
                "reorder_point": _decimal_string(row.reorder_point),
                "maximum_stock": _decimal_string(row.maximum_stock),
                "available_quantity": _decimal_string(
                    row.available_quantity
                ),
            }
        )

    def _master_data_evidence(
        self,
        session: Session,
        actor: ActorContext,
        items: Sequence[DemandListItem],
    ) -> dict[str, Any]:
        spare_part_ids = sorted({item.spare_part_id for item in items})

        spare_parts = self._tenant_rows(
            session,
            SparePart,
            actor.tenant_id,
            SparePart.id.in_(spare_part_ids),
        )
        reliability_profiles = self._tenant_rows(
            session,
            ReliabilityProfile,
            actor.tenant_id,
            ReliabilityProfile.spare_part_id.in_(spare_part_ids),
        )
        configuration_items = self._tenant_rows(
            session,
            ConfigurationItem,
            actor.tenant_id,
            ConfigurationItem.spare_part_id.in_(spare_part_ids),
        )

        configuration_version_ids = sorted(
            {
                row.configuration_version_id
                for row in configuration_items
            }
        )
        configuration_versions = (
            self._tenant_rows(
                session,
                ConfigurationVersion,
                actor.tenant_id,
                ConfigurationVersion.id.in_(configuration_version_ids),
            )
            if configuration_version_ids
            else []
        )
        part_ids = sorted({row.part_id for row in configuration_items})
        parts = (
            self._tenant_rows(
                session,
                Part,
                actor.tenant_id,
                Part.id.in_(part_ids),
            )
            if part_ids
            else []
        )

        return _normalize(
            {
                "parts_by_id": _map_by_id(parts, self._part_evidence),
                "spare_parts_by_id": _map_by_id(
                    spare_parts,
                    self._spare_part_evidence,
                ),
                "reliability_profiles_by_id": _map_by_id(
                    reliability_profiles,
                    self._reliability_evidence,
                ),
                "configuration_versions_by_id": _map_by_id(
                    configuration_versions,
                    self._configuration_version_evidence,
                ),
                "configuration_items_by_id": _map_by_id(
                    configuration_items,
                    self._configuration_item_evidence,
                ),
                "substitution_evidence": _unavailable_relation(),
                "kit_evidence": _unavailable_relation(),
            }
        )

    @staticmethod
    def _tenant_rows(
        session: Session,
        model: Any,
        tenant_id: str,
        condition: Any,
    ) -> list[Any]:
        return list(
            session.scalars(
                select(model)
                .where(
                    model.tenant_id == tenant_id,
                    condition,
                )
                .order_by(model.id)
            ).all()
        )

    @staticmethod
    def _part_evidence(row: Part) -> dict[str, Any]:
        return {
            "id": row.id,
            "code": row.code,
            "name": row.name,
            "part_type": row.part_type,
            "unit": row.unit,
            "is_active": row.is_active,
            "version": row.version,
        }

    @staticmethod
    def _spare_part_evidence(row: SparePart) -> dict[str, Any]:
        return {
            "id": row.id,
            "code": row.code,
            "name": row.name,
            "unit": row.unit,
            "is_active": row.is_active,
            "is_critical": row.is_critical,
            "is_repairable": row.is_repairable,
            "version": row.version,
        }

    @staticmethod
    def _reliability_evidence(row: ReliabilityProfile) -> dict[str, Any]:
        return _normalize(
            {
                "id": row.id,
                "spare_part_id": row.spare_part_id,
                "configuration_version_id": row.configuration_version_id,
                "model_type": _enum_value(row.model_type),
                "failure_rate": _decimal_string(row.failure_rate),
                "mtbf_hours": _decimal_string(row.mtbf_hours),
                "weibull_shape": _decimal_string(row.weibull_shape),
                "weibull_scale": _decimal_string(row.weibull_scale),
                "valid_from": row.valid_from,
                "valid_to": row.valid_to,
                "is_active": row.is_active,
                "version": row.version,
            }
        )

    @staticmethod
    def _configuration_version_evidence(
        row: ConfigurationVersion,
    ) -> dict[str, Any]:
        return _normalize(
            {
                "id": row.id,
                "equipment_model_id": row.equipment_model_id,
                "version_code": row.version_code,
                "status": _enum_value(row.status),
                "effective_date": row.effective_date,
                "expiry_date": row.expiry_date,
                "is_default": row.is_default,
                "is_active": row.is_active,
                "version": row.version,
            }
        )

    @staticmethod
    def _configuration_item_evidence(
        row: ConfigurationItem,
    ) -> dict[str, Any]:
        return _normalize(
            {
                "id": row.id,
                "configuration_version_id": row.configuration_version_id,
                "item_code": row.item_code,
                "parent_item_id": row.parent_item_id,
                "part_id": row.part_id,
                "spare_part_id": row.spare_part_id,
                "install_quantity": _decimal_string(row.install_quantity),
                "criticality_level": _enum_value(row.criticality_level),
                "replacement_ratio": _decimal_string(row.replacement_ratio),
                "is_mandatory": row.is_mandatory,
                "sort_order": row.sort_order,
                "version": row.version,
            }
        )
