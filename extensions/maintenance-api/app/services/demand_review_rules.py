from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from typing import Any

from app.models.enums import DemandReviewSeverity
from app.schemas.demand_review import (
    DemandReviewSnapshot,
    FindingDraft,
)

RULE_CODES = (
    "COMPLETENESS",
    "CONFIGURATION_APPLICABILITY",
    "KIT_COMPLETENESS",
    "RATIO_CONSISTENCY",
    "MUTUAL_EXCLUSION",
    "COMMON_PART_DUPLICATION",
    "SUBSTITUTE_VALIDITY",
    "RELIABILITY_ANOMALY",
    "MODEL_ANOMALY",
    "INVENTORY_GAP",
    "EVIDENCE_VALIDITY",
)

SEVERITY_ORDER = {
    DemandReviewSeverity.CRITICAL: 0,
    DemandReviewSeverity.HIGH: 1,
    DemandReviewSeverity.MEDIUM: 2,
    DemandReviewSeverity.LOW: 3,
}


def _finding_sort_key(finding: FindingDraft) -> tuple[Any, ...]:
    source_demand_list_item_id = finding.source_demand_list_item_id
    return (
        SEVERITY_ORDER[finding.severity],
        source_demand_list_item_id is None,
        (
            source_demand_list_item_id
            if source_demand_list_item_id is not None
            else 0
        ),
        finding.finding_key,
    )


def _quantity_effect_key(source_demand_list_item_id: int) -> str:
    return f"FINAL_QUANTITY:{source_demand_list_item_id}"


def _evidence_finding(
    key: str,
    *,
    reason: str,
    source_demand_list_item_id: int | None = None,
) -> FindingDraft:
    return FindingDraft(
        finding_key=f"EVIDENCE_VALIDITY:{key}",
        rule_code="EVIDENCE_VALIDITY",
        finding_type="EVIDENCE",
        severity=DemandReviewSeverity.HIGH,
        blocking=True,
        requires_admin_acceptance=True,
        source_demand_list_item_id=source_demand_list_item_id,
        evidence_snapshot={
            "missing_authority": key,
            "reason": reason,
        },
        suggestion_snapshot={
            "action": "PROVIDE_AUTHORITATIVE_SERVER_EVIDENCE",
        },
    )


def _completeness(snapshot: DemandReviewSnapshot) -> list[FindingDraft]:
    findings: list[FindingDraft] = []
    if not snapshot.source_items:
        findings.append(
            FindingDraft(
                finding_key="COMPLETENESS:NO_ITEMS",
                rule_code="COMPLETENESS",
                finding_type="COMPLETENESS",
                severity=DemandReviewSeverity.CRITICAL,
                blocking=True,
                requires_admin_acceptance=True,
                evidence_snapshot={"source_item_count": 0},
                suggestion_snapshot={
                    "action": "REBUILD_DEMAND_LIST_WITH_ITEMS",
                },
            )
        )
        return findings

    required = (
        "spare_part_id",
        "spare_part_code_snapshot",
        "spare_part_name_snapshot",
        "spare_part_unit_snapshot",
        "final_quantity",
    )
    for item in snapshot.source_items:
        missing = [
            field
            for field in required
            if item.get(field) in {None, ""}
        ]
        if missing:
            item_id = int(item["id"])
            findings.append(
                FindingDraft(
                    finding_key=f"COMPLETENESS:ITEM:{item_id}",
                    rule_code="COMPLETENESS",
                    finding_type="COMPLETENESS",
                    severity=DemandReviewSeverity.CRITICAL,
                    blocking=True,
                    requires_admin_acceptance=True,
                    source_demand_list_item_id=item_id,
                    evidence_snapshot={
                        "missing_fields": sorted(missing),
                    },
                    suggestion_snapshot={
                        "action": "RESTORE_PERSISTED_SOURCE_FIELDS",
                    },
                )
            )
    return findings


def _configuration_applicability(
    snapshot: DemandReviewSnapshot,
) -> list[FindingDraft]:
    configuration_items = snapshot.master_data_evidence.get(
        "configuration_items_by_id",
        {},
    )
    by_spare = {
        int(row["spare_part_id"])
        for row in configuration_items.values()
        if row.get("spare_part_id") is not None
    }
    findings: list[FindingDraft] = []
    for item in snapshot.source_items:
        spare_part_id = int(item["spare_part_id"])
        if spare_part_id not in by_spare:
            findings.append(
                _evidence_finding(
                    f"CONFIGURATION_APPLICABILITY:{item['id']}",
                    reason="NO_CONFIGURATION_ITEM_FOR_SOURCE_PART",
                    source_demand_list_item_id=int(item["id"]),
                )
            )
    return findings


