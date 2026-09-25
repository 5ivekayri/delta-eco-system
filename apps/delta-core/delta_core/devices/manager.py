import asyncio
from dataclasses import dataclass, field
from datetime import timedelta
from uuid import uuid4

from fastapi import WebSocket
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from delta_contracts.devices import CommandRequest, CommandResult, PAYLOAD_SCHEMAS, Registration
from delta_contracts.errors import DeltaError
from delta_contracts.storage import serialize, utcnow
from delta_core.activity.models import ActivityEvent, record_event
from .models import Device


@dataclass
class Connection:
    socket: WebSocket
    pending: dict[str, asyncio.Future] = field(default_factory=dict)
    send_lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class DeviceManager:
    def __init__(self, engine, settings):
        self.engine = engine
        self.settings = settings
        self.connections: dict[str, Connection] = {}

    def reset_online(self):
        with Session(self.engine) as session:
            session.execute(update(Device).values(status="offline"))
            session.commit()

    async def register(self, registration: Registration, socket: WebSocket) -> tuple[str, Connection]:
        with Session(self.engine) as session:
            device = session.scalar(select(Device).where(Device.device_uid == registration.device_uid))
            if device is None:
                device = Device()
                session.add(device)
            for key, value in registration.model_dump(exclude={"type"}).items():
                setattr(device, key, value)
            device.status = "online"
            device.last_seen = utcnow()
            session.flush()
            device_id = device.id
            record_event(session, "DEVICE_CONNECTED", f"{device.display_name} connected", device_id=device_id)
            session.commit()
        previous = self.connections.get(device_id)
        connection = Connection(socket)
        self.connections[device_id] = connection
        if previous:
            self.fail_pending(previous, "Device reconnected")
            await previous.socket.close(code=1000)
        return device_id, connection

    def fail_pending(self, connection: Connection, message: str):
        for future in connection.pending.values():
            if not future.done():
                future.set_exception(DeltaError("DEVICE_OFFLINE", message, 409))

    def disconnect(self, device_id: str, connection: Connection):
        if self.connections.get(device_id) is not connection:
            return
        self.connections.pop(device_id)
        self.fail_pending(connection, "Device disconnected")
        with Session(self.engine) as session:
            device = session.get(Device, device_id)
            if device:
                device.status = "offline"
                record_event(session, "DEVICE_OFFLINE", f"{device.display_name} disconnected", device_id=device_id)
                session.commit()

    def heartbeat(self, device_id: str, connection: Connection):
        if self.connections.get(device_id) is not connection:
            return
        with Session(self.engine) as session:
            device = session.get(Device, device_id)
            device.last_seen = utcnow()
            record_event(session, "HEARTBEAT", "Heartbeat received", device_id=device_id)
            session.commit()

    async def expire(self):
        with Session(self.engine) as session:
            stale = list(session.scalars(select(Device.id).where(
                Device.status == "online", Device.last_seen < utcnow() - timedelta(seconds=self.settings.heartbeat_timeout))))
        for device_id in stale:
            connection = self.connections.get(device_id)
            if connection:
                self.disconnect(device_id, connection)
                await connection.socket.close(code=1001)

    async def monitor(self):
        while True:
            await asyncio.sleep(min(5, self.settings.heartbeat_timeout / 2))
            await self.expire()

    def get(self, device_id: str) -> dict:
        with Session(self.engine) as session:
            device = session.get(Device, device_id)
            if not device:
                raise DeltaError("DEVICE_NOT_FOUND", "Device not found", 404)
            return serialize(device)

    async def dispatch(self, device_id: str, request: CommandRequest) -> dict:
        device = self.get(device_id)
        connection = self.connections.get(device_id)
        if device["status"] != "online" or connection is None:
            raise DeltaError("DEVICE_OFFLINE", "Target device is offline", 409)
        if request.action not in device["capabilities"]:
            raise DeltaError("CAPABILITY_NOT_SUPPORTED", "Device does not support this action", 400)
        payload = PAYLOAD_SCHEMAS[request.action].model_validate(request.payload).model_dump()
        command_id = str(uuid4())
        future = asyncio.get_running_loop().create_future()
        connection.pending[command_id] = future
        message = {"type": "command", "command_id": command_id, "action": request.action, "payload": payload}
        with Session(self.engine) as session:
            record_event(session, "COMMAND_SENT", request.action, device_id=device_id, details=message)
            session.commit()
        try:
            async with connection.send_lock:
                await connection.socket.send_json(message)
            result = await asyncio.wait_for(future, timeout=self.settings.command_timeout)
        except asyncio.TimeoutError:
            result = {"command_id": command_id, "success": False, "message": "Command timed out; outcome unknown",
                      "error_code": "COMMAND_TIMEOUT"}
        except (RuntimeError, OSError):
            raise DeltaError("DEVICE_OFFLINE", "Connection lost", 409)
        finally:
            connection.pending.pop(command_id, None)
        with Session(self.engine) as session:
            record_event(session, "COMMAND_COMPLETED", result["message"], device_id=device_id, details=result)
            session.commit()
        return result

    def result(self, device_id: str, connection: Connection, result: CommandResult):
        if self.connections.get(device_id) is not connection:
            return
        future = connection.pending.get(result.command_id)
        if future is not None and not future.done():
            future.set_result(result.model_dump())
