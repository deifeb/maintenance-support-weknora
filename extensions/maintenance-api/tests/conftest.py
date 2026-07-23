import os
import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


_TEST_TEMP_DIR = tempfile.TemporaryDirectory(
    prefix="maintenance_api_tests_"
)
_TEST_DATABASE_PATH = Path(_TEST_TEMP_DIR.name) / "test.db"

os.environ["DATABASE_URL"] = (
    f"sqlite:///{_TEST_DATABASE_PATH.as_posix()}"
)
os.environ["DATABASE_ECHO"] = "false"


@pytest.fixture()
def client() -> Generator[TestClient, None, None]:
    from app.main import create_app

    with TestClient(create_app()) as test_client:
        yield test_client


@pytest.fixture(scope="session", autouse=True)
def cleanup_test_database() -> Generator[None, None, None]:
    yield

    from app.db.session import engine

    engine.dispose()
    _TEST_TEMP_DIR.cleanup()
