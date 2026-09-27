from alembic import context
from sqlalchemy import create_engine
from delta_contracts.config import Settings
from delta_core.db import Base
from delta_core.devices.models import Device
from delta_core.activity.models import ActivityEvent
from delta_core.workspaces.models import Workspace,WorkspaceDeviceBinding
from delta_core.assistant.models import Interaction
from delta_core.iot.models import VirtualIoTState

config = context.config
settings = Settings()
if context.is_offline_mode():
    context.configure(url=settings.database_url, target_metadata=Base.metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = create_engine(settings.database_url)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=Base.metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()
