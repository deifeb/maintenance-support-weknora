from dataclasses import dataclass
from enum import StrEnum


class MaintenanceRole(StrEnum):
    VIEWER = "viewer"
    CONTRIBUTOR = "contributor"
    ADMIN = "admin"


@dataclass(frozen=True, slots=True)
class ActorContext:
    user_id: str
    tenant_id: str
    role: MaintenanceRole
    request_id: str
    token_id: str
