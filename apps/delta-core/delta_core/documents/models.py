from datetime import datetime
from sqlalchemy import ForeignKey, Integer, LargeBinary, String, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from delta_contracts.storage import Record, utcnow
from delta_core.db import Base


class DocumentRecord(Record, Base):
    __tablename__ = 'documents'
    owner_id: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(255))
    revision: Mapped[int] = mapped_column(Integer, default=1)


class DocumentVersion(Base):
    __tablename__ = 'document_versions'
    document_id: Mapped[str] = mapped_column(ForeignKey('documents.id', ondelete='CASCADE'), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, primary_key=True)
    content: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
