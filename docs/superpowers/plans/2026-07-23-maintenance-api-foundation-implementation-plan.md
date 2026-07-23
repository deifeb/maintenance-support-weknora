# Maintenance API Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python 3.11 FastAPI foundation service with configurable SQLite/SQLAlchemy access, unified responses, health endpoints, exception handling, tests, and local run documentation.

**Architecture:** Use a layered modular monolith under `extensions/maintenance-api`. HTTP endpoints call focused core and DB helpers; no route performs raw SQL directly. Database configuration is environment-driven so SQLite can later be replaced by PostgreSQL.

**Tech Stack:** Python 3.11, FastAPI, Uvicorn, Pydantic Settings, SQLAlchemy 2.x synchronous API, SQLite, pytest, HTTPX, Ruff.

## Global Constraints

- Python version is exactly 3.11 for development and tests.
- Dependency management uses `venv + pip + requirements.txt`.
- SQLAlchemy uses synchronous sessions in this phase.
- `DATABASE_URL` is environment configurable and defaults to `sqlite:///./data/maintenance.db`.
- Route modules must not execute SQL directly.
- Do not modify WeKnora core code.
- Do not commit `.env`, `.venv`, SQLite database files, credentials, or enterprise data.
- All public API errors use a controlled JSON structure.
- This phase does not create domain business tables or Alembic migrations.

---

## File Map

```text
extensions/maintenance-api/
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── api/
│   │   ├── __init__.py
│   │   └── v1/
│   │       ├── __init__.py
│   │       ├── router.py
│   │       └── endpoints/
│   │           ├── __init__.py
│   │           ├── health.py
│   │           └── system.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py
│   │   ├── exceptions.py
│   │   └── responses.py
│   ├── db/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── health.py
│   │   └── session.py
│   ├── repositories/
│   │   └── __init__.py
│   ├── services/
│   │   └── __init__.py
│   └── schemas/
│       ├── __init__.py
│       ├── common.py
│       └── system.py
├── tests/
│   ├── conftest.py
│   ├── test_health.py
│   └── test_system.py
├── data/
│   └── .gitkeep
├── .env.example
├── pyproject.toml
├── requirements.txt
├── requirements-dev.txt
└── README.md
```

---

### Task 1: Configuration and Common Response Models

**Files:**
- Create: `extensions/maintenance-api/app/core/config.py`
- Create: `extensions/maintenance-api/app/schemas/common.py`
- Create: `extensions/maintenance-api/app/core/responses.py`
- Test: `extensions/maintenance-api/tests/test_system.py`

**Interfaces:**
- Produces: `Settings`, `get_settings()`, `SuccessResponse[T]`, `ErrorResponse`, `success_response()`.
- Consumes: environment variables from `.env` or process environment.

- [ ] **Step 1: Write the failing configuration test**

Create `tests/test_system.py` initially with:

```python
from app.core.config import get_settings


def test_settings_have_expected_defaults() -> None:
    settings = get_settings()

    assert settings.app_name == "Maintenance Support API"
    assert settings.app_version == "0.1.0"
    assert settings.api_v1_prefix == "/api/v1"
    assert settings.database_url.startswith("sqlite")
```

- [ ] **Step 2: Run the test and verify failure**

```powershell
cd E:\weknora_projects\maintenance-support-weknora\extensions\maintenance-api
pytest tests\test_system.py::test_settings_have_expected_defaults -v
```

Expected: collection/import failure because `app.core.config` does not exist.

- [ ] **Step 3: Implement configuration**

Create `app/core/config.py`:

```python
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


SERVICE_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATABASE_PATH = (SERVICE_ROOT / "data" / "maintenance.db").as_posix()


class Settings(BaseSettings):
    app_name: str = "Maintenance Support API"
    app_version: str = "0.1.0"
    app_env: str = "development"
    app_debug: bool = True
    api_v1_prefix: str = "/api/v1"
    database_url: str = Field(
        default=f"sqlite:///{DEFAULT_DATABASE_PATH}",
        description="SQLAlchemy database URL",
    )
    database_echo: bool = False

    model_config = SettingsConfigDict(
        env_file=SERVICE_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 4: Implement response schemas**

Create `app/schemas/common.py`:

```python
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field


T = TypeVar("T")


class SuccessResponse(BaseModel, Generic[T]):
    success: bool = True
    data: T
    message: str = ""


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: Any | None = None


class ErrorResponse(BaseModel):
    success: bool = False
    error: ErrorDetail = Field(...)
