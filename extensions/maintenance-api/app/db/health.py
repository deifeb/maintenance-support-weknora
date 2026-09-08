from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.db.session import engine


@dataclass(frozen=True)
class DatabaseHealth:
    status: str
    error: str | None = None


def check_database_health() -> DatabaseHealth:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return DatabaseHealth(status="healthy")
    except SQLAlchemyError:
        return DatabaseHealth(status="unhealthy", error="Database connection failed")
