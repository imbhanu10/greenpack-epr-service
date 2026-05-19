"""SQLite persistence operations for EPR declarations."""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import JSON, DateTime, String, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.db.database import Base
from app.schemas.declaration import DeclarationSubmitRequest


class DeclarationRecord(Base):
    """SQLAlchemy model for persisted EPR declaration submissions."""

    __tablename__ = "declarations"

    record_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    producer_id: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    month: Mapped[str] = mapped_column(String(7), index=True, nullable=False)
    declaration_data: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )


def create_declaration_record(
    session: Session,
    payload: DeclarationSubmitRequest,
) -> DeclarationRecord:
    """Persist a validated declaration submission."""
    Base.metadata.create_all(bind=session.get_bind())

    record = DeclarationRecord(
        record_id=str(uuid4()),
        producer_id=payload.producer_id,
        month=payload.month,
        declaration_data=payload.declaration_data.model_dump(mode="json"),
        created_at=datetime.now(UTC),
    )
    session.add(record)
    session.flush()
    session.refresh(record)
    return record


def get_declaration_record(
    session: Session,
    record_id: str,
) -> DeclarationRecord | None:
    """Fetch a declaration submission by record ID."""
    return session.get(DeclarationRecord, record_id)


def get_latest_declaration_record(
    session: Session,
    *,
    producer_id: str,
    month: str,
) -> DeclarationRecord | None:
    """Fetch the latest declaration submission for a producer and month."""
    statement = (
        select(DeclarationRecord)
        .where(DeclarationRecord.producer_id == producer_id)
        .where(DeclarationRecord.month == month)
        .order_by(DeclarationRecord.created_at.desc())
        .limit(1)
    )
    return session.scalars(statement).first()


def list_declaration_records(
    session: Session,
    *,
    producer_id: str | None = None,
    month: str | None = None,
) -> list[DeclarationRecord]:
    """List declaration submissions with optional producer and month filters."""
    statement = select(DeclarationRecord)

    if producer_id is not None:
        statement = statement.where(DeclarationRecord.producer_id == producer_id)

    if month is not None:
        statement = statement.where(DeclarationRecord.month == month)

    return list(session.scalars(statement).all())


def delete_declaration_record(session: Session, record_id: str) -> bool:
    """Stage deletion of a declaration submission by record ID."""
    record = session.get(DeclarationRecord, record_id)
    if record is None:
        return False

    session.delete(record)
    session.flush()
    return True
