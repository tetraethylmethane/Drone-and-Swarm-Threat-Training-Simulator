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
        self.engine: Engine = create_engine(
            url,
            pool_pre_ping=True,
            pool_size=10,
            max_overflow=10,
            future=True,
            **engine_kwargs,
        )
        self.session_factory = sessionmaker(bind=self.engine, expire_on_commit=False, autoflush=False)

    def session(self) -> Iterator[Session]:
        db = self.session_factory()
        try:
            yield db
        finally:
            db.close()

    def dispose(self) -> None:
        self.engine.dispose()
