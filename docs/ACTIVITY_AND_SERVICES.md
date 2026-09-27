# Activity and service health

Phase 9 exposes the existing Core activity records through authenticated
`GET /api/v1/activity`. Parameters: `limit` (1–100, default 30), `event_type`,
`include_heartbeats` (default false), and the returned `next_cursor` fields
`before_time` / `before_id`. Ordering is descending timestamp and ID, so records
sharing timestamps paginate without duplicates. No Tasks database access occurs.

Activity displays the latest 30 records and polls every five seconds. Loading
older records pauses automatic replacement; Refresh returns to the latest page.
Overview shows the latest five events. Errors retain previously loaded rows and
mark them stale. Developer mode reveals event details; it is a presentation
setting, not an authorization boundary. The API always requires the Delta token.

Services polls the registry snapshot every five seconds; the existing registry
checks health every 15 seconds (plus request time). Refresh reloads the snapshot;
it does not force a new network health probe. Online, offline, degraded and
disabled statuses remain distinct. Unavailable services expose no available
tools. Malformed health payloads cannot terminate monitoring, and an activity
write failure does not interrupt health updates. Service URLs are shown in
developer mode. Assistant already exposes tool arguments, target service,
results, durations and voice timings in developer mode.

Updates use polling, not a WebSocket subscription. Direct changes made in the
Tasks service are not automatically copied into Core activity; assistant tool
executions are recorded by Core. Phase 10 covers final acceptance and polish.
