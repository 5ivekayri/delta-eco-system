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

The desktop client advertises only locally enabled capabilities and enforces them
again on receipt. Application IDs also require local approval. A timed-out native
opener returns `ACTION_TIMEOUT`; this does not prove that the OS did not perform
the action, so it is never retried. OS filesystem permission errors return
`LOCAL_PERMISSION_REQUIRED`. Setup and packages: [Desktop Agent](DESKTOP_AGENT.md).

## Errors

```json
{"type":"error","success":false,"error_code":"CAPABILITY_NOT_SUPPORTED","message":"Action is not supported by this device"}
```

A failed command result also includes `command_id` so its caller can resolve the pending operation. Authentication failure closes the socket. Disconnect/reconnect uses bounded backoff; heartbeat and command processing must not block one another.

### Desktop approvals

Registration may include `approval_timeout` (integer 0–60 seconds, default 0).
Core stores it on the connection only, without a database migration. For clients
with a nonzero approval timeout, dispatch adds this budget to COMMAND_TIMEOUT and
includes `expires_at` (Unix seconds) in the command. Legacy clients receive the
original message without this field. Desktop clients wait at most 60 seconds and
check expiry/cancellation again before invoking the platform adapter.

Local command policy is applied after payload/app/root validation. Declines return
`APPROVAL_DECLINED`, local deny `COMMAND_DENIED`, stale/cancelled requests
`COMMAND_EXPIRED`, and saturated queues `AGENT_BUSY`. Denied capabilities are not
advertised. OS actions are never automatically replayed. Receipt continues during
approval so a disconnected session cancels pending approvals. A running, already
approved OS action cannot be undone by disconnecting.

## Installed application catalogue (Agent 0.2.0)

Registration optionally includes `applications`: a list of `{id,name,aliases}`
(up to 1024 entries). Missing/null means legacy Agent; an empty list means no
permitted applications. Core keeps this catalogue on the live connection, not in
the database. Reconnect/restart Agent after installing/removing apps or changing
permissions. Core must be updated before deploying this client.

`open_app.app_id` accepts bounded logical IDs (`[A-Za-z0-9_.-]+`), including
`installed-<24 hex characters>`. The Agent maps IDs only to locally discovered
installed apps and resolves again before launch. No remote path, argument list,
shell, executable text or URL is accepted as an application ID. macOS uses
`/usr/bin/open -a` with a discovered .app bundle; Linux uses `gio launch` for an
installed .desktop entry; Windows uses Start Menu .lnk entries. Catalogue scanning
skips links that escape the configured installation directories. Filesystem paths
are not transmitted in the catalogue. Some apps outside standard install locations
will require moving/installing them into those locations.

`allow_installed_apps=true` enables discovered applications, while local
open_app deny/ask/allow, confirmation, expiry and disconnect cancellation still
apply. Defaults use confirmation. Existing explicit deny remains deny. The
confirmation dialog shows the locally resolved application name. Success means
the OS launcher accepted the command; it is not a screenshot/foreground guarantee.

Core exposes `devices.list_apps` and `devices.open_app` registered tools. An
explicit target overrides the selected device. Without a target Core only launches
a unique permitted app on one connected, catalogue-capable device. Ambiguous
targets/names require clarification; an explicit offline/unsupported target never
falls back to another computer. Legacy Agents return AGENT_UPDATE_REQUIRED, not
a generic model refusal. A failed command is never presented as a successful open.
