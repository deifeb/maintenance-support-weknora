from __future__ import annotations

import json
from typing import Annotated, Any

from fastapi import Depends, Header, Request
from fastapi.exceptions import RequestValidationError
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.security.actor import ActorContext
from app.security.permissions import (
    require_admin,
    require_contributor,
    require_viewer,
)

# PLAN05_4D_TASK6_GREEN_D: API-only dependencies and guards.
SessionDep = Annotated[Session, Depends(get_db_session)]
ViewerDep = Annotated[ActorContext, Depends(require_viewer)]
ContributorDep = Annotated[
    ActorContext,
    Depends(require_contributor),
]
AdminDep = Annotated[ActorContext, Depends(require_admin)]
IdempotencyKeyDep = Annotated[
    str,
    Header(
        alias="Idempotency-Key",
        min_length=1,
        max_length=128,
    ),
]


def _tenant_override_error(
    *,
    location: str,
    value: Any,
) -> RequestValidationError:
    return RequestValidationError(
        [
            {
                "type": "extra_forbidden",
                "loc": (location, "tenant_id"),
                "msg": "tenant_id is not accepted",
                "input": value,
            }
        ]
    )


async def reject_tenant_override(request: Request) -> None:
    if "tenant_id" in request.query_params:
        raise _tenant_override_error(
            location="query",
            value=request.query_params.get("tenant_id"),
        )

    raw_body = await request.body()
    if not raw_body:
        return

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return

    if isinstance(payload, dict) and "tenant_id" in payload:
        raise _tenant_override_error(
            location="body",
            value=payload["tenant_id"],
        )


def _duplicate_query_error(
    *,
    parameter: str,
    values: list[str],
) -> RequestValidationError:
    return RequestValidationError(
        [
            {
                "type": "multiple_argument_values",
                "loc": ("query", parameter),
                "msg": (
                    "query parameter must be provided at most once"
                ),
                "input": values,
            }
        ]
    )


def _reject_duplicate_query_parameters(
    parameter_names: frozenset[str],
):
    async def dependency(request: Request) -> None:
        for parameter in parameter_names:
            values = request.query_params.getlist(parameter)
            if len(values) > 1:
                raise _duplicate_query_error(
                    parameter=parameter,
                    values=values,
                )

    return dependency


_RULE_LIST_QUERY_PARAMS = frozenset(
    {"page", "page_size", "status", "lineage_id"}
)
_PLAN_LIST_QUERY_PARAMS = frozenset(
    {
        "page",
        "page_size",
        "status",
        "source_demand_list_id",
        "rule_id",
    }
)

TenantGuardDep = Annotated[
    None,
    Depends(reject_tenant_override),
]
RuleListQueryGuardDep = Annotated[
    None,
    Depends(
        _reject_duplicate_query_parameters(
            _RULE_LIST_QUERY_PARAMS
        )
    ),
]
PlanListQueryGuardDep = Annotated[
    None,
    Depends(
        _reject_duplicate_query_parameters(
            _PLAN_LIST_QUERY_PARAMS
        )
    ),
]
