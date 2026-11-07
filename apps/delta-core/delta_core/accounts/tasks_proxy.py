"""Authenticated HTTP adapter; Tasks remains a separate database/service."""
import re
from fastapi import APIRouter,Request
from fastapi.responses import Response
from delta_contracts.errors import DeltaError
router=APIRouter(prefix='/api/v1/task-proxy')

@router.api_route('/{path:path}',methods=['GET','POST','PATCH','DELETE'])
async def proxy(path:str,request:Request):
    if not re.fullmatch(r'tasks(?:/[A-Za-z0-9-]+(?:/complete)?)?',path):
        raise DeltaError('NOT_FOUND','Маршрут не найден.',404)
    raw=await request.body()
    if len(raw)>65536:raise DeltaError('TOO_LARGE','Слишком большой запрос.',413)
    response=await request.app.state.http.request(request.method,
        request.app.state.settings.tasks_url.rstrip('/')+'/api/v1/'+path,
        params=request.query_params,content=raw,headers={'Content-Type':'application/json'})
    return Response(content=response.content,status_code=response.status_code,media_type='application/json')
