"""Conservative fast-path eligibility and factual tool-result responses.

This module never dispatches tools or interprets arguments. The Tool Registry
remains the execution/validation boundary. Unknown tools use the smart path.
"""
import re


def is_simple_action(message: str) -> bool:
    text = message.strip().casefold()
    if len(text) > 600 or re.search(
        r'объясн|почему|зачем|сравн|проанализ|суммир|резюм|подведи|оцен[ик]|порекоменд|'
        r'посовет|затем|потом|после этого|если|сводк|итог|вывод|лендинг|html|программир|\bи\b|'
        r'\b(why|explain|compare|analy[sz]e|summari[sz]e|recommend|then|if|and)\b', text
    ):
        return False
    return bool(re.match(
        r'^(?:(?:пожалуйста|please)[, ]+)?'
        r'(?:покажи|показать|список|перечисли|добавь|добавить|создай|создать|'
        r'заверши|завершить|отметь|открой|открыть|запусти|включи|выключи|'
        r'show|list|add|create|complete|open|launch|turn on|turn off)\b', text
    ))


def deterministic_response(result: dict) -> str | None:
    """Return None when the result requires the smart path, never fabricate success."""
    if not result.get('success'):
        return None
    tool, data = result.get('tool'), result.get('data')
    if tool in {'devices.open_app','devices.close_app','devices.minimize_app'} and isinstance(data, dict) and data.get('success') is True and data.get('app_name') and data.get('device_name'):
        return data['message']
    if tool == 'devices.describe_screen' and isinstance(data, dict) and data.get('description'):
        return data['description']
    if tool == 'devices.list_apps' and isinstance(data, list):
        sections = []
        for device in data:
            apps = device.get('applications', [])
            sections.append(f"{device.get('device_name', 'Компьютер')} — доступно программ: {len(apps)}\n" +
                            '\n'.join('• ' + item['name'] for item in apps))
        return '\n\n'.join(sections) or 'Доступных приложений нет.'
    if tool == 'services.list' and isinstance(data, list) and all(
        isinstance(item, dict) and isinstance(item.get('name'), str) and isinstance(item.get('status'), str) for item in data
    ):
        return '\n'.join('• ' + item['name'] + ' — ' + item['status'] for item in data) or 'Сервисы не найдены.'
    if tool == 'workspaces.list' and isinstance(data, list) and all(
        isinstance(item, dict) and isinstance(item.get('name'), str) for item in data
    ):
        return '\n'.join('• ' + item['name'] for item in data) or 'Рабочие пространства не найдены.'
    if tool in {'tasks.create', 'tasks.complete'} and isinstance(data, dict) and isinstance(data.get('title'), str):
        if tool == 'tasks.create':
            return 'Задача добавлена: ' + data['title']
        if data.get('status') == 'done':
            return 'Задача выполнена: ' + data['title']
    if tool == 'tasks.delete' and isinstance(data, dict) and data.get('success') is True and data.get('id'):
        return 'Задача удалена.'
    if tool == 'tasks.update' and isinstance(data, dict) and isinstance(data.get('title'), str):
        return 'Задача обновлена: ' + data['title'] + (' · приоритет: ' + {'high':'высокий','medium':'средний','low':'низкий'}.get(data.get('priority'), str(data.get('priority'))) if data.get('priority') else '')
    if tool == 'workspaces.create' and isinstance(data, dict) and data.get('id') and isinstance(data.get('name'), str):
        return 'Рабочее пространство создано: ' + data['name'] + (
            '. Настройки устройства сохранены.' if data.get('bindings') else
            '. Для запуска добавьте привязку к устройству в разделе Workspaces.')
    if tool == 'devices.list' and isinstance(data, list) and all(
        isinstance(d, dict) and isinstance(d.get('display_name'), str) and d.get('status') in {'online', 'offline'} for d in data
    ):
        online = [d['display_name'] for d in data if d['status'] == 'online']
        offline = [d['display_name'] for d in data if d['status'] == 'offline']
        text = 'Подключены: ' + ', '.join(online) if online else 'Сейчас нет подключённых устройств.'
        if offline:
            text += '\nНе в сети: ' + ', '.join(offline)
        return text
    if tool == 'workspaces.launch' and isinstance(data, dict) and data.get('success') is True:
        results = data.get('results')
        if isinstance(results, list) and results and all(isinstance(r, dict) and r.get('success') is True for r in results):
            return data.get('message') or 'Рабочее пространство запущено.'
    if tool == 'iot.set_light' and isinstance(data, dict) and isinstance(data.get('enabled'), bool):
        return 'Свет включён.' if data['enabled'] else 'Свет выключен.'
    if tool == 'tasks.list' and isinstance(data, list) and all(
        isinstance(task, dict) and isinstance(task.get('title'), str) for task in data
    ):
        return '\n'.join('• ' + task['title'] for task in data) or 'Задач не найдено.'
    if tool == 'iot.get_temperature' and isinstance(data, dict) and type(data.get('temperature')) in {int, float}:
        return f"Температура: {data['temperature']:g} °C."
    if tool == 'iot.get_brightness' and isinstance(data, dict) and type(data.get('brightness')) in {int, float}:
        return f"Освещённость: {data['brightness']:g} %."
    if tool == 'iot.get_motion' and isinstance(data, dict) and isinstance(data.get('motion'), bool):
        return 'Движение обнаружено.' if data['motion'] else 'Движение не обнаружено.'
    return None


def requested_action(message: str) -> str | None:
    text = message.strip().casefold()
    text = re.sub(r'^(?:пожалуйста|please)[, ]+', '', text)
    if re.match(r'^(?:сверни|свернуть|minimize)\b', text):
        return 'devices.minimize_app'
    if re.match(r'^(?:закрой|закрыть|close)\b', text) and not re.search(r'\b(задач\w*|task)\b', text):
        return 'devices.close_app'
    if re.match(r'^(?:создай|создать|добавь|добавить|create|add)\s+(?:(?:новое|новый|a|new)\s+)*(?:рабочее пространство|пространство|воркспейс|workspace)\b', text):
        return 'workspaces.create'
    required = None
    for pattern, name in [
        (r'^(?:добавь|создай|добавить|создать)\b', 'tasks.create'),
        (r'^(?:заверши|закрой|завершить|отметь)\b', 'tasks.complete'),
        (r'^(?:удали|удалить)\b', 'tasks.delete'),
        (r'^(?:переименуй|поставь|установи|задай)\b', 'tasks.update'),
        (r'^(?:открой|запусти|открыть)\b', 'workspaces.launch'),
        (r'^(?:включи|выключи)\b', 'iot.set_light'),
    ]:
        if re.match(pattern, text):
            required = name
            break
    return required


def action_is_fulfilled(message: str, results: list[dict]) -> bool:
    required = requested_action(message)
    if required == 'workspaces.launch' and not re.search(r'\b(пространство|workspace)\b', message, re.I):
        return any(r.get('tool') in {'workspaces.launch','devices.open_app'} for r in results)
    return required is None or any(r.get('tool') == required for r in results)


def unexecuted_response(model_text: str) -> str:
    questions = re.findall(r'[^.!?\n]+\?', model_text)
    return 'Действие пока не выполнено. ' + (questions[-1].strip() if questions else
        'Модель не сформировала нужную команду. Уточните цель и действие.')
