"""Conservative contextual task references, independent of AssistantService."""
import re
from jsonschema import Draft202012Validator, FormatChecker
from delta_contracts.tools import ToolCall
from .intents import IntentDecision, normalized
from .responses import deterministic_response


class ConversationIntentRouter:
    def __init__(self, fallback, task_lookup):
        self.fallback = fallback
        self.task_lookup = task_lookup

    async def route(self, text, specifications, context):
        command = re.fullmatch(
            r'\s*(заверши|закрой|удали|переименуй)\s+(.+?)\s*[.!]?\s*', text, re.I)
        priority = re.fullmatch(r'\s*(?:поставь|установи|задай)\s+(ей|ей задаче|этой задаче|этому заданию)\s+(высокий|средний|низкий)\s+приоритет[.!]?\s*', text, re.I)
        updates = {}
        if priority:
            reference = priority[1]
            name = 'tasks.update'
            updates = {'priority': {'высокий':'high','средний':'medium','низкий':'low'}[priority[2].lower()]}
        elif command:
            action, reference = command[1].lower(), command[2].strip()
            name = {'заверши':'tasks.complete','закрой':'tasks.complete','удали':'tasks.delete','переименуй':'tasks.update'}[action]
            if action == 'переименуй':
                parts = re.split(r'\s+в\s+', reference, maxsplit=1, flags=re.I)
                if len(parts) != 2:
                    return await self.fallback.route(text, specifications, context)
                reference, title = parts
                updates = {'title': title.strip(' «»"')}
        else:
            return await self.fallback.route(text, specifications, context)
        # Only explicit references supported here; complex instructions stay with the LLM.
        ref = normalized(reference)
        ordinal = {'первую':0, 'вторую':1, 'третью':2, 'четвертую':3, 'первое':0, 'второе':1, 'третье':2}
        ref = re.sub(r'\s+(задачу|задание)$', '', ref)
        pronoun = ref in {'ее', 'его', 'ей', 'эту', 'это', 'эту задачу', 'это задание', 'этой задаче', 'этому заданию'}
        index = ordinal.get(ref)
        if not pronoun and index is None:
            # Explicit title: resolve only an exact unique match in current Tasks data.
            # 'задание номер 6' may itself be the title, not a numeric database ID.
            if not re.match(r'^(?:задачу|задание)\s+', normalized(reference)) or updates:
                return await self.fallback.route(text, specifications, context)
            title = re.sub(r'^(?:задачу|задание)\s+', '', normalized(reference)).strip(' «»"')
            live = await self.task_lookup()
            matches = [row for row in live if normalized(row.get('title', '')) in {title, normalized(reference)}]
            spec = next((s for s in specifications if s['name'] == name and s.get('enabled', True)), None)
            if len(matches) != 1 or spec is None:
                return IntentDecision(confidence=1.0, clarification='Не удалось однозначно найти задачу с таким названием. Уточните название или покажите список задач.')
            arguments = {'id': str(matches[0]['id'])}
            if not Draft202012Validator(spec['input_schema'], format_checker=FormatChecker()).is_valid(arguments):
                return IntentDecision()
            return IntentDecision(ToolCall(name=name, arguments=arguments), .99)
        spec = next((s for s in specifications if s['name'] == name and s.get('enabled', True)), None)
        if spec is None:
            return IntentDecision()
        def clarify():
            return IntentDecision(confidence=1.0, clarification='Уточните, какую задачу вы имеете в виду: укажите её название или номер в последнем показанном списке.')
        rows = None
        for turn in reversed(context.get('recent_interactions', [])):
            results = turn.get('tool_results', [])
            task_results = [r for r in results if r.get('tool', '').startswith('tasks.')]
            if task_results:
                # Never reach past a failed/deleted/ambiguous most-recent task result.
                if len(task_results) != 1 or not task_results[0].get('success') or task_results[0]['tool'] == 'tasks.delete':
                    return clarify()
                if index is not None and turn.get('assistant_text') != deterministic_response(task_results[0]):
                    return clarify()
                data = task_results[0].get('data')
                rows = data if isinstance(data, list) else [data] if isinstance(data, dict) else []
                break
            # A different entity/action changes focus; don't act on an older task.
            if results:
                return clarify()
        if not rows or (pronoun and len(rows) != 1) or (index is not None and index >= len(rows)):
            return clarify()
        target = rows[0 if index is None else index]
        if not isinstance(target, dict) or not target.get('id'):
            return clarify()
        # Resolve through the Tasks service, never through Core's database or stale snapshots.
        live = await self.task_lookup()
        if sum(str(row.get('id')) == str(target['id']) for row in live) != 1:
            return clarify()
        arguments = {'id': str(target['id']), **updates}
        if not Draft202012Validator(spec['input_schema'], format_checker=FormatChecker()).is_valid(arguments):
            return clarify()
        return IntentDecision(ToolCall(name=name, arguments=arguments), .99)
