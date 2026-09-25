from sqlalchemy import select, func
from sqlalchemy.orm import Session
from delta_contracts.devices import CommandRequest
from delta_contracts.errors import DeltaError
from delta_contracts.storage import serialize
from delta_contracts.workspaces import LaunchInput
from delta_core.devices.models import Device
from delta_core.activity.models import record_event
from .models import Workspace, WorkspaceDeviceBinding


def get_workspace(session, workspace_id):
    workspace=session.get(Workspace,str(workspace_id))
    if workspace is None:
        raise DeltaError('WORKSPACE_NOT_FOUND','Workspace not found',404)
    return workspace


class WorkspaceService:
    def __init__(self,engine,devices):
        self.engine=engine
        self.devices=devices

    async def launch(self, arguments: LaunchInput):
        with Session(self.engine) as session:
            if arguments.workspace_id:
                workspace=get_workspace(session,arguments.workspace_id)
            elif arguments.workspace_name:
                workspace=session.scalar(select(Workspace).where(func.lower(Workspace.name)==arguments.workspace_name.lower()))
                if not workspace:
                    raise DeltaError('WORKSPACE_NOT_FOUND','Workspace not found',404)
            else:
                raise DeltaError('TOOL_VALIDATION_ERROR','Specify a workspace',422)
            if arguments.device_id:
                device=session.get(Device,str(arguments.device_id))
            elif arguments.device_name:
                matches=list(session.scalars(select(Device).where(func.lower(Device.display_name)==arguments.device_name.lower())))
                if len(matches)>1:
                    raise DeltaError('DEVICE_AMBIGUOUS','Several devices match; select a device',409)
                device=matches[0] if matches else None
            else:
                raise DeltaError('DEVICE_CONTEXT_REQUIRED','Select the current or target device',422)
            if device is None:
                raise DeltaError('DEVICE_NOT_FOUND','Device not found',404)
            if device.status!='online':
                raise DeltaError('DEVICE_OFFLINE','Target device is offline',409)
            binding=session.scalar(select(WorkspaceDeviceBinding).where(
                WorkspaceDeviceBinding.workspace_id==workspace.id,WorkspaceDeviceBinding.device_id==device.id))
            if not binding:
                raise DeltaError('WORKSPACE_BINDING_NOT_FOUND','Configure this workspace for the target device first',404)
            commands=[CommandRequest(action='open_app',payload={'app_id':app}) for app in binding.apps]
            if binding.local_path:
                commands.append(CommandRequest(action='open_path',payload={'path':binding.local_path}))
            commands.extend(CommandRequest(action='open_url',payload={'url':url}) for url in binding.urls)
            if any(command.action not in device.capabilities for command in commands):
                raise DeltaError('CAPABILITY_NOT_SUPPORTED','Device lacks a required workspace capability',400)
            device_id,workspace_id,name=device.id,workspace.id,workspace.name
        results=[]
        for command in commands:
            try:
                result=await self.devices.dispatch(device_id,command)
            except DeltaError as error:
                result={'success':False,'error_code':error.code,'message':error.message}
            results.append({'action':command.action,**result})
        success=bool(results) and all(result['success'] for result in results)
        result={'success':success,'workspace_id':workspace_id,'device_id':device_id,'results':results,
                'message':f'{name}: workspace launched' if success else f'{name}: launch incomplete'}
        with Session(self.engine) as session:
            record_event(session,'WORKSPACE_LAUNCHED' if success else 'WORKSPACE_LAUNCH_FAILED',result['message'],
                         workspace_id=workspace_id,device_id=device_id,details=result)
            session.commit()
        return result
