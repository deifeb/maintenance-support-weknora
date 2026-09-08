from maintenance_ai.enums import EvidenceStatus, SensitivityLevel
from maintenance_ai.evidence import EvidenceEntry, EvidencePackageBuilder, detect_conflicts


def entry(eid, value, source="MANUAL"):
    return EvidenceEntry(
        evidence_id=eid,
        evidence_type="PARAMETER",
        statement="failure rate",
        parameter_name="failure_rate",
        structured_value=value,
        unit="1/h",
        applicable_equipment="EQ1",
        source_name=source,
        status=EvidenceStatus.VALID,
        sensitivity_level=SensitivityLevel.INTERNAL,
    )


def test_conflicts_are_detected_and_original_citations_retained():
    package = EvidencePackageBuilder().build([entry("E1", 0.1), entry("E2", 0.2)])
    assert len(package.conflicts) == 1
    assert {e.evidence_id for e in package.entries} == {"E1", "E2"}
    assert detect_conflicts(package.entries)[0].parameter_name == "failure_rate"


def test_evidence_query_and_builder_support_http_contract_aliases():
    from maintenance_ai.enums import SensitivityLevel
    from maintenance_ai.evidence import EvidenceEntry, EvidencePackageBuilder, EvidenceQuery

    query = EvidenceQuery(
        query_text="EQ-A 失效率",
        equipment_model_id=1,
        configuration_version_id=2,
        spare_part_ids=[3],
        purpose="reliability_parameter",
        sensitivity=SensitivityLevel.INTERNAL,
        max_items=20,
    )
    assert query.question == "EQ-A 失效率"
    assert query.max_evidence == 20
    item = EvidenceEntry(
        evidence_id="E-1",
        evidence_type="TEXT_EXCERPT",
        statement="evidence",
        source_name="manual",
    )
    package = EvidencePackageBuilder().build(query_text="x", items=(item,))
    assert package.items[0].evidence_id == "E-1"
