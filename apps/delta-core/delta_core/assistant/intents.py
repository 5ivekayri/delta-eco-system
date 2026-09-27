"""Replaceable local intent router. Classification never executes mutating tools."""
import re
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Protocol
from uuid import UUID

from jsonschema import Draft202012Validator, FormatChecker
from delta_contracts.tools import ToolCall


def normalized(text: str) -> str:
    return ' '.join(text.casefold().replace('ё', 'е').split()).strip(' .!?«»"')


@dataclass
class IntentDecision:
    call: ToolCall | None = None
    confidence: float = 0.0
    slots: dict = field(default_factory=dict)


class IntentRouter(Protocol):
    async def route(self, text: str, specifications: list[dict], context: dict) -> IntentDecision: ...


class RegistryTaskLookup:
    """Resolve titles through the registered read tool, never the Tasks database."""
    def __init__(self, registry):
        self.registry = registry

    async def __call__(self):
        result = await self.registry.execute(ToolCall(name='tasks.list'))
        return result.data if result.success and isinstance(result.data, list) else []


class LocalIntentRouter:
    def __init__(self, task_lookup: Callable[[], Awaitable[list[dict]]] | None = None):
        self.task_lookup = task_lookup

    async def route(self, text, specifications, context):
        decision = self.classify(text, context)
        if decision.call is None:
            return decision
        available = {s['name']: s for s in specifications if s.get('enabled', True)}
        spec = available.get(decision.call.name)
        if spec is None:
            return IntentDecision(confidence=0.0, slots=decision.slots)
        if decision.call.name == 'tasks.complete' and 'title' in decision.call.arguments:
            if self.task_lookup is None or 'tasks.list' not in available:
                return IntentDecision(confidence=0.0, slots=decision.slots)
            rows = await self.task_lookup()
            matches = [r for r in rows if isinstance(r, dict) and
                       normalized(str(r.get('title', ''))) == normalized(decision.call.arguments['title'])]
            # Even an already completed duplicate makes the spoken reference ambiguous.
            if len(matches) != 1 or not matches[0].get('id'):
                return IntentDecision(confidence=0.0, slots=decision.slots)
            decision.call.arguments = {'id': str(matches[0]['id'])}
        validator = Draft202012Validator(spec['input_schema'], format_checker=FormatChecker())
        if not validator.is_valid(decision.call.arguments):
            return IntentDecision(confidence=0.0, slots=decision.slots)
        return decision

    def classify(self, text: str, context: dict) -> IntentDecision:
        if '\n' in text or '\r' in text:
            return IntentDecision()
        text = ' '.join(text.strip().split()).strip(' .!?')
        text = re.sub(r'^пожалуйста[, ]+|[, ]+пожалуйста$', '', text, flags=re.I)
        # Full matches and explicit compound/conditional guards avoid guessing actions.
        if len(text) > 600 or re.search(
            r'\b(если|потом|затем|почему|объясни|сравни|проанализируй|после|через)\b|[;\n]|'
            r'(?:\b(?:и|а)\s+|[,.:]\s*)(?:покажи|создай|добавь|заверши|открой|запусти|включи|выключи)\b', text, re.I
        ):
            return IntentDecision()
        def match(pattern):
            return re.fullmatch(pattern, text, re.I)
        def decision(name, arguments=None, slots=None):
            return IntentDecision(ToolCall(name=name, arguments=arguments or {}), .99, slots or {})
        if match(r'(?:(?:покажи|перечисли|показать) (?:все |подключенные |подключённые )?(?:устройства|компьютеры)|'
                 r'(?:покажи|показать) устройство|'
                 r'список (?:устройств|компьютеров)|какие (?:устройства|компьютеры) (?:сейчас )?подключены)'):
            return decision('devices.list')
        m = match(r'(?:добавь|создай|добавить|создать) (?:новую )?задачу\s+(.+)')
        if m:
            title = m[1].strip(' «»"')
            if not title or re.search(r'\b(?:до|завтра|сегодня|приоритет|приоритетом|срок|пространств\w*|по)\b|\b(?:для|в) проект[ае]\b', title, re.I):
                return IntentDecision()
            return decision('tasks.create', {'title': title}, {'task_title': title})
        m = match(r'(?:покажи|перечисли|показать) (?:(все|новые|выполненные) )?задачи|список задач')
        if m:
            status = {'новые': 'todo', 'выполненные': 'done'}.get((m[1] or '').casefold())
            return decision('tasks.list', {'status': status} if status else {})
        if match(r'(?:покажи|перечисли) задачи в работе'):
            return decision('tasks.list', {'status':'in_progress'})
        m = match(r'(?:заверши|закрой|завершить) задачу (.+)|отметь задачу (.+) выполненной')
        if m:
            title = (m[1] or m[2]).strip(' «»"')
            try:
                task_id = str(UUID(title))
                return decision('tasks.complete', {'id': task_id})
            except ValueError:
                return decision('tasks.complete', {'title': title}, {'task_title': title})
        m = match(r'(?:открой|запусти|открыть) (?:рабочее пространство |пространство )?(.+)')
        if m:
            target = m[1]
            parts = re.split(r'\s+на\s+', target, maxsplit=1, flags=re.I)
            workspace = self.unique(parts[0], context.get('workspaces', []), 'name')
            if workspace is None:
                return IntentDecision()
            arguments = {'workspace_id': str(workspace['id'])}
            slots = {'workspace_name': workspace['name']}
            if len(parts) == 2 and normalized(parts[1]) not in {'этом компьютере', 'текущем устройстве'}:
                device = self.unique(parts[1], context.get('devices', []), 'display_name')
                if device is None:
                    return IntentDecision()
                arguments['device_id'] = str(device['id'])
                slots['device_name'] = device['display_name']
            elif context.get('device_id'):
                arguments['device_id'] = str(context['device_id'])
            else:
                return IntentDecision()
            return decision('workspaces.launch', arguments, slots)
        m = match(r'(включи|выключи|включить|выключить) (?:рабочий |настольный |настольную )?(?:свет|лампу)(?: на (.+))?')
        if m:
            arguments = {'enabled': m[1].casefold() in {'включи', 'включить'}}
            slots = {'light_state': arguments['enabled']}
            if m[2]:
                arguments['device_name'] = m[2].strip(' «»"')
                slots['device_name'] = arguments['device_name']
            return decision('iot.set_light', arguments, slots)
        if match(r'(?:какая (?:сейчас )?температура|покажи температуру|узнай температуру|температура в комнате)'):
            return decision('iot.get_temperature')
        if match(r'(?:покажи (?:яркость|освещенность|освещённость)|какая (?:сейчас )?(?:яркость|освещенность|освещённость))'):
            return decision('iot.get_brightness')
        if match(r'(?:есть ли движение|покажи (?:датчик движения|состояние датчика движения))'):
            return decision('iot.get_motion')
        return IntentDecision()

    @staticmethod
    def unique(name, rows, field):
        matches = [row for row in rows if normalized(row[field]) == normalized(name)]
        return matches[0] if len(matches) == 1 else None
