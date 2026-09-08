from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any


@dataclass(frozen=True, slots=True)
class ReviewRuleDefinition:
    rule_code: str
    version: str
    category: str
    title: str
    severity: str
    blocking_level: str
    enabled: bool = True
    parameters: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ReviewContext:
    scenario_snapshot: dict[str, Any]
    calculation_items: list[dict[str, Any]]
    evidence_items: list[dict[str, Any]]
    repair_items: list[dict[str, Any]] = field(default_factory=list)
    substitute_relations: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ReviewFindingDraft:
    rule_code: str
    rule_version: str
    category: str
    severity: str
    blocking_level: str
    affected_entity_type: str | None
    affected_entity_id: int | None
    affected_spare_part_id: int | None
    finding_title: str
    deterministic_message: str
    observed_value: Any = None
    expected_range: Any = None
    evidence_references: list[str] = field(default_factory=list)
    calculation_reference: str | None = None
    suggested_actions: list[str] = field(default_factory=list)


_RULES = {
    "DAT-001": ("DATA", "高风险场景字段缺失", "ERROR", "BLOCK_FORMAL_CALCULATION"),
    "DAT-002": ("DATA", "可靠性参数未关联来源", "ERROR", "BLOCK_FORMAL_CALCULATION"),
    "DAT-003": ("DATA", "计算快照缺失", "CRITICAL", "BLOCK_REPORT_FINALIZATION"),
    "DAT-004": ("DATA", "参数单位不受支持", "ERROR", "BLOCK_FORMAL_CALCULATION"),
    "CFG-001": ("CONFIGURATION", "器材不属于当前构型", "ERROR", "BLOCK_FORMAL_CALCULATION"),
    "CFG-002": ("CONFIGURATION", "安装数量与构型不一致", "ERROR", "BLOCK_FORMAL_CALCULATION"),
    "CFG-003": ("CONFIGURATION", "失效器材进入正式结果", "ERROR", "BLOCK_REPORT_FINALIZATION"),
    "REL-001": ("RELIABILITY", "可靠性参数超出有效范围", "ERROR", "BLOCK_FORMAL_CALCULATION"),
    "REL-002": ("RELIABILITY", "可靠性来源已失效", "WARNING", "BLOCK_REPORT_FINALIZATION"),
    "REL-003": ("RELIABILITY", "可靠性证据冲突", "ERROR", "BLOCK_FORMAL_CALCULATION"),
    "REL-004": ("RELIABILITY", "模型与参数集不兼容", "ERROR", "BLOCK_FORMAL_CALCULATION"),
    "DEM-001": ("DEMAND", "需求超过历史倍数阈值", "WARNING", "NONE"),
    "DEM-002": ("DEMAND", "需求异常为零", "WARNING", "NONE"),
    "DEM-003": ("DEMAND", "单机需求超过安装位阈值", "WARNING", "NONE"),
    "DEM-004": ("DEMAND", "解析与蒙特卡洛结果偏差过大", "WARNING", "NONE"),
    "DEM-005": ("DEMAND", "共同冲击贡献异常", "WARNING", "NONE"),
    "INV-001": ("INVENTORY", "可用库存低于需求", "ERROR", "BLOCK_REPORT_FINALIZATION"),
    "INV-002": ("INVENTORY", "在途库存晚于任务窗口", "WARNING", "BLOCK_REPORT_FINALIZATION"),
    "INV-003": ("INVENTORY", "修理回流晚于需求时间", "WARNING", "BLOCK_REPORT_FINALIZATION"),
    "INV-004": ("INVENTORY", "安全库存被完全消耗", "WARNING", "NONE"),
    "INV-005": ("INVENTORY", "保障率低于目标", "ERROR", "BLOCK_REPORT_FINALIZATION"),
    "REP-001": ("REPAIR", "可修件缺少修理档案", "ERROR", "BLOCK_FORMAL_CALCULATION"),
    "REP-002": ("REPAIR", "修理回流超过送修数量", "ERROR", "BLOCK_REPORT_FINALIZATION"),
    "REP-003": ("REPAIR", "修理能力超过上限", "WARNING", "BLOCK_REPORT_FINALIZATION"),
    "REP-004": ("REPAIR", "报废数量错误计入回流", "ERROR", "BLOCK_REPORT_FINALIZATION"),
    "SUB-001": ("SUBSTITUTE", "替代件与构型不兼容", "ERROR", "BLOCK_REPORT_FINALIZATION"),
    "SUB-002": ("SUBSTITUTE", "替代比例超过上限", "WARNING", "BLOCK_REPORT_FINALIZATION"),
    "SUB-003": ("SUBSTITUTE", "互斥器材同时选用", "ERROR", "BLOCK_REPORT_FINALIZATION"),
    "SUB-004": ("SUBSTITUTE", "成套器材数量不一致", "WARNING", "BLOCK_REPORT_FINALIZATION"),
    "EVD-001": ("EVIDENCE", "关键参数缺少证据", "ERROR", "BLOCK_FORMAL_CALCULATION"),
    "EVD-002": ("EVIDENCE", "引用版本已失效", "WARNING", "BLOCK_REPORT_FINALIZATION"),
    "EVD-003": ("EVIDENCE", "场景与计算版本不一致", "ERROR", "BLOCK_REPORT_FINALIZATION"),
    "EVD-004": ("EVIDENCE", "模型推断被标记为事实", "ERROR", "BLOCK_REPORT_FINALIZATION"),
}


