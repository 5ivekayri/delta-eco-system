# Service integration contract

Registry/discovery is implemented in phase 3; validated HTTP tool execution follows in phase 5.

## Ownership

A service runs independently, owns its database and exposes a versioned HTTP API. Core never imports its ORM models or reads its tables. Shared packages contain wire schemas only. HTTP failures must become structured tool failures; do not replace a failed service with fabricated success.

## Manifest

Core loads `SERVICE_CONFIGS` from an environment JSON array, for example `[{"service_id":"delta-tasks","base_url":"http://delta-tasks:8000","enabled":true}]`. If omitted, it registers Tasks using `TASKS_URL`. Each service exposes an authenticated `GET /api/v1/manifest`. Core uses the configured development token, fetches the manifest and checks health every 15 seconds. A configuration change currently requires a Core restart.

Register an operator-controlled configuration entry containing `service_id`, `name`, `version`, `base_url`, `health_url`, `enabled` and `tools`. Each tool contains `name`, `description`, `input_schema`, `permissions`, `enabled` and its HTTP adapter mapping: method, relative path and argument placement. Identity and URL come from configuration, not model-generated arguments.

The Tool Registry publishes only enabled tools belonging to enabled, healthy services. Validate the manifest at startup, reject duplicate tool names and invalid JSON schemas, and fail closed when metadata is invalid. The Service Registry tracks `status`, `last_health_check` and `available_tools`. Background health checks update status and activity only on transitions; callers also handle a service going offline between discovery and invocation.

## HTTP adapter

Build the target URL from a configured base URL and manifest route. Path parameters must be escaped, JSON arguments validated and timeouts bounded. No arbitrary destination URL is accepted from the assistant. Send configured service authentication; never put it in tool arguments or browser-visible debug output. Map connection errors/timeouts to `SERVICE_UNAVAILABLE`, preserve validation failures and report non-2xx responses honestly. Do not automatically retry mutating calls: a lost response may follow a successful write.

## Adding a service

1. Implement its independent REST API and `/health`.
2. Define input/output contracts and safe operations.
3. Describe tools and HTTP mapping in a manifest.
4. Add its trusted base URL/authentication to service configuration.
5. Verify discovery, schema validation, healthy/offline transitions and API errors.
6. Verify the tool appears in OpenRouter tool definitions without editing Assistant business logic.

The deterministic MockLLM deliberately recognizes a limited set of demo phrases; it is not a general natural-language planner for arbitrary new services. Architectural extensibility must be tested through registry dispatch and schema-aware LLM providers, not by pretending the mock understands every future domain.

## Hypothetical Delta Weather

Weather is deferred; do not implement the service in v0.1. A future manifest may register `weather.current` and `weather.forecast`, with a required `location` string and forecast duration bounds. Each maps to the service's REST endpoint. Core handles discovery/validation/HTTP transport exactly as for Tasks; weather calculations, external provider credentials and forecasts remain inside that service.

## Required architectural test

Register an in-test HTTP service with an unfamiliar tool name and valid schema, dispatch it through the same registry/adapter, and assert correct HTTP method/path/body/result without modifying Assistant Core. This establishes pluggability independently of the built-in Tasks integration.
