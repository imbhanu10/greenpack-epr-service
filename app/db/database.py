"""SQLite database configuration for the GreenPack EPR service."""

from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


DATABASE_PATH = Path(__file__).resolve().parents[2] / "greenpack_epr.db"
DATABASE_URL = f"sqlite:///{DATABASE_PATH.as_posix()}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Base class for SQLAlchemy ORM models."""


def initialize_database() -> None:
    """Create database tables for registered ORM models."""
    from app.db import crud  # noqa: F401

    Base.metadata.create_all(bind=engine)


def get_engine() -> Engine:
    """Return the configured SQLAlchemy engine."""
    return engine


def get_session() -> Generator[Session, None, None]:
    """Yield a database session and close it after use."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
