from __future__ import annotations

from io import BytesIO

from app.models import SparePart
from app.services.import_service import master_data_import_service
from openpyxl import load_workbook
from sqlalchemy import select


def _workbook_with_spare_row(
    *,
    operation: str,
    code: str,
    name: str,
) -> bytes:
    workbook = load_workbook(
        BytesIO(master_data_import_service.template_bytes())
    )
    sheet = workbook["04_维修器材"]
    values = {
        "操作": operation,
        "器材编码": code,
        "器材名称": name,
        "单位": "件",
    }
    headers = [cell.value for cell in sheet[1]]
    sheet.append([values.get(header) for header in headers])

    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def test_validation_does_not_treat_other_tenant_code_as_conflict(
    session,
):
    session.add(
        SparePart(
            tenant_id="tenant-b",
            code="SP-SHARED",
            name="Tenant B Part",
            unit="件",
            is_active=True,
        )
    )
    session.commit()

    result = master_data_import_service.validate(
        session,
        tenant_id="tenant-a",
        content=_workbook_with_spare_row(
            operation="CREATE",
            code="SP-SHARED",
            name="Tenant A Part",
        ),
        filename="tenant-a.xlsx",
    )

    assert result.valid is True
    assert not any(
        issue.code == "CREATE_CONFLICT"
        for issue in result.errors
    )


def test_apply_creates_rows_for_actor_tenant_only(
    session,
    actor_admin,
):
    result = master_data_import_service.apply(
        session,
        actor=actor_admin,
        content=_workbook_with_spare_row(
            operation="CREATE",
            code="SP-A-001",
            name="Tenant A Part",
        ),
        filename="tenant-a.xlsx",
    )
    session.commit()

    assert result.imported is True
    created = session.scalar(
        select(SparePart).where(
            SparePart.tenant_id == "tenant-a",
            SparePart.code == "SP-A-001",
        )
    )
    assert created is not None
    assert created.tenant_id == "tenant-a"


def test_apply_never_updates_same_code_in_other_tenant(
    session,
    actor_admin,
):
    tenant_b = SparePart(
        tenant_id="tenant-b",
        code="SP-SHARED",
        name="Do Not Change",
        unit="件",
        is_active=True,
    )
    session.add(tenant_b)
    session.commit()

    master_data_import_service.apply(
        session,
        actor=actor_admin,
        content=_workbook_with_spare_row(
            operation="CREATE",
            code="SP-SHARED",
            name="Tenant A Record",
        ),
        filename="tenant-a.xlsx",
    )
    session.commit()
    session.refresh(tenant_b)

    assert tenant_b.name == "Do Not Change"
    assert session.scalar(
        select(SparePart).where(
            SparePart.tenant_id == "tenant-a",
            SparePart.code == "SP-SHARED",
        )
    ) is not None