```

Create `app/core/responses.py`:

```python
from typing import Any

from app.schemas.common import SuccessResponse


def success_response(data: Any, message: str = "") -> SuccessResponse[Any]:
    return SuccessResponse(data=data, message=message)
```

- [ ] **Step 5: Run the test and verify pass**

```powershell
pytest tests\test_system.py::test_settings_have_expected_defaults -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add extensions\maintenance-api\app\core extensions\maintenance-api\app\schemas extensions\maintenance-api\tests\test_system.py
git commit -m "feat: add maintenance API configuration and responses"
```

---

### Task 2: SQLAlchemy Engine, Session, and Database Health

**Files:**
- Create: `extensions/maintenance-api/app/db/base.py`
- Create: `extensions/maintenance-api/app/db/session.py`
- Create: `extensions/maintenance-api/app/db/health.py`
- Test: `extensions/maintenance-api/tests/test_health.py`
- Test support: `extensions/maintenance-api/tests/conftest.py`

**Interfaces:**
- Produces: `Base`, `engine`, `SessionLocal`, `get_db_session()`, `check_database_health()`.
- Consumes: `get_settings().database_url` and `database_echo`.

- [ ] **Step 1: Write the failing DB health test**

Create `tests/test_health.py`:

```python
from app.db.health import check_database_health


def test_database_health_is_healthy() -> None:
    result = check_database_health()

    assert result.status == "healthy"
    assert result.error is None
```

Create `tests/conftest.py`:

```python
import os
from pathlib import Path

import pytest


@pytest.fixture(scope="session", autouse=True)
def configure_test_database(tmp_path_factory: pytest.TempPathFactory) -> None:
    test_dir: Path = tmp_path_factory.mktemp("maintenance_api")
    os.environ["DATABASE_URL"] = f"sqlite:///{(test_dir / 'test.db').as_posix()}"
```

- [ ] **Step 2: Run and verify failure**

```powershell
pytest tests\test_health.py::test_database_health_is_healthy -v
```

Expected: import failure because DB health module is missing.

- [ ] **Step 3: Implement SQLAlchemy base**

Create `app/db/base.py`:

```python
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
```

- [ ] **Step 4: Implement engine and session factory**

Create `app/db/session.py`:

```python
from collections.abc import Generator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


def _engine_kwargs(database_url: str) -> dict[str, object]:
    kwargs: dict[str, object] = {
        "echo": get_settings().database_echo,
        "pool_pre_ping": True,
    }
    if database_url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    return kwargs