class AIReviewEngine:
    rule_set_version = "1.0"

    @property
    def rule_definitions(self) -> dict[str, ReviewRuleDefinition]:
        return {
            code: ReviewRuleDefinition(
                rule_code=code,
                version=self.rule_set_version,
                category=data[0],
                title=data[1],
                severity=data[2],
                blocking_level=data[3],
            )
            for code, data in _RULES.items()
        }

    def _finding(
        self,
        code: str,
        *,
        item: dict[str, Any] | None = None,
        message: str,
        observed: Any = None,
        expected: Any = None,
        evidence: list[str] | None = None,
        actions: list[str] | None = None,
    ) -> ReviewFindingDraft:
        rule = self.rule_definitions[code]
        spare_id = (item or {}).get("spare_part_id")
        return ReviewFindingDraft(
            rule_code=code,
            rule_version=rule.version,
            category=rule.category,
            severity=rule.severity,
            blocking_level=rule.blocking_level,
            affected_entity_type="SPARE_PART" if spare_id is not None else "SCENARIO",
            affected_entity_id=spare_id,
            affected_spare_part_id=spare_id,
            finding_title=rule.title,
            deterministic_message=message,
            observed_value=None if observed is None else str(observed),
            expected_range=None if expected is None else str(expected),
            evidence_references=evidence or [],
            calculation_reference=(item or {}).get("calculation_reference"),
            suggested_actions=actions or [],
        )

    def run(self, context: ReviewContext) -> list[ReviewFindingDraft]:
        findings: list[ReviewFindingDraft] = []
        snapshot = context.scenario_snapshot
        if not snapshot:
            findings.append(
                self._finding(
                    "DAT-003",
                    message="需求计算未关联不可变输入快照",
                    actions=["重新生成计算快照"],
                )
            )
        required = ("equipment_model", "configuration_version", "stages")
        missing = [name for name in required if not snapshot.get(name)]
        if missing and snapshot:
            findings.append(
                self._finding(
                    "DAT-001",
                    message="高风险场景字段缺失",
                    observed=",".join(missing),
                    expected="all required fields",
                    actions=["补齐并确认场景字段"],
                )
            )

        evidence_by_id = {str(item.get("evidence_id")): item for item in context.evidence_items}
        conflicting = {
            str(item.get("evidence_id"))
            for item in context.evidence_items
            if item.get("status") == "CONFLICTED"
        }
        stale = {
            str(item.get("evidence_id"))
            for item in context.evidence_items
            if item.get("status") == "STALE"
        }

        for item in context.calculation_items:
            recommended = Decimal(str(item.get("recommended_spare_quantity", 0)))
            usable = Decimal(str(item.get("usable_inventory", 0)))
            gap = Decimal(str(item.get("net_demand_gap", max(Decimal("0"), recommended - usable))))
            coverage = Decimal(str(item.get("inventory_coverage_rate", 1)))
            target = Decimal(str(item.get("target_service_level", 0.95)))
            installed = Decimal(str(item.get("installed_positions", 0)))
            equipment_quantity = Decimal(str(item.get("equipment_quantity", 1) or 1))
            evidence_ids = [str(value) for value in item.get("evidence_references", [])]

            if item.get("belongs_to_configuration") is False:
                findings.append(
                    self._finding(
                        "CFG-001",
                        item=item,
                        message="器材不属于当前构型快照",
                        actions=["移除器材或修正构型"],
                    )
                )
            if item.get("installed_quantity_consistent") is False:
                findings.append(
                    self._finding(
                        "CFG-002",
                        item=item,
                        message="安装数量与构型快照不一致",
                    )
                )
            if item.get("is_active") is False:
                findings.append(
                    self._finding("CFG-003", item=item, message="失效器材仍进入正式结果")
                )
            if item.get("selected_reliability_profile_id") is None:
                findings.append(
                    self._finding(
                        "DAT-002",
                        item=item,
                        message="器材未关联正式可靠性参数档案",
                    )
                )
            if not evidence_ids and item.get("parameter_source_required", False):
                findings.append(
                    self._finding(
                        "EVD-001",
                        item=item,
                        message="关键可靠性参数缺少证据引用",
                    )
                )
            if conflicting.intersection(evidence_ids):
                findings.append(
                    self._finding(
                        "REL-003",
                        item=item,
                        message="可靠性参数关联了冲突证据",
                        evidence=evidence_ids,
                    )
                )
            if stale.intersection(evidence_ids):
                findings.append(
                    self._finding(
                        "EVD-002",
                        item=item,
                        message="引用证据已过有效期",
                        evidence=evidence_ids,
                    )
                )
            if item.get("model_compatible") is False:
                findings.append(self._finding("REL-004", item=item, message="模型与参数集不兼容"))
            if item.get("reliability_parameter_valid") is False:
                findings.append(
                    self._finding("REL-001", item=item, message="可靠性参数超出允许范围")
                )
            if recommended == 0 and installed > 0:
                findings.append(
                    self._finding(
                        "DEM-002",
                        item=item,
                        message="存在安装位但需求异常为零",
                        observed=recommended,
                        expected=">0 or documented reason",
                    )
                )
            if (
                installed > 0
                and recommended / max(equipment_quantity, Decimal("1")) > installed * 2
            ):
                findings.append(
                    self._finding(
                        "DEM-003",
                        item=item,
                        message="单位装备需求超过安装位倍数阈值",
                        observed=recommended / equipment_quantity,
                        expected=f"<={installed * 2}",
                    )
                )
            deviation = item.get("model_relative_difference")
            if deviation is not None and Decimal(str(deviation)) > Decimal("0.25"):
                findings.append(
                    self._finding(
                        "DEM-004",
                        item=item,
                        message="解析与蒙特卡洛结果相对偏差超过25%",
                        observed=deviation,
                        expected="<=0.25",
                    )
                )
            common = Decimal(str(item.get("common_shock_ratio", 0)))
            if common > Decimal("0.5"):
                findings.append(
                    self._finding(
                        "DEM-005",
                        item=item,
                        message="共同冲击贡献比例超过50%",
                        observed=common,
                        expected="<=0.5",
                    )
                )
            if gap > 0 or usable < recommended:
                findings.append(
                    self._finding(
                        "INV-001",
                        item=item,
                        message="可用库存低于建议需求数量",
                        observed=usable,
                        expected=f">={recommended}",
                        actions=["安排采购、调拨或修理回流"],
                    )
                )
            if coverage < target:
                findings.append(
                    self._finding(
                        "INV-005",
                        item=item,
                        message="库存覆盖率低于目标保障水平",
                        observed=coverage,
                        expected=f">={target}",
                    )
                )
            if item.get("in_transit_outside_window"):
                findings.append(
                    self._finding("INV-002", item=item, message="在途库存到达时间晚于任务窗口")
                )
            if item.get("repair_return_after_need"):
                findings.append(
                    self._finding("INV-003", item=item, message="修理回流时间晚于需求时间")
                )
            if item.get("safety_stock_fully_consumed"):
                findings.append(
                    self._finding("INV-004", item=item, message="任务需求将完全消耗安全库存")
                )
            if item.get("is_repairable") and item.get("selected_repair_profile_id") is None:
                findings.append(self._finding("REP-001", item=item, message="可修件未配置修理档案"))
            if Decimal(str(item.get("repair_return_quantity", 0))) > Decimal(
                str(item.get("repair_inducted_quantity", 0))
            ):
                findings.append(
                    self._finding("REP-002", item=item, message="修理回流数量超过送修数量")
                )
            if item.get("repair_capacity_exceeded"):
                findings.append(
                    self._finding("REP-003", item=item, message="修理任务超过设施能力上限")
                )
            if item.get("condemned_counted_as_return"):
                findings.append(
                    self._finding("REP-004", item=item, message="报废数量被错误计入修理回流")
                )
            if item.get("inferred_marked_as_fact"):
                findings.append(
                    self._finding("EVD-004", item=item, message="LLM推断被错误标记为确定事实")
                )
            for evidence_id in evidence_ids:
                if evidence_id and evidence_id not in evidence_by_id:
                    findings.append(
                        self._finding(
                            "EVD-001",
                            item=item,
                            message="引用的证据不存在于当前证据包",
                            evidence=[evidence_id],
                        )
                    )

        for relation in context.substitute_relations:
            item = {"spare_part_id": relation.get("spare_part_id")}
            if relation.get("compatible") is False:
                findings.append(
                    self._finding("SUB-001", item=item, message="替代件不适用于当前构型")
                )
            if Decimal(str(relation.get("ratio", 0))) > Decimal(
                str(relation.get("maximum_ratio", 1))
            ):
                findings.append(self._finding("SUB-002", item=item, message="替代比例超过允许上限"))
            if relation.get("mutually_exclusive_selected"):
                findings.append(self._finding("SUB-003", item=item, message="互斥器材被同时选入"))
            if relation.get("kit_quantity_consistent") is False:
                findings.append(self._finding("SUB-004", item=item, message="成套器材数量不匹配"))
        return findings

    def review_items(self, items: list[dict[str, Any]]) -> list[ReviewFindingDraft]:
        return self.run(
            ReviewContext(
                scenario_snapshot={"scenario_version_id": None, "stages": [{"code": "S1"}]},
                calculation_items=items,
                evidence_items=[],
            )
        )


ai_review_engine = AIReviewEngine()
