import asyncio
import hmac

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from pydantic import TypeAdapter, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from delta_contracts.devices import Action, CommandRequest, CommandResult, Registration
from delta_contracts.errors import DeltaError
from delta_contracts.storage import serialize
from delta_core.activity.models import ActivityEvent
from .models import Device

router = APIRouter()


@router.get("/api/v1/devices")
def devices(request: Request):
    with Session(request.app.state.engine) as session:
        return [serialize(d) for d in session.scalars(select(Device).order_by(Device.created_at))]


@router.get("/api/v1/devices/{device_id}")
def device_details(device_id: str, request: Request):
    result = request.app.state.devices.get(device_id)
    with Session(request.app.state.engine) as session:
        result["recent_commands"] = [serialize(e) for e in session.scalars(select(ActivityEvent).where(
            ActivityEvent.device_id == device_id,
            ActivityEvent.event_type.in_(["COMMAND_SENT", "COMMAND_COMPLETED"])
        ).order_by(ActivityEvent.created_at.desc()).limit(30))]
    return result


@router.post("/api/v1/devices/{device_id}/commands")
async def command(device_id: str, body: CommandRequest, request: Request):
    try:
        return await request.app.state.devices.dispatch(device_id, body)
    except ValidationError:
        raise DeltaError("TOOL_VALIDATION_ERROR", "Invalid command payload", 422)


@router.websocket("/ws/agents")
async def agent_socket(socket: WebSocket):
    settings = socket.app.state.settings
    if not hmac.compare_digest(socket.headers.get("authorization", ""), f"Bearer {settings.delta_token}"):
        await socket.close(code=1008)
        return
    await socket.accept()
    manager = socket.app.state.devices
    device_id = None
    connection = None
    try:
        registration = Registration.model_validate(await asyncio.wait_for(socket.receive_json(), 10))
        device_id, connection = await manager.register(registration, socket)
        await socket.send_json({"type": "register_ack", "device_id": device_id,
                                "heartbeat_interval": max(1, settings.heartbeat_timeout // 3)})
        while True:
            message = await socket.receive_json()
            if not isinstance(message, dict):
                raise ValueError("Expected a JSON object")
            if message.get("type") == "heartbeat":
                manager.heartbeat(device_id, connection)
            elif message.get("type") == "command_result":
                manager.result(device_id, connection, CommandResult.model_validate(message))
            elif message.get("type") == "capabilities_update":
                if manager.connections.get(device_id) is not connection:
                    continue
                capabilities = TypeAdapter(list[Action]).validate_python(message.get("capabilities"))
                with Session(manager.engine) as session:
                    session.get(Device, device_id).capabilities = sorted(set(capabilities))
                    session.commit()
            else:
                await socket.send_json({"type": "error", "error_code": "INVALID_MESSAGE", "message": "Unknown message type"})
    except (WebSocketDisconnect, RuntimeError):
        pass
    except (ValidationError, ValueError, asyncio.TimeoutError):
        await socket.close(code=1008, reason="Invalid protocol message")
    finally:
        if device_id and connection:
            manager.disconnect(device_id, connection)
