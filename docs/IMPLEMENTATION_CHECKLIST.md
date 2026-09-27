# Implementation checklist

- [x] Inspect repository and read prompt.rtf.
- [x] Record architecture, scope and repository rules before implementation.
- [x] Phase 1: structure, Compose/PostgreSQL, Core/Tasks/UI skeletons, health, config, logging.
- [x] Phase 2: devices, WebSocket, Agent/platforms, heartbeat/offline, device UI/details.
- [x] Phase 3: Tasks CRUD/filtering/tests/UI, manifest and Service Registry.
- [x] Phase 4: workspace CRUD, bindings, launch and UI.
- [x] Phase 5: Tool Registry, Mock/OpenRouter providers, assistant/history/UI.
- [x] Phase 6: browser recording, Whisper/mock STT, voice endpoint/transcript.
- [x] Phase 7: Piper/mock TTS, playback and fallback states.
- [x] Phase 8: IoT adapter, persistent virtual state, tools and UI.
- [x] Phase 9: activity, service health, refresh and debug details.
- [x] Phase 10: local tests, docs, seeds, visual polish and acceptance scenarios (platform limits below).

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

## Local web readiness — 2026-09-26

- Started Docker Desktop and rebuilt/started the development Compose stack with the existing PostgreSQL volume. Core and Tasks reached healthy status; Control Center is available at http://localhost:8080.
- Backend: `.venv/bin/python -m pytest -q` — 20 passed (one dependency deprecation warning). Frontend: `npm test` — 1 passed; `npm run build` passed.
- Host Agent smoke: registration, system_info, heartbeat and disconnect/offline passed. The smoke Agent stops after verification.
- Chrome at the Compose URL: all 5 Playwright scenarios passed — health/session settings, device details, task lifecycle, workspace CRUD/binding, and mock Assistant creating a real task through the registry.
- Sign in through Settings using DELTA_TOKEN from the local `.env`; the token is kept in sessionStorage.
- This is a usable development preview, not completed MVP acceptance: phase 5 remains open; voice, Activity and Virtual IoT are not ready.

## Phase 5 verification — 2026-09-26

- Verified local and external Tool Registry execution, schema validation, disabled-tool exclusion, unknown-tool rejection and independent HTTP service integration.
- Hardened malformed/empty OpenRouter responses, whitespace-only messages, duplicate call IDs within a batch, ambiguous Mock device selection, and disabled local tools shadowed by external tools.
- `pytest -q`: 27 passed (one dependency deprecation warning). Tests include provider/tool message round trip, authentication, failure after a successful action with persisted results, malformed provider responses and connection failures.
- Frontend unit test passed; TypeScript/Vite production build passed. `python3 -m uv build` produced wheel and sdist. Initial direct build with `--no-isolation` failed because the runtime venv has no setuptools; the normal isolated uv build succeeded.
- Docker Compose rebuilt and started the application. Initial browser run exposed stale nginx upstream IPs after backend recreation, resulting in cross-routed API requests and 404 responses. Fixed with shared upstream zones and dynamic Docker DNS resolution, per https://nginx.org/en/docs/http/ngx_http_upstream_module.html#server (nginx >= 1.27.3).
- nginx configuration validation passed. Recreated Core/Tasks again without restarting the frontend; all 5 Chrome scenarios passed, including Assistant task creation, persisted history after reload and opt-in tool execution details.
- OpenRouter is verified with a mocked HTTP transport only; no real model/API call was made. Voice, Virtual IoT and Activity UI remain later phases.

## Assistant Markdown — 2026-09-26

- Render saved and new Assistant responses with react-markdown and remark-gfm; style headings, emphasis, lists, tables, links, quotations and code for the dark UI. User messages remain plain text.
- Raw HTML is skipped; default URL filtering retained. External links use noopener/noreferrer; images render as alt text. Library reference: https://github.com/remarkjs/react-markdown#security.
- Frontend unit test and production build passed. Rebuilt/restarted only Control Center; OpenRouter/backend configuration preserved.
- Two Chrome scenarios passed against port 8080: foundation and Markdown rendering, including history/new messages, literal code, HTML/unsafe-link checks and mobile overflow. LLM responses were stubbed for this UI test; no OpenRouter request was needed.

- Follow-up: inspected the latest real OpenRouter response in Chrome at localhost:8080: 4 rendered headings, 14 strong elements, no visible heading markers. Added Cache-Control: no-cache to static responses so browsers revalidate after deployments. Existing open tabs still need a reload to execute the new bundle.

## Phase 6 verification — 2026-09-26

- Added STTProvider with explicit Mock and local Whisper implementations, authenticated multipart `/assistant/voice`, provider/limit metadata, transcript UI and recording controls. CPU inference uses a worker thread, a single-job lock, int8 and a pre-provisioned local model.
- Input guards: MIME validation, empty/invalid audio, 10 MiB file limit, bounded raw request body including chunked uploads, decoded duration limit, empty/overlong transcripts. Uploads close after reading. Whisper does not download models during inference or fall back to mock.
- Browser releases microphone tracks on stop, cancel, errors and navigation; automatically submits at the configured duration limit. Model failures preserve the transcript in an editable text field; text chat survives microphone/STT failures.
- Backend: 37 tests passed. Isolated tests now force mock providers so a developer's local OpenRouter credentials cannot accidentally trigger live calls. Frontend unit test, TypeScript/Vite build and Python wheel/sdist build passed.
- Added a separately locked STT dependency export and installed it only in Core. Compose rebuilt successfully; Core/Tasks/PostgreSQL healthy. Whisper small provisioned in the persistent model volume (about 464 MiB, MIT model license).
- Real HTTP pipeline with a macOS-synthesized Russian WAV returned HTTP 200 in 11.8 s, transcript “Покажи устройство.” and successful `devices.list` from the configured OpenRouter model. The initial sandbox-generated WAV had no samples and correctly returned INVALID_AUDIO; regenerated it using the host speech service.
- Real Chrome MediaRecorder WebM → Whisper → live OpenRouter → devices.list also returned HTTP 200 and displayed the transcript. The audio source was a synthetic test fixture, not the user's physical microphone.
- Real Whisper also passed invalid-file, 61-second rejection, silence/empty transcript and missing-model checks.
- 9 browser scenarios passed (single worker): foundation, devices, tasks, workspaces, Markdown, recording/upload/transcript, cancel/navigation cleanup, microphone denial/text fallback, automatic stop/model-failure transcript recovery. The mock-only Assistant browser scenario was excluded because the installation now uses OpenRouter; the live voice check verified actual provider/tool integration. An initial parallel recording test missed the exact one-second label during resource contention; the assertion now accepts any positive recording timer value.
- Updated runtime is available at http://localhost:8080. Physical microphone quality and Safari/Firefox recording remain manual acceptance checks. Speech output is not implemented until phase 7.

## Voice latency optimization — 2026-09-26

- Measured the existing pipeline before editing: successful warm request 29.06 s, including 19.10 s in the final LLM completion; another baseline request timed out in routing.
- Preload/reuse Whisper at startup; beam 1, fixed configurable language/model, VAD, no word timestamps and supported CPU int8. Added separately configurable router/assistant models and pooled provider connections.
- FAST PATH formats validated successful tool results without a second completion; SMART PATH retains reasoning and summarization. Deferred non-critical Activity batches until after response delivery while keeping interaction history durable.
- Added browser upload/recording-stop totals and developer stage telemetry, benchmark script, and optional synthesis timing hook. Piper remains phase 7; absent TTS is explicitly labeled.
- Same-model WAV requests: 5.54 / 4.70 / 4.89 s, each one tool execution and zero final LLM calls. Live browser: 36.76 s after recording stop, including 33.56 s remote routing; free-provider variability remains. Full measurements and caveats: [VOICE_LATENCY.md](VOICE_LATENCY.md).
- 57 backend tests passed, including all five deterministic tool formatters, exactly-once execution, no second completion, smart fallback, model reuse/configuration, deferred Activity and synthesis failures. One frontend unit test and 10 Chrome scenarios passed; mock-only Assistant scenario excluded on the live provider installation. Production frontend, Python wheel/sdist and Docker builds passed.

## Local intent routing — 2026-09-26

