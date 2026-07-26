import os
import tempfile
import uuid
from collections.abc import Callable, Generator
from datetime import datetime, timedelta, timezone
from pathlib import Path

_TEST_DIR = tempfile.TemporaryDirectory(prefix="maintenance_master_data_tests_")
_TEST_DB = Path(_TEST_DIR.name) / "test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB.as_posix()}"
os.environ["APP_VERSION"] = "0.2.0"
os.environ["DATABASE_ECHO"] = "false"
os.environ["INTERNAL_JWT_SECRET"] = "unit-five-internal-jwt-secret-0001"
os.environ["INTERNAL_JWT_ISSUER"] = "weknora"
os.environ["INTERNAL_JWT_AUDIENCE"] = "maintenance-api"
os.environ["INTERNAL_JWT_MAX_LIFETIME_SECONDS"] = "180"
os.environ["INTERNAL_JWT_CLOCK_SKEW_SECONDS"] = "5"

import app.models  # noqa: F401
import jwt
import pytest
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.security.actor import ActorContext, MaintenanceRole
from app.security.dependencies import get_actor
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


@pytest.fixture()
def authenticated_client(
    actor_contributor: ActorContext,
) -> Generator[TestClient, None, None]:
    from app.main import create_app

    app = create_app()

    def override_actor() -> ActorContext:
        return actor_contributor

    app.dependency_overrides[get_actor] = override_actor
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


@pytest.fixture()
def actor_context() -> Callable[..., ActorContext]:
    def build(
        *,
        tenant_id: str = "tenant-a",
        user_id: str = "user-a",
        role: MaintenanceRole = MaintenanceRole.CONTRIBUTOR,
        request_id: str = "request-a",
        token_id: str = "token-a",
    ) -> ActorContext:
        return ActorContext(
            user_id=user_id,
            tenant_id=tenant_id,
            role=role,
            request_id=request_id,
            token_id=token_id,
        )

    return build


@pytest.fixture()
def internal_auth_headers() -> Callable[..., dict[str, str]]:
    def build(
        *,
        tenant_id: str = "tenant-a",
        user_id: str = "user-a",
        role: MaintenanceRole = MaintenanceRole.CONTRIBUTOR,
        request_id: str | None = None,
    ) -> dict[str, str]:
        now = datetime.now(timezone.utc)
        payload = {
            "sub": user_id,
            "tenant_id": tenant_id,
            "roles": [role.value],
            "aud": ["maintenance-api"],
            "iss": "weknora",
            "iat": int(now.timestamp()),
            "exp": int(
                (
                    now
                    + timedelta(seconds=180)
                ).timestamp()
            ),
            "jti": str(uuid.uuid4()),
            "request_id": (
                request_id
                or f"request-{uuid.uuid4()}"
            ),
        }
        token = jwt.encode(
            payload,
            os.environ[
                "INTERNAL_JWT_SECRET"
            ],
            algorithm="HS256",
        )
        return {
            "Authorization": f"Bearer {token}"
        }

    return build


@pytest.fixture()
def actor_viewer(actor_context: Callable[..., ActorContext]) -> ActorContext:
    return actor_context(role=MaintenanceRole.VIEWER)


@pytest.fixture()
def actor_contributor(
    actor_context: Callable[..., ActorContext],
) -> ActorContext:
    return actor_context(role=MaintenanceRole.CONTRIBUTOR)


@pytest.fixture()
def actor_admin(actor_context: Callable[..., ActorContext]) -> ActorContext:
    return actor_context(role=MaintenanceRole.ADMIN)
