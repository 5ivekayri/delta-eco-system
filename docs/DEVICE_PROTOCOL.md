# Agent WebSocket protocol

Implemented in phase 2 at `/ws/agents`. All messages are JSON objects. Agent authenticates with the configured development bearer token at the handshake. Core and Agent validate message type and payload; invalid input produces a structured error rather than executable text.

## Registration

Agent persists a randomly generated `device_uid` in its local configuration directory. Hostname is display metadata, not stable identity. On connect it sends:

```json
{"type":"register","device_uid":"local-persistent-uuid","hostname":"my-laptop","display_name":"My laptop","os":"macos","architecture":"arm64","username":"user","agent_version":"0.1.0","capabilities":["system_info","open_url","open_path","open_app"]}
```

Core upserts by UID and responds:

```json
{"type":"register_ack","device_id":"core-device-uuid","heartbeat_interval":10}
```

Registration must precede commands/heartbeat. Reconnecting the same UID must not create duplicate devices. A new connection replaces the old connection explicitly; a late disconnect from the old socket must not mark the new connection offline.

## Heartbeats and capabilities

```json
{"type":"heartbeat"}
```

Core updates `last_seen` using server time. Configurable expiry marks the device offline and fails pending requests. A clean disconnect does the same immediately. `capabilities_update` contains the validated replacement capability list.

## Commands and results

```json
{"type":"command","command_id":"command-uuid","action":"open_url","payload":{"url":"https://example.com"}}
```

```json
{"type":"command_result","command_id":"command-uuid","success":true,"message":"URL opened","data":{}}
```

Allowed actions: `system_info` (empty payload), `open_url` (`url`), `open_path` (`path`), `open_app` (`app_id`). Agent validates again even if Core already validated. Logical app IDs resolve through its platform adapter. Local path access is limited by Agent configuration. No shell action exists.

Core matches command ID **and originating device connection**. Ignore/reject unknown or duplicate results. Record command/result in activity; don't leak bearer tokens. Bounded timeout is reported separately from a negative Agent result. Never replay desktop actions automatically after reconnect or timeout.

## Errors

```json
{"type":"error","success":false,"error_code":"CAPABILITY_NOT_SUPPORTED","message":"Action is not supported by this device"}
```

A failed command result also includes `command_id` so its caller can resolve the pending operation. Authentication failure closes the socket. Disconnect/reconnect uses bounded backoff; heartbeat and command processing must not block one another.
