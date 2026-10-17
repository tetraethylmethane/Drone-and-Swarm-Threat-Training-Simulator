"""Database engine, session factory and declarative base."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from sqlalchemy import MetaData, create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

NAMING = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)


class Database:
    def __init__(self, url: str, **engine_kwargs: Any) -> None:
        # Synchronous routes run in Starlette's worker-thread pool (40 threads by default). The
        # connection pool matches it, so a request that has a thread never queues for a connection;
        # a 20-connection pool timed out under load (docs/testing/load-resilience-report.md, L-01).
        options: dict[str, Any] = {"pool_size": 20, "max_overflow": 20, **engine_kwargs}
        self.engine: Engine = create_engine(url, pool_pre_ping=True, future=True, **options)
        self.session_factory = sessionmaker(bind=self.engine, expire_on_commit=False, autoflush=False)

    def session(self) -> Iterator[Session]:
        db = self.session_factory()
        try:
            yield db
        finally:
            db.close()

    def dispose(self) -> None:
        self.engine.dispose()
