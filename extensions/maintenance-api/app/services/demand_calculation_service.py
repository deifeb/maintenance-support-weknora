from __future__ import annotations

import uuid
from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Protocol

from demand_engine import DemandCalculationEngine
from demand_engine.enums import AgeDistributionType as EngineAgeDistributionType
from demand_engine.enums import ExecutionMode as EngineExecutionMode
from demand_engine.enums import FailureProcessMode as EngineFailureProcessMode
from demand_engine.enums import ReliabilityModelType as EngineReliabilityModelType
from demand_engine.enums import ShockApplicationMode as EngineShockApplicationMode
from demand_engine.exceptions import CalculationCancelledError
from demand_engine.models import (
    AgeGroupInput,
    CalculationInput,
    CommonShockInput,
    DemandItemInput,
    InventoryInput,
    ReliabilityInput,
    RepairInput,
    SimulationConfig,
    StageInput,
)
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import BusinessValidationError, ConflictError, NotFoundError
from app.models import (
    DemandCalculation,
    DemandScenarioVersion,
    ReliabilityProfile,
    RepairProfile,
    SparePart,
)
from app.models.enums import (
    CalculationExecutionType,
    CalculationStatus,
    DemandExecutionMode,
    FailureProcessMode,
    ItemCalculationStatus,
    MissingParameterPolicy,
    ReliabilityModelType,
    RerunMode,
    ScenarioVersionStatus,
    ShortageRiskLevel,
)
from app.repositories import (
    ConfigurationItemRepository,
    DemandCalculationRepository,
    DemandCalculationRunRepository,
    DemandRunContributionRepository,
    DemandRunItemResultRepository,
    ReliabilityRepository,
    RepairRepository,
    SparePartRepository,
)
from app.schemas.demand_calculation import (
    CalculationCreateRequest,
    CalculationPreviewRead,
    CalculationPreviewRequest,
)
from app.security.actor import ActorContext
from app.services.inventory_gap_service import inventory_gap_service
from app.services.inventory_query_service import InventoryQueryService
from app.services.scenario_service import scenario_service
from app.services.snapshot_service import snapshot_service

_SOURCE_PRIORITY = {
    "MAINTENANCE_RECORD": 0,
    "TEST_DATA": 1,
    "DESIGN_PARAMETER": 2,
    "MANUAL_ESTIMATE": 3,
    "EXPERT_JUDGMENT": 4,
    "LITERATURE": 5,
}


@dataclass(frozen=True, slots=True)
class CandidateExecutionSpec:
    candidate_key: str
    reliability_model: ReliabilityModelType
    execution_mode: DemandExecutionMode
    random_seed: int


class DemandExecutionObserver(Protocol):
    def started(
        self,
        session: Session,
        calculation: DemandCalculation,
    ) -> None: ...

    def progress(
        self,
        session: Session,
        calculation: DemandCalculation,
        percent: Decimal,
    ) -> None: ...

    def completed(
        self,
        session: Session,
        calculation: DemandCalculation,
    ) -> None: ...

    def failed(
        self,
        session: Session,
        calculation: DemandCalculation,
        error: Exception,
    ) -> None: ...


