from dataclasses import dataclass
import re
import time
from urllib.parse import quote
from typing import Awaitable,Callable

import httpx
from jsonschema import Draft202012Validator,FormatChecker
from jsonschema.exceptions import ValidationError as SchemaValidationError
from pydantic import BaseModel,ValidationError

from delta_contracts.errors import DeltaError
from delta_contracts.tools import ToolCall,ToolResult


@dataclass
class LocalTool:
    name: str
    description: str
    schema: type[BaseModel]
    handler: Callable[[BaseModel],Awaitable[object]]
    permissions: list[str]
    enabled: bool = True
    service_id: str = 'delta-core'


class ToolRegistry:
    def __init__(self,services):
        self.services=services
        self.local:dict[str,LocalTool]={}

    def register(self,tool:LocalTool):
        if tool.name in self.local or any(t.name==tool.name for _,t in self.services.available_tools()):
            raise ValueError('Duplicate tool name')
        self.local[tool.name]=tool

    def specifications(self):
        local=[{'name':t.name,'description':t.description,'input_schema':t.schema.model_json_schema(),
                'service_id':t.service_id,'permissions':t.permissions,'enabled':t.enabled}
               for t in self.local.values() if t.enabled]
        external=[{**t.model_dump(),'service_id':s.service_id} for s,t in self.services.available_tools() if t.name not in self.local]
        return local+external

    async def execute(self,call:ToolCall)->ToolResult:
        start=time.monotonic();service_id=None
        try:
            local=self.local.get(call.name)
            if local and local.enabled:
                service_id=local.service_id
                arguments=local.schema.model_validate(call.arguments)
                data=await local.handler(arguments)
            else:
                match=next(((s,t) for s,t in self.services.available_tools() if t.name==call.name),None)
                if match is None:
                    registered=any(s.manifest and any(t.name==call.name for t in s.manifest.tools) for s in self.services.services.values())
                    raise DeltaError('SERVICE_UNAVAILABLE' if registered else 'TOOL_NOT_FOUND','Tool is not currently available',503 if registered else 404)
                service,tool=match;service_id=service.service_id
                Draft202012Validator(tool.input_schema,format_checker=FormatChecker()).validate(call.arguments)
                arguments=dict(call.arguments)
                def parameter(match):
                    key=match.group(1)
                    if key not in arguments:
                        raise DeltaError('TOOL_VALIDATION_ERROR','Missing route parameter',422)
                    value=str(arguments.pop(key))
                    if value in {'.','..'} or '/' in value or '\\' in value:
                        raise DeltaError('TOOL_VALIDATION_ERROR','Invalid route parameter',422)
                    return quote(value,safe='')
                path=re.sub(r'\{([a-z_]+)\}',parameter,tool.path)
                kwargs={'json':arguments} if tool.arguments_in=='body' else {'params':{k:v for k,v in arguments.items() if v is not None}}
                response=await self.services.client.request(tool.method,service.base_url.rstrip('/')+path,**kwargs)
                if not response.is_success:
                    try: error=response.json()
                    except ValueError: error={}
                    raise DeltaError(error.get('error_code','SERVICE_ERROR'),error.get('message',f'Service returned HTTP {response.status_code}'),response.status_code)
                data=response.json()
            success=not isinstance(data,dict) or data.get('success',True)
            result=ToolResult(tool=call.name,success=success,data=data,service_id=service_id,
                              message=data.get('message','') if isinstance(data,dict) else '')
        except (ValidationError,SchemaValidationError):
            result=ToolResult(tool=call.name,success=False,error_code='TOOL_VALIDATION_ERROR',message='Invalid tool arguments',service_id=service_id)
        except DeltaError as error:
            result=ToolResult(tool=call.name,success=False,error_code=error.code,message=error.message,service_id=service_id)
        except (httpx.HTTPError,ValueError):
            result=ToolResult(tool=call.name,success=False,error_code='SERVICE_UNAVAILABLE',message='Service request failed',service_id=service_id)
        result.duration_ms=round((time.monotonic()-start)*1000)
        return result
