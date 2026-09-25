from sqlalchemy import select
from sqlalchemy.orm import Session
from delta_contracts.devices import EmptyPayload
from delta_contracts.storage import serialize
from delta_contracts.workspaces import LaunchInput
from delta_core.devices.models import Device
from delta_core.workspaces.models import Workspace
from .registry import LocalTool


def register_builtins(app):
    async def devices(arguments):
        with Session(app.state.engine) as session:
            return [serialize(d) for d in session.scalars(select(Device))]
    async def services(arguments):
        return [s.public() for s in app.state.services.services.values()]
    async def workspaces(arguments):
        with Session(app.state.engine) as session:
            return [serialize(w) for w in session.scalars(select(Workspace))]
    for name,description,handler in [
        ('devices.list','List registered devices and online status',devices),
        ('services.list','List registered independent services',services),
        ('workspaces.list','List workspaces',workspaces),
    ]:
        app.state.tools.register(LocalTool(name,description,EmptyPayload,handler,['read']))
    app.state.tools.register(LocalTool('workspaces.launch','Launch a workspace on a target device; use current device context when requested',LaunchInput,app.state.workspaces.launch,['device:open']))
