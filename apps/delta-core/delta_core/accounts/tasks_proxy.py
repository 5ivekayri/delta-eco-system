"""Authenticated HTTP adapter; Tasks remains a separate database/service."""
import re
import httpx
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
    # A pooled keep-alive connection may close between periodic GET requests.
    # Only retry reads: mutating requests may already have reached Tasks.
    for attempt in range(2):
        try:
            response=await request.app.state.http.request(request.method,
                request.app.state.settings.tasks_url.rstrip('/')+'/api/v1/'+path,
                params=request.query_params,content=raw,headers={'Content-Type':'application/json'})
            break
        except httpx.RemoteProtocolError:
            if request.method=='GET' and attempt==0:continue
            raise DeltaError('TASKS_UNAVAILABLE','Связь с Tasks прервалась. Изменяющая команда не повторялась; проверьте результат перед повтором.',503) from None
        except httpx.HTTPError:
            raise DeltaError('TASKS_UNAVAILABLE','Сервис Tasks временно недоступен.',503) from None
    return Response(content=response.content,status_code=response.status_code,media_type='application/json')
