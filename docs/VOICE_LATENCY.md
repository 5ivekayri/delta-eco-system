# Voice latency pass — 2026-09-26

Scope: voice input, Assistant dispatch/response generation, OpenRouter connections,
optional synthesis timing and developer telemetry. Registries, service/database
boundaries, Agent actions and task/workspace business logic remain in place.

## Baseline measured before changing application code

A temporary, runtime-instrumented instance of the existing application was run
inside the current Core container (no source changes). It used the existing
PostgreSQL services and live OpenRouter. Wrappers timed body receipt, STT, the
first LLM completion, tool execution, the final LLM completion and Activity writes.
No device status reset or application startup migration was run by the probe.

Fixture: 1.300375-second, mono 16 kHz Russian WAV, synthesized on macOS from
“Покажи устройства”. Model: Whisper `small`, fixed `ru`, CPU int8, beam size 3.
LLM: `nvidia/nemotron-3-ultra-550b-a55b:free`. No TTS provider existed.

All values below are milliseconds; zero TTS means **not configured**, not instantaneous synthesis.

| Stage | Cold run | Warm run | Third run (failed) |
|---|---:|---:|---:|
| Audio body receipt | 1.8 | 1.1 | 8.2 |
| STT | 8028.5 | 6124.7 | 8411.0 |
| LLM routing | 7296.4 | 3708.8 | 60033.9 |
| Tool execution | 6.7 | 5.0 | not reached |
| Final LLM response | 20492.8 | 19100.9 | not reached |
| TTS | not configured | not configured | not configured |
| Activity writes (included in total) | 45.7 | 47.4 | 23.0 |
| Server total | 35949.0 | 29048.2 | 68495.8 |
| HTTP client total | 35958.9 | 29058.8 | 68507.6 |

Actual bottleneck: the unnecessary final LLM completion, followed by model routing
and STT. The third sample timed out during routing (HTTP 503), illustrating remote
free-provider variability. Activity/database work was a much smaller contributor.

The baseline upload is container loopback body receipt. HTTP client totals start
with a ready audio fixture; they exclude microphone/encoder finalization. They
must not be presented as a physical-microphone measurement.

## Optimizations

- Whisper is constructed once during the FastAPI lifespan, before serving requests.
  It is reused across requests, with local-only model loading. A startup failure
  leaves text available and reports STT_UNAVAILABLE; requests never download or
  retry construction. Provision the model and restart Core to recover.
- Command settings: configurable WHISPER_MODEL, fixed WHISPER_LANGUAGE (ru by
  default), beam_size=1, VAD enabled, word_timestamps=False, temperature=0,
  condition_on_previous_text=False. CPU int8 is selected when supported, otherwise
  float32. The command benchmark retained `small` to preserve the model comparison.
- Direct, single-action commands are eligible for FAST PATH. A tool-capable router
  chooses registered tools; the registry validates and executes them. Successful,
  recognized result schemas for tasks.create/tasks.complete/workspaces.launch/
  devices.list/iot.set_light get factual deterministic responses, with no second
  completion. No new IoT execution capability is added by a response formatter.
- SMART PATH retains the full model loop for reasoning/summarization, compound or
  unmatched requests, unknown tools, insufficient result data and partial failures.
  Handoff preserves existing tool calls/results. Repeated IDs or identical
  name/argument calls are not executed again during the same request.
- DELTA_ROUTER_MODEL and DELTA_ASSISTANT_MODEL are independent. Empty settings fall
  back to OPENROUTER_MODEL for compatibility. The local installation explicitly
  preserves the same model for both roles. Router requests use a smaller configurable
  completion cap (DELTA_ROUTER_MAX_TOKENS=512), temperature 0, reasoning disabled
  where the provider supports it, and provider.sort=latency.
- Both roles share a dedicated reusable httpx client. It carries no internal Delta
  credentials. Smart requests retain the standard response token budget.
- Activity batches run on a worker thread after response delivery. Failures are
  logged without failing or replaying successful actions. Interaction history
  remains durable before acknowledgment. Tool-specific audit writes are preserved.
- Optional TTS hook runs once after the final answer and is timed separately. No
  Piper implementation was introduced by this optimization pass. TTS remains
  phase 7; telemetry reports not_configured. Injected-synthesizer tests verify
  timing and that a synthesis failure cannot lose results or replay tools.

