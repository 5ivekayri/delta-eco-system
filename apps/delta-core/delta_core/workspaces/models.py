from sqlalchemy import String, Text, JSON, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from delta_contracts.storage import Record
from delta_core.db import Base


class Workspace(Record, Base):
    __tablename__='workspaces'
    name: Mapped[str] = mapped_column(String(200), unique=True)
    description: Mapped[str] = mapped_column(Text, default='')
    storage_mode: Mapped[str] = mapped_column(String(16), default='cloud', server_default='cloud')
    work_type: Mapped[str] = mapped_column(String(16), default='general', server_default='general')
    storage_device_id: Mapped[str | None] = mapped_column(String(36), nullable=True)


class WorkspaceDeviceBinding(Record, Base):
    __tablename__='workspace_bindings'
    __table_args__=(UniqueConstraint('workspace_id','device_id'),)
    workspace_id: Mapped[str] = mapped_column(ForeignKey('workspaces.id',ondelete='CASCADE'))
    device_id: Mapped[str] = mapped_column(ForeignKey('devices.id',ondelete='CASCADE'))
    local_path: Mapped[str] = mapped_column(Text, default='')
    apps: Mapped[list] = mapped_column(JSON, default=list)
    urls: Mapped[list] = mapped_column(JSON, default=list)
