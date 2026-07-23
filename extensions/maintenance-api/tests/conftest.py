import os
import tempfile
from collections.abc import Generator
from pathlib import Path

_TEST_DIR = tempfile.TemporaryDirectory(prefix="maintenance_master_data_tests_")
_TEST_DB = Path(_TEST_DIR.name) / "test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB.as_posix()}"
os.environ["APP_VERSION"] = "0.2.0"
os.environ["DATABASE_ECHO"] = "false"

import app.models  # noqa: F401
import pytest
from app.db.base import Base
from app.db.session import SessionLocal, engine
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


@pytest.fixture(scope="session", autouse=True)
def database_schema() -> Generator[None, None, None]:
    Base.metadata.create_all(engine)
    yield
    engine.dispose()
    _TEST_DIR.cleanup()


@pytest.fixture(autouse=True)
def clean_database() -> Generator[None, None, None]:
    yield
    with engine.begin() as connection:
        for table in reversed(Base.metadata.sorted_tables):
            connection.execute(table.delete())


@pytest.fixture()
def session() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture()
def client() -> Generator[TestClient, None, None]:
    from app.main import create_app

    with TestClient(create_app()) as test_client:
        yield test_client
