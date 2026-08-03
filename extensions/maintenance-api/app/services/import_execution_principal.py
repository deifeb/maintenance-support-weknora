from __future__ import annotations

from app.core.exceptions import InsufficientMaintenanceRoleError
from app.models.import_task import MasterDataImportTask
from app.security.actor import ActorContext, MaintenanceRole

INVALID_IMPORT_EXECUTION_PRINCIPAL_CODE = (
    "IMPORT_EXECUTION_PRINCIPAL_INVALID"
)
INVALID_IMPORT_EXECUTION_PRINCIPAL_MESSAGE = (
    "Import execution requires a persisted administrator principal"
)


def execution_actor_from_task(
    task: MasterDataImportTask,
) -> ActorContext:
    roles = task.execution_roles_json
    user_id = task.execution_user_id
    request_id = task.execution_request_id
    token_id = task.execution_token_id
    valid = (
        isinstance(roles, list)
        and MaintenanceRole.ADMIN.value in roles
        and isinstance(user_id, str)
        and bool(user_id.strip())
        and isinstance(request_id, str)
        and bool(request_id.strip())
        and isinstance(token_id, str)
        and bool(token_id.strip())
    )
    if not valid:
        actual_role = (
            ",".join(str(role) for role in roles)
            if isinstance(roles, list) and roles
            else "missing"
        )
        raise InsufficientMaintenanceRoleError(
            required_role=MaintenanceRole.ADMIN.value,
            actual_role=actual_role,
            request_id=(
                request_id
                if isinstance(request_id, str) and request_id
                else f"import-task:{task.id}"
            ),
        )
    return ActorContext(
        user_id=user_id,
        tenant_id=task.tenant_id,
        role=MaintenanceRole.ADMIN,
        request_id=request_id,
        token_id=token_id,
    )


def has_valid_execution_principal(
    task: MasterDataImportTask,
) -> bool:
    try:
        execution_actor_from_task(task)
    except InsufficientMaintenanceRoleError:
        return False
    return True
