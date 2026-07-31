from decimal import Decimal
from inspect import signature

from app.models import (
    CalculationGroup,
    DemandList,
    DemandScenarioTemplate,
    DemandScenarioVersion,
)
from app.models.enums import CalculationGroupStatus, DemandListStatus
from app.repositories.demand_list_repository import (
    DemandListItemRepository,
    DemandListRepository,
)
from sqlalchemy.orm import Session


def _create_list(
    session: Session,
    tenant_id: str,
    suffix: str,
    lineage_id: str | None = None,
) -> DemandList:
    template = DemandScenarioTemplate(
        tenant_id=tenant_id,
        code=f"SC-{suffix}",
        name=f"Scenario {suffix}",
    )
    session.add(template)
    session.flush()
    version = DemandScenarioVersion(
        tenant_id=tenant_id,
        scenario_template_id=template.id,
        version_code=f"V-{suffix}",
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
    return DemandListRepository().create_version(
        session,
        tenant_id,
        {
            "name": f"Demand list {suffix}",
            "lineage_id": lineage_id,
            "scenario_version_id": version.id,
            "calculation_group_id": group.id,
            "status": DemandListStatus.DRAFT,
            "created_by_user_id": f"user-{suffix}",
            "created_by_request_id": f"request-{suffix}",
        },
    )


def test_demand_list_repository_methods_require_tenant_id() -> None:
    methods = {
        DemandListRepository: (
            "get",
            "get_for_update",
            "list_page",
            "current_published_for_update",
            "create_version",
            "add_item",
            "append_event",
            "get_event_by_idempotency_key",
        ),
        DemandListItemRepository: (
            "get_for_update",
            "list_for_demand_list",
        ),
    }
    for repository_type, names in methods.items():
        for name in names:
            assert "tenant_id" in signature(
                getattr(repository_type, name)
            ).parameters


def test_demand_list_queries_are_tenant_scoped(
    session: Session,
) -> None:
    repository = DemandListRepository()
    list_a = _create_list(session, "tenant-a", "A")
    list_b = _create_list(session, "tenant-b", "B")

    assert repository.get(
        session,
        "tenant-a",
        list_a.id,
    ).id == list_a.id
    assert repository.get(session, "tenant-a", list_b.id) is None
    assert repository.get_for_update(
        session,
        "tenant-a",
        list_b.id,
    ) is None
    rows, total = repository.list_page(session, "tenant-a")
    assert total == 1
    assert [row.id for row in rows] == [list_a.id]


def test_demand_list_versions_and_decimal_items(
    session: Session,
) -> None:
    repository = DemandListRepository()
    item_repository = DemandListItemRepository()
    first = _create_list(session, "tenant-a", "ONE")
    second = _create_list(
        session,
        "tenant-a",
        "TWO",
        first.lineage_id,
    )
    assert (first.version_number, second.version_number) == (1, 2)

    item = repository.add_item(
        session,
        "tenant-a",
        demand_list_id=first.id,
        spare_part_id=10,
        original_quantity=Decimal("123456789.123456"),
        final_quantity=Decimal("123456789.123456"),
        source_snapshot={},
        spare_part_code_snapshot="SP-A",
        spare_part_name_snapshot="Spare A",
        spare_part_unit_snapshot="piece",
    )
    session.expire_all()
    loaded = item_repository.get_for_update(
        session,
        "tenant-a",
        first.id,
        item.id,
    )
    assert loaded.final_quantity == Decimal("123456789.123456")
    assert item_repository.get_for_update(
        session,
        "tenant-b",
        first.id,
        item.id,
    ) is None