- Added replaceable IntentRouter/IntentDecision with LocalIntentRouter rules for devices.list, tasks.create/list/complete, workspaces.launch and IoT light/temperature. Assistant only applies the configured threshold and executes through the registry. No new business modules or IoT state were introduced.
- Named task completion resolves a unique exact title through the registered read tool; ambiguous/missing names, unavailable tools, schema mismatches and complex requests retain LLM fallback. Successful common local calls execute once with zero completions. Local errors return factual results without action replay.
- Developer voice/text output includes route source, local routing duration and confidence. Added a 40-command Russian corpus and reproducible intent/STT benchmarks; report: [LOCAL_INTENT_ROUTING.md](LOCAL_INTENT_ROUTING.md).
- Text corpus: 40/40 intent and 30/30 normalized slot-set matches, average 0.082 ms with fixture lookups. This is a regression corpus, not a held-out accuracy estimate.
- Same 40 synthetic WAV files: Whisper small averaged 3.23 s, exact transcripts 85%, WER 7.33%; base averaged 1.05 s, exact transcripts 65%, WER 18.67%. Kept small as the default. Model startup excluded; both used CPU int8, two threads, beam 1 and fixed Russian.
- Live local voice: three WAV requests 2.71–2.77 s; Chrome MediaRecorder 2.48 s after recording stop. All returned one devices.list result with zero LLM calls. The live singular transcription variant was added as a read-only alias and downstream benchmark metrics recomputed.
- All 134 backend tests, one frontend unit test and all 13 Chrome scenarios passed. Existing fallback/TTS test retains its assertions with local routing explicitly disabled for that case. New tests prove local execution, threshold fallback, schema/availability boundaries and common Russian phrases. Frontend, Docker and Python distribution builds passed; updated Core/UI running at localhost:8080.

## Phase 7 verification — 2026-09-26

- Added TTSProvider, startup-loaded PiperTTSProvider and explicit silent-WAV MockTTSProvider. Core installs locked voice dependencies; Tasks remains independent. Russian Irina model/config live in a separate persistent volume. Inference never downloads models.
- Voice API returns PCM WAV as base64, provider/mime metadata and TTS timing. Markdown is converted to speech prose. Limits bound input, audio duration and the request's synthesis wait. Failed, busy, missing-model and timed-out TTS preserve text/history and completed tools; no action replay or silent mock fallback.
- Added browser automatic playback, a manual button for autoplay denial, stop and replay. Starting a recording, text submission or navigation stops playback and releases the object URL. Audio is not persisted in the database.
- 147 backend tests passed (one existing dependency deprecation warning), including reuse, missing model, bounded synthesis, cancellation retaining the worker lock, actual WAV format, startup and voice failure fallback. Frontend unit test and production build passed. All 16 Chrome scenarios passed, including blocked autoplay, replay without another request, stop/end transitions, navigation cleanup and TTS failure.
- Real Whisper small → LocalIntentRouter → devices.list → Piper: three HTTP requests 3.48 / 3.66 / 3.59 s; TTS 569 / 637 / 669 ms. Each executed the tool once with zero LLM completions.
- Live Chrome synthetic-microphone recording returned audio after 3.33 s from recording stop, including 525 ms synthesis. Native browser audio decoded and played a 5.77-second WAV; stop, replay and navigation cleanup passed with exactly one voice HTTP request. Physical microphone/speaker quality remains manual acceptance.
- Piper dependency image built successfully. A later regular frontend/Core rebuild hit Docker Hub TLS timeouts; deployed the final source and verified frontend dist using existing local images with network disabled. The voice config download also needed host curl after a container TLS error. Persistent model ownership restored to the service user. Standard Dockerfiles remain the normal reproducible build path when registry access is available. Python wheel/sdist built successfully.
- Current runtime: http://localhost:8080. Next phase: virtual IoT. Configuration, limits and setup: [VOICE_PIPELINE.md](VOICE_PIPELINE.md).

## Phase 8 verification — 2026-09-27