settings = get_settings()
engine: Engine = create_engine(
    settings.database_url,
    **_engine_kwargs(settings.database_url),
)
SessionLocal = sessionmaker(
    bind=engine,
    class_=Session,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


def get_db_session() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
```

- [ ] **Step 5: Implement DB health result and query**

Create `app/db/health.py`:

```python
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
        return DatabaseHealth(
            status="unhealthy",
            error="Database connection failed",
        )
```

- [ ] **Step 6: Run and verify pass**

```powershell
pytest tests\test_health.py::test_database_health_is_healthy -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add extensions\maintenance-api\app\db extensions\maintenance-api\tests
git commit -m "feat: add SQLAlchemy connection and health check"
```

---

### Task 3: Application Exceptions and Handlers

**Files:**
- Create: `extensions/maintenance-api/app/core/exceptions.py`
- Modify later: `extensions/maintenance-api/app/main.py`
- Test: `extensions/maintenance-api/tests/test_health.py`

**Interfaces:**
- Produces: `AppException`, `DatabaseUnavailableError`, `register_exception_handlers(app)`.
- Consumes: FastAPI application instance.

- [ ] **Step 1: Add a failing exception response test**

Append to `tests/test_health.py` after the client fixture exists in Task 5:

```python
def test_database_failure_uses_controlled_error(monkeypatch, client) -> None:
    from app.api.v1.endpoints import health
    from app.db.health import DatabaseHealth

    monkeypatch.setattr(
        health,
        "check_database_health",
        lambda: DatabaseHealth(
            status="unhealthy",
            error="Database connection failed",
        ),
    )

    response = client.get("/health")

    assert response.status_code == 503
    assert response.json() == {
        "success": False,
        "error": {
            "code": "DATABASE_UNAVAILABLE",
            "message": "Database connection failed",
            "details": None,
        },
    }
```

- [ ] **Step 2: Implement exceptions**

Create `app/core/exceptions.py`:

```python
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class AppException(Exception):
    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        message: str,
        details: Any | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details


class DatabaseUnavailableError(AppException):
    def __init__(self) -> None:
        super().__init__(
            status_code=503,
            code="DATABASE_UNAVAILABLE",
            message="Database connection failed",
        )


def _error_body(
    *,
    code: str,
    message: str,
    details: Any | None = None,
) -> dict[str, Any]:
    return {
        "success": False,
        "error": {
            "code": code,
            "message": message,
            "details": details,
        },
    }


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppException)
    async def handle_app_exception(
        request: Request,
        exc: AppException,
    ) -> JSONResponse:
        del request
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_body(
                code=exc.code,
                message=exc.message,
                details=exc.details,
            ),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        del request
        return JSONResponse(
            status_code=422,
            content=_error_body(
                code="VALIDATION_ERROR",
                message="Request validation failed",
                details=exc.errors(),
            ),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        del request, exc
        return JSONResponse(
            status_code=500,
            content=_error_body(
                code="INTERNAL_SERVER_ERROR",
                message="An unexpected error occurred",
            ),
        )
```

- [ ] **Step 3: Do not run yet**

The behavior test depends on the application and endpoint implemented in Tasks 4 and 5.

- [ ] **Step 4: Commit**

```powershell
git add extensions\maintenance-api\app\core\exceptions.py extensions\maintenance-api\tests\test_health.py
git commit -m "feat: add maintenance API exception handling"
```

---

### Task 4: API Schemas and Endpoints

**Files:**
- Create: `extensions/maintenance-api/app/schemas/system.py`
- Create: `extensions/maintenance-api/app/api/v1/endpoints/health.py`
- Create: `extensions/maintenance-api/app/api/v1/endpoints/system.py`
- Create: `extensions/maintenance-api/app/api/v1/router.py`
- Test: `extensions/maintenance-api/tests/test_health.py`
- Test: `extensions/maintenance-api/tests/test_system.py`

**Interfaces:**
- Produces: `api_router`, `/health`, `/api/v1/system/info`.
- Consumes: settings, DB health function, unified response helper.

- [ ] **Step 1: Define endpoint output schemas**

Create `app/schemas/system.py`:

```python
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
```

- [ ] **Step 2: Implement health endpoint**

Create `app/api/v1/endpoints/health.py`:

```python
from fastapi import APIRouter

from app.core.config import get_settings
from app.core.exceptions import DatabaseUnavailableError
from app.core.responses import success_response
from app.db.health import check_database_health
from app.schemas.common import SuccessResponse
from app.schemas.system import HealthData


router = APIRouter(tags=["health"])


@router.get(
    "/health",
    response_model=SuccessResponse[HealthData],
)
def health_check() -> SuccessResponse[HealthData]:
    settings = get_settings()
    database_health = check_database_health()

    if database_health.status != "healthy":
        raise DatabaseUnavailableError()

    return success_response(
        HealthData(
            status="ok",
            service="maintenance-api",
            version=settings.app_version,
            database=database_health.status,
        ),
        message="Service is healthy",
    )
```

- [ ] **Step 3: Implement system info endpoint**

Create `app/api/v1/endpoints/system.py`:

```python
import platform
from urllib.parse import urlparse

from fastapi import APIRouter

from app.core.config import get_settings
from app.core.responses import success_response
from app.schemas.common import SuccessResponse
from app.schemas.system import SystemInfoData


router = APIRouter(prefix="/system", tags=["system"])


def _database_type(database_url: str) -> str:
    scheme = urlparse(database_url).scheme
    return scheme.split("+", maxsplit=1)[0] or "unknown"


@router.get(
    "/info",
    response_model=SuccessResponse[SystemInfoData],
)
def system_info() -> SuccessResponse[SystemInfoData]:
    settings = get_settings()

    return success_response(
        SystemInfoData(
            service="maintenance-api",
            version=settings.app_version,
            environment=settings.app_env,
            api_prefix=settings.api_v1_prefix,
            python_version=platform.python_version(),
            database_type=_database_type(settings.database_url),
        ),
        message="System information retrieved",
    )
```

- [ ] **Step 4: Compose the v1 router**

Create `app/api/v1/router.py`:

```python
from fastapi import APIRouter

from app.api.v1.endpoints import system


api_router = APIRouter()
api_router.include_router(system.router)
```

The health route is intentionally mounted at application root, not under `/api/v1`.

- [ ] **Step 5: Commit**

```powershell
git add extensions\maintenance-api\app\api extensions\maintenance-api\app\schemas
git commit -m "feat: add maintenance health and system endpoints"
```

---

### Task 5: FastAPI Application Factory and API Tests

**Files:**
- Create: `extensions/maintenance-api/app/main.py`
- Modify: `extensions/maintenance-api/tests/conftest.py`
- Modify: `extensions/maintenance-api/tests/test_health.py`
- Modify: `extensions/maintenance-api/tests/test_system.py`

**Interfaces:**
- Produces: `create_app() -> FastAPI`, module-level `app`.
- Consumes: `api_router`, health router, settings, exception registration.

- [ ] **Step 1: Add TestClient fixture**

Replace `tests/conftest.py` with:

```python
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="session", autouse=True)
def configure_test_database(tmp_path_factory: pytest.TempPathFactory) -> None:
    test_dir: Path = tmp_path_factory.mktemp("maintenance_api")
    os.environ["DATABASE_URL"] = f"sqlite:///{(test_dir / 'test.db').as_posix()}"


