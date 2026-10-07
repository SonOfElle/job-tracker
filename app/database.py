"""Engine, session factory, schema bootstrap."""
from __future__ import annotations

import os
from typing import Generator

from sqlmodel import Session, SQLModel, create_engine


def _normalize_url(url: str) -> str:
    """Force the psycopg 3 driver so the plain `postgresql://` URL keeps working."""
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


DATABASE_URL = _normalize_url(
    os.getenv(
        "DATABASE_URL",
        "postgresql://tracker_user:change_me@localhost:5432/application_tracker",
    )
)

engine = create_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    pool_recycle=1800,
)


def init_db() -> None:
    from app import models  # noqa: F401  -- registers tables on the metadata
    SQLModel.metadata.create_all(engine)


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session