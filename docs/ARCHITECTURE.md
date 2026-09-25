# Delta Digital Ecosystem — architecture

Delta connects personal computers and independent services through a single text and voice interface. Core owns device/workspace state, assistant history, activity and virtual IoT. Tasks owns task state exclusively. The browser calls their versioned APIs through a same-origin gateway. The host Agent connects to Core over authenticated WebSocket; it does not run in Docker.

## Boundaries

- **Core:** FastAPI modular monolith; separate modules for devices, commands, workspaces, services, tools, assistant, LLM, voice, activity and IoT.
- **Tasks:** separate FastAPI process, SQLAlchemy metadata, Alembic migrations and PostgreSQL database/user. Core uses HTTP only.
- **Agent:** persistent local device UID, reconnect/heartbeat loop, validated messages, capability allowlist and platform adapters. Logical application identifiers resolve locally.
- **Control Center:** React/TypeScript with typed API layer, shared components, periodic status refresh, microphone capture and audio playback.
- **Storage:** one PostgreSQL instance, two independent databases and users; no cross-service queries or foreign keys.

## Request flow

Text or recorded browser audio enters Core. Local STT produces text. LLMProvider receives context and enabled tool schemas; it returns structured calls. Tool Router validates arguments and dispatches to a local handler or manifest-defined HTTP adapter. Results and activity are persisted. Assistant returns text and optional local TTS audio. Provider failures have explicit error codes; TTS failure preserves successful tool execution and text.

Service manifests describe identity, health route, tools, input schemas, permissions and HTTP mapping. Registration is configuration-driven in v0.1. A new external service requires a manifest/config entry, not assistant business logic. A deterministic MockLLM supports documented demo phrases; OpenRouter supports general tool selection.

## Devices and workspaces

Core correlates command UUIDs with the originating WebSocket and rejects unmatched results. Disconnect/heartbeat expiry marks devices offline. Commands time out without automatic replay. Workspace launch resolves an explicit target or current-device context, checks binding/capabilities, sends allowlisted operations and reports individual results, including partial failure. Paths belong to per-device bindings, not workspace identity.

## Trust and runtime

Development bearer token is configured at runtime. Bind public development ports to loopback. Remote deployment requires TLS and a trusted network; pairing and per-user permissions are future work. LLM cannot access databases, execute shell, or supply arbitrary binaries. Use one Core worker in v0.1 because active sockets and pending commands are process-local.

## Future interfaces

IoTAdapter initially uses persistent virtual state. A future MQTT adapter connects Core → Mosquitto → Raspberry Pi sensors/GPIO without changing tools. Dark Weather will be an independent registered service. Neither is implemented in MVP. Future authentication may replace the development token without changing service boundaries.

Diagrams and verified deployment details will be added with the corresponding implementation phases.
