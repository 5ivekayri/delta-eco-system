# Implementation checklist

- [x] Inspect repository and read prompt.rtf.
- [x] Record architecture, scope and repository rules before implementation.
- [x] Phase 1: structure, Compose/PostgreSQL, Core/Tasks/UI skeletons, health, config, logging.
- [x] Phase 2: devices, WebSocket, Agent/platforms, heartbeat/offline, device UI/details.
- [x] Phase 3: Tasks CRUD/filtering/tests/UI, manifest and Service Registry.
- [x] Phase 4: workspace CRUD, bindings, launch and UI.
- [ ] Phase 5: Tool Registry, Mock/OpenRouter providers, assistant/history/UI.
- [ ] Phase 6: browser recording, Whisper/mock STT, voice endpoint/transcript.
- [ ] Phase 7: Piper/mock TTS, playback and fallback states.
- [ ] Phase 8: IoT adapter, persistent virtual state, tools and UI.
- [ ] Phase 9: activity, service health, refresh and debug details.
- [ ] Phase 10: full tests, docs, seeds, visual polish and acceptance scenarios.

Each phase must pass build/tests/backend/frontend checks before the next phase. Record commands, outcomes and unverified environment-dependent checks below. Never mark a phase complete just because files exist.

## Environment inspection

2026-09-25: repository initially contains only prompt.rtf. macOS system Python is 3.9.6; Python 3.12+, Node/npm and Docker are not on PATH. Required runtimes must be provisioned before phase verification.

## Phase 1 verification (in progress)

- Installed user-local Python 3.12.14 through uv; project dependencies isolated in `.venv` and locked in `uv.lock`/`requirements.lock`.
- Installed user-local Node.js 22.23.0; frontend dependencies locked in `package-lock.json`.
- `pytest -q`: 3 passed (health of both services, authentication boundary, unavailable database). SQLite is used only for these isolated tests.
- `uv build`: wheel and source distribution built successfully.
- `npm test`: 1 passed (API authentication header and structured error handling).
- `npm run build`: TypeScript and Vite production build passed.
- Playwright with installed Chrome at 1366×768: 1 passed; real Core status through Vite proxy, session token, navigation collapse, no horizontal overflow.
- npm audit after updating Vitest: 0 vulnerabilities.
- Core and Tasks run independently on loopback ports 8000/8001 for smoke checks.
- PostgreSQL and Docker Compose startup: pending Docker runtime installation. Phase 1 remains unchecked until this passes.
- Docker Desktop 29.8.0 / Compose 5.5.1 installed under user Applications and started. Compose configuration validates.
- First container attempt exposed a macOS bind-mount execute-permission problem in PostgreSQL initialization. Fixed by baking the init script into a PostgreSQL image with explicit permissions.
- Fresh `delta-verify` volume initializes successfully. SQL checks confirm `delta_core` can connect only to `delta_core` and `delta_tasks` only to `delta_tasks`.
- Original development volume recovered by running its previously failed initialization script, without deleting data.
- Clean Compose build/start passed; Core and Tasks healthy against PostgreSQL. Production UI passed the Chrome smoke test through nginx at port 8080. Phase 1 completed.

## Phase 2 verification

- 12 backend/Agent tests passed, including registration/reconnect, heartbeat, command correlation, expiry, timeout, URL/app/path rejection and platform selection.
- Python wheel/sdist, frontend production build and API-client test passed.
- Compose migrated PostgreSQL and all services became healthy.
- Real macOS host Agent: registration, system_info command/result, advancing heartbeat and disconnect→offline passed (`scripts/smoke_devices.py`). No arbitrary desktop action executed by this check.
- 2 Chrome tests passed against containerized UI, including real persisted device details.
- Windows/Linux adapters covered with mocks; native execution on those operating systems remains unverified.

## Phase 3 verification

- 14 backend tests pass, including full task lifecycle, filters, required-field validation and service discovery/offline/disabled states.
- Python build, frontend build and API-client test pass. Compose migrations and service health pass.
- Browser task create/edit/filter/complete/delete passes against the independent PostgreSQL-backed Tasks API. Services shows Delta Tasks with 6 tools.
- Browser testing exposed ambiguous accessible select labels; explicit labels fixed and scenario passed on rerun.

## Phase 4 verification

- 15 backend tests pass; workspace CRUD, duplicate-name handling, binding validation, complete/partial launch and missing-context errors covered.
- Python/frontend builds and frontend unit test pass. PostgreSQL migration and Compose health pass.
- All 4 browser tests pass, including workspace create, device binding, offline launch disabled and deletion.
- Workspace command sequencing tested with mocked desktop dispatch; real host system_info/connectivity was verified in phase 2. Full desktop workspace launch remains an acceptance check for phase 10.
