# Virtual IoT — phase 8

Core provides a virtual desk light and three sensor readings. These are explicitly
labeled emulated values; no physical sensor, GPIO, MQTT or Raspberry Pi is used.
The initial state is light off, temperature 23 °C, brightness 30%, motion detected.
Sensor readings are fixed demo values in this phase; only the light is user-writable.
Brightness means ambient light level, not the desk-light dimmer.

## State and boundaries

`IoTAdapter` exposes asynchronous `get_state` and `set_light` methods returning a
shared `IoTState` contract. HTTP routes and registered tools depend on this boundary.
`VirtualIoTAdapter` stores a singleton row in Core's database. A future MQTT adapter
can implement the same contract; AssistantService and tool dispatch do not need to
know which adapter is installed. The current app composition installs the virtual
adapter explicitly; no unimplemented real-hardware mode is advertised.

Migration `0005` creates and seeds `virtual_iot_state`. Startup/restart does not
reset values. First-use initialization also supports fresh test databases created
with metadata; a unique singleton key and savepoint handle initialization races.
PostgreSQL row locks serialize updates. A changed light value and its `IOT_ACTION`
event commit in the same transaction. Setting an already-current value is
idempotent and creates no extra state-change event. SQL errors do not return a
fabricated success. Core never reads the Tasks database.

## Authenticated API

- `GET /api/v1/iot/state`: `source`, `desk_light`, `temperature`, `brightness`,
  `motion`, `updated_at`.
- `POST /api/v1/iot/light`: `{ "enabled": true }` or `{ "enabled": false }`;
  returns the confirmed full state.

Both require the existing development bearer token. The light input is a strict
boolean: strings, numbers, null, missing fields and extra fields are rejected.
There is one default desk light; named device targeting is not supported by its
schema and is not silently ignored. Commands set a desired value rather than
requesting a server-side toggle. Neither the UI nor adapter automatically retries
a write after an uncertain network outcome.

## Assistant tools

| Registered tool | Result | Example local phrase |
|---|---|---|
| iot.set_light | enabled, source | «Включи рабочий свет», «Выключи свет» |
| iot.get_temperature | temperature, unit=C, source | «Какая температура?» |
| iot.get_brightness | brightness, unit=percent, source | «Покажи освещённость» |
| iot.get_motion | motion, source | «Есть ли движение?» |

Tools use the same adapter as the UI. The registry validates arguments and remains
the execution boundary. Recognized simple commands execute once with zero LLM
completions and factual result-based responses. Other requests retain the existing
LLM fallback. Voice commands use the existing Whisper/Piper pipeline; the IoT module
contains no separate speech or LLM implementation.

## Web UI

Open **Virtual IoT** at http://localhost:8080. The page shows all four values and
lets you switch the desk light. It displays the confirmed response rather than
optimistically claiming a write succeeded. A three-second poll synchronizes changes
made by Assistant or another client; older in-flight reads cannot overwrite a newer
confirmed write. Reloading or restarting Core preserves the state.

Errors show either an explicit empty/error state or clearly marked last-known
values. Controls are disabled while writing or while the displayed state is stale
following an error. A manual refresh is available. Read-only sensor values remain
labeled virtual; the UI does not generate random measurements.

## Setup and verification

Normal `docker compose up --build -d` applies the Core migration. No extra service,
credential or dependency is required. Existing database data is preserved.

Backend tests cover defaults, persistence, idempotence/audit, authorization, strict
validation, adapter substitution, rollback on audit failure, migration upgrade and
downgrade, and text/voice tool execution without an LLM. Browser tests cover the real
switch, reload, Assistant changes, polling, API failure and stale-read ordering.

Verified on 2026-09-27: 163 backend tests, one frontend unit test and all 19 Chrome
scenarios passed. Normal Compose build/migration and Python/frontend builds passed.
Live PostgreSQL state and its timestamp survived Core restart. Real Whisper/Piper
requests for light on, light off and temperature completed the server pipeline in
3.37 / 3.64 / 3.65 seconds, with exactly one tool and zero LLM completions each.
TTS took 363 / 326 / 605 ms. These used synthetic Russian audio; original light
state was restored afterward.
