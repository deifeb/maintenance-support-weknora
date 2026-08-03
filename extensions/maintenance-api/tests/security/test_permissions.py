from __future__ import annotations

from typing import Annotated

import pytest
from app.core.exceptions import (
    InsufficientMaintenanceRoleError,
    register_exception_handlers,
)
from app.security.actor import ActorContext, MaintenanceRole
from app.security.dependencies import get_actor
from app.security.permissions import (
    require_admin,
    require_contributor,
    require_role,
    require_viewer,
)
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

TOKEN_ID = "5ea49880-7b27-4d9e-a383-1219b8164dc0"


def actor(role: MaintenanceRole) -> ActorContext:
    return ActorContext(
        user_id="user-1",
        tenant_id="12",
        role=role,
        request_id="request-1",
        token_id=TOKEN_ID,
    )


@pytest.mark.parametrize(
    ("actual", "minimum"),
    [
        (MaintenanceRole.VIEWER, MaintenanceRole.VIEWER),
        (MaintenanceRole.CONTRIBUTOR, MaintenanceRole.VIEWER),
        (MaintenanceRole.CONTRIBUTOR, MaintenanceRole.CONTRIBUTOR),
        (MaintenanceRole.ADMIN, MaintenanceRole.VIEWER),
        (MaintenanceRole.ADMIN, MaintenanceRole.CONTRIBUTOR),
        (MaintenanceRole.ADMIN, MaintenanceRole.ADMIN),
    ],
)
def test_require_role_accepts_role_floor(
    actual: MaintenanceRole,
    minimum: MaintenanceRole,
) -> None:
    current = actor(actual)

    assert require_role(current, minimum) is current


@pytest.mark.parametrize(
    ("actual", "minimum"),
    [
        (MaintenanceRole.VIEWER, MaintenanceRole.CONTRIBUTOR),
        (MaintenanceRole.VIEWER, MaintenanceRole.ADMIN),
        (MaintenanceRole.CONTRIBUTOR, MaintenanceRole.ADMIN),
    ],
)
def test_require_role_rejects_insufficient_role(
    actual: MaintenanceRole,
    minimum: MaintenanceRole,
) -> None:
    with pytest.raises(InsufficientMaintenanceRoleError) as exc_info:
        require_role(actor(actual), minimum)

    assert exc_info.value.status_code == 403
    assert exc_info.value.code == "INSUFFICIENT_MAINTENANCE_ROLE"
    assert exc_info.value.request_id == "request-1"
    assert exc_info.value.details == {
        "required_role": minimum.value,
        "actual_role": actual.value,
    }


def test_named_role_dependencies_use_the_same_ladder() -> None:
    viewer = actor(MaintenanceRole.VIEWER)
    contributor = actor(MaintenanceRole.CONTRIBUTOR)
    admin = actor(MaintenanceRole.ADMIN)

    assert require_viewer(viewer) is viewer
    assert require_contributor(contributor) is contributor
    assert require_admin(admin) is admin

    with pytest.raises(InsufficientMaintenanceRoleError):
        require_contributor(viewer)

    with pytest.raises(InsufficientMaintenanceRoleError):
        require_admin(contributor)


def test_contributor_dependency_returns_controlled_403() -> None:
    application = FastAPI()
    register_exception_handlers(application)
    application.dependency_overrides[get_actor] = lambda: actor(MaintenanceRole.VIEWER)

    @application.post("/protected")
    def protected(
        current: Annotated[ActorContext, Depends(require_contributor)],
    ) -> dict[str, str]:
        return {"user_id": current.user_id}

    with TestClient(application) as client:
        response = client.post("/protected")

    assert response.status_code == 403
    assert response.json() == {
        "success": False,
        "error": {
            "code": "INSUFFICIENT_MAINTENANCE_ROLE",
            "message": "contributor role is required",
            "details": {
                "required_role": "contributor",
                "actual_role": "viewer",
            },
            "request_id": "request-1",
        },
    }
