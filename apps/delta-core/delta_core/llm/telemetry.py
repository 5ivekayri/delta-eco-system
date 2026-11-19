"""Opt-in request-local inference metadata, never prompts or credentials."""
from contextvars import ContextVar

requests: ContextVar[list | None] = ContextVar('llm_requests', default=None)


def record(**entry):
    entries = requests.get()
    if entries is not None and len(entries) < 32:
        entries.append(entry)


def snapshot():
    entries = requests.get()
    return {'llm_requests': list(entries)} if entries is not None else {}


class InferenceDiagnostics:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        enabled = dict(scope.get('headers', [])).get(b'x-delta-llm-log') == b'1'
        token = requests.set([] if enabled else None)
        try:
            await self.app(scope, receive, send)
        finally:
            requests.reset(token)
