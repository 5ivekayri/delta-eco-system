import argparse
import asyncio
import json
import logging
import os
from pathlib import Path
from uuid import uuid4
from threading import Event

from websockets.asyncio.client import connect
from delta_contracts.devices import Registration
from .commands import CommandExecutor
from .platforms import get_platform

logger = logging.getLogger("delta-agent")


def persistent_uid(directory: Path) -> str:
    directory.mkdir(parents=True, exist_ok=True)
    file = directory / "device_uid"
    if not file.exists():
        try:
            with file.open("x") as output:
                output.write(str(uuid4()))
        except FileExistsError:
            pass
    return file.read_text().strip()


async def run_agent(url: str, token: str, name: str | None, config_dir: Path, allowed_roots: list[str],
                    *, capabilities=None, allowed_apps=None, on_event=None, adapter=None, permission=None, confirm=None):
    def event(kind, **data):
        if on_event:
            on_event({'event': kind, **data})
    adapter = adapter or get_platform()
    capabilities = adapter.capabilities if capabilities is None else capabilities
    info = adapter.get_system_info()
    executor = CommandExecutor(adapter, allowed_roots, capabilities, allowed_apps, permission, confirm)
    applications = [item.public() for item in executor.applications().values()] if 'open_app' in capabilities else []
    applications += [{'id': key, 'name': label} for key, label in [('browser','Браузер'),('vscode','Visual Studio Code')]
                     if key in executor.allowed_apps and 'open_app' in capabilities
                     and not any(label.casefold() == item['name'].casefold() for item in applications)]
    registration = Registration(device_uid=persistent_uid(config_dir), display_name=name or info["hostname"],
                                capabilities=capabilities, applications=applications[:1024], approval_timeout=60 if confirm else 0, **info)
    delay = 1
    while True:
        try:
            event('connecting')
            async with connect(url, additional_headers={"Authorization": f"Bearer {token}"},
                               max_size=1_000_000, open_timeout=10) as socket:
                await socket.send(registration.model_dump_json())
                ack = json.loads(await asyncio.wait_for(socket.recv(), 10))
                if ack.get("type") != "register_ack":
                    raise ValueError("Expected registration acknowledgement")
                logger.info(json.dumps({"event": "connected", "device_id": ack["device_id"]}))
                event('connected', device_id=ack['device_id'])
                delay = 1

                async def heartbeat():
                    while True:
                        await socket.send('{"type":"heartbeat"}')
                        await asyncio.sleep(ack["heartbeat_interval"])

                heartbeat_task = asyncio.create_task(heartbeat())
                cancelled = Event()
                command_lock = asyncio.Lock()
                jobs = set()
                async def handle(message):
                    async with command_lock:
                        result = await asyncio.to_thread(executor.execute, message, cancelled)
                        await socket.send(json.dumps(result))
                        event('command', success=result['success'], action=message.get('action'), error_code=result.get('error_code'))
                try:
                    async for raw in socket:
                        message = json.loads(raw)
                        if message.get('type') == 'command':
                            if len(jobs) >= 16:
                                await socket.send(json.dumps({'type':'command_result', 'command_id':str(message.get('command_id','')),
                                    'success':False, 'message':'На компьютере уже ожидают команды.', 'error_code':'AGENT_BUSY', 'data':{}}))
                                continue
                            job = asyncio.create_task(handle(message))
                            jobs.add(job)
                            def completed(task):
                                jobs.discard(task)
                                if not task.cancelled():
                                    task.exception()  # Observe send failures; the reader handles disconnection.
                            job.add_done_callback(completed)
                finally:
                    cancelled.set()
                    for job in list(jobs):
                        job.cancel()
                    await asyncio.gather(*jobs, return_exceptions=True)
                    heartbeat_task.cancel()
                    await asyncio.gather(heartbeat_task, return_exceptions=True)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            if type(error).__name__ == 'InvalidStatus':
                event('auth_required')
                return
            # Exception text may contain request headers; log type only.
            logger.warning(json.dumps({"event": "reconnecting", "error_type": type(error).__name__, "delay": delay}))
            event('reconnecting', error_type=type(error).__name__, delay=delay)
        await asyncio.sleep(delay)
        delay = min(delay * 2, 30)


def main():
    parser = argparse.ArgumentParser(description="Delta desktop Agent")
    parser.add_argument("--url", default=os.environ.get("DELTA_CORE_WS", "ws://127.0.0.1:8000/ws/agents"))
    parser.add_argument("--name")
    parser.add_argument("--config-dir", type=Path, default=Path.home() / ".delta-agent")
    parser.add_argument("--allow-root", action="append", default=[])
    args = parser.parse_args()
    token = os.environ.get("DELTA_TOKEN", "")
    if len(token) < 16:
        parser.error("Set DELTA_TOKEN (at least 16 characters) in the environment")
    if not args.url.startswith(("ws://", "wss://")):
        parser.error("Core URL must use ws:// or wss://")
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        asyncio.run(run_agent(args.url, token, args.name, args.config_dir, args.allow_root))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
