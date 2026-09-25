from uuid import UUID
from fastapi import APIRouter,Request
from sqlalchemy import select,delete,func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from delta_contracts.errors import DeltaError
from delta_contracts.storage import serialize
from delta_contracts.workspaces import WorkspaceCreate,WorkspaceUpdate,BindingInput,LaunchInput
from delta_core.devices.models import Device
from .models import Workspace,WorkspaceDeviceBinding
from .service import get_workspace

router=APIRouter(prefix='/api/v1/workspaces')


def unique_name(session,name,exclude=None):
    found=session.scalar(select(Workspace).where(func.lower(Workspace.name)==name.lower()))
    if found and found.id!=exclude:
        raise DeltaError('WORKSPACE_EXISTS','A workspace with this name already exists',409)


def commit(session):
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise DeltaError('CONFLICT','This workspace or binding already exists',409)


@router.get('')
def list_workspaces(request:Request):
    with Session(request.app.state.engine) as session:
        result=[]
        for workspace in session.scalars(select(Workspace).order_by(Workspace.name)):
            data=serialize(workspace)
            data['bindings']=[serialize(b) for b in session.scalars(select(WorkspaceDeviceBinding).where(WorkspaceDeviceBinding.workspace_id==workspace.id))]
            result.append(data)
        return result


@router.post('',status_code=201)
def create_workspace(body:WorkspaceCreate,request:Request):
    with Session(request.app.state.engine) as session:
        unique_name(session,body.name)
        workspace=Workspace(**body.model_dump())
        session.add(workspace);commit(session);session.refresh(workspace)
        return serialize(workspace)


@router.get('/{workspace_id}')
def read_workspace(workspace_id:UUID,request:Request):
    with Session(request.app.state.engine) as session:
        return serialize(get_workspace(session,workspace_id))


@router.patch('/{workspace_id}')
def update_workspace(workspace_id:UUID,body:WorkspaceUpdate,request:Request):
    with Session(request.app.state.engine) as session:
        workspace=get_workspace(session,workspace_id)
        if body.name:
            unique_name(session,body.name,workspace.id)
        for key,value in body.model_dump(exclude_unset=True).items():
            setattr(workspace,key,value)
        commit(session);session.refresh(workspace)
        return serialize(workspace)


@router.delete('/{workspace_id}')
def delete_workspace(workspace_id:UUID,request:Request):
    with Session(request.app.state.engine) as session:
        workspace=get_workspace(session,workspace_id)
        session.execute(delete(WorkspaceDeviceBinding).where(WorkspaceDeviceBinding.workspace_id==workspace.id))
        session.delete(workspace);commit(session)
    return {'success':True}


@router.get('/{workspace_id}/bindings')
def bindings(workspace_id:UUID,request:Request):
    with Session(request.app.state.engine) as session:
        get_workspace(session,workspace_id)
        return [serialize(b) for b in session.scalars(select(WorkspaceDeviceBinding).where(WorkspaceDeviceBinding.workspace_id==str(workspace_id)))]


@router.post('/{workspace_id}/bindings')
def bind(workspace_id:UUID,body:BindingInput,request:Request):
    with Session(request.app.state.engine) as session:
        get_workspace(session,workspace_id)
        if session.get(Device,str(body.device_id)) is None:
            raise DeltaError('DEVICE_NOT_FOUND','Device not found',404)
        binding=session.scalar(select(WorkspaceDeviceBinding).where(WorkspaceDeviceBinding.workspace_id==str(workspace_id),WorkspaceDeviceBinding.device_id==str(body.device_id)))
        if binding is None:
            binding=WorkspaceDeviceBinding(workspace_id=str(workspace_id),device_id=str(body.device_id))
            session.add(binding)
        for key,value in body.model_dump(mode='json').items():
            setattr(binding,key,value)
        commit(session);session.refresh(binding)
        return serialize(binding)


@router.post('/{workspace_id}/launch')
async def launch(workspace_id:UUID,body:LaunchInput,request:Request):
    return await request.app.state.workspaces.launch(body.model_copy(update={'workspace_id':workspace_id}))
