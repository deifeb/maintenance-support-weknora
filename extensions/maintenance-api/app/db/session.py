from collections.abc import Generator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


def build_engine(database_url: str, echo: bool = False) -> Engine:
    kwargs: dict[str, object] = {"echo": echo, "pool_pre_ping": True}
    if database_url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    return create_engine(database_url, **kwargs)


settings = get_settings()
engine: Engine = build_engine(settings.database_url, settings.database_echo)
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
