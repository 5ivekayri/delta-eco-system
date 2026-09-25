import argparse
import asyncio
from contextlib import suppress
import json
import logging
import os
from pathlib import Path
from uuid import uuid4

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


async def run_agent(url: str, token: str, name: str | None, config_dir: Path, allowed_roots: list[str]):
    adapter = get_platform()
    info = adapter.get_system_info()
    registration = Registration(device_uid=persistent_uid(config_dir), display_name=name or info["hostname"],
                                capabilities=adapter.capabilities, **info)
    executor = CommandExecutor(adapter, allowed_roots)
    delay = 1
    while True:
        try:
            async with connect(url, additional_headers={"Authorization": f"Bearer {token}"},
                               max_size=1_000_000, open_timeout=10) as socket:
                await socket.send(registration.model_dump_json())
                ack = json.loads(await asyncio.wait_for(socket.recv(), 10))
                if ack.get("type") != "register_ack":
                    raise ValueError("Expected registration acknowledgement")
                logger.info(json.dumps({"event": "connected", "device_id": ack["device_id"]}))
                delay = 1

                async def heartbeat():
                    while True:
                        await socket.send('{"type":"heartbeat"}')
                        await asyncio.sleep(ack["heartbeat_interval"])

                heartbeat_task = asyncio.create_task(heartbeat())
                try:
                    async for raw in socket:
                        message = json.loads(raw)
                        if message.get("type") == "command":
                            result = await asyncio.to_thread(executor.execute, message)
                            await socket.send(json.dumps(result))
                finally:
                    heartbeat_task.cancel()
                    with suppress(asyncio.CancelledError, Exception):
                        await heartbeat_task
        except asyncio.CancelledError:
            raise
        except Exception as error:
            # Exception text may contain request headers; log type only.
            logger.warning(json.dumps({"event": "reconnecting", "error_type": type(error).__name__, "delay": delay}))
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
