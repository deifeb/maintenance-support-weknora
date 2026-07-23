from pydantic import BaseModel


class HealthData(BaseModel):
    status: str
    service: str
    version: str
    database: str


class SystemInfoData(BaseModel):
    service: str
    version: str
    environment: str
    api_prefix: str
    python_version: str
    database_type: str
