from __future__ import annotations

from collections.abc import Callable

import pytest
from app.repositories.ai_report_repository import ai_report_repository
from app.security.actor import ActorContext, MaintenanceRole
from app.services.ai_report_service import ai_report_service
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

LIFECYCLE_PATHS = {
    "generate": "/api/v1/reports/{report_id}/generate",
    "validate": "/api/v1/reports/{report_id}/validate",
    "finalize": "/api/v1/reports/{report_id}/finalize",
}

COMPACT_JOB_KEYS = {
    "report_id",
    "report_code",
    "report_type",
    "job_status",
    "title",
    "progress_percent",
    "error_code",
    "latest_version",
}

VERSION_KEYS = {
    "id",
    "version_number",
    "status",
    "parent_version_id",
    "template_version",
    "content_digest",
    "input_digest",
    "generation_mode",
    "generated_at",
}


def _require_route(client: TestClient, name: str) -> None:
    path = LIFECYCLE_PATHS[name]
    path_item = client.app.openapi()["paths"].get(path)
    assert path_item is not None and "post" in path_item, (
        f"C2C RED: POST {path} is absent"
    )


def _require_all_lifecycle_routes(client: TestClient) -> None:
    for name in LIFECYCLE_PATHS:
        _require_route(client, name)


def _headers(
    internal_auth_headers: Callable[..., dict[str, str]],
    *,
    tenant_id: str,
    user_id: str,
    role: MaintenanceRole,
) -> dict[str, str]:
    return internal_auth_headers(
        tenant_id=tenant_id,
        user_id=user_id,
        role=role,
    )


def _assert_compact_job(data: dict[str, object]) -> None:
    assert set(data) == COMPACT_JOB_KEYS
    latest = data["latest_version"]
    assert isinstance(latest, dict)
    assert set(latest) == VERSION_KEYS


def _create_draft(
    client: TestClient,
    headers: dict[str, str],
    *,
    title: str,
) -> int:
    response = client.post(
        "/api/v1/reports/jobs",
        headers=headers,
        json={
            "title": title,
            "report_type": "MANAGEMENT_DECISION",
            "metadata": {"allowed_numbers": []},
        },
    )
    assert response.status_code == 200
    data = response.json()["data"]
    _assert_compact_job(data)
    assert data["job_status"] == "CREATED"
    assert data["progress_percent"] == 0
    assert data["error_code"] is None
    assert data["latest_version"]["status"] == "DRAFT"
    assert data["latest_version"]["version_number"] == 1
    assert data["latest_version"]["generation_mode"] is None
    assert data["latest_version"]["generated_at"] is None
    return int(data["report_id"])


def _snapshot(
    session: Session,
    actor_context: Callable[..., ActorContext],
    *,
    tenant_id: str,
    report_id: int,
) -> dict[str, object]:
    session.expire_all()
    actor = actor_context(
        tenant_id=tenant_id,
        user_id="c2c-state-reader",
        role=MaintenanceRole.ADMIN,
    )
    job = ai_report_service.get_job(
        session,
        actor,
        report_id,
    )
    version = ai_report_service.latest_version(
        session,
        actor,
        report_id,
    )
    versions = ai_report_service.list_versions(
        session,
        actor,
        report_id,
    )
    sections = ai_report_repository.list_sections(
        session,
        tenant_id,
        version.id,
    )
    findings = ai_report_repository.list_validation_findings(
        session,
        tenant_id,
        version.id,
    )
    return {
        "job_status": job.status.value,
        "progress_percent": job.progress_percent,
        "error_code": job.error_code,
        "version_id": version.id,
        "version_number": version.version_number,
        "version_status": version.status.value,
        "generated_at": version.generated_at,
        "finalized_by": version.finalized_by,
        "version_count": len(versions),
        "section_count": len(sections),
        "finding_count": len(findings),
    }


@pytest.mark.parametrize(
    ("name", "path"),
    tuple(LIFECYCLE_PATHS.items()),
)
def test_report_center_lifecycle_routes_are_exposed(
    client: TestClient,
    name: str,
    path: str,
) -> None:
    del path
    _require_route(client, name)


