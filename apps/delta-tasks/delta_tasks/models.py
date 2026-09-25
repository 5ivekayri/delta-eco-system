from datetime import date, datetime
from sqlalchemy import String, Text, Date, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from delta_contracts.storage import Record
from .db import Base


class Task(Record, Base):
    __tablename__ = 'tasks'
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default='')
    workspace_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(24), default='todo', index=True)
    priority: Mapped[str] = mapped_column(String(16), default='medium')
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
