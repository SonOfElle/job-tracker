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


def check_schema() -> None:
    """Refuse to start if the DB schema isn't managed by Alembic or is out of date.

    The API does not create tables. Migrations own the schema; this only verifies
    that `alembic upgrade head` has been run against the current codebase.
    """
    from pathlib import Path

    from alembic.config import Config
    from alembic.runtime.migration import MigrationContext
    from alembic.script import ScriptDirectory

    migrations_dir = Path(__file__).resolve().parents[1] / "migrations"
    if not migrations_dir.is_dir():
        raise RuntimeError(
            f"Migrations directory not found at {migrations_dir}. "
            "The API image must include the alembic migrations."
        )

    cfg = Config()
    cfg.set_main_option("script_location", str(migrations_dir))
    expected_head = ScriptDirectory.from_config(cfg).get_current_head()

    with engine.connect() as conn:
        current_rev = MigrationContext.configure(conn).get_current_revision()

    if current_rev is None:
        raise RuntimeError(
            "Database has no schema (alembic_version is empty). "
            "Run `alembic upgrade head` first."
        )
    if current_rev != expected_head:
        raise RuntimeError(
            f"Database is at revision {current_rev}, but the code expects {expected_head}. "
            "Run `alembic upgrade head` to bring the DB up to date."
        )


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session