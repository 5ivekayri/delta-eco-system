"""Conservative fast-path eligibility and factual tool-result responses.

This module never dispatches tools or interprets arguments. The Tool Registry
remains the execution/validation boundary. Unknown tools use the smart path.
"""
import re


def is_simple_action(message: str) -> bool:
    text = message.strip().casefold()
    if len(text) > 600 or re.search(
        r'объясн|почему|зачем|сравн|проанализ|суммир|резюм|подведи|оцен[ик]|порекоменд|'
        r'посовет|затем|потом|после этого|если|сводк|итог|вывод|\bи\b|'
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
    if tool in {'tasks.create', 'tasks.complete'} and isinstance(data, dict) and isinstance(data.get('title'), str):
        if tool == 'tasks.create':
            return 'Задача добавлена: ' + data['title']
        if data.get('status') == 'done':
            return 'Задача выполнена: ' + data['title']
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