def test_report_center_create_generate_validate_finalize_flow(
    client: TestClient,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    _require_all_lifecycle_routes(client)
    tenant_id = "tenant-c2c-flow"
    contributor = _headers(
        internal_auth_headers,
        tenant_id=tenant_id,
        user_id="c2c-contributor",
        role=MaintenanceRole.CONTRIBUTOR,
    )
    admin = _headers(
        internal_auth_headers,
        tenant_id=tenant_id,
        user_id="c2c-admin",
        role=MaintenanceRole.ADMIN,
    )
    report_id = _create_draft(
        client,
        contributor,
        title="C2C lifecycle flow",
    )

    generated = client.post(
        LIFECYCLE_PATHS["generate"].format(report_id=report_id),
        headers=contributor,
    )
    assert generated.status_code == 200
    generated_data = generated.json()["data"]
    _assert_compact_job(generated_data)
    assert generated_data["job_status"] == "VALIDATING_NUMBERS"
    assert generated_data["progress_percent"] == 75
    assert generated_data["error_code"] is None
    assert generated_data["latest_version"]["status"] == "DRAFT"
    assert (
        generated_data["latest_version"]["generation_mode"]
        == "RULE_FALLBACK"
    )
    assert generated_data["latest_version"]["generated_at"] is not None

    validated = client.post(
        LIFECYCLE_PATHS["validate"].format(report_id=report_id),
        headers=contributor,
    )
    assert validated.status_code == 200
    validated_data = validated.json()["data"]
    _assert_compact_job(validated_data)
    assert validated_data["job_status"] == "READY_FOR_REVIEW"
    assert validated_data["progress_percent"] == 100
    assert validated_data["error_code"] is None
    assert validated_data["latest_version"]["status"] == "REVIEWED"

    finalized = client.post(
        LIFECYCLE_PATHS["finalize"].format(report_id=report_id),
        headers=admin,
    )
    assert finalized.status_code == 200
    finalized_data = finalized.json()["data"]
    _assert_compact_job(finalized_data)
    assert finalized_data["job_status"] == "FINALIZED"
    assert finalized_data["progress_percent"] == 100
    assert finalized_data["error_code"] is None
    assert finalized_data["latest_version"]["status"] == "FINAL"


def test_admin_can_generate_and_validate(
    client: TestClient,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    _require_all_lifecycle_routes(client)
    admin = _headers(
        internal_auth_headers,
        tenant_id="tenant-c2c-admin-flow",
        user_id="c2c-admin",
        role=MaintenanceRole.ADMIN,
    )
    report_id = _create_draft(
        client,
        admin,
        title="C2C admin lifecycle",
    )
    generated = client.post(
        LIFECYCLE_PATHS["generate"].format(report_id=report_id),
        headers=admin,
    )
    assert generated.status_code == 200
    validated = client.post(
        LIFECYCLE_PATHS["validate"].format(report_id=report_id),
        headers=admin,
    )
    assert validated.status_code == 200
    assert validated.json()["data"]["job_status"] == "READY_FOR_REVIEW"


def test_viewer_commands_are_403_without_mutation(
    client: TestClient,
    session: Session,
    actor_context: Callable[..., ActorContext],
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    _require_all_lifecycle_routes(client)
    tenant_id = "tenant-c2c-viewer"
    contributor = _headers(
        internal_auth_headers,
        tenant_id=tenant_id,
        user_id="c2c-owner",
        role=MaintenanceRole.CONTRIBUTOR,
    )
    viewer = _headers(
        internal_auth_headers,
        tenant_id=tenant_id,
        user_id="c2c-viewer",
        role=MaintenanceRole.VIEWER,
    )
    report_id = _create_draft(
        client,
        contributor,
        title="C2C viewer authorization",
    )

    for name, prepare in (
        ("generate", None),
        ("validate", "generate"),
        ("finalize", "validate"),
    ):
        if prepare == "generate":
            assert client.post(
                LIFECYCLE_PATHS["generate"].format(report_id=report_id),
                headers=contributor,
            ).status_code == 200
        elif prepare == "validate":
            assert client.post(
                LIFECYCLE_PATHS["validate"].format(report_id=report_id),
                headers=contributor,
            ).status_code == 200

        before = _snapshot(
            session,
            actor_context,
            tenant_id=tenant_id,
            report_id=report_id,
        )
        response = client.post(
            LIFECYCLE_PATHS[name].format(report_id=report_id),
            headers=viewer,
        )
        assert response.status_code == 403
        assert (
            response.json()["error"]["code"]
            == "INSUFFICIENT_MAINTENANCE_ROLE"
        )
        assert _snapshot(
            session,
            actor_context,
            tenant_id=tenant_id,
            report_id=report_id,
        ) == before


def test_contributor_cannot_finalize_without_mutation(
    client: TestClient,
    session: Session,
    actor_context: Callable[..., ActorContext],
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    _require_all_lifecycle_routes(client)
    tenant_id = "tenant-c2c-contributor-finalize"
    contributor = _headers(
        internal_auth_headers,
        tenant_id=tenant_id,
        user_id="c2c-contributor",
        role=MaintenanceRole.CONTRIBUTOR,
    )
    report_id = _create_draft(
        client,
        contributor,
        title="C2C contributor finalize",
    )
    assert client.post(
        LIFECYCLE_PATHS["generate"].format(report_id=report_id),
        headers=contributor,
    ).status_code == 200
    assert client.post(
        LIFECYCLE_PATHS["validate"].format(report_id=report_id),
        headers=contributor,
    ).status_code == 200
    before = _snapshot(
        session,
        actor_context,
        tenant_id=tenant_id,
        report_id=report_id,
    )
    response = client.post(
        LIFECYCLE_PATHS["finalize"].format(report_id=report_id),
        headers=contributor,
    )
    assert response.status_code == 403
    assert (
        response.json()["error"]["code"]
        == "INSUFFICIENT_MAINTENANCE_ROLE"
    )
    assert _snapshot(
        session,
        actor_context,
        tenant_id=tenant_id,
        report_id=report_id,
    ) == before


def test_foreign_tenant_commands_are_404_before_mutation(
    client: TestClient,
    session: Session,
    actor_context: Callable[..., ActorContext],
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    _require_all_lifecycle_routes(client)
    owner_tenant = "tenant-c2c-owner"
    owner = _headers(
        internal_auth_headers,
        tenant_id=owner_tenant,
        user_id="c2c-owner",
        role=MaintenanceRole.CONTRIBUTOR,
    )
    foreign = _headers(
        internal_auth_headers,
        tenant_id="tenant-c2c-foreign",
        user_id="c2c-foreign",
        role=MaintenanceRole.CONTRIBUTOR,
    )
    foreign_admin = _headers(
        internal_auth_headers,
        tenant_id="tenant-c2c-foreign",
        user_id="c2c-foreign-admin",
        role=MaintenanceRole.ADMIN,
    )
    report_id = _create_draft(
        client,
        owner,
        title="C2C tenant isolation",
    )

    before = _snapshot(
        session,
        actor_context,
        tenant_id=owner_tenant,
        report_id=report_id,
    )
    denied = client.post(
        LIFECYCLE_PATHS["generate"].format(report_id=report_id),
        headers=foreign,
    )
    assert denied.status_code == 404
    assert _snapshot(
        session,
        actor_context,
        tenant_id=owner_tenant,
        report_id=report_id,
    ) == before

    assert client.post(
        LIFECYCLE_PATHS["generate"].format(report_id=report_id),
        headers=owner,
    ).status_code == 200

    before = _snapshot(
        session,
        actor_context,
        tenant_id=owner_tenant,
        report_id=report_id,
    )
    denied = client.post(
        LIFECYCLE_PATHS["validate"].format(report_id=report_id),
        headers=foreign,
    )
    assert denied.status_code == 404
    assert _snapshot(
        session,
        actor_context,
        tenant_id=owner_tenant,
        report_id=report_id,
    ) == before

    assert client.post(
        LIFECYCLE_PATHS["validate"].format(report_id=report_id),
        headers=owner,
    ).status_code == 200

    before = _snapshot(
        session,
        actor_context,
        tenant_id=owner_tenant,
        report_id=report_id,
    )
    denied = client.post(
        LIFECYCLE_PATHS["finalize"].format(report_id=report_id),
        headers=foreign_admin,
    )
    assert denied.status_code == 404
    assert _snapshot(
        session,
        actor_context,
        tenant_id=owner_tenant,
        report_id=report_id,
    ) == before


def test_lifecycle_validation_guards_are_preserved(
    client: TestClient,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    _require_all_lifecycle_routes(client)
    tenant_id = "tenant-c2c-guards"
    contributor = _headers(
        internal_auth_headers,
        tenant_id=tenant_id,
        user_id="c2c-contributor",
        role=MaintenanceRole.CONTRIBUTOR,
    )
    admin = _headers(
        internal_auth_headers,
        tenant_id=tenant_id,
        user_id="c2c-admin",
        role=MaintenanceRole.ADMIN,
    )

    ungenerated = _create_draft(
        client,
        contributor,
        title="C2C generation required",
    )
    response = client.post(
        LIFECYCLE_PATHS["validate"].format(report_id=ungenerated),
        headers=contributor,
    )
    assert response.status_code == 422
    assert (
        response.json()["error"]["code"]
        == "REPORT_GENERATION_REQUIRED"
    )

    generated = _create_draft(
        client,
        contributor,
        title="C2C already generated",
    )
    assert client.post(
        LIFECYCLE_PATHS["generate"].format(report_id=generated),
        headers=contributor,
    ).status_code == 200
    duplicate = client.post(
        LIFECYCLE_PATHS["generate"].format(report_id=generated),
        headers=contributor,
    )
    assert duplicate.status_code == 422
    assert (
        duplicate.json()["error"]["code"]
        == "REPORT_VERSION_ALREADY_GENERATED"
    )

    premature = _create_draft(
        client,
        contributor,
        title="C2C validation required",
    )
    assert client.post(
        LIFECYCLE_PATHS["generate"].format(report_id=premature),
        headers=contributor,
    ).status_code == 200
    not_ready = client.post(
        LIFECYCLE_PATHS["finalize"].format(report_id=premature),
        headers=admin,
    )
    assert not_ready.status_code == 422
    assert (
        not_ready.json()["error"]["code"]
        == "REPORT_VALIDATION_REQUIRED"
    )


def test_final_version_is_immutable_for_generate_and_validate(
    client: TestClient,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    _require_all_lifecycle_routes(client)
    tenant_id = "tenant-c2c-final"
    contributor = _headers(
        internal_auth_headers,
        tenant_id=tenant_id,
        user_id="c2c-contributor",
        role=MaintenanceRole.CONTRIBUTOR,
    )
    admin = _headers(
        internal_auth_headers,
        tenant_id=tenant_id,
        user_id="c2c-admin",
        role=MaintenanceRole.ADMIN,
    )
    report_id = _create_draft(
        client,
        contributor,
        title="C2C final immutable",
    )
    for name, headers in (
        ("generate", contributor),
        ("validate", contributor),
        ("finalize", admin),
    ):
        assert client.post(
            LIFECYCLE_PATHS[name].format(report_id=report_id),
            headers=headers,
        ).status_code == 200

    for name in ("generate", "validate"):
        response = client.post(
            LIFECYCLE_PATHS[name].format(report_id=report_id),
            headers=contributor,
        )
        assert response.status_code == 422
        assert (
            response.json()["error"]["code"]
            == "REPORT_FINAL_VERSION_IMMUTABLE"
        )


def test_regenerate_then_validate_finalize_preserves_linear_versions(
    client: TestClient,
    internal_auth_headers: Callable[..., dict[str, str]],
) -> None:
    _require_all_lifecycle_routes(client)
    tenant_id = "tenant-c2c-regenerate"
    contributor = _headers(
        internal_auth_headers,
        tenant_id=tenant_id,
        user_id="c2c-contributor",
        role=MaintenanceRole.CONTRIBUTOR,
    )
    admin = _headers(
        internal_auth_headers,
        tenant_id=tenant_id,
        user_id="c2c-admin",
        role=MaintenanceRole.ADMIN,
    )
    report_id = _create_draft(
        client,
        contributor,
        title="C2C regenerate flow",
    )
    assert client.post(
        LIFECYCLE_PATHS["generate"].format(report_id=report_id),
        headers=contributor,
    ).status_code == 200

    before = client.get(
        f"/api/v1/reports/{report_id}/versions",
        headers=contributor,
    )
    assert before.status_code == 200
    v1 = dict(before.json()["data"][0])

    regenerated = client.post(
        f"/api/v1/reports/{report_id}/regenerate",
        headers=contributor,
    )
    assert regenerated.status_code == 200
    latest = regenerated.json()["data"]["latest_version"]
    assert latest["version_number"] == 2
    assert latest["parent_version_id"] == v1["id"]
    assert latest["status"] == "DRAFT"
    assert latest["generation_mode"] == "RULE_FALLBACK"
    assert latest["generated_at"] is not None

    assert client.post(
        LIFECYCLE_PATHS["validate"].format(report_id=report_id),
        headers=contributor,
    ).status_code == 200
    finalized = client.post(
        LIFECYCLE_PATHS["finalize"].format(report_id=report_id),
        headers=admin,
    )
    assert finalized.status_code == 200
    assert finalized.json()["data"]["latest_version"]["status"] == "FINAL"

    after = client.get(
        f"/api/v1/reports/{report_id}/versions",
        headers=contributor,
    )
    assert after.status_code == 200
    versions = after.json()["data"]
    assert len(versions) == 2
    assert versions[0]["id"] == v1["id"]
    assert versions[0]["status"] == v1["status"]
    assert versions[0]["content_digest"] == v1["content_digest"]
    assert versions[1]["parent_version_id"] == v1["id"]
    assert versions[1]["status"] == "FINAL"
