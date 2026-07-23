from pydantic import BaseModel


class HealthData(BaseModel):
    status: str
    service: str
    version: str
    database: str
