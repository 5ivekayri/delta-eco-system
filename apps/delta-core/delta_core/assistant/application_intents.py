"""Exact desktop commands use registered tools and preserve local policy."""
import re
from delta_contracts.tools import ToolCall
from .intents import IntentDecision


class ApplicationIntentRouter:
    def __init__(self, fallback):
        self.fallback = fallback

    async def route(self, text, specifications, context):
        clean = re.sub(r'^\s*(?:пожалуйста|please)[, ]+', '', text, flags=re.I).strip().rstrip('.!?')
        enabled = {s['name'] for s in specifications if s.get('enabled', True)}
        tool = None
        arguments = {}
        parts = None
        if '\n' not in clean and len(clean) <= 600:
            listing = re.fullmatch(r'(?:(?:выведи|покажи|дай|перечисли|show|list)\s+)?(?:список\s+)?(?:(?:всех|все|установленных|доступных)\s+)*(?:программ|программы|приложений|приложения|applications|apps)(?:\s+(?:на|on)\s+(.+))?', clean, re.I)
            screen = re.fullmatch(r'(?:что (?:происходит |сейчас )?на экране|опиши экран|describe (?:my )?screen)(?:\s+(?:на|on)\s+(.+))?', clean, re.I)
            action = re.fullmatch(r'(открой|открыть|запусти|запустить|open|launch|закрой|закрыть|close|сверни|свернуть|minimize)\s+(?:приложение\s+|программу\s+)?(.+)', clean, re.I)
            if listing:
                tool, parts = 'devices.list_apps', ['', listing[1]]
            elif screen:
                tool, parts = 'devices.describe_screen', ['', screen[1]]
            elif action and not re.search(r'\b(и|затем|потом|если|после|через|and|then|if|задач\w*|task|папку|файл|сайт|пространство|folder|file|workspace|website)\b|[/\\:;]', action[2], re.I):
                verb = action[1].casefold()
                tool = 'devices.close_app' if verb in {'закрой','закрыть','close'} else 'devices.minimize_app' if verb in {'сверни','свернуть','minimize'} else 'devices.open_app'
                parts = re.split(r'\s+(?:на|on)\s+', action[2], maxsplit=1, flags=re.I)
                arguments['app_name'] = parts[0].strip(' «»"')
                if arguments['app_name'].casefold() in {'программу', 'приложение', 'app', 'application'}:
                    return IntentDecision(confidence=1, clarification='Укажите название программы, например: «сверни vscode».')
        if tool not in enabled:
            return await self.fallback.route(text, specifications, context)
        name = parts[1] if len(parts)>1 else None
        if name and name.casefold() not in {'этом компьютере','текущем компьютере','этом устройстве'}:
            arguments['device_name'] = name.strip(' «»"')
        elif context.get('device_id'):
            arguments['device_id'] = context['device_id']
        elif name or tool == 'devices.describe_screen':
            return IntentDecision(confidence=1, clarification='Выберите текущий компьютер или укажите его имя.')
        return IntentDecision(call=ToolCall(name=tool, arguments=arguments), confidence=.99)
