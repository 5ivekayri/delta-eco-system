from uuid import UUID
from urllib.parse import quote
from fastapi import APIRouter,Request,UploadFile,File,Form,Query
from fastapi.responses import Response
from pydantic import Field
from delta_contracts.devices import StrictModel
from delta_contracts.workspace_files import MAX_FILE
from delta_core.documents.router import owner
from .studio import FileSave,DocumentSave,SearchInput,ImportInput,ChatInput

router=APIRouter(prefix='/api/v1/workspaces/{workspace_id}/studio',tags=['workspace-studio'])

@router.get('/files')
async def files(workspace_id:UUID,request:Request):
    return await request.app.state.studio.operation(workspace_id,'list')

@router.get('/file')
async def read(workspace_id:UUID,request:Request,path:str=Query(max_length=512),version:str=''):
    return await request.app.state.studio.read(workspace_id,path,version)

@router.put('/file')
async def save(workspace_id:UUID,body:FileSave,request:Request):
    return await request.app.state.studio.save(workspace_id,body.path,body.text.encode(),body.expected_hash)

@router.put('/document')
async def edit_document(workspace_id:UUID,body:DocumentSave,request:Request):
    return await request.app.state.studio.edit_document(workspace_id,body)

@router.get('/history')
async def history(workspace_id:UUID,request:Request,path:str=Query(max_length=512)):
    return await request.app.state.studio.operation(workspace_id,'history',path)

@router.get('/download')
async def download(workspace_id:UUID,request:Request,path:str=Query(max_length=512),version:str=''):
    _,data=await request.app.state.studio.source(workspace_id,path,version)
    return Response(data,media_type='application/octet-stream',headers={
        'Content-Disposition':"attachment; filename*=UTF-8''"+quote(path.split('/')[-1],safe=''),
        'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'})

@router.post('/upload',status_code=201)
async def upload(workspace_id:UUID,request:Request,file:UploadFile=File(...),destination:str=Form(default='')):
    try:
        content=await file.read(MAX_FILE+1)
        return await request.app.state.studio.save(workspace_id,destination or file.filename or '',content)
    finally:await file.close()

@router.post('/search')
async def search(workspace_id:UUID,body:SearchInput,request:Request):
    request.app.state.studio.workspace(workspace_id)
    return await request.app.state.studio.search(body)

@router.post('/import')
async def import_file(workspace_id:UUID,body:ImportInput,request:Request):
    request.app.state.studio.workspace(workspace_id)
    return await request.app.state.studio.import_file(workspace_id,body)

class LibraryInput(StrictModel):
    document_id:UUID
    destination:str=Field(default='',max_length=512)

@router.post('/library')
async def from_library(workspace_id:UUID,body:LibraryInput,request:Request):
    row,data,_=request.app.state.documents.source(owner(request),str(body.document_id))
    return await request.app.state.studio.save(workspace_id,body.destination or row['name'],data)

@router.post('/chat')
async def chat(workspace_id:UUID,body:ChatInput,request:Request):
    return await request.app.state.studio.chat(workspace_id,body,request.app.state.assistant.provider)

@router.get('/preview')
async def preview(workspace_id:UUID,request:Request):
    service=request.app.state.studio
    listing=await service.operation(workspace_id,'list')
    assets={};size=0
    for file in listing['files']:
        if not file['path'].lower().endswith(('.html','.htm','.css','.js','.mjs','.svg')):continue
        size+=file['size']
        if size>2*1024*1024:
            from delta_contracts.errors import DeltaError
            raise DeltaError('PREVIEW_TOO_LARGE','Для превью допускается до 2 МБ исходников.',422)
        data=await service.read(workspace_id,file['path'])
        assets[file['path']]=data['text']
    return {'assets':assets}

class RestoreInput(StrictModel):
    path:str=Field(min_length=1,max_length=512)
    version:str=Field(pattern=r'^[a-f0-9]{64}$')
    expected_hash:str=Field(pattern=r'^[a-f0-9]{64}$')

@router.post('/restore')
async def restore(workspace_id:UUID,body:RestoreInput,request:Request):
    _,data=await request.app.state.studio.source(workspace_id,body.path,body.version)
    return await request.app.state.studio.save(workspace_id,body.path,data,body.expected_hash)

@router.post('/new-document',status_code=201)
async def new_document(workspace_id:UUID,body:FileSave,request:Request):
    return await request.app.state.studio.new_document(workspace_id,body.path,body.text)
