from datetime import datetime
from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, Integer
from sqlalchemy.orm import Mapped, mapped_column
from delta_contracts.storage import utcnow
from delta_core.db import Base


class VirtualIoTState(Base):
    __tablename__ = 'virtual_iot_state'
    __table_args__ = (CheckConstraint('id = 1', name='iot_singleton'),
                      CheckConstraint('brightness >= 0 AND brightness <= 100', name='iot_brightness_range'))
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    desk_light: Mapped[bool] = mapped_column(Boolean, default=False)
    temperature: Mapped[float] = mapped_column(Float, default=23.0)
    brightness: Mapped[int] = mapped_column(Integer, default=30)
    motion: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