def _kit_completeness(
    snapshot: DemandReviewSnapshot,
) -> list[FindingDraft]:
    evidence = snapshot.master_data_evidence.get("kit_evidence", {})
    if evidence.get("status") == "UNAVAILABLE":
        return [
            _evidence_finding(
                "KIT_COMPLETENESS",
                reason=str(
                    evidence.get(
                        "reason",
                        "NO_AUTHORITATIVE_RELATION",
                    )
                ),
            )
        ]
    return []


def _ratio_consistency(
    snapshot: DemandReviewSnapshot,
) -> list[FindingDraft]:
    findings: list[FindingDraft] = []
    configuration_items = snapshot.master_data_evidence.get(
        "configuration_items_by_id",
        {},
    )
    for row in configuration_items.values():
        raw_ratio = row.get("replacement_ratio")
        if raw_ratio is None:
            continue
        ratio = Decimal(str(raw_ratio))
        if ratio < 0 or ratio > 1:
            findings.append(
                FindingDraft(
                    finding_key=f"RATIO_CONSISTENCY:{row['id']}",
                    rule_code="RATIO_CONSISTENCY",
                    finding_type="MASTER_DATA",
                    severity=DemandReviewSeverity.HIGH,
                    blocking=True,
                    requires_admin_acceptance=True,
                    evidence_snapshot={
                        "configuration_item_id": row["id"],
                        "replacement_ratio": str(ratio),
                    },
                    suggestion_snapshot={
                        "action": "CORRECT_MASTER_DATA",
                    },
                )
            )
    return findings


def _mutual_exclusion(
    snapshot: DemandReviewSnapshot,
) -> list[FindingDraft]:
    del snapshot
    return []


def _common_part_duplication(
    snapshot: DemandReviewSnapshot,
) -> list[FindingDraft]:
    seen: dict[int, int] = {}
    findings: list[FindingDraft] = []
    for item in snapshot.source_items:
        spare_part_id = int(item["spare_part_id"])
        item_id = int(item["id"])
        if spare_part_id in seen:
            findings.append(
                FindingDraft(
                    finding_key=(
                        f"COMMON_PART_DUPLICATION:"
                        f"{seen[spare_part_id]}:{item_id}"
                    ),
                    rule_code="COMMON_PART_DUPLICATION",
                    finding_type="DUPLICATION",
                    severity=DemandReviewSeverity.HIGH,
                    blocking=True,
                    requires_admin_acceptance=False,
                    source_demand_list_item_id=item_id,
                    evidence_snapshot={
                        "spare_part_id": spare_part_id,
                        "first_item_id": seen[spare_part_id],
                        "duplicate_item_id": item_id,
                    },
                    suggestion_snapshot={
                        "action": "REVIEW_DUPLICATE_SOURCE_ITEMS",
                    },
                )
            )
        else:
            seen[spare_part_id] = item_id
    return findings


def _substitute_validity(
    snapshot: DemandReviewSnapshot,
) -> list[FindingDraft]:
    evidence = snapshot.master_data_evidence.get(
        "substitution_evidence",
        {},
    )
    if evidence.get("status") == "UNAVAILABLE":
        return [
            _evidence_finding(
                "SUBSTITUTE_VALIDITY",
                reason=str(
                    evidence.get(
                        "reason",
                        "NO_AUTHORITATIVE_RELATION",
                    )
                ),
            )
        ]
    return []


def _reliability_anomaly(
    snapshot: DemandReviewSnapshot,
) -> list[FindingDraft]:
    profiles = snapshot.master_data_evidence.get(
        "reliability_profiles_by_id",
        {},
    )
    profile_part_ids = {
        int(row["spare_part_id"])
        for row in profiles.values()
        if row.get("spare_part_id") is not None
    }
    findings: list[FindingDraft] = []
    for item in snapshot.source_items:
        if item.get("reliability_model") is None:
            continue
        spare_part_id = int(item["spare_part_id"])
        if spare_part_id not in profile_part_ids:
            findings.append(
                _evidence_finding(
                    f"RELIABILITY_ANOMALY:{item['id']}",
                    reason="NO_RELIABILITY_PROFILE_FOR_SELECTED_MODEL",
                    source_demand_list_item_id=int(item["id"]),
                )
            )
    return findings


