from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from app.core.exceptions import InsufficientMaintenanceRoleError
from app.security.actor import ActorContext, MaintenanceRole
from app.security.dependencies import get_actor

ROLE_RANK: dict[MaintenanceRole, int] = {
    MaintenanceRole.VIEWER: 10,
    MaintenanceRole.CONTRIBUTOR: 20,
    MaintenanceRole.ADMIN: 30,
}


def require_role(
    actor: ActorContext,
    minimum: MaintenanceRole,
) -> ActorContext:
    if ROLE_RANK[actor.role] < ROLE_RANK[minimum]:
        raise InsufficientMaintenanceRoleError(
            required_role=minimum.value,
            actual_role=actor.role.value,
            request_id=actor.request_id,
        )
    return actor


def require_viewer(
    actor: Annotated[ActorContext, Depends(get_actor)],
) -> ActorContext:
    return require_role(actor, MaintenanceRole.VIEWER)


def require_contributor(
    actor: Annotated[ActorContext, Depends(get_actor)],
) -> ActorContext:
    return require_role(actor, MaintenanceRole.CONTRIBUTOR)


def require_admin(
    actor: Annotated[ActorContext, Depends(get_actor)],
) -> ActorContext:
    return require_role(actor, MaintenanceRole.ADMIN)
