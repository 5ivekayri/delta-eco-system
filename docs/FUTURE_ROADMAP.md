# Roadmap after v0.1

These are deferred design directions, not implemented features.

## v0.2 — independent services and context

Dark Weather, Calendar, Notes and a better Context Engine. Every service owns its data/API and supplies a tool manifest. Context remains separate from tool execution and permissions.

## v0.3 — physical devices

Raspberry Pi, Mosquitto/MQTT and real IoT sensors. Replace VirtualIoTAdapter with a compatible MQTT adapter. Keep permission checks and structured results at the same Core boundary.

## v0.4 — automation

Automation Engine, voice-created rules and cross-device session handoff. Define deterministic triggers/actions, validation and user-visible execution histories before introducing scheduling.

## v0.5 — file intelligence

Local document indexing, File Intelligence and project memory. Scope indexed paths explicitly and preserve local data control. Do not introduce semantic indexing in v0.1.