class DemandCalculationService:
    def __init__(self) -> None:
        self.calculation_repository = (
            DemandCalculationRepository()
        )
        self.run_repository = (
            DemandCalculationRunRepository()
        )
        self.item_result_repository = (
            DemandRunItemResultRepository()
        )
        self.contribution_repository = (
            DemandRunContributionRepository()
        )
        self.configuration_item_repository = (
            ConfigurationItemRepository()
        )
        self.inventory_query_service = InventoryQueryService()
        self.spare_part_repository = SparePartRepository()
        self.reliability_repository = (
            ReliabilityRepository()
        )
        self.repair_repository = RepairRepository()

    def preview(
        self,
        session: Session,
        actor: ActorContext,
        payload: CalculationPreviewRequest,
    ) -> CalculationPreviewRead:
        snapshot, warnings = self.build_snapshot(
            session,
            actor,
            payload,
        )
        stage_count = len(snapshot.get("stages", []))
        item_count = len(snapshot.get("items", []))
        fleet_count = len(snapshot.get("fleet_groups", []))
        positions = sum(
            float(item.get("installed_positions", 0)) for item in snapshot.get("items", [])
        )
        mode = payload.requested_mode.value
        complex_scene = any(
            item.get("reliability", {}).get("model_type") == "WEIBULL"
            or item.get("age_groups")
            or item.get("common_shocks")
            for item in snapshot.get("items", [])
        )
        recommended_mode = (
            "MONTE_CARLO"
            if mode == "AUTO" and complex_scene
            else ("ANALYTICAL" if mode == "AUTO" else mode)
        )
        simulation = snapshot.get("simulation", {})
        runs = (
            int(simulation.get("min_runs", 1000))
            if recommended_mode in {"MONTE_CARLO", "COMPARE"}
            else 1
        )
        complexity = max(1.0, stage_count * max(positions, 1) * runs)
        execution_type = (
            "ASYNCHRONOUS"
            if recommended_mode == "COMPARE" or complexity > 2_000_000
            else "SYNCHRONOUS"
        )
        return CalculationPreviewRead(
            stage_count=stage_count,
            fleet_group_count=fleet_count,
            demand_item_count=item_count,
            installed_position_estimate=positions,
            recommended_mode=recommended_mode,
            recommended_execution_type=execution_type,
            complexity_score=complexity,
            warnings=warnings,
        )

    def build_snapshot(
        self,
        session: Session,
        actor: ActorContext,
        payload: CalculationPreviewRequest,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        if payload.temporary_scenario is not None:
            snapshot = self._validated_temporary_snapshot(
                session,
                actor,
                payload.temporary_scenario,
            )
            return snapshot_service.normalize(snapshot), []

        assert payload.scenario_version_id is not None
        version = scenario_service.get_version(
            session,
            actor,
            payload.scenario_version_id,
            full=True,
        )
        if version.status is not ScenarioVersionStatus.PUBLISHED:
            raise BusinessValidationError(
                "scenario version must be published",
                code="SCENARIO_NOT_PUBLISHED",
            )
        return self._snapshot_from_version(
            session,
            actor,
            version,
        )

    @classmethod
    def _strip_untrusted_tenant_fields(
        cls,
        value: Any,
    ) -> Any:
        if isinstance(value, dict):
            return {
                key: cls._strip_untrusted_tenant_fields(item)
                for key, item in value.items()
                if key != "tenant_id"
            }
        if isinstance(value, list):
            return [
                cls._strip_untrusted_tenant_fields(item)
                for item in value
            ]
        return value

    def _validated_temporary_snapshot(
        self,
        session: Session,
        actor: ActorContext,
        source: dict[str, Any],
    ) -> dict[str, Any]:
        snapshot = self._strip_untrusted_tenant_fields(
            dict(source)
        )
        snapshot.setdefault("calculation_code", "TEMP")
        snapshot.setdefault("simulation", {})
        snapshot.setdefault("fleet_groups", [])
        self._validate_snapshot_shape(snapshot)

        trusted_items: list[dict[str, Any]] = []
        for source_item in snapshot.get("items", []):
            item = dict(source_item)
            spare_id = int(item["spare_part_id"])
            spare = self.spare_part_repository.get_by_id(
                session,
                actor.tenant_id,
                spare_id,
            )
            if spare is None:
                raise NotFoundError("spare_part", spare_id)

            item["spare_part_code"] = spare.code
            item["spare_part_name"] = spare.name
            item.pop(
                "selected_reliability_profile_id",
                None,
            )
            item.pop(
                "selected_repair_profile_id",
                None,
            )

            trusted_contributions = []
            for source_contribution in (
                item.get("contributions") or []
            ):
                contribution = dict(
                    source_contribution
                )
                for key in (
                    "stage_id",
                    "fleet_group_id",
                    "configuration_version_id",
                    "configuration_item_id",
                ):
                    contribution.pop(key, None)
                trusted_contributions.append(
                    contribution
                )
            if "contributions" in item:
                item["contributions"] = (
                    trusted_contributions
                )

            trusted_items.append(item)

        snapshot["items"] = trusted_items
        return snapshot

    @staticmethod
    def _validate_snapshot_shape(snapshot: dict[str, Any]) -> None:
        if not snapshot.get("stages"):
            raise BusinessValidationError(
                "temporary scenario requires stages", code="SCENARIO_VALIDATION_FAILED"
            )
        if "items" not in snapshot:
            raise BusinessValidationError(
                "temporary scenario requires items", code="SCENARIO_VALIDATION_FAILED"
            )

    def _snapshot_from_version(
        self,
        session: Session,
        actor: ActorContext,
        version: DemandScenarioVersion,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        warnings: list[dict[str, Any]] = []
        stages = [
            {
                "code": stage.stage_code,
                "name": stage.stage_name,
                "order": stage.stage_order,
                "duration_hours": str(stage.duration_hours),
                "utilization_rate": str(stage.utilization_rate),
                "mission_intensity_factor": str(stage.mission_intensity_factor),
                "environment_factor": str(stage.environment_factor),
                "temperature_factor": str(stage.temperature_factor),
                "dust_factor": str(stage.dust_factor),
                "humidity_factor": str(stage.humidity_factor),
                "vibration_factor": str(stage.vibration_factor),
            }
            for stage in sorted(version.stages, key=lambda row: row.stage_order)
        ]
        aggregate: dict[int, dict[str, Any]] = {}
        fleet_rows = []
        today = date.today()
        for fleet in version.fleet_groups:
            active_quantities = [
                usage.active_quantity for usage in fleet.stage_usages if usage.is_active
            ]
            equipment_quantity = max(active_quantities, default=fleet.initial_quantity)
            fleet_rows.append(
                {
                    "group_code": fleet.group_code,
                    "configuration_version_id": fleet.configuration_version_id,
                    "initial_quantity": fleet.initial_quantity,
                    "active_quantity": equipment_quantity,
                    "age_groups": [
                        {
                            "distribution_type": group.distribution_type.value,
                            "proportion": str(group.proportion),
                            "fixed_hours": None
                            if group.fixed_hours is None
                            else str(group.fixed_hours),
                            "minimum_hours": None
                            if group.minimum_hours is None
                            else str(group.minimum_hours),
                            "maximum_hours": None
                            if group.maximum_hours is None
                            else str(group.maximum_hours),
                            "mean_hours": None
                            if group.mean_hours is None
                            else str(group.mean_hours),
                            "std_hours": None if group.std_hours is None else str(group.std_hours),
                            "mode_hours": None
                            if group.mode_hours is None
                            else str(group.mode_hours),
                        }
                        for group in fleet.age_groups
                    ],
                }
            )
            items = [
                item
                for item in (
                    self.configuration_item_repository
                    .list_for_version(
                        session,
                        actor.tenant_id,
                        fleet.configuration_version_id,
                    )
                )
                if item.spare_part_id is not None
            ]
            for config_item in items:
                spare = self.spare_part_repository.get_by_id(
                    session,
                    actor.tenant_id,
                    config_item.spare_part_id,
                )
                if spare is None or not spare.is_active:
                    continue
                row = aggregate.setdefault(
                    spare.id,
                    {
                        "spare": spare,
                        "configuration_version_id": fleet.configuration_version_id,
                        "installed_positions": Decimal("0"),
                        "replacement_ratio_sum": Decimal("0"),
                        "weight": Decimal("0"),
                        "criticality": config_item.criticality_level.value,
                        "age_groups": fleet_rows[-1]["age_groups"],
                        "contributions": [],
                    },
                )
                positions = Decimal(config_item.install_quantity) * Decimal(equipment_quantity)
                row["installed_positions"] += positions
                row["replacement_ratio_sum"] += Decimal(config_item.replacement_ratio) * positions
                row["weight"] += positions
                row["contributions"].append(
                    {
                        "configuration_item_id": config_item.id,
                        "item_code": config_item.item_code,
                        "configuration_version_id": fleet.configuration_version_id,
                        "fleet_group_code": fleet.group_code,
                        "install_quantity": str(config_item.install_quantity),
                        "equipment_quantity": equipment_quantity,
                        "replacement_ratio": str(config_item.replacement_ratio),
                    }
                )
        all_shocks = [
            {
                "code": shock.shock_code,
                "probability": str(shock.probability),
                "multiplier": str(shock.multiplier),
                "application_mode": shock.application_mode.value,
                "maximum_occurrences": shock.maximum_occurrences,
            }
            for stage in version.stages
            for shock in stage.shocks
        ]
        snapshot_items = []
        for spare_id, row in aggregate.items():
            spare: SparePart = row["spare"]
            reliability = self._select_reliability(
                session,
                actor,
                spare_id,
                row["configuration_version_id"],
                today,
            )
            if reliability is None:
                if version.missing_parameter_policy is MissingParameterPolicy.STRICT:
                    raise BusinessValidationError(
                        "reliability profile missing",
                        details={"spare_part_id": spare_id},
                        code="RELIABILITY_PROFILE_MISSING",
                    )
                if version.missing_parameter_policy is MissingParameterPolicy.WARN_AND_SKIP:
                    warnings.append(
                        {
                            "code": "RELIABILITY_PROFILE_MISSING",
                            "spare_part_id": spare_id,
                            "action": "SKIPPED",
                        }
                    )
                    continue
                fallback = version.fallback_parameters_json or {}
                reliability_data = {
                    "model_type": "EXPONENTIAL",
                    "failure_rate": str(fallback.get("failure_rate", "0.0001")),
                }
                warnings.append({"code": "RELIABILITY_PROFILE_FALLBACK", "spare_part_id": spare_id})
                reliability_id = None
            else:
                reliability_data = self._reliability_snapshot(reliability)
                reliability_id = reliability.id
            repair = (
                self._select_repair(
                    session,
                    actor,
                    spare_id,
                    row["configuration_version_id"],
                    None,
                    today,
                )
                if spare.is_repairable
                else None
            )
            inventories = self.inventory_query_service.summary_for_part(
                session,
                actor,
                spare_id,
            )
            available = sum(
                (inventory.available_quantity for inventory in inventories), Decimal("0")
            )
            on_hand = sum((inventory.on_hand_quantity for inventory in inventories), Decimal("0"))
            in_transit = sum(
                (inventory.in_transit_quantity for inventory in inventories), Decimal("0")
            )
            safety = sum((inventory.safety_stock for inventory in inventories), Decimal("0"))
            default_service = spare.default_service_level or version.default_service_level
            replacement_ratio = (
                row["replacement_ratio_sum"] / row["weight"] if row["weight"] else Decimal("0")
            )
            item_data = {
                "spare_part_id": spare.id,
                "spare_part_code": spare.code,
                "spare_part_name": spare.name,
                "installed_positions": str(row["installed_positions"]),
                "replacement_ratio": str(replacement_ratio),
                "is_repairable": spare.is_repairable,
                "reliability": reliability_data,
                "selected_reliability_profile_id": reliability_id,
                "failure_process_mode": "AUTO",
                "target_service_level": str(default_service),
                "initial_age_hours": str(version.default_initial_age_hours),
                "age_groups": row["age_groups"],
                "inventory": {
                    "on_hand_quantity": str(on_hand),
                    "available_quantity": str(available),
                    "in_transit_quantity": str(in_transit),
                    "safety_stock": str(safety),
                },
                "contributions": row["contributions"],
                "criticality_level": row["criticality"],
                "selection_reason": "CONFIGURATION_MATCH" if reliability_id else "FALLBACK",
                "common_shocks": all_shocks,
            }
            if repair is not None:
                item_data["repair"] = {
                    "success_rate": str(repair.repair_success_rate),
                    "condemnation_rate": str(repair.condemnation_rate),
                    "turnaround_hours": str(repair.repair_turnaround_hours),
                    "turnaround_std_hours": str(repair.turnaround_std_hours),
                    "initial_pipeline_quantity": str(repair.initial_repair_pipeline_quantity),
                }
                item_data["selected_repair_profile_id"] = repair.id
            snapshot_items.append(item_data)
        snapshot = {
            "calculation_code": "SCENARIO-SNAPSHOT",
            "scenario_version_id": version.id,
            "stages": stages,
            "fleet_groups": fleet_rows,
            "items": snapshot_items,
            "requested_mode": version.execution_mode.value,
            "simulation": version.simulation_config_json,
            "formula_version": version.formula_version,
            "input_schema_version": version.input_schema_version,
        }
        return snapshot_service.normalize(snapshot), warnings

    def _select_reliability(
        self,
        session: Session,
        actor: ActorContext,
        spare_part_id: int,
        configuration_version_id: int,
        valid_at: date,
    ) -> ReliabilityProfile | None:
        candidates = (
            self.reliability_repository
            .list_active_for_selection(
                session,
                actor.tenant_id,
                spare_part_id,
                valid_at,
            )
        )
        candidates.sort(
            key=lambda row: (
                row.configuration_version_id != configuration_version_id,
                row.configuration_version_id is None,
                _SOURCE_PRIORITY.get(row.data_source_type.value, 99),
                -(float(row.confidence_level) if row.confidence_level is not None else -1),
                -(row.sample_size or -1),
                row.profile_code,
            )
        )
        return candidates[0] if candidates else None

    def _select_repair(
        self,
        session: Session,
        actor: ActorContext,
        spare_part_id: int,
        configuration_version_id: int,
        maintenance_level: str | None,
        valid_at: date,
    ) -> RepairProfile | None:
        candidates = (
            self.repair_repository
            .list_active_for_selection(
                session,
                actor.tenant_id,
                spare_part_id,
                valid_at,
            )
        )
        candidates.sort(
            key=lambda row: (
                row.configuration_version_id != configuration_version_id,
                row.configuration_version_id is None,
                row.maintenance_level != maintenance_level,
                row.maintenance_level is None,
                row.profile_code,
            )
        )
        return candidates[0] if candidates else None

    @staticmethod
    def _reliability_snapshot(profile: ReliabilityProfile) -> dict[str, Any]:
        names = (
            "failure_rate",
            "mtbf_hours",
            "weibull_shape",
            "weibull_scale",
            "binomial_trials",
            "binomial_probability",
            "negative_binomial_r",
            "negative_binomial_p",
            "empirical_mean",
            "empirical_variance",
        )
        result = {"model_type": profile.model_type.value}
        for name in names:
            value = getattr(profile, name)
            if value is not None:
                result[name] = str(value)
        extension = profile.extension_parameters_json or {}
        if extension.get("reference_duration_hours") is not None:
            result["reference_duration_hours"] = str(extension["reference_duration_hours"])
        return result

    @staticmethod
    def _validate_candidate_parameters(
        snapshot: dict[str, Any],
        spec: CandidateExecutionSpec,
    ) -> None:
        items = list(snapshot.get("items") or [])
        missing_by_item: list[dict[str, Any]] = []
        for index, item in enumerate(items):
            reliability = item.get("reliability")
            reliability = (
                reliability
                if isinstance(reliability, dict)
                else {}
            )
            missing = []
            if (
                spec.reliability_model
                is ReliabilityModelType.EXPONENTIAL
            ):
                if (
                    reliability.get("failure_rate") is None
                    and reliability.get("mtbf_hours") is None
                ):
                    missing.append("failure_rate_or_mtbf")
            elif (
                spec.reliability_model
                is ReliabilityModelType.WEIBULL
            ):
                for name in (
                    "weibull_shape",
                    "weibull_scale",
                ):
                    if reliability.get(name) is None:
                        missing.append(name)
            elif (
                spec.reliability_model
                is ReliabilityModelType.BINOMIAL
            ):
                for name in (
                    "binomial_trials",
                    "binomial_probability",
                ):
                    if reliability.get(name) is None:
                        missing.append(name)
            elif (
                spec.reliability_model
                is ReliabilityModelType.NEGATIVE_BINOMIAL
            ):
                for name in (
                    "negative_binomial_r",
                    "negative_binomial_p",
                ):
                    if reliability.get(name) is None:
                        missing.append(name)
            elif (
                spec.reliability_model
                is ReliabilityModelType.EMPIRICAL
            ):
                for name in (
                    "empirical_mean",
                    "empirical_variance",
                ):
                    if reliability.get(name) is None:
                        missing.append(name)
            if missing:
                missing_by_item.append(
                    {
                        "item_index": index,
                        "missing_requirements": missing,
                    }
                )
        if not items:
            missing_by_item.append(
                {
                    "item_index": None,
                    "missing_requirements": [
                        "demand_items",
                    ],
                }
            )
        if missing_by_item:
            raise BusinessValidationError(
                "candidate reliability parameters are missing",
                code="CANDIDATE_PARAMETERS_MISSING",
                details={
                    "candidate_key": spec.candidate_key,
                    "items": missing_by_item,
                },
            )

    def submit_candidate(
        self,
        session: Session,
        actor: ActorContext,
        *,
        scenario_version_id: int,
        spec: CandidateExecutionSpec,
        idempotency_key: str,
    ) -> DemandCalculation:
        existing = (
            self.calculation_repository
            .get_by_idempotency_key(
                session,
                actor.tenant_id,
                idempotency_key,
            )
        )
        if existing is not None:
            return existing

        trusted_snapshot, warnings = self.build_snapshot(
            session,
            actor,
            CalculationPreviewRequest(
                scenario_version_id=scenario_version_id,
            ),
        )
        snapshot = deepcopy(trusted_snapshot)
        self._validate_candidate_parameters(snapshot, spec)
        for item in snapshot["items"]:
            item["reliability"]["model_type"] = (
                spec.reliability_model.value
            )
        snapshot["candidate_key"] = spec.candidate_key
        snapshot["requested_mode"] = (
            spec.execution_mode.value
        )
        snapshot["random_seed"] = spec.random_seed
        now = datetime.now(timezone.utc)
        calculation = self.calculation_repository.create(
            session,
            actor.tenant_id,
            {
                "calculation_code": (
                    "DC-"
                    f"{now:%Y%m%d%H%M%S}"
                    f"-{uuid.uuid4().hex[:8].upper()}"
                ),
                "calculation_name": (
                    "Candidate "
                    f"{spec.candidate_key}"
                ),
                "scenario_version_id": scenario_version_id,
                "rerun_mode": RerunMode.NEW,
                "execution_type": (
                    CalculationExecutionType.ASYNCHRONOUS
                ),
                "requested_mode": spec.execution_mode,
                "status": CalculationStatus.PENDING,
                "input_snapshot_json": snapshot,
                "input_snapshot_hash": (
                    snapshot_service.canonical_hash(snapshot)
                ),
                "inventory_snapshot_at": now,
                "warnings_json": warnings,
                "submitted_at": now,
                "idempotency_key": idempotency_key,
            },
        )
        return calculation

    def retry_candidate(
        self,
        session: Session,
        actor: ActorContext,
        *,
        source: DemandCalculation,
        idempotency_key: str,
    ) -> DemandCalculation:
        existing = (
            self.calculation_repository
            .get_by_idempotency_key(
                session,
                actor.tenant_id,
                idempotency_key,
            )
        )
        if existing is not None:
            return existing
        now = datetime.now(timezone.utc)
        return self.calculation_repository.create(
            session,
            actor.tenant_id,
            {
                "calculation_code": (
                    "DC-"
                    f"{now:%Y%m%d%H%M%S}"
                    f"-{uuid.uuid4().hex[:8].upper()}"
                ),
                "calculation_name": source.calculation_name,
                "scenario_version_id": (
                    source.scenario_version_id
                ),
                "rerun_mode": RerunMode.REPLAY_SNAPSHOT,
                "source_calculation_id": source.id,
                "execution_type": (
                    CalculationExecutionType.ASYNCHRONOUS
                ),
                "requested_mode": source.requested_mode,
                "status": CalculationStatus.PENDING,
                "input_snapshot_json": deepcopy(
                    source.input_snapshot_json
                ),
                "input_snapshot_hash": (
                    source.input_snapshot_hash
                ),
                "inventory_snapshot_at": (
                    source.inventory_snapshot_at
                ),
                "warnings_json": deepcopy(
                    source.warnings_json
                ),
                "submitted_at": now,
                "idempotency_key": idempotency_key,
            },
        )

    def submit(
        self,
        session: Session,
        actor: ActorContext,
        payload: CalculationCreateRequest,
        *,
        idempotency_key: str | None = None,
        force_async: bool | None = None,
    ) -> DemandCalculation:
        existing = (
            self.calculation_repository
            .get_by_idempotency_key(
                session,
                actor.tenant_id,
                idempotency_key,
            )
            if idempotency_key
            else None
        )
        if existing is not None:
            return existing

        preview = self.preview(
            session,
            actor,
            payload,
        )
        if (
            payload.execution_preference == "SYNC"
            and preview.recommended_execution_type
            == "ASYNCHRONOUS"
        ):
            raise BusinessValidationError(
                "calculation is too complex for "
                "synchronous execution",
                code="SYNC_COMPLEXITY_EXCEEDED",
            )

        snapshot, warnings = self.build_snapshot(
            session,
            actor,
            payload,
        )
        code = (
            "DC-"
            f"{datetime.now(timezone.utc):%Y%m%d%H%M%S}"
            f"-{uuid.uuid4().hex[:8].upper()}"
        )
        execution = (
            CalculationExecutionType.ASYNCHRONOUS
            if (
                force_async
                or payload.execution_preference == "ASYNC"
                or (
                    payload.execution_preference == "AUTO"
                    and preview.recommended_execution_type
                    == "ASYNCHRONOUS"
                )
            )
            else CalculationExecutionType.SYNCHRONOUS
        )
        calculation = (
            self.calculation_repository.create(
                session,
                actor.tenant_id,
                {
                    "calculation_code": code,
                    "calculation_name": (
                        payload.calculation_name
                    ),
                    "scenario_version_id": (
                        payload.scenario_version_id
                    ),
                    "rerun_mode": RerunMode.NEW,
                    "execution_type": execution,
                    "requested_mode": (
                        payload.requested_mode
                    ),
                    "status": CalculationStatus.PENDING,
                    "input_snapshot_json": snapshot,
                    "input_snapshot_hash": (
                        snapshot_service.canonical_hash(
                            snapshot
                        )
                    ),
                    "inventory_snapshot_at": (
                        datetime.now(timezone.utc)
                    ),
                    "warnings_json": warnings,
                    "submitted_at": datetime.now(
                        timezone.utc
                    ),
                    "idempotency_key": idempotency_key,
                },
            )
        )
        session.commit()
        session.refresh(calculation)

        if (
            execution
            is CalculationExecutionType.SYNCHRONOUS
        ):
            self.run(
                session,
                actor,
                calculation.id,
                random_seed=payload.random_seed,
            )
            session.refresh(calculation)

        return calculation

    def run(
        self,
        session: Session,
        actor: ActorContext,
        calculation_id: int,
        *,
        random_seed: int | None = None,
    ) -> DemandCalculation:
        return self._run_for_tenant(
            session,
            actor.tenant_id,
            calculation_id,
            random_seed=random_seed,
        )

    def run_internal(
        self,
        session: Session,
        *,
        tenant_id: str,
        calculation_id: int,
        random_seed: int | None = None,
        observer: DemandExecutionObserver | None = None,
    ) -> DemandCalculation:
        return self._run_for_tenant(
            session,
            tenant_id,
            calculation_id,
            random_seed=random_seed,
            observer=observer,
        )

    def _run_for_tenant(
        self,
        session: Session,
        tenant_id: str,
        calculation_id: int,
        *,
        random_seed: int | None = None,
        observer: DemandExecutionObserver | None = None,
    ) -> DemandCalculation:
        calculation = (
            self.calculation_repository.get_by_id(
                session,
                tenant_id,
                calculation_id,
            )
        )
        if calculation is None:
            raise NotFoundError(
                "demand_calculation",
                calculation_id,
            )
        if calculation.status not in {
            CalculationStatus.PENDING,
            CalculationStatus.FAILED,
            CalculationStatus.INTERRUPTED,
        }:
            raise ConflictError(
                "calculation is not runnable",
                code="CALCULATION_ALREADY_RUNNING",
            )

        calculation.status = CalculationStatus.RUNNING
        calculation.progress_percent = Decimal("1")
        calculation.started_at = datetime.now(
            timezone.utc
        )
        if observer is not None:
            session.flush()
            observer.started(session, calculation)
        session.commit()

        try:
            engine_input = self._to_engine_input(
                calculation.input_snapshot_json,
                calculation.requested_mode,
                random_seed or 20260723,
            )
            engine = DemandCalculationEngine()
            result = engine.calculate(
                engine_input,
                progress_callback=(
                    lambda done, maximum, _:
                    self._update_progress(
                        session,
                        calculation,
                        done,
                        maximum,
                        observer,
                    )
                ),
                cancel_check=lambda: (
                    self._cancel_requested(
                        session,
                        tenant_id,
                        calculation.id,
                    )
                ),
            )
            self._persist_result(
                session,
                tenant_id,
                calculation,
                result,
            )
            calculation.status = (
                CalculationStatus.PARTIAL_SUCCESS
                if calculation.warnings_json
                else CalculationStatus.SUCCEEDED
            )
            calculation.progress_percent = Decimal(
                "100"
            )
            calculation.completed_at = datetime.now(
                timezone.utc
            )
            calculation.result_summary_json = {
                "runs": len(result.runs),
                "items": sum(
                    len(run.items)
                    for run in result.runs
                ),
                "comparison": (
                    asdict(result.comparison)
                    if result.comparison
                    else None
                ),
            }
            if observer is not None:
                session.flush()
                observer.completed(session, calculation)
            session.commit()
            session.refresh(calculation)
            return calculation
        except Exception as exc:
            session.rollback()
            failed = (
                self.calculation_repository.get_by_id(
                    session,
                    tenant_id,
                    calculation_id,
                )
            )
            if failed is not None:
                failed.status = (
                    CalculationStatus.CANCELLED
                    if isinstance(
                        exc,
                        CalculationCancelledError,
                    )
                    else CalculationStatus.FAILED
                )
                failed.error_code = getattr(
                    exc,
                    "code",
                    type(exc).__name__.upper(),
                )
                failed.error_message = str(exc)[:2000]
                failed.completed_at = datetime.now(
                    timezone.utc
                )
                if observer is not None:
                    session.flush()
                    observer.failed(
                        session,
                        failed,
                        exc,
                    )
                session.commit()
            raise

    @staticmethod
    def _update_progress(
        session: Session,
        calculation: DemandCalculation,
        done: int,
        maximum: int,
        observer: DemandExecutionObserver | None = None,
    ) -> None:
        calculation.progress_percent = Decimal(str(min(99, max(1, done * 100 / maximum))))
        if observer is not None:
            observer.progress(
                session,
                calculation,
                calculation.progress_percent,
            )
        session.commit()

    def _cancel_requested(
        self,
        session: Session,
        tenant_id: str,
        calculation_id: int,
    ) -> bool:
        session.expire_all()
        row = self.calculation_repository.get_by_id(
            session,
            tenant_id,
            calculation_id,
        )
        return bool(row and row.cancel_requested)

    def _to_engine_input(
        self, snapshot: dict[str, Any], requested_mode: DemandExecutionMode, random_seed: int
    ) -> CalculationInput:
        stages = tuple(
            StageInput(
                code=stage["code"],
                name=stage.get("name", stage["code"]),
                order=int(stage["order"]),
                duration_hours=float(stage["duration_hours"]),
                utilization_rate=float(stage.get("utilization_rate", 1)),
                mission_intensity_factor=float(stage.get("mission_intensity_factor", 1)),
                environment_factor=float(stage.get("environment_factor", 1)),
                temperature_factor=float(stage.get("temperature_factor", 1)),
                dust_factor=float(stage.get("dust_factor", 1)),
                humidity_factor=float(stage.get("humidity_factor", 1)),
                vibration_factor=float(stage.get("vibration_factor", 1)),
            )
            for stage in snapshot["stages"]
        )
        items = []
        for row in snapshot.get("items", []):
            rel = dict(row["reliability"])
            rel["model_type"] = EngineReliabilityModelType(rel["model_type"])
            for key in (
                "failure_rate",
                "mtbf_hours",
                "weibull_shape",
                "weibull_scale",
                "binomial_probability",
                "negative_binomial_r",
                "negative_binomial_p",
                "empirical_mean",
                "empirical_variance",
                "reference_duration_hours",
            ):
                if rel.get(key) is not None:
                    rel[key] = float(rel[key])
            if rel.get("binomial_trials") is not None:
                rel["binomial_trials"] = int(rel["binomial_trials"])
            repair = row.get("repair")
            age_groups = tuple(
                AgeGroupInput(
                    proportion=float(group["proportion"]),
                    distribution_type=EngineAgeDistributionType(
                        group.get("distribution_type", "FIXED")
                    ),
                    fixed_hours=None
                    if group.get("fixed_hours") is None
                    else float(group["fixed_hours"]),
                    minimum_hours=None
                    if group.get("minimum_hours") is None
                    else float(group["minimum_hours"]),
                    maximum_hours=None
                    if group.get("maximum_hours") is None
                    else float(group["maximum_hours"]),
                    mean_hours=None
                    if group.get("mean_hours") is None
                    else float(group["mean_hours"]),
                    std_hours=None if group.get("std_hours") is None else float(group["std_hours"]),
                    mode_hours=None
                    if group.get("mode_hours") is None
                    else float(group["mode_hours"]),
                )
                for group in row.get("age_groups", [])
            )
            shocks = tuple(
                CommonShockInput(
                    code=shock["code"],
                    probability=float(shock["probability"]),
                    multiplier=float(shock["multiplier"]),
                    application_mode=EngineShockApplicationMode(
                        shock.get("application_mode", "FAILURE_RATE")
                    ),
                    maximum_occurrences=int(shock.get("maximum_occurrences", 1)),
                )
                for shock in row.get("common_shocks", [])
            )
            items.append(
                DemandItemInput(
                    spare_part_id=int(row["spare_part_id"]),
                    spare_part_code=row["spare_part_code"],
                    spare_part_name=row["spare_part_name"],
                    installed_positions=float(row["installed_positions"]),
                    replacement_ratio=float(row.get("replacement_ratio", 1)),
                    is_repairable=bool(row.get("is_repairable", False)),
                    reliability=ReliabilityInput(**rel),
                    failure_process_mode=EngineFailureProcessMode(
                        row.get("failure_process_mode", "AUTO")
                    ),
                    target_service_level=float(row.get("target_service_level", 0.95)),
                    initial_age_hours=float(row.get("initial_age_hours", 0)),
                    age_groups=age_groups,
                    common_shocks=shocks,
                    repair=RepairInput(**{k: float(v) for k, v in repair.items()})
                    if repair
                    else None,
                    inventory=InventoryInput(
                        **{k: float(v) for k, v in row.get("inventory", {}).items()}
                    ),
                    selection_reason=row.get("selection_reason", "AUTO_SELECTED"),
                )
            )
        sim = snapshot.get("simulation", {})
        config = SimulationConfig(
            min_runs=int(sim.get("min_runs", 1000)),
            max_runs=min(
                int(sim.get("max_runs", 50000)), get_settings().demand_max_monte_carlo_runs
            ),
            batch_size=int(sim.get("batch_size", 1000)),
            mean_relative_tolerance=float(sim.get("mean_relative_tolerance", 0.01)),
            quantile_absolute_tolerance=float(sim.get("quantile_absolute_tolerance", 1)),
            required_stable_batches=int(sim.get("required_stable_batches", 3)),
            quantiles=tuple(
                float(value) for value in sim.get("quantiles", [0.5, 0.8, 0.9, 0.95, 0.99])
            ),
        )
        return CalculationInput(
            calculation_code=snapshot.get("calculation_code", "SNAPSHOT"),
            stages=stages,
            items=tuple(items),
            requested_mode=EngineExecutionMode(requested_mode.value),
            simulation=config,
            random_seed=random_seed,
        )

    def _persist_result(
        self,
        session: Session,
        tenant_id: str,
        calculation: DemandCalculation,
        result,
    ) -> None:
        snapshot_by_part = {
            int(row["spare_part_id"]): row
            for row in (
                calculation.input_snapshot_json.get(
                    "items",
                    [],
                )
            )
        }
        for run_result in result.runs:
            run_mode = DemandExecutionMode(
                run_result.mode.value
            )
            run = self.run_repository.create(
                session,
                tenant_id,
                {
                    "calculation_id": calculation.id,
                    "run_mode": run_mode,
                    "status": CalculationStatus.SUCCEEDED,
                    "attempt_number": (
                        self.run_repository.next_attempt(
                            session,
                            tenant_id,
                            calculation.id,
                            run_mode,
                        )
                    ),
                    "is_current_attempt": True,
                    "progress_percent": Decimal("100"),
                    "engine_version": result.engine_version,
                    "formula_version": result.formula_version,
                    "random_seed": (
                        calculation.input_snapshot_json
                        .get("random_seed")
                    ),
                    "simulation_config_json": (
                        calculation.input_snapshot_json
                        .get("simulation")
                    ),
                    "actual_simulation_runs": (
                        run_result.actual_simulation_runs
                    ),
                    "converged": run_result.converged,
                    "stop_reason": run_result.stop_reason,
                    "warnings_json": list(
                        run_result.warnings
                    ),
                    "started_at": calculation.started_at,
                    "completed_at": datetime.now(
                        timezone.utc
                    ),
                },
            )

            for item in run_result.items:
                source = snapshot_by_part.get(
                    item.spare_part_id,
                    {},
                )
                inventory = source.get("inventory", {})
                gap = inventory_gap_service.calculate(
                    recommended_spare_quantity=(
                        item.recommended_spare_quantity
                    ),
                    available_quantity=inventory.get(
                        "available_quantity",
                        0,
                    ),
                    in_transit_quantity=inventory.get(
                        "in_transit_quantity",
                        0,
                    ),
                    safety_stock_reserved=inventory.get(
                        "safety_stock",
                        0,
                    ),
                )
                self.item_result_repository.create(
                    session,
                    tenant_id,
                    {
                        "calculation_run_id": run.id,
                        "spare_part_id": item.spare_part_id,
                        "spare_part_code_snapshot": (
                            item.spare_part_code
                        ),
                        "spare_part_name_snapshot": (
                            item.spare_part_name
                        ),
                        "criticality_level": source.get(
                            "criticality_level"
                        ),
                        "calculation_status": (
                            ItemCalculationStatus.CALCULATED
                        ),
                        "selected_model_type": (
                            item.selected_model_type.value
                        ),
                        "failure_process_mode": (
                            FailureProcessMode(
                                item.failure_process_mode.value
                            )
                        ),
                        "selected_reliability_profile_id": (
                            source.get(
                                "selected_reliability_profile_id"
                            )
                        ),
                        "selected_repair_profile_id": (
                            source.get(
                                "selected_repair_profile_id"
                            )
                        ),
                        "selection_reason_json": {
                            "reason": source.get(
                                "selection_reason"
                            )
                        },
                        "parameter_snapshot_json": {
                            "reliability": source.get(
                                "reliability"
                            ),
                            "repair": source.get("repair"),
                        },
                        "is_manually_overridden": bool(
                            source.get(
                                "manual_override",
                                False,
                            )
                        ),
                        "target_service_level": Decimal(
                            str(item.target_service_level)
                        ),
                        "expected_demand": Decimal(
                            str(item.expected_demand)
                        ),
                        "variance": Decimal(
                            str(item.variance)
                        ),
                        "standard_deviation": Decimal(
                            str(item.standard_deviation)
                        ),
                        "p50": Decimal(str(item.p50)),
                        "p80": Decimal(str(item.p80)),
                        "p90": Decimal(str(item.p90)),
                        "p95": Decimal(str(item.p95)),
                        "p99": Decimal(str(item.p99)),
                        "target_quantile_demand": Decimal(
                            str(item.target_quantile_demand)
                        ),
                        "gross_replacement_demand": Decimal(
                            str(item.gross_replacement_demand)
                        ),
                        "repair_pipeline_demand": Decimal(
                            str(item.repair_pipeline_demand)
                        ),
                        "repair_pipeline_peak": Decimal(
                            str(item.repair_pipeline_peak)
                        ),
                        "net_consumption_demand": Decimal(
                            str(item.net_consumption_demand)
                        ),
                        "recommended_spare_quantity": (
                            Decimal(
                                str(
                                    item.recommended_spare_quantity
                                )
                            )
                        ),
                        "on_hand_quantity": Decimal(
                            str(
                                inventory.get(
                                    "on_hand_quantity",
                                    0,
                                )
                            )
                        ),
                        "available_quantity": Decimal(
                            str(
                                inventory.get(
                                    "available_quantity",
                                    0,
                                )
                            )
                        ),
                        "in_transit_quantity": Decimal(
                            str(
                                inventory.get(
                                    "in_transit_quantity",
                                    0,
                                )
                            )
                        ),
                        "safety_stock_reserved": Decimal(
                            str(
                                inventory.get(
                                    "safety_stock",
                                    0,
                                )
                            )
                        ),
                        "usable_inventory": (
                            gap.usable_inventory
                        ),
                        "net_demand_gap": gap.net_demand_gap,
                        "inventory_coverage_rate": Decimal(
                            str(gap.inventory_coverage_rate)
                        ),
                        "shortage_risk_level": (
                            ShortageRiskLevel(
                                gap.shortage_risk_level
                            )
                        ),
                        "minimum_inventory_point": (
                            -gap.net_demand_gap
                        ),
                        "maximum_simultaneous_gap": (
                            gap.net_demand_gap
                        ),
                        "common_shock_demand": Decimal("0"),
                        "warning_codes_json": list(
                            item.warnings
                        ),
                    },
                )

                contributions = (
                    source.get("contributions") or [{}]
                )
                share = (
                    Decimal(str(item.expected_demand))
                    / Decimal(len(contributions))
                )
                for contribution in contributions:
                    self.contribution_repository.create(
                        session,
                        tenant_id,
                        {
                            "calculation_run_id": run.id,
                            "spare_part_id": item.spare_part_id,
                            "fleet_group_code_snapshot": (
                                contribution.get(
                                    "fleet_group_code"
                                )
                            ),
                            "configuration_version_id": (
                                contribution.get(
                                    "configuration_version_id"
                                )
                            ),
                            "configuration_item_id": (
                                contribution.get(
                                    "configuration_item_id"
                                )
                            ),
                            "item_code_snapshot": (
                                contribution.get("item_code")
                            ),
                            "install_quantity_snapshot": (
                                Decimal(
                                    str(
                                        contribution.get(
                                            "install_quantity",
                                            0,
                                        )
                                    )
                                )
                            ),
                            "equipment_quantity_snapshot": (
                                Decimal(
                                    str(
                                        contribution.get(
                                            "equipment_quantity",
                                            0,
                                        )
                                    )
                                )
                            ),
                            "replacement_ratio_snapshot": (
                                Decimal(
                                    str(
                                        contribution.get(
                                            "replacement_ratio",
                                            1,
                                        )
                                    )
                                )
                            ),
                            "expected_failure_contribution": (
                                share
                            ),
                            "gross_replacement_contribution": (
                                share
                            ),
                            "net_consumption_contribution": (
                                share
                            ),
                            "repair_pipeline_contribution": (
                                Decimal("0")
                            ),
                            "common_shock_contribution": (
                                Decimal("0")
                            ),
                            "reliability_parameter_snapshot_json": (
                                source.get("reliability")
                            ),
                            "repair_parameter_snapshot_json": (
                                source.get("repair")
                            ),
                            "selection_reason_json": {
                                "reason": source.get(
                                    "selection_reason"
                                )
                            },
                        },
                    )

        session.flush()


    def get(
        self,
        session: Session,
        actor: ActorContext,
        calculation_id: int,
    ) -> DemandCalculation:
        row = self.calculation_repository.get_by_id(
            session,
            actor.tenant_id,
            calculation_id,
        )
        if row is None:
            raise NotFoundError(
                "demand_calculation",
                calculation_id,
            )
        return row

    def cancel(
        self,
        session: Session,
        actor: ActorContext,
        calculation_id: int,
    ) -> DemandCalculation:
        row = self.get(
            session,
            actor,
            calculation_id,
        )
        if row.status not in {
            CalculationStatus.PENDING,
            CalculationStatus.RUNNING,
        }:
            raise ConflictError(
                "calculation is not cancellable"
            )
        row.cancel_requested = True
        if row.status is CalculationStatus.PENDING:
            row.status = CalculationStatus.CANCELLED
            row.completed_at = datetime.now(
                timezone.utc
            )
        session.commit()
        session.refresh(row)
        return row


calculation_service = DemandCalculationService()
