import asyncio
import logging
from sqlalchemy.exc import SQLAlchemyError
from dataclasses import dataclass

import httpx
from sqlalchemy.orm import Session

from delta_contracts.errors import DeltaError
from delta_contracts.services import ServiceManifest
from delta_contracts.storage import utcnow
from delta_core.activity.models import record_event


@dataclass
class Service:
    service_id: str
    base_url: str
    enabled: bool = True
    manifest: ServiceManifest | None = None
    status: str = 'offline'
    last_health_check: str | None = None

    def public(self):
        manifest = self.manifest
        return {'service_id': self.service_id, 'name': manifest.name if manifest else self.service_id,
                'version': manifest.version if manifest else None, 'base_url': self.base_url,
                'health_url': manifest.health_url if manifest else '/health', 'enabled': self.enabled,
                'status': self.status, 'last_health_check': self.last_health_check,
                'available_tools': [t.model_dump() for t in manifest.tools if t.enabled] if manifest and self.enabled and self.status == 'online' else []}


class ServiceRegistry:
    def __init__(self, configs: list[dict], client: httpx.AsyncClient, engine=None):
        self.client = client
        self.engine = engine
        self.services: dict[str, Service] = {}
        for config in configs:
            service = Service(**config)
            url = httpx.URL(service.base_url)
            if url.scheme not in {'http','https'} or not url.host or url.username or url.password or url.query or url.fragment:
                raise ValueError('Invalid service base URL')
            if service.service_id in self.services:
                raise ValueError('Duplicate service ID')
            self.services[service.service_id] = service

    def get(self, service_id: str) -> Service:
        if service_id not in self.services:
            raise DeltaError('SERVICE_NOT_FOUND', 'Service not found', 404)
        return self.services[service_id]

    async def refresh(self):
        for service in self.services.values():
            previous = service.status
            if not service.enabled:
                service.status = 'disabled'
                continue
            try:
                if service.manifest is None:
                    response = await self.client.get(service.base_url.rstrip('/') + '/api/v1/manifest')
                    response.raise_for_status()
                    manifest = ServiceManifest.model_validate(response.json())
                    if manifest.service_id != service.service_id:
                        raise ValueError('Manifest identity mismatch')
                    names = [t.name for t in manifest.tools]
                    existing = {t.name for s in self.services.values() if s.manifest and s is not service for t in s.manifest.tools}
                    if len(set(names)) != len(names) or existing.intersection(names):
                        raise ValueError('Duplicate tool name')
                    service.manifest = manifest
                response = await self.client.get(service.base_url.rstrip('/') + service.manifest.health_url)
                response.raise_for_status()
                service.status = 'online' if (response.json() if isinstance(response.json(), dict) else {}).get('status') == 'ok' else 'degraded'
                if not service.manifest.enabled:
                    service.status = 'disabled'
            except (httpx.HTTPError, ValueError):
                service.status = 'offline'
            service.last_health_check = utcnow().isoformat()
            if self.engine is not None and previous != service.status:
                try:
                    with Session(self.engine) as session:
                        record_event(session, 'SERVICE_ONLINE' if service.status == 'online' else 'SERVICE_OFFLINE',
                                 f'{service.service_id}: {service.status}', service_id=service.service_id)
                        session.commit()
                except SQLAlchemyError:
                    logging.getLogger(__name__).warning("Service activity event could not be saved")

    async def monitor(self):
        while True:
            await self.refresh()
            await asyncio.sleep(15)

    def available_tools(self):
        return [(service, tool) for service in self.services.values()
                if service.enabled and service.status == 'online' and service.manifest
                for tool in service.manifest.tools if tool.enabled]
