"""Command tools route to one Agent; Core never starts a local subprocess."""
from delta_contracts.devices import CommandRequest
from delta_contracts.errors import DeltaError
from .applications import ApplicationService


class TerminalService(ApplicationService):
    def target(self, arguments):
        if not arguments.device_id and not arguments.device_name:
            raise DeltaError('DEVICE_REQUIRED', 'Выберите компьютер для выполнения команд.', 409)
        device = self.single_target(arguments)
        if device['os'] != 'linux':
            raise DeltaError('PLATFORM_UNSUPPORTED', 'Выполнение команд пока доступно только на Linux.', 409)
        return device

    async def access(self, arguments):
        device = self.target(arguments)
        if 'command_access' not in self.manager.get(device['id'])['capabilities']:
            return {'device_id': device['id'], 'mode': 'off',
                    'message': 'Обновите клиент и разрешите терминал в его локальных настройках.'}
        return await self.manager.dispatch(device['id'], CommandRequest(action='command_access'))

    async def run(self, arguments):
        device = self.target(arguments)
        return await self.manager.dispatch(device['id'], CommandRequest(action='run_command',
            payload=arguments.model_dump(exclude={'device_id', 'device_name'})))


def safe_terminal_call(call):
    if call.get('name') != 'devices.run_command':
        return call
    return {**call, 'arguments': {k: v for k, v in call.get('arguments', {}).items()
                                 if k in {'device_id', 'device_name', 'timeout_seconds', 'root_id'}},
            'command_redacted': True}


def safe_terminal_result(result):
    if result.get('tool') != 'devices.run_command':
        return result
    data = result.get('data') or {}
    execution = data.get('data') or {}
    return {**result, 'data': {k: execution.get(k) for k in
            ('exit_code', 'duration_ms', 'truncated', 'termination')}, 'output_redacted': True}