@pytest.fixture()
def client() -> TestClient:
    from app.main import create_app

    with TestClient(create_app()) as test_client:
        yield test_client
```

- [ ] **Step 2: Replace health tests with HTTP behavior tests**

Set `tests/test_health.py` to:

```python
def test_health_endpoint_returns_database_status(client) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["status"] == "ok"
    assert body["data"]["service"] == "maintenance-api"
    assert body["data"]["database"] == "healthy"
    assert body["message"] == "Service is healthy"


def test_database_failure_uses_controlled_error(monkeypatch, client) -> None:
    from app.api.v1.endpoints import health
    from app.db.health import DatabaseHealth

    monkeypatch.setattr(
        health,
        "check_database_health",
        lambda: DatabaseHealth(
            status="unhealthy",
            error="Database connection failed",
        ),
    )

    response = client.get("/health")

    assert response.status_code == 503
    assert response.json() == {
        "success": False,
        "error": {
            "code": "DATABASE_UNAVAILABLE",
            "message": "Database connection failed",
            "details": None,
        },
    }
```

- [ ] **Step 3: Replace system tests**

Set `tests/test_system.py` to:

```python
from app.core.config import get_settings


def test_settings_have_expected_defaults() -> None:
    settings = get_settings()

    assert settings.app_name == "Maintenance Support API"
    assert settings.app_version == "0.1.0"
    assert settings.api_v1_prefix == "/api/v1"
    assert settings.database_url.startswith("sqlite")


def test_root_endpoint(client) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "data": {
            "service": "maintenance-api",
            "docs": "/docs",
        },
        "message": "Maintenance Support API is running",
    }


def test_system_info_does_not_expose_database_url(client) -> None:
    response = client.get("/api/v1/system/info")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["service"] == "maintenance-api"
    assert body["data"]["version"] == "0.1.0"
    assert body["data"]["database_type"] == "sqlite"
    assert "database_url" not in body["data"]
    assert "password" not in body["data"]
```

- [ ] **Step 4: Run tests and verify failure**

```powershell
pytest -v
```

Expected: tests fail because `app.main` does not exist.

- [ ] **Step 5: Implement FastAPI application**

Create `app/main.py`:

```python
from fastapi import FastAPI

from app.api.v1.endpoints.health import router as health_router
from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.responses import success_response


def create_app() -> FastAPI:
    settings = get_settings()

    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        debug=settings.app_debug,
    )

    register_exception_handlers(application)
    application.include_router(health_router)
    application.include_router(
        api_router,
        prefix=settings.api_v1_prefix,
    )

    @application.get("/")
    def root():
        return success_response(
            {
                "service": "maintenance-api",
                "docs": "/docs",
            },
            message="Maintenance Support API is running",
        )

    return application


