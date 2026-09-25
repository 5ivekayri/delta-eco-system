from datetime import datetime

from sqlalchemy import JSON, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from delta_contracts.storage import Record
from delta_core.db import Base


class Device(Record, Base):
    __tablename__ = "devices"
    device_uid: Mapped[str] = mapped_column(String(128), unique=True)
    display_name: Mapped[str] = mapped_column(String(255))
    hostname: Mapped[str] = mapped_column(String(255))
    os: Mapped[str] = mapped_column(String(16))
    architecture: Mapped[str] = mapped_column(String(64))
    username: Mapped[str] = mapped_column(String(255))
    agent_version: Mapped[str] = mapped_column(String(32))
    capabilities: Mapped[list] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(16), default="offline")
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True))