def _model_anomaly(
    snapshot: DemandReviewSnapshot,
) -> list[FindingDraft]:
    findings: list[FindingDraft] = []
    for item in snapshot.source_items:
        warnings = item.get("warning_snapshot_json") or []
        if warnings:
            item_id = int(item["id"])
            findings.append(
                FindingDraft(
                    finding_key=f"MODEL_ANOMALY:{item_id}",
                    rule_code="MODEL_ANOMALY",
                    finding_type="MODEL",
                    severity=DemandReviewSeverity.MEDIUM,
                    blocking=False,
                    requires_admin_acceptance=False,
                    source_demand_list_item_id=item_id,
                    evidence_snapshot={
                        "warning_codes": sorted(str(code) for code in warnings),
                    },
                    suggestion_snapshot={
                        "action": "REVIEW_MODEL_WARNINGS",
                    },
                )
            )
    return findings


def _inventory_gap(
    snapshot: DemandReviewSnapshot,
) -> list[FindingDraft]:
    available_by_part: dict[int, Decimal] = {}
    for row in snapshot.current_inventory:
        spare_part_id = int(row["spare_part_id"])
        available_by_part[spare_part_id] = (
            available_by_part.get(spare_part_id, Decimal("0"))
            + Decimal(str(row["available_quantity"]))
        )

    findings: list[FindingDraft] = []
    for item in snapshot.source_items:
        item_id = int(item["id"])
        spare_part_id = int(item["spare_part_id"])
        demand_quantity = Decimal(str(item["final_quantity"]))
        available = available_by_part.get(
            spare_part_id,
            Decimal("0"),
        )
        if available < demand_quantity:
            findings.append(
                FindingDraft(
                    finding_key=f"INVENTORY_GAP:{item_id}",
                    rule_code="INVENTORY_GAP",
                    finding_type="QUANTITY",
                    severity=DemandReviewSeverity.HIGH,
                    blocking=True,
                    requires_admin_acceptance=False,
                    source_demand_list_item_id=item_id,
                    effect_key=_quantity_effect_key(item_id),
                    evidence_snapshot={
                        "spare_part_id": spare_part_id,
                        "final_quantity": format(demand_quantity, "f"),
                        "available_quantity": format(available, "f"),
                        "gap_quantity": format(
                            demand_quantity - available,
                            "f",
                        ),
                    },
                    suggestion_snapshot={
                        "final_quantity": format(demand_quantity, "f"),
                        "reason": "INVENTORY_BELOW_DEMAND",
                    },
                )
            )
    return findings


def _evidence_validity(
    snapshot: DemandReviewSnapshot,
) -> list[FindingDraft]:
    del snapshot
    return []


_RULES: tuple[
    tuple[str, Callable[[DemandReviewSnapshot], list[FindingDraft]]],
    ...,
] = (
    ("COMPLETENESS", _completeness),
    ("CONFIGURATION_APPLICABILITY", _configuration_applicability),
    ("KIT_COMPLETENESS", _kit_completeness),
    ("RATIO_CONSISTENCY", _ratio_consistency),
    ("MUTUAL_EXCLUSION", _mutual_exclusion),
    ("COMMON_PART_DUPLICATION", _common_part_duplication),
    ("SUBSTITUTE_VALIDITY", _substitute_validity),
    ("RELIABILITY_ANOMALY", _reliability_anomaly),
    ("MODEL_ANOMALY", _model_anomaly),
    ("INVENTORY_GAP", _inventory_gap),
    ("EVIDENCE_VALIDITY", _evidence_validity),
)


def run_rules(
    snapshot: DemandReviewSnapshot,
) -> tuple[FindingDraft, ...]:
    findings: list[FindingDraft] = []
    for rule_code, evaluator in _RULES:
        if rule_code not in RULE_CODES:
            raise RuntimeError(f"unknown demand review rule: {rule_code}")
        findings.extend(evaluator(snapshot))

    effect_keys = [
        finding.effect_key
        for finding in findings
        if finding.effect_key is not None
    ]
    if len(effect_keys) != len(set(effect_keys)):
        raise RuntimeError("duplicate demand review quantity effect")

    return tuple(sorted(findings, key=_finding_sort_key))
