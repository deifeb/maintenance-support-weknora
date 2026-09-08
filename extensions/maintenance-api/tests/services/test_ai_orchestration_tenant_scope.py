from __future__ import annotations

import ast
from inspect import signature
from pathlib import Path

from app.services.ai_orchestration_service import (
    AIOrchestrationService,
)
from app.services.ai_plan_service import (
    AIPlanService,
)
from app.services.ai_tool_registry import (
    ToolExecutionContext,
)


def test_plan_and_orchestration_public_methods_require_actor(
) -> None:
    matrix = (
        (
            AIPlanService,
            ("create_and_validate",),
        ),
        (
            AIOrchestrationService,
            (
                "handle_message",
                "resume",
                "execute_plan",
            ),
        ),
    )

    for service_type, method_names in matrix:
        for method_name in method_names:
            parameters = signature(
                getattr(
                    service_type,
                    method_name,
                )
            ).parameters
            assert "actor" in parameters
            assert "user_id" not in parameters

    assert (
        "actor"
        in ToolExecutionContext.model_fields
    )
    assert (
        "tenant_id"
        not in ToolExecutionContext.model_fields
    )
    assert (
        "user_id"
        not in ToolExecutionContext.model_fields
    )


def test_orchestration_and_tools_have_no_direct_tenant_queries(
) -> None:
    root = Path(__file__).parents[2]
    relatives = (
        "app/services/ai_plan_service.py",
        "app/services/ai_orchestration_service.py",
        "app/services/ai_tool_adapters.py",
    )
    forbidden = {
        "get",
        "scalar",
        "scalars",
        "query",
        "execute",
        "add",
        "add_all",
    }

    for relative in relatives:
        path = root / relative
        tree = ast.parse(
            path.read_text(encoding="utf-8"),
            filename=str(path),
        )
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not isinstance(
                func,
                ast.Attribute,
            ):
                continue
            if (
                isinstance(func.value, ast.Name)
                and func.value.id == "session"
                and func.attr in forbidden
            ):
                raise AssertionError(
                    f"{relative}:{node.lineno}: "
                    f"session.{func.attr}"
                )

    adapter_source = (
        root
        / "app/services/ai_tool_adapters.py"
    ).read_text(encoding="utf-8")
    assert "from sqlalchemy import select" not in (
        adapter_source
    )
    assert (
        "demand_task_executor.submit(\n"
        "            context.tenant_id,"
        in adapter_source
    )
