"""Exact single-app commands keep desktop dispatch independent from the LLM."""
import re
from delta_contracts.tools import ToolCall
from .intents import IntentDecision


class ApplicationIntentRouter:
    def __init__(self, fallback):
        self.fallback = fallback

    async def route(self, text, specifications, context):
        previous = await self.fallback.route(text, specifications, context)
        if previous.call or previous.clarification:
            return previous
        if '\n' in text or len(text) > 600 or re.search(r'\b(и|затем|потом|если|после|через|and|then|if)\b|[;]',text,re.I):
            return previous
        match = re.fullmatch(r'\s*(?:пожалуйста[, ]+)?(?:открой|открыть|запусти|запустить|open|launch)\s+(?:приложение\s+|программу\s+)?(.+?)\s*[.!]?\s*',text,re.I)
        if not match or not any(s['name']=='devices.open_app' and s.get('enabled',True) for s in specifications):
            return previous
        name = match[1]
        if re.search(r'[/\\:]|\b(папку|файл|сайт|пространство|folder|file|workspace|website)\b',name,re.I):
            return previous
        parts = re.split(r'\s+(?:на|on)\s+', name, maxsplit=1, flags=re.I)
        arguments = {'app_name':parts[0].strip(' «»"')}
        if len(parts)==2 and parts[1].casefold() not in {'этом компьютере','текущем компьютере','этом устройстве'}:
            arguments['device_name'] = parts[1].strip(' «»"')
        elif context.get('device_id'):
            arguments['device_id'] = context['device_id']
        elif len(parts)==2:
            return IntentDecision(confidence=1,clarification='Выберите текущий компьютер или укажите его имя.')
        return IntentDecision(call=ToolCall(name='devices.open_app',arguments=arguments),confidence=.99)
