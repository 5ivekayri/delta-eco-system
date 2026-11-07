"""Resolve applications on the target Agent; the Core never launches host apps."""
from sqlalchemy import select
from sqlalchemy.orm import Session
from delta_contracts.devices import CommandRequest
from delta_contracts.errors import DeltaError
from .models import Device


def normalize(value):
    return ' '.join(value.casefold().replace('ё','е').split()).strip(' «»"')


class ApplicationService:
    def __init__(self, manager):
        self.manager = manager

    def devices(self):
        with Session(self.manager.engine) as db:
            return [{'id':d.id,'name':d.display_name,'hostname':d.hostname,'os':d.os,'status':d.status} for d in db.scalars(select(Device))]

    def targets(self, target):
        devices = self.devices()
        if target.device_name:
            name = normalize(target.device_name)
            exact = [d for d in devices if name in {normalize(d['name']),normalize(d['hostname'])}]
            os_alias = {'mac':'macos','мак':'macos','macbook':'macos','макбук':'macos','windows':'windows','linux':'linux'}
            devices = exact or [d for d in devices if os_alias.get(name) == d['os']]
        elif target.device_id:
            devices = [d for d in devices if d['id'] == str(target.device_id)]
        return devices

    def catalogue(self, device):
        connection = self.manager.connections.get(device['id'])
        if connection is None:
            raise DeltaError('DEVICE_OFFLINE', f"Компьютер «{device['name']}» не в сети. Подключите Agent.",409)
        if connection.applications is None:
            raise DeltaError('AGENT_UPDATE_REQUIRED', f"Обновите Delta Agent на «{device['name']}»: этот клиент ещё не передаёт каталог установленных приложений.",409)
        return connection.applications

    async def list_apps(self, target):
        devices = self.targets(target)
        if not devices:
            raise DeltaError('DEVICE_NOT_FOUND','Указанный компьютер не найден.',404)
        return [{'device_id':d['id'],'device_name':d['name'],'applications':self.catalogue(d)} for d in devices]

    async def open_app(self, target):
        return await self.application_action(target, 'open_app')

    async def close_app(self, target):
        return await self.application_action(target, 'close_app')

    async def minimize_app(self, target):
        return await self.application_action(target, 'minimize_app')

    def single_target(self, target):
        devices = self.targets(target)
        if len(devices) != 1:
            raise DeltaError('DEVICE_AMBIGUOUS', 'Укажите один компьютер для действия.', 409)
        return devices[0]

    async def application_action(self, target, action):
        devices = self.targets(target)
        explicit = bool(target.device_id or target.device_name)
        if explicit and len(devices) != 1:
            raise DeltaError('DEVICE_AMBIGUOUS','Уточните точное имя целевого компьютера.',409)
        name = normalize(target.app_name)
        matches = []
        for device in devices:
            if not explicit and device['id'] not in self.manager.connections:
                continue
            try:
                apps = self.catalogue(device)
            except DeltaError:
                if explicit:
                    raise
                continue
            for app in apps:
                aliases = [app['id'], app['name'], *app.get('aliases',[])]
                if name in {normalize(a) for a in aliases}:
                    matches.append((device, app))
        if len(matches) > 1:
            raise DeltaError('APP_AMBIGUOUS','Найдено несколько приложений или компьютеров. Уточните имя приложения и целевого компьютера.',409)
        if not matches:
            if not explicit:
                raise DeltaError('APP_TARGET_REQUIRED','Укажите компьютер, где установлено приложение; убедитесь, что его Agent обновлён и подключён.',409)
            raise DeltaError('APP_NOT_AVAILABLE',f"«{target.app_name}» не найдено среди разрешённых приложений на «{devices[0]['name']}». Проверьте установку и настройки Agent.",404)
        device, app = matches[0]
        result = await self.manager.dispatch(device['id'],CommandRequest(action=action,payload={'app_id':app['id']}))
        if not result['success']:
            return result
        message = f"Команда открытия «{app['name']}» выполнена на «{device['name']}»."
        if action == 'close_app':
            message = f"Приложению «{app['name']}» на «{device['name']}» отправлен запрос закрытия. Если появились несохранённые документы, выберите действие в самом приложении."
        elif action == 'minimize_app':
            message = f"Окна «{app['name']}» на «{device['name']}» свёрнуты или скрыты."
        return {**result, 'app_name':app['name'], 'device_id':device['id'], 'device_name':device['name'],
                'message':message}
