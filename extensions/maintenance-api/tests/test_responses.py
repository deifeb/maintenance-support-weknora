import pytest
from app.core.responses import success_response
from app.schemas.common import MaintenanceSuccessResponse, SuccessResponse
from app.security.actor import ActorContext, MaintenanceRole

TOKEN_ID = "5ea49880-7b27-4d9e-a383-1219b8164dc0"


def actor() -> ActorContext:
    return ActorContext(
        user_id="user-1",
        tenant_id="12",
        role=MaintenanceRole.CONTRIBUTOR,
        request_id="request-1",
        token_id=TOKEN_ID,
    )


def test_legacy_success_response_shape_is_unchanged() -> None:
    response = success_response({"value": 1}, "Operation successful")

    assert type(response) is SuccessResponse
    assert response.model_dump() == {
        "success": True,
        "data": {"value": 1},
        "message": "Operation successful",
    }


def test_actor_aware_success_response_contains_request_metadata() -> None:
    response = success_response(
        {"value": 1},
        "Operation successful",
        actor=actor(),
    )

    assert isinstance(response, MaintenanceSuccessResponse)
    assert response.model_dump() == {
        "success": True,
        "data": {"value": 1},
        "message": "Operation successful",
        "meta": {
            "request_id": "request-1",
            "tenant_id": "12",
            "version": None,
        },
    }


def test_actor_aware_success_response_contains_object_version() -> None:
    response = success_response(
        {"value": 1},
        actor=actor(),
        version=4,
    )

    assert response.meta.version == 4


def test_version_metadata_requires_authenticated_actor() -> None:
    with pytest.raises(
        ValueError,
        match="version metadata requires an authenticated actor",
    ):
        success_response({"value": 1}, version=4)
