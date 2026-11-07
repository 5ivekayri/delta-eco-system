from sqlalchemy import String, Boolean, Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from delta_contracts.storage import Record
from delta_core.db import Base

class User(Record, Base):
    __tablename__='account_users'
    username:Mapped[str]=mapped_column(String(64),unique=True)
    password_hash:Mapped[str]=mapped_column(String(256))
    role:Mapped[str]=mapped_column(String(16),default='pending')
    active:Mapped[bool]=mapped_column(Boolean,default=True)

class LoginSession(Record, Base):
    __tablename__='account_sessions'
    digest:Mapped[str]=mapped_column(String(64),unique=True)
    user_id:Mapped[str]=mapped_column(ForeignKey('account_users.id'))
    kind:Mapped[str]=mapped_column(String(16))
    expires:Mapped[float]=mapped_column(Float)
