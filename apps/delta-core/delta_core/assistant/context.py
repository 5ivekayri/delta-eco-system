"""Durable conversation context shared by text and voice, bounded per request."""
import json
from sqlalchemy import select
from .models import Interaction

MAX_TURNS = 12
MAX_HISTORY_CHARS = 30000


def compact(value, depth=0):
    if depth > 5:
        return '[nested data omitted]'
    if isinstance(value, str):
        return value if len(value) <= 1200 else value[:1200] + ' [truncated]'
    if isinstance(value, list):
        return [compact(item, depth + 1) for item in value[:20]]
    if isinstance(value, dict):
        return {key: compact(item, depth + 1) for key, item in list(value.items())[:24]}
    return value


def load_conversation(session):
    # Same single-user conversation displayed by /history. No device filter:
    # selecting a different target computer must not discard the dialogue.
    rows = list(session.scalars(select(Interaction).order_by(
        Interaction.created_at.desc(), Interaction.id.desc()).limit(MAX_TURNS)))
    blocks, recent, used = [], [], 0
    for row in rows:
        results = compact(row.tool_results or [])
        for result in results:
            if result.get('tool', '').startswith('tasks.') and isinstance(result.get('data'), list):
                result['data'] = [{key: value for key, value in task.items()
                                   if key in {'id', 'title', 'status', 'priority', 'workspace_id', 'due_date'}}
                                  for task in result['data'] if isinstance(task, dict)]
        block = [{'role': 'user', 'content': compact(row.user_message)}]
        if results:
            calls = []
            for index, result in enumerate(results):
                original = row.tool_calls[index] if index < len(row.tool_calls or []) else {}
                calls.append({'id': f"history_{row.id.replace('-', '')}_{index}", 'type': 'function',
                              'function': {'name': result.get('tool', 'unknown'),
                                           'arguments': json.dumps(compact(original.get('arguments', {})), ensure_ascii=False)}})
            block.append({'role': 'assistant', 'content': None, 'tool_calls': calls})
            block.extend({'role':'tool','tool_call_id':call['id'], 'content':json.dumps(result, ensure_ascii=False)}
                         for call, result in zip(calls, results))
        block.append({'role':'assistant', 'content':compact(row.assistant_text)})
        size = len(json.dumps(block, ensure_ascii=False))
        if used + size > MAX_HISTORY_CHARS:
            break
        used += size
        blocks.append(block)
        recent.append({'user_message': row.user_message, 'assistant_text': row.assistant_text,
                       'tool_results': results})
    return [message for block in reversed(blocks) for message in block], list(reversed(recent))