## Same-model optimized measurements

Same WAV, same Whisper model, same OpenRouter model. Measurements from the deployed
API through nginx, using `scripts/benchmark_voice.py`:

| Stage | Run 1 | Run 2 | Run 3 |
|---|---:|---:|---:|
| Audio body receipt at Core | 0.02 | 0.03 | 0.02 |
| STT | 3490.92 | 3824.67 | 4042.32 |
| Router | 2003.64 | 844.40 | 819.05 |
| Tool | 2.50 | 3.13 | 2.95 |
| Deterministic response builder | 0.01 | 0.01 | 0.01 |
| Final LLM calls | 0 | 0 | 0 |
| TTS | not configured | not configured | not configured |
| Server total | 5535.61 | 4691.58 | 4877.46 |
| HTTP client total | 5543.38 | 4700.56 | 4885.60 |

All three returned HTTP 200 and exactly one successful devices.list result.
Optimized median HTTP latency: **4885.60 ms**. The successful warm baseline was
**29058.8 ms** (about 83% lower in this small comparison). This is not an SLA:
the sample is small, the external provider varies, and baseline had one timeout.
STT dominates these three successful WAV samples. A smaller model can trade accuracy
for speed through configuration; no smaller-model accuracy claim is made here.

### Live browser recording check

Chrome MediaRecorder, with the same synthetic audio source recorded as WebM, also
returned HTTP 200 and exactly one devices.list result. Developer telemetry showed:
browser upload 101 ms, recording finalization 14 ms, Core upload 0.02 ms,
STT 3150.22 ms, router 33556.34 ms, tool 3.40 ms, response builder 0.01 ms,
zero final LLM calls, TTS not configured, server total 36737.07 ms and
**36757 ms after recording ended**. Client upload and server processing overlap;
these intervals must not be summed. This slower sample confirms that external
router latency can still dominate despite eliminating the second completion.
It is a browser/encoder measurement with synthetic input, not a physical mic test.

Validation: 57 backend tests, one frontend unit test and 10 Chrome scenarios passed;
the existing mock-only Assistant scenario was excluded on the live OpenRouter
installation. Live WAV and browser checks separately exercised the real provider.
Frontend, Python distribution and Docker builds passed.

## Telemetry definitions and reproduction

Settings → Developer mode, then send a voice command. The response includes:

- upload_ms: Core's initial ASGI request-body receive interval. nginx may buffer
  the upload before forwarding; this is not browser-to-server upload time.
- client_upload_ms: browser XHR upload-complete interval, including connection and
  browser scheduling. Kept distinct from Core body receipt.
- stt_ms: decode, VAD and transcription; model construction is at startup.
- router_ms: first completion (the router model on FAST PATH; assistant model on SMART).
- tool_ms: accumulated registered-tool execution time.
- response_generation_ms: deterministic formatting or subsequent LLM completions;
  response_generation_calls distinguishes zero-completion FAST PATH from SMART.
- tts_ms and tts_status: synthesis interval, or explicitly not_configured.
- server_total_ms: request entry through response preparation, including multipart,
  context and durable interaction persistence, excluding deferred Activity work.
- finalization_ms: recording-stop through starting upload, including encoder flush.
- total_ms: browser recording-stop through response receipt/JSON parsing, including
  finalization, upload, server processing and response transport. Playback is not
  included. It is not computed by adding overlapping client/server measurements.

Developer timing is attached to the live voice response (and handled errors).
Historical interactions retain their existing schema and do not backfill timings;
enable developer mode before the voice request. Client totals are per browser
session and use its monotonic clock; they cannot be reconstructed from server logs.

```sh
# Use a harmless recorded command: the script invokes the configured LLM/tools.
.venv/bin/python scripts/benchmark_voice.py .runtime/voice-check.wav --runs 3
```

Configuration changes require `docker compose up -d delta-core`. Model provisioning:

```sh
docker compose exec -T delta-core python -m delta_core.voice.provision
docker compose restart delta-core
```

References: [faster-whisper](https://github.com/SYSTRAN/faster-whisper),
[OpenRouter provider routing](https://openrouter.ai/docs/guides/routing/provider-selection).
