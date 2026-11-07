"""Bound document request bodies before JSON/multipart parsing, including chunks."""
from starlette.responses import JSONResponse
from .ooxml import MAX_UPLOAD


class DocumentBodyLimit:
    def __init__(self,app):self.app=app
    async def __call__(self,scope,receive,send):
        if scope['type']!='http' or not scope['path'].startswith('/api/v1/documents') or scope['method'] not in {'POST','PUT'}:
            return await self.app(scope,receive,send)
        maximum=MAX_UPLOAD+65536 if scope['path']=='/api/v1/documents' else 2*1024*1024
        body=bytearray()
        while True:
            message=await receive()
            if message['type']=='http.disconnect':return
            chunk=message.get('body',b'')
            if len(body)+len(chunk)>maximum:
                return await JSONResponse({'error_code':'DOCUMENT_TOO_LARGE','message':'Запрос слишком большой. DOCX: максимум 10 МБ.'},status_code=413)(scope,receive,send)
            body.extend(chunk)
            if not message.get('more_body',False):break
        delivered=False
        async def bounded():
            nonlocal delivered
            if not delivered:
                delivered=True
                return {'type':'http.request','body':bytes(body),'more_body':False}
            return await receive()
        await self.app(scope,bounded,send)
