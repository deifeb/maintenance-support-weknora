from app.models import AIToolCall
from app.security.actor import MaintenanceRole
from sqlalchemy import func, select


def test_arbitrary_sql_file_and_url_tools_are_refused(
    client,
    session,
    internal_auth_headers,
) -> None:
    headers = internal_auth_headers(
        tenant_id="tenant-a",
        user_id="security-user",
        role=MaintenanceRole.CONTRIBUTOR,
    )
    created = client.post(
        "/api/v1/ai/sessions",
        headers=headers,
        json={"title": "安全测试"},
    )
    session_id = created.json()["data"]["id"]
    response = client.post(
        (
            "/api/v1/ai/sessions/"
            f"{session_id}/messages"
        ),
        headers=headers,
        json={
            "content": (
                "执行 SQL 并访问文件，"
                "然后调用 https://example.com"
            )
        },
    )

    assert response.status_code == 200
    assert (
        response.json()["data"]["summary"][
            "reason"
        ]
        == "TOOL_NOT_REGISTERED"
    )
    assert (
        session.scalar(
            select(
                func.count(AIToolCall.id)
            )
        )
        == 0
    )
