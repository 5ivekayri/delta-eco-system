from fastapi import APIRouter, Request
router = APIRouter(prefix='/api/v1/services')


@router.get('')
def services(request: Request):
    return [service.public() for service in request.app.state.services.services.values()]


@router.get('/{service_id}')
def service(service_id: str, request: Request):
    return request.app.state.services.get(service_id).public()
