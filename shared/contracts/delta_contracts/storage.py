from datetime import date, datetime, timezone
from uuid import uuid4

from sqlalchemy import DateTime, String, inspect
from sqlalchemy.orm import Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Record:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


def serialize(record) -> dict:
    data = {column.key: getattr(record, column.key) for column in inspect(record).mapper.column_attrs}
    for key, value in data.items():
        if isinstance(value, datetime):
            data[key] = value.replace(tzinfo=value.tzinfo or timezone.utc).isoformat()
        elif isinstance(value, date):
            data[key] = value.isoformat()
    return data
