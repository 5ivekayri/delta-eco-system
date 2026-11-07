"""Loopback inference bridge. Produces tool proposals; never executes tools."""
import asyncio
from contextlib import asynccontextmanager, suppress
import hmac
import json
import os
from pathlib import Path
import signal
import sys
import time

import httpx
import jsonschema
from dotenv import dotenv_values
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from typing import Literal

ROOT = Path(__file__).resolve().parent


class BackendFailure(Exception):
    pass


class LocalRuntime:
    def __init__(self, config):
        self.config = config
        self.process = None
        self.lock = asyncio.Lock()
        self.log = None

    async def start(self):
        async with self.lock:
            if self.process and self.process.returncode is None:
                return
            binary = str((ROOT/self.config['binary']).resolve())
            model = str((ROOT/self.config['model_file']).resolve())
            if not Path(binary).is_file() or not Path(model).is_file():
                raise BackendFailure('Local model/runtime files missing')
            self.log = open(ROOT/'runtime.log', 'a')
            # Guard installs Linux parent-death signal before exec. No shell is used.
            args = [sys.executable, str(ROOT/'parent_guard.py'), str(os.getpid()), binary,
                    '-m', model, '--host', '127.0.0.1', '--port', str(self.config['local_port']),
                    '-c', '16384', '-np', '1', '-t', '4', '-ngl', '99', '--device', self.config.get('device', 'Vulkan1'), '--jinja',
                    '--alias', 'delta-local', '--reasoning-budget', '0']
            self.process = await asyncio.create_subprocess_exec(*args, stdin=asyncio.subprocess.DEVNULL,
                stdout=self.log, stderr=asyncio.subprocess.STDOUT)
            try:
                async with asyncio.timeout(self.config['startup_timeout']):
                    async with httpx.AsyncClient() as client:
                        while True:
                            if self.process.returncode is not None:
                                raise BackendFailure('Local runtime exited during startup')
                            try:
                                if (await client.get(self.url+'/health', timeout=1)).status_code == 200:
                                    return
                            except httpx.HTTPError:
                                pass
                            await asyncio.sleep(.2)
            except BaseException:
                await self._stop()
                raise

    @property
    def url(self):
        return f"http://127.0.0.1:{self.config['local_port']}"

    async def _stop(self):
        if self.process and self.process.returncode is None:
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), 5)
            except asyncio.TimeoutError:
                self.process.kill()
                await self.process.wait()
        self.process = None
        if self.log:
            self.log.close()
            self.log = None

    async def stop(self):
        async with self.lock:
            await self._stop()


def validate_reply(body, payload):
    try:
        choice = body['choices'][0]
        if choice.get('finish_reason') == 'length':
            raise ValueError('truncated')
        message = choice['message']
        calls = message.get('tool_calls') or []
        if not isinstance(calls, list) or len(calls) > 1:
            raise ValueError('only one tool proposal at a time')
        allowed = {t['function']['name']: t['function']['parameters'] for t in payload.get('tools', [])}
        for call in calls:
            fn = call['function']
            args = json.loads(fn['arguments'])
            jsonschema.validate(args, allowed[fn['name']])
        if not calls and not (message.get('content') or '').strip():
            raise ValueError('empty')
        return body
    except (KeyError, IndexError, TypeError, ValueError, AttributeError, jsonschema.ValidationError, jsonschema.SchemaError):
        raise BackendFailure('Invalid model reply or tool proposal') from None


