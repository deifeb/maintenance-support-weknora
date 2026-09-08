from __future__ import annotations

from collections.abc import Callable

import app.repositories.base as base_repository
import pytest
from app.core.exceptions import NotFoundError
from app.models import ConfigurationVersion, EquipmentModel
from app.repositories.base import TenantScopeError
from app.repositories.equipment_repository import EquipmentRepository
from app.schemas.equipment import EquipmentModelCreate
from app.security.actor import ActorContext
from app.services import equipment_service
from sqlalchemy import select
from sqlalchemy.orm import Session


def add_equipment(
    session: Session,
    *,
    tenant_id: str,
    code: str,
    name: str,
    is_active: bool = True,
) -> EquipmentModel:
    row = EquipmentModel(
        tenant_id=tenant_id,
        code=code,
        name=name,
        is_active=is_active,
    )
    session.add(row)
    session.commit()
    return row


def test_get_by_id_never_returns_another_tenant(
    session: Session,
) -> None:
    first = add_equipment(
        session,
        tenant_id="tenant-a",
        code="EQ",
        name="Tenant A",
    )
    second = add_equipment(
        session,
        tenant_id="tenant-b",
        code="EQ",
        name="Tenant B",
    )
    repository = EquipmentRepository()

    assert repository.get_by_id(
        session,
        "tenant-a",
        first.id,
    ) is first
    assert repository.get_by_id(
        session,
        "tenant-a",
        second.id,
    ) is None


def test_get_by_code_is_scoped_per_tenant(
    session: Session,
) -> None:
    add_equipment(
        session,
        tenant_id="tenant-a",
        code="EQ",
        name="Tenant A",
    )
    add_equipment(
        session,
        tenant_id="tenant-b",
        code="EQ",
        name="Tenant B",
    )
    repository = EquipmentRepository()

    tenant_a = repository.get_by_code(
        session,
        "tenant-a",
        "EQ",
    )
    tenant_b = repository.get_by_code(
        session,
        "tenant-b",
        "EQ",
    )

    assert tenant_a is not None
    assert tenant_a.name == "Tenant A"
    assert tenant_b is not None
    assert tenant_b.name == "Tenant B"


def test_list_and_exists_do_not_cross_tenants(
    session: Session,
) -> None:
    add_equipment(
        session,
        tenant_id="tenant-a",
        code="A-1",
        name="Visible",
    )
    add_equipment(
        session,
        tenant_id="tenant-a",
        code="A-2",
        name="Inactive",
        is_active=False,
    )
    add_equipment(
        session,
        tenant_id="tenant-b",
        code="B-1",
        name="Foreign",
    )
    repository = EquipmentRepository()

    items, total = repository.list_page(
        session,
        "tenant-a",
        page=1,
        page_size=20,
    )

    assert [item.code for item in items] == ["A-1"]
    assert total == 1
    assert repository.exists(
        session,
        "tenant-a",
        code="A-1",
    )
    assert not repository.exists(
        session,
        "tenant-a",
        code="B-1",
    )


def test_create_overrides_protected_fields(
    session: Session,
) -> None:
    repository = EquipmentRepository()

    row = repository.create(
        session,
        "tenant-a",
        {
            "id": 999,
            "tenant_id": "tenant-b",
            "version": 99,
            "code": "EQ",
            "name": "Safe",
        },
    )

    assert row.id != 999
    assert row.tenant_id == "tenant-a"
    assert row.version == 1


def test_update_filters_protected_fields(
    session: Session,
) -> None:
    row = add_equipment(
        session,
        tenant_id="tenant-a",
        code="EQ",
        name="Original",
    )
    repository = EquipmentRepository()

    updated = repository.update(
        session,
        "tenant-a",
        row,
        {
            "id": 999,
            "tenant_id": "tenant-b",
            "version": 99,
            "name": "Updated",
        },
    )

    assert updated.id == row.id
    assert updated.tenant_id == "tenant-a"
    assert updated.version == 1
    assert updated.name == "Updated"


def test_update_and_delete_reject_mismatched_instances(
    session: Session,
) -> None:
    foreign = add_equipment(
        session,
        tenant_id="tenant-b",
        code="EQ",
        name="Foreign",
    )
    repository = EquipmentRepository()

    with pytest.raises(
        TenantScopeError,
        match="another tenant",
    ):
        repository.update(
            session,
            "tenant-a",
            foreign,
            {"name": "Compromised"},
        )

    with pytest.raises(
        TenantScopeError,
        match="another tenant",
    ):
        repository.delete(
            session,
            "tenant-a",
            foreign,
        )


def test_tenant_loader_criteria_filters_mapped_mixins(
    session: Session,
) -> None:
    add_equipment(
        session,
        tenant_id="tenant-a",
        code="A",
        name="Tenant A",
    )
    add_equipment(
        session,
        tenant_id="tenant-b",
        code="B",
        name="Tenant B",
    )

    rows = list(
        session.scalars(
            select(EquipmentModel).options(
                base_repository.tenant_loader_criteria(
                    "tenant-a",
                )
            )
        ).all()
    )

    assert [row.tenant_id for row in rows] == ["tenant-a"]



def test_base_repository_applies_loader_criteria_to_relationships(
    session: Session,
) -> None:
    equipment = add_equipment(
        session,
        tenant_id="tenant-a",
        code="EQ",
        name="Tenant A",
    )
    session.add(
        ConfigurationVersion(
            tenant_id="tenant-b",
            equipment_model_id=equipment.id,
            version_code="V1",
            version_name="Foreign version",
        )
    )
    session.commit()
    session.expire_all()

    loaded = EquipmentRepository().get_by_id(
        session,
        "tenant-a",
        equipment.id,
    )

    assert loaded is not None
    assert loaded.configuration_versions == []

def test_crud_service_derives_tenant_from_actor(
    session: Session,
    actor_context: Callable[..., ActorContext],
) -> None:
    actor_a = actor_context(tenant_id="tenant-a")
    actor_b = actor_context(tenant_id="tenant-b")

    first = equipment_service.create(
        session,
        actor_a,
        EquipmentModelCreate(
            code="EQ",
            name="Tenant A",
        ),
    )
    second = equipment_service.create(
        session,
        actor_b,
        EquipmentModelCreate(
            code="EQ",
            name="Tenant B",
        ),
    )

    assert first.tenant_id == "tenant-a"
    assert second.tenant_id == "tenant-b"
    assert equipment_service.get(
        session,
        actor_a,
        first.id,
    ) is first

    with pytest.raises(NotFoundError):
        equipment_service.get(
            session,
            actor_a,
            second.id,
        )

    page = equipment_service.list(
        session,
        actor_a,
        page=1,
        page_size=20,
        keyword=None,
        include_inactive=False,
        sort_by="id",
        sort_order="asc",
    )

    assert page.total == 1
    assert [item.name for item in page.items] == ["Tenant A"]
