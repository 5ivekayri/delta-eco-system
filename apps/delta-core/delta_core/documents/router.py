from uuid import UUID
from fastapi import APIRouter,Request,UploadFile,File,Query
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool
from urllib.parse import quote
from .schemas import SaveInput,AIInput,DocumentName,RenameInput,CopyInput
from .rich import RichSaveInput
from .ooxml import MAX_UPLOAD
from delta_contracts.errors import DeltaError

router=APIRouter(prefix='/api/v1/documents',tags=['documents'])


def owner(request):
    user=getattr(request.state,'user',None)
    if getattr(request.app.state,'account_authorizer',None) and not user:
        raise DeltaError('UNAUTHORIZED','Войдите в аккаунт.',401)
    return str(user['id']) if user else 'development'


@router.get('')
def listing(request:Request):return request.app.state.documents.listing(owner(request))


@router.post('',status_code=201)
async def upload(request:Request,file:UploadFile=File(...)):
    try:
        data=await file.read(MAX_UPLOAD+1)
        return await run_in_threadpool(request.app.state.documents.upload,owner(request),file.filename,data)
    finally:await file.close()


@router.post('/blank', status_code=201)
def blank(body:DocumentName,request:Request):
    from io import BytesIO
    from docx import Document
    from docx.shared import Mm
    name=body.name.strip()
    if not name:raise DeltaError('INVALID_NAME','Введите название документа.',422)
    document=Document()
    section=document.sections[0]
    section.page_width=Mm(210);section.page_height=Mm(297)
    section.top_margin=section.bottom_margin=section.left_margin=section.right_margin=Mm(20)
    document.add_paragraph('')
    out=BytesIO();document.save(out)
    row=request.app.state.documents.upload(owner(request),name if name.lower().endswith('.docx') else name+'.docx',out.getvalue())
    return request.app.state.documents.read(owner(request),row['id'])


@router.patch('/{doc_id}')
def rename(doc_id:UUID,body:RenameInput,request:Request):
    return request.app.state.documents.rename(owner(request),str(doc_id),body)


@router.post('/{doc_id}/copy',status_code=201)
def copy_document(doc_id:UUID,body:CopyInput,request:Request):
    return request.app.state.documents.copy(owner(request),str(doc_id),body)


@router.put('/{doc_id}/content')
def save_content(doc_id:UUID,body:RichSaveInput,request:Request):
    return request.app.state.documents.save(owner(request),str(doc_id),body,formatted=True)


@router.get('/{doc_id}')
def read(doc_id:UUID,request:Request,revision:int|None=Query(default=None,ge=1)):
    return request.app.state.documents.read(owner(request),str(doc_id),revision)


@router.put('/{doc_id}')
def save(doc_id:UUID,body:SaveInput,request:Request):
    return request.app.state.documents.save(owner(request),str(doc_id),body)


@router.get('/{doc_id}/download')
def download(doc_id:UUID,request:Request,revision:int|None=Query(default=None,ge=1)):
    row,data,number=request.app.state.documents.source(owner(request),str(doc_id),revision)
    return Response(data,media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        headers={'Content-Disposition':f"attachment; filename=delta-document-v{number}.docx; filename*=UTF-8''{quote(row['name'],safe='')}", 'Cache-Control':'no-store'})


@router.post('/{doc_id}/ask')
async def ask(doc_id:UUID,body:AIInput,request:Request):
    return await request.app.state.documents.ai(owner(request),str(doc_id),body,request.app.state.assistant.provider)


@router.post('/{doc_id}/propose')
async def propose(doc_id:UUID,body:AIInput,request:Request):
    return await request.app.state.documents.ai(owner(request),str(doc_id),body,request.app.state.assistant.provider,edit=True)
