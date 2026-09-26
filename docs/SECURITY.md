# Security boundaries

This document records the intended MVP boundary. HTTP authentication, network/database separation and Agent allowlist enforcement are implemented. Tool/LLM validation and enabled-tool enforcement are implemented.

## Development authentication

`DELTA_TOKEN` is supplied through environment and checked using a constant-time comparison on `/api/` routes. `/health` is intentionally public and only returns service/database health, not connection strings. Never commit `.env`. Browser stores the token in sessionStorage; this is a single-user development mechanism, not production IAM. Future pairing, device trust and per-tool permissions must replace this boundary for shared deployment.

Compose publishes Core and UI only on loopback. PostgreSQL and Tasks are internal. Use TLS and trusted network access when changing these defaults. Database roles cannot connect to each other's databases; the PostgreSQL administrative account is reserved for initialization.

## Implemented Agent policy

Only `system_info`, `open_url`, `open_path`, `open_app` are valid actions. Validate payloads, allow only HTTP(S) URLs, restrict paths to explicitly configured directories and resolve app identifiers locally. Never use a shell interpreter, evaluate source code or accept arbitrary executable paths. Reject unknown actions and malformed messages. Correlate results to a pending command on the authenticated originating connection. Do not replay a timed-out desktop action automatically.

## Implemented LLM policy

LLM selects registered, enabled tools. The registry validates local arguments with Pydantic and external arguments against manifest JSON Schema. Permission metadata describes capabilities; per-user permission enforcement remains future work. Service manifests/configuration are trusted operator input, never assistant-generated executable instructions. No direct LLM database/filesystem access. Tool output is data, not instructions. Error reporting must preserve partial failures and never claim successful execution when an adapter failed.

## Logs and voice

Foundation request logs contain request ID, service ID, path, method, duration and success. They exclude authorization headers and bodies. Voice implementation must limit upload size, avoid arbitrary file paths, isolate temporary files and clean up audio. History and activity contain personal content; retention/export controls are future work and should be documented before multi-user use.
