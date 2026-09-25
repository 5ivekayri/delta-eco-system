# Delta Digital Ecosystem

Read docs/REQUIREMENTS.txt, extracted from the original prompt.rtf.

- Python 3.12+, FastAPI, SQLAlchemy 2, Alembic; React/TypeScript/Vite frontend.
- Delta Core is a modular monolith. Delta Tasks is a separate HTTP microservice with its own database and credentials. Never cross database boundaries.
- Service Registry and Tool Registry are mandatory. Validate tool arguments; LLMs only choose registered tools. New services integrate through manifests and adapters.
- Host Agent supports Windows/macOS/Linux through platform adapters. Explicit capabilities only; no arbitrary shell, Python evaluation, executable paths, destructive filesystem actions, or credential access.
- Voice input and output are mandatory, with local Whisper/Piper and explicit mock providers. Text survives voice failures.
- Dark Delta design, device dashboard, workspace bindings/launch, activity and virtual IoT are mandatory.
- Weather, real MQTT/IoT, Raspberry Pi, semantic memory and automation are deferred. Keep extension interfaces; avoid unnecessary infrastructure.
- Follow phases in docs/IMPLEMENTATION_CHECKLIST.md. Build, test, check backend/frontend and fix regressions before advancing. Record actual verification and limitations honestly.
- Configure secrets through environment. Do not commit credentials or log tokens.
