from fastapi import APIRouter, Request
from delta_contracts.iot import IoTState, LightInput

router = APIRouter(prefix='/api/v1/iot', tags=['IoT'])


@router.get('/state', response_model=IoTState)
async def state(request: Request):
    return await request.app.state.iot.get_state()


@router.post('/light', response_model=IoTState)
async def light(body: LightInput, request: Request):
    return await request.app.state.iot.set_light(body.enabled)
