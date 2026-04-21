"""SQLAlchemy database setup — SQLite for local, PostgreSQL for cloud."""

from __future__ import annotations

import hashlib
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""
    pass


# Import all models so they register with Base.metadata
def _import_models() -> None:
    import contextsync.models.context_file  # noqa: F401
    import contextsync.models.relationship  # noqa: F401
    import contextsync.models.change_log  # noqa: F401
    import contextsync.models.entity  # noqa: F401


def get_db_path(repo_root: Path) -> Path:
    """Get the SQLite database path for a repo."""
    return repo_root / ".contextsync" / "contextsync.db"


def get_engine(repo_root: Path | None = None, url: str | None = None) -> Engine:
    """Create a SQLAlchemy engine.

    Args:
        repo_root: Path to repo root (uses SQLite). Mutually exclusive with url.
        url: Database URL (for PostgreSQL cloud). Mutually exclusive with repo_root.
    """
    if url:
        return create_engine(url, echo=False)

    if repo_root is None:
        raise ValueError("Either repo_root or url must be provided")

    db_path = get_db_path(repo_root)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{db_path}", echo=False)

    # Enable WAL mode for better concurrent read performance
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def get_session(engine: Engine) -> Session:
    """Create a new database session."""
    session_factory = sessionmaker(bind=engine)
    return session_factory()


def init_db(engine: Engine) -> None:
    """Create all tables."""
    _import_models()
    Base.metadata.create_all(engine)


def make_id(repo: str, path: str) -> str:
    """Generate a deterministic ID from repo + path."""
    return hashlib.sha256(f"{repo}:{path}".encode()).hexdigest()[:16]
