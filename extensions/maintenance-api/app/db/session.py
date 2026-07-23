from collections.abc import Generator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


def _build_engine_kwargs(
    database_url: str,
) -> dict[str, object]:
    settings = get_settings()

    kwargs: dict[str, object] = {
        "echo": settings.database_echo,
        "pool_pre_ping": True,
    }

    if database_url.startswith("sqlite"):
        kwargs["connect_args"] = {
            "check_same_thread": False,
        }

    return kwargs


settings = get_settings()

engine: Engine = create_engine(
    settings.database_url,
    **_build_engine_kwargs(settings.database_url),
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
