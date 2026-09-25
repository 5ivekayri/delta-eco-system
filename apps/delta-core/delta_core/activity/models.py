from sqlalchemy import JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from delta_contracts.storage import Record
from delta_core.db import Base


class ActivityEvent(Record, Base):
    __tablename__ = "activity"
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    source: Mapped[str] = mapped_column(String(64), default="core")
    device_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    workspace_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    service_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    message: Mapped[str] = mapped_column(Text)
    details: Mapped[dict] = mapped_column("metadata", JSON, default=dict)


def record_event(session, event_type: str, message: str, **kwargs):
    event = ActivityEvent(event_type=event_type, message=message, **kwargs)
    session.add(event)
    return event
