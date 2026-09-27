"""IoT boundary: the Assistant and HTTP routes do not know how hardware works."""
from abc import ABC, abstractmethod
import asyncio
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session
from delta_contracts.errors import DeltaError
from delta_contracts.iot import IoTState
from delta_contracts.storage import serialize
from delta_core.activity.models import record_event
from .models import VirtualIoTState


class IoTAdapter(ABC):
    @abstractmethod
    async def get_state(self) -> IoTState: ...

    @abstractmethod
    async def set_light(self, enabled: bool) -> IoTState: ...


class VirtualIoTAdapter(IoTAdapter):
    def __init__(self, engine):
        self.engine = engine

    async def get_state(self):
        return await asyncio.to_thread(self._access, None)

    async def set_light(self, enabled: bool):
        return await asyncio.to_thread(self._access, enabled)

    def _access(self, enabled):
        try:
            with Session(self.engine) as session:
                # Row locking serializes writes/audits on PostgreSQL. A unique key
                # and savepoint also make first-use initialization race-safe.
                query = select(VirtualIoTState).where(VirtualIoTState.id == 1)
                row = session.scalar(query.with_for_update())
                if row is None:
                    try:
                        with session.begin_nested():
                            session.add(VirtualIoTState(id=1))
                            session.flush()
                    except IntegrityError:
                        pass
                    row = session.scalar(query.with_for_update())
                if enabled is not None and row.desk_light != enabled:
                    row.desk_light = enabled
                    record_event(session, 'IOT_ACTION', 'Рабочий свет включён' if enabled else 'Рабочий свет выключен',
                                 source='iot', details={'adapter':'virtual', 'enabled':enabled})
                session.flush()
                data = serialize(row)
                state = IoTState(source='virtual', **{k:v for k,v in data.items() if k != 'id'})
                session.commit()
                return state
        except SQLAlchemyError:
            raise DeltaError('IOT_UNAVAILABLE', 'Не удалось получить подтверждённое состояние IoT. Обновите страницу перед повтором.', 503)
