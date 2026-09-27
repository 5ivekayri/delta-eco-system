"""Bound the voice HTTP body before multipart parsing, including chunked uploads."""
from starlette.responses import JSONResponse
from .telemetry import VoiceTimings
from time import perf_counter


class VoiceUploadLimit:
    def __init__(self, app, max_bytes: int):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope['path'] != '/api/v1/assistant/voice' or scope['method'] != 'POST':
            return await self.app(scope, receive, send)
        timings = VoiceTimings()
        scope.setdefault('state', {})['voice_timings'] = timings
        body = bytearray()
        while True:
            message = await receive()
            if message['type'] == 'http.disconnect':
                return
            body.extend(message.get('body', b''))
            if len(body) > self.max_bytes:
                response = JSONResponse({'success': False, 'error_code': 'AUDIO_TOO_LARGE',
                                         'message': 'Аудиозапись слишком большая. Запишите более короткое сообщение.'}, status_code=413)
                return await response(scope, receive, send)
            if not message.get('more_body', False):
                break
        timings.upload_ms = (perf_counter() - timings.started) * 1000
        delivered = False
        async def bounded_receive():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {'type': 'http.request', 'body': bytes(body), 'more_body': False}
            return await receive()
        await self.app(scope, bounded_receive, send)