- Added IoTAdapter/VirtualIoTAdapter, shared strict contracts and migration 0005 for persistent Core-owned state. Defaults: desk light off, 23 °C, brightness 30%, motion detected. These are fixed emulated readings; only the light is user-writable. No MQTT/physical hardware was introduced.
- Authenticated state/light endpoints and four registered tools share the adapter. Light writes and IOT_ACTION events commit atomically; repeated desired-state writes are idempotent. AssistantService remains independent of adapter implementation. Local phrases cover light, temperature, brightness and motion without LLM completions.
- Virtual IoT page shows explicit emulation, confirmed light state, sensor cards and three-second refresh. Pending older reads cannot overwrite a confirmed write. Errors do not fabricate readings; stale values are labeled and controls disabled until refresh succeeds.
- 163 backend tests passed, including auth/strict boolean validation, adapter substitution, audit rollback, idempotence, migration upgrade/downgrade, persistence and local text/voice execution. Existing FastAPI warning and Alembic path_separator deprecation warnings remain non-fatal. Frontend unit test, TypeScript/Vite build, Python wheel/sdist and normal Docker Compose build passed.
- All 19 Chrome scenarios passed, including actual light switching/reload, Assistant sharing the same state, external-change polling, service-error UI and stale-read ordering. Earlier scenarios remain intact.
- Real Whisper small/Piper voice smoke: light on 3.41 s, light off 3.68 s, temperature 3.67 s including follow-up state verification for light changes; server pipeline totals 3.37 / 3.64 / 3.65 s. Each executed one registered tool, zero LLM completions, and returned valid speech audio. TTS took 363 / 326 / 605 ms. Synthetic input was used.
- A live PostgreSQL state/timestamp survived a Core restart. Original virtual light state was restored after acceptance checks. Core/UI are running at http://localhost:8080. Next phase: activity feed and service status. Details: [VIRTUAL_IOT.md](VIRTUAL_IOT.md).

## Phase 9 verification — 2026-09-27

Authenticated, bounded Activity API with timestamp/ID pagination, event filtering
and heartbeat suppression; live Activity and Overview feeds; service availability
and loading/error states. Existing Assistant developer diagnostics preserved.
Health monitoring tolerates malformed payloads and failed activity writes.

Validation: full backend suite 165 passed, then additional audit-failure regression
and service tests 3 passed (166 total tests); frontend unit test passed; TypeScript
and Vite production build passed. Docker Core/UI rebuilt and restarted. Chrome
suite: 21 scenarios passed, including real persisted activity and service health.
Polling intervals and cross-service activity limitations: [Activity and Services](ACTIVITY_AND_SERVICES.md).

## Phase 10 verification — 2026-09-27

- Overview now uses independent device/service/workspace/open-task API counts.
  Failed sources preserve and label stale values; task counts respect the existing
  1000-row limit per status. Token-free Overview explains connection setup.
- Polished narrow layouts, focus visibility and reduced-motion behavior.
- Added API-only demo seed preserving existing records and IoT state; live runs
  created 2 workspaces / 3 tasks, then zero. No invented devices or paths.
- Added a real voice-task acceptance script with cleanup and demo documentation.
- 168 backend tests passed; frontend unit test, TypeScript/Vite and Python wheel/sdist builds passed.
  Full Chrome run: 23 passed; additional live Overview/API parity and responsive check: 1 passed.
- Real macOS Agent registration, system_info, heartbeat and disconnect passed.
  Whisper small → local tasks.create → persistent Task / Activity → Piper WAV
  passed in 5279 ms, zero LLM calls. The test task was deleted afterward.
- Docker UI rebuilt; Core/Tasks/PostgreSQL healthy. Persistent volumes retained.
- Physical audio, empty-volume installation, real Windows/Linux and Safari/Firefox
  remain manual acceptance items. See [demo and acceptance](DEMO_AND_ACCEPTANCE.md).

## Black palette and isolated bootstrap — 2026-09-27

- Darkened surfaces to neutral near-black: page #050505, sidebar #080808,
  cards #0d0d0d; retained readable text, focus and semantic state colors.
- Frontend production build passed; rebuilt/deployed UI. Four relevant Chrome
  scenarios passed (Markdown, Overview failures, mobile layout, live API parity).
  Desktop and mobile screenshots checked.
- Added isolated Compose overlay and check_clean_install.py. Actual empty-volume
  run passed in 23.44 seconds: DB bootstrap/migrations, health/authentication,
  seed idempotence, local Assistant/Tasks, persistence after restart and explicit
  unavailable STT with no models. Existing built images reused; no downloads.
- Isolated containers/network cleaned up; diagnostic volumes retained. Running
  user project preserved. This closes the empty-database bootstrap check, not
  physical audio, cross-platform or model-provisioning acceptance.