app = create_app()
```

- [ ] **Step 6: Run full tests**

```powershell
pytest -v
```

Expected: all tests PASS.

- [ ] **Step 7: Run Ruff**

```powershell
ruff check app tests
```

Expected: no lint errors.

- [ ] **Step 8: Commit**

```powershell
git add extensions\maintenance-api
git commit -m "feat: complete maintenance API foundation"
```

---

### Task 6: Dependency Pinning, Ignore Rules, and Documentation

**Files:**
- Modify: `extensions/maintenance-api/requirements.txt`
- Modify: `extensions/maintenance-api/requirements-dev.txt`
- Modify: `extensions/maintenance-api/pyproject.toml`
- Modify: `extensions/maintenance-api/.env.example`
- Modify: `extensions/maintenance-api/README.md`
- Modify: repository root `.gitignore`

**Interfaces:**
- Produces: reproducible local installation and documented run commands.
- Consumes: files implemented in Tasks 1–5.

- [ ] **Step 1: Pin runtime dependencies**

Set `requirements.txt`:

```text
fastapi>=0.115,<1.0
uvicorn[standard]>=0.34,<1.0
pydantic>=2.10,<3.0
pydantic-settings>=2.7,<3.0
sqlalchemy>=2.0,<3.0
```

Set `requirements-dev.txt`:

```text
-r requirements.txt

httpx>=0.28,<1.0
pytest>=8.3,<9.0
ruff>=0.9,<1.0
```

- [ ] **Step 2: Configure pytest and Ruff**

Set `pyproject.toml`:

```toml
[project]
name = "maintenance-api"
version = "0.1.0"
description = "Maintenance support business API"
requires-python = ">=3.11,<3.12"

[tool.pytest.ini_options]
pythonpath = ["."]
testpaths = ["tests"]
addopts = "-ra"

[tool.ruff]
target-version = "py311"
line-length = 100
src = ["app", "tests"]

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]
```

- [ ] **Step 3: Set environment example**

Set `.env.example`:

```dotenv
APP_NAME=Maintenance Support API
APP_VERSION=0.1.0
APP_ENV=development
APP_DEBUG=true
API_V1_PREFIX=/api/v1
DATABASE_URL=sqlite:///./data/maintenance.db
DATABASE_ECHO=false
```

- [ ] **Step 4: Extend root ignore rules**

Append to the repository root `.gitignore`:

```gitignore

# Maintenance Python extensions
extensions/**/.venv/
extensions/**/.env
extensions/**/.pytest_cache/
extensions/**/.ruff_cache/
extensions/**/data/*.db
extensions/**/data/*.db-shm
extensions/**/data/*.db-wal
```

Do not remove existing root ignore rules.

- [ ] **Step 5: Write service README**

Set `extensions/maintenance-api/README.md`:

```markdown
# Maintenance Support API

维修器材需求管理系统的独立 Python 业务服务。当前版本提供配置读取、SQLite/SQLAlchemy 连接、健康检查、系统信息、统一响应和异常处理。

## Requirements

- Python 3.11
- Windows PowerShell
- Git

## Create Environment

```powershell
cd E:\weknora_projects\maintenance-support-weknora\extensions\maintenance-api
py -3.11 -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
Copy-Item .env.example .env
```

## Run

```powershell
uvicorn app.main:app --reload --host 127.0.0.1 --port 8100
```

## Verify

- `http://127.0.0.1:8100/`
- `http://127.0.0.1:8100/health`
- `http://127.0.0.1:8100/api/v1/system/info`
- `http://127.0.0.1:8100/docs`

## Test

```powershell
pytest -v
ruff check app tests
```

## Database

The default database is:

```text
data/maintenance.db
```

Override it with `DATABASE_URL` in `.env`. SQLite database files are ignored by Git.
```

- [ ] **Step 6: Recreate environment and verify install**

```powershell
python --version
pip install -r requirements-dev.txt
pytest -v
ruff check app tests
```

Expected:
- Python reports `3.11.x`.
- All tests pass.
- Ruff reports no errors.

- [ ] **Step 7: Inspect Git changes**

```powershell
git status
git diff --check
```

Expected:
- Only intended maintenance API and ignore/documentation files are changed.
- `git diff --check` prints no errors.
- `.env`, `.venv`, and `*.db` do not appear.

- [ ] **Step 8: Commit and push**

```powershell
git add .gitignore extensions\maintenance-api
git commit -m "feat: establish maintenance API foundation"
git push
```

---

## Final Verification

Run from `extensions/maintenance-api`:

```powershell
python --version
pytest -v
ruff check app tests
uvicorn app.main:app --host 127.0.0.1 --port 8100
```

In another PowerShell window:

```powershell
Invoke-RestMethod http://127.0.0.1:8100/health
Invoke-RestMethod http://127.0.0.1:8100/api/v1/system/info
```

Expected:
- Python is 3.11.x.
- Tests all pass.
- Ruff reports no errors.
- Health returns `status=ok` and `database=healthy`.
- System info exposes only non-sensitive information.
