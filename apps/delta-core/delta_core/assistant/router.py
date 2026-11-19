from uuid import UUID
from fastapi import APIRouter,Request,BackgroundTasks
from fastapi.responses import JSONResponse
from delta_contracts.errors import DeltaError
from pydantic import Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session
from delta_contracts.devices import StrictModel
from delta_contracts.storage import serialize
from .models import Interaction
from delta_core.voice.telemetry import VoiceTimings
import logging
import json

router=APIRouter(prefix='/api/v1/assistant')


class MessageInput(StrictModel):
    message:str=Field(min_length=1,max_length=10000)
    device_id:UUID|None=None

    @field_validator('message')
    @classmethod
    def nonblank_message(cls, value):
        value = value.strip()
        if not value:
            raise ValueError('Message must not be blank')
        return value


@router.post('/message')
async def message(body:MessageInput,request:Request,background_tasks:BackgroundTasks):
    timings = VoiceTimings()
    try:
        result = await request.app.state.assistant.message(body.message,str(body.device_id) if body.device_id else None, timings=timings, background=background_tasks)
        return {**result, 'timings': timings.snapshot()}
    except DeltaError as error:
        return JSONResponse({'success':False,'error_code':error.code,'message':error.message,'timings':timings.snapshot()},status_code=error.status,background=background_tasks)
    finally:
        logging.getLogger(__name__).info(json.dumps({'event':'assistant_timing', 'request_id':getattr(request.state,'request_id',None), **timings.snapshot()}))


@router.get('/history')
def history(request:Request):
    with Session(request.app.state.engine) as session:
        return [serialize(r) for r in reversed(list(session.scalars(select(Interaction).order_by(Interaction.created_at.desc()).limit(50))))]


@router.get('/tools')
def tools(request:Request):
    return request.app.state.tools.specifications()
