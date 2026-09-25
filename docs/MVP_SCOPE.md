# Delta v0.1 scope

Source of truth: ../prompt.rtf; searchable copy: REQUIREMENTS.txt.

Required: Core, independent Tasks, host Agent, dark Control Center; PostgreSQL/Alembic/Compose; authenticated device registration, heartbeat/offline detection and commands; workspace CRUD/device bindings/launch; extensible service/tool registries; Mock/OpenRouter LLM; local Whisper STT/Piper TTS plus test mocks; assistant history/activity; virtual IoT; seed data, tests and deployment documentation.

Deferred: real Weather/Dark Weather services, calendar/notes, MQTT/Raspberry Pi, automation, RAG, wake word, mobile app, enterprise IAM and distributed infrastructure.

Acceptance requires a clean Compose start, healthy services, real host Agent online/offline and allowlisted actions, workspace launch, independent persistent task CRUD, assistant tool execution, microphone→STT→tool→TTS→playback, observable activity and a working responsive dashboard. Mock tests alone do not establish real speech or cross-platform acceptance.

Demo workspaces: Master Thesis, Dark Weather. Tasks: Prepare API tests, Finish architecture, Add device agent. Virtual state: 23°C, brightness 30, motion true, desk light false. No fabricated online devices or successful tool results.
