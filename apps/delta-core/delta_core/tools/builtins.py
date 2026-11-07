from sqlalchemy import select
from sqlalchemy.orm import Session
from delta_contracts.devices import EmptyPayload, OpenApplication, ApplicationTarget
from delta_contracts.storage import serialize
from delta_contracts.workspaces import LaunchInput, WorkspaceCreateTool
from delta_core.devices.models import Device
from delta_core.workspaces.models import Workspace
from .registry import LocalTool


def register_builtins(app):
    from delta_core.devices.applications import ApplicationService
    applications = ApplicationService(app.state.devices)
    app.state.tools.register(LocalTool('devices.open_app',
        'Open an installed application by name on a target computer through its Agent. Use explicit device_name or selected device_id. Never use server paths. Agent enforces local permissions.',
        OpenApplication, applications.open_app, ['device:open']))
    app.state.tools.register(LocalTool('devices.list_apps',
        'List installed and permitted applications on connected target computers.',
        ApplicationTarget, applications.list_apps, ['read']))
    app.state.tools.register(LocalTool('devices.close_app',
        'Request normal application/window close on a target computer. Never force-kill. Unsaved documents may require user input.',
        OpenApplication, applications.close_app, ['device:open']))
    app.state.tools.register(LocalTool('devices.minimize_app',
        'Minimize or hide windows of an installed application on a target computer.',
        OpenApplication, applications.minimize_app, ['device:open']))
    async def describe_screen(target):
        from delta_core.devices.screen import describe_screen
        return await describe_screen(app, applications, target)
    app.state.tools.register(LocalTool('devices.describe_screen',
        'Describe the current screen on one target computer. Uses the saved Agent ask/allow/deny policy to capture and send one screenshot to OpenRouter. Use only when the user explicitly asks to inspect their screen.',
        ApplicationTarget, describe_screen, ['device:screen']))
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

    app.state.tools.register(LocalTool(
        'workspaces.create',
        'Create a workspace with name and description, optionally with a device binding (path, allowed apps, URLs). '
        'Does not launch apps or create folders. Ask for a missing name; never invent paths, URLs or device IDs. '
        'Creating without a binding needs no device.',
        WorkspaceCreateTool, app.state.workspaces.create, ['workspaces:write']))