class Bridge:
    def __init__(self, config, api_key, client=None, runtime=None):
        self.config = config
        self.api_key = api_key
        self.client = client or httpx.AsyncClient(timeout=60)
        self.runtime = runtime or LocalRuntime(config)
        self.mode = config.get('mode', 'auto')
        self.lock = asyncio.Lock()
        self.active = 0
        self.last_use = time.monotonic()
        self.cloud_retry_at = 0.
        self.last_backend = None
        self.last_reason = None
        self.core_ready = True
        self.stopping = False

    async def cloud(self, payload):
        if not self.api_key:
            raise BackendFailure('OpenRouter key is not configured')
        # Coding requests need room for complete files; simple commands retain the short deadline.
        timeout=max(self.config['cloud_timeout'],45) if payload.get('max_tokens',0)>1200 else self.config['cloud_timeout']
        async with asyncio.timeout(timeout):
            response = await self.client.post('https://openrouter.ai/api/v1/chat/completions',
                headers={'Authorization': 'Bearer '+self.api_key}, json=payload)
            response.raise_for_status()
            return validate_reply(response.json(), payload)

    async def vision(self, payload):
        if self.mode == 'local' or not self.config.get('vision_model'):
            raise BackendFailure('Local model does not support screen images')
        payload = {**payload, 'model': self.config['vision_model']}
        payload.pop('tools', None)
        payload.pop('tool_choice', None)
        async with asyncio.timeout(self.config.get('vision_timeout', 45)):
            response = await self.client.post('https://openrouter.ai/api/v1/chat/completions',
                headers={'Authorization': 'Bearer '+self.api_key}, json=payload)
            response.raise_for_status()
            return validate_reply(response.json(), payload)

    async def local(self, payload):
        async with self.lock:
            if self.stopping or not self.core_ready:
                raise BackendFailure('Core is stopped')
            await self.runtime.start()
            local_payload = {k: v for k, v in payload.items() if k in
                {'messages', 'tools', 'tool_choice', 'temperature', 'max_tokens'}}
            local_payload.update(model='delta-local', parallel_tool_calls=False,
                                 chat_template_kwargs={'enable_thinking': False})
            async with asyncio.timeout(self.config['local_timeout']):
                response = await self.client.post(self.runtime.url+'/v1/chat/completions', json=local_payload)
                response.raise_for_status()
                return validate_reply(response.json(), local_payload)

    async def respond(self, payload):
        if self.stopping or not self.core_ready:
            raise BackendFailure('Core is stopped or unavailable')
        if self.active >= 2:
            raise BackendFailure('Bridge is busy; retry later')
        self.active += 1
        try:
            has_image = any(isinstance(message.get('content'), list) and
                            any(isinstance(part, dict) and part.get('type') == 'image_url' for part in message['content'])
                            for message in payload.get('messages', []))
            if has_image:
                result = await self.vision(payload)
                self.last_backend, self.last_reason = 'openrouter-vision', None
                return result
            mode = self.mode  # One routing decision per request.
            if mode in {'openrouter', 'auto'} and (mode == 'openrouter' or time.monotonic() >= self.cloud_retry_at):
                try:
                    result = await self.cloud(payload)
                    self.last_backend, self.last_reason = 'openrouter', None
                    self.cloud_retry_at = 0
                    return result
                except (BackendFailure, httpx.HTTPError, TimeoutError, ValueError):
                    self.last_reason = 'OpenRouter failed or exceeded deadline'
                    if mode == 'openrouter':
                        raise BackendFailure(self.last_reason) from None
                    self.cloud_retry_at = time.monotonic()+self.config['cooldown']
            # Cancellation is deliberately not caught: a cancelled caller cannot trigger fallback.
            async with asyncio.timeout(self.config.get('fallback_timeout', 60)):
                result = await self.local(payload)
            self.last_backend = 'local'
            return result
        finally:
            self.active -= 1
            self.last_use = time.monotonic()

    async def set_mode(self, mode):
        if self.active:
            raise HTTPException(409, 'Wait for current inference to finish')
        self.mode = mode
        self.config['mode'] = mode
        if mode == 'openrouter':
            await self.runtime.stop()
        temporary = ROOT/'state.json.tmp'
        temporary.write_text(json.dumps({'mode':mode}))
        temporary.replace(ROOT/'state.json')
        self.cloud_retry_at = 0

    async def monitor(self):
        failures = 0
        while True:
            await asyncio.sleep(2)
            try:
                response = await self.client.get(self.config['core_health'], timeout=2)
                healthy = response.status_code == 200
            except httpx.HTTPError:
                healthy = False
            failures = 0 if healthy else failures+1
            self.core_ready = failures < 2
            if not self.core_ready or (not self.active and time.monotonic()-self.last_use > self.config['idle_seconds']):
                await self.runtime.stop()

    async def close(self):
        self.stopping = True
        await self.runtime.stop()
        await self.client.aclose()


def load_configuration():
    config = json.loads((ROOT/'config.json').read_text())
    if (ROOT/'state.json').exists():
        config['mode'] = json.loads((ROOT/'state.json').read_text())['mode']
    if config['mode'] not in {'auto', 'openrouter', 'local'}:
        raise ValueError('Invalid bridge mode')
    # Read only inference credentials from the backend env; never copy it to the client.
    source = dotenv_values((ROOT/config['server_env']).resolve())
    key = os.environ.get('OPENROUTER_API_KEY') or source.get('OPENROUTER_API_KEY', '')
    return config, key


class ModeRequest(BaseModel):
    mode: Literal['auto', 'openrouter', 'local']


def create_app():
    config, key = load_configuration()
    bridge = Bridge(config, key)
    @asynccontextmanager
    async def lifespan(app):
        monitor = asyncio.create_task(bridge.monitor())
        try:
            yield
        finally:
            monitor.cancel()
            with suppress(asyncio.CancelledError):
                await monitor
            await bridge.close()
    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None)
    def auth(request):
        if not key or not hmac.compare_digest(request.headers.get('Authorization', ''), 'Bearer '+key):
            raise HTTPException(401, 'Authentication required')
    @app.get('/health')
    async def health():
        return {'status':'ok', 'core_ready':bridge.core_ready}
    @app.get('/control/status')
    async def status(request: Request):
        auth(request)
        return {'mode':bridge.mode, 'last_backend':bridge.last_backend, 'last_reason':bridge.last_reason,
                'local_running':bool(bridge.runtime.process and bridge.runtime.process.returncode is None),
                'active':bridge.active, 'core_ready':bridge.core_ready,
                'vision_available':bridge.mode != 'local' and bool(config.get('vision_model'))}
    @app.post('/control/mode')
    async def mode(request: Request, body: ModeRequest):
        auth(request)
        await bridge.set_mode(body.mode)
        return {'mode':bridge.mode}
    @app.post('/v1/chat/completions')
    async def completions(request: Request):
        auth(request)
        raw = await request.body()
        if len(raw)>1_000_000:
            raise HTTPException(413, 'Request too large')
        try:
            body = json.loads(raw)
            if not isinstance(body, dict) or not isinstance(body.get('messages'), list):
                raise ValueError()
            if body.get('stream'):
                raise HTTPException(400, 'Streaming is disabled to ensure atomic fallback')
            body['parallel_tool_calls'] = False
            body.setdefault('reasoning', {'enabled': False})
            body.setdefault('provider', {'sort': 'latency'})
            body['max_tokens'] = max(1, min(int(body.get('max_tokens', 512)), 6000))
            task = asyncio.create_task(bridge.respond(body))
            try:
                while not task.done():
                    await asyncio.wait({task}, timeout=.25)
                    if await request.is_disconnected():
                        task.cancel()
                        raise HTTPException(499, 'Caller disconnected')
                return await task
            finally:
                if not task.done():
                    task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
        except (BackendFailure, httpx.HTTPError, TimeoutError):
            raise HTTPException(503, 'Inference unavailable; no tool has been executed by the bridge') from None
        except (ValueError, TypeError):
            raise HTTPException(400, 'Invalid request') from None
    return app
