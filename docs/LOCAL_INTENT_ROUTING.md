# Local intent routing and Russian voice benchmark — 2026-09-26

## Runtime behavior

Both text and voice requests now try the injected `IntentRouter` before an LLM.
`LocalIntentRouter` is a deterministic implementation; its interface returns an
`IntentDecision` containing a proposed `ToolCall`, confidence and extracted slots.
AssistantService applies `DELTA_LOCAL_INTENT_THRESHOLD` (default **0.9**) and uses
its existing Tool Registry execution loop. There are no phrase patterns or new
action-specific dispatch branches in AssistantService.

A complete recognized pattern gets heuristic confidence **0.99**. Unmatched,
ambiguous, unavailable or schema-incompatible routes return no call with confidence
zero. This score is a rule confidence, not a calibrated statistical probability
or Whisper's recognition confidence. A replacement classifier can return graduated
scores without changing AssistantService. Setting the threshold to 1 disables
acceptance of the current rules, preserving the LLM fallback for comparison.

Supported intents:

| Tool | Examples | Arguments and constraints |
|---|---|---|
| devices.list | «Покажи устройства», «Какие устройства сейчас подключены?» | No arguments |
| tasks.create | «Добавь задачу купить молоко» | Extracts title; deadlines/priorities/compound instructions fall back |
| tasks.list | «Покажи задачи», «Покажи выполненные задачи» | Optional exact status: new / completed / in progress |
| tasks.complete | «Заверши задачу купить молоко» | UUID or unique exact title resolved to UUID through registered tasks.list |
| workspaces.launch | «Открой Диплом», «Открой Диплом на Ноутбук» | Exact registered workspace/device names; requires explicit or selected device |
| iot.set_light | «Включи свет», «Выключи рабочий свет» | Boolean enabled; optional device_name only when the registered schema accepts it |
| iot.get_temperature | «Какая сейчас температура?» | No arguments |

Name matching ignores case, surrounding quotes and е/ё differences. It does not
invent aliases, perform fuzzy matching or choose among duplicate task/device
names. Display names in commands must match registered names; declension and
unsupported qualifiers can require the LLM. A named task completion makes one
read-only registry lookup before one completion; it never accesses the Tasks DB.
A failed lookup falls back before any mutation. Duplicate titles, even when one
is already completed, do not cause a guessed completion.

Only enabled, available registered tools with valid input schemas can be locally
accepted. Registry validation and permissions remain authoritative at execution.
At the time of the benchmark, IoT tools were fixtures only. Phase 8 now registers
the persistent [virtual IoT adapter](VIRTUAL_IOT.md) in Core. Light/temperature
commands execute locally; brightness/motion phrases were added as well. The
production light tool accepts only `enabled` for one default light; named targets
in the historical corpus use an explicitly broader fixture schema and remain
unsupported by the current virtual adapter.

Successful supported results use deterministic response builders, including task
lists and temperature. They make zero LLM calls. Local execution failures return
the factual tool error without replaying an action or consulting OpenRouter.
An unexpected successful result schema can still use the existing SMART response
pipeline. OpenRouter remains configured for all other requests.

## Telemetry and UI

Developer mode displays **Local route / LLM route**, `local_router_ms` and
`confidence`, alongside existing voice stage timings and LLM completion counts.
Text responses also carry these fields and display the route in developer mode.
These are live-response fields; the existing historical interaction schema is
unchanged. `route_source` describes the initial routing decision, not whether a
later response interpretation needed the assistant model. `confidence` describes
the local candidate even when it falls below the threshold and falls back.

`local_router_ms` includes classification, schema checks and the read-only HTTP
lookup when completing by title. That lookup is not included again in `tool_ms`;
`tool_ms` measures execution of the chosen action. `router_ms` continues to mean
LLM routing time and is zero for a local route.

## Text corpus benchmark

Corpus: [40 labeled Russian commands](../benchmarks/russian_commands.json):
30 actionable phrases across all seven intents, plus 10 negative/ambiguous/complex
fallback cases. Fixtures include known workspace/device names and task titles.
Evaluation never invokes real tools. Task lookups return fixture data in memory;
network/database latency is excluded. The corpus was written with the deterministic
grammar and is a regression benchmark, **not a held-out generalization estimate**.

Results from 100 repetitions (4,000 routing decisions) on the development Mac:

| Metric | Result |
|---|---:|
| Intent accuracy, including correct fallback | 40/40 — 100% |
| Exact normalized slot-set accuracy, positive commands | 30/30 — 100% |
| Exact slot-set accuracy, nonempty slot sets only | 17/17 — 100% |
| Average routing latency, including fixture resolution/schema checks | 0.082 ms |
| Maximum routing latency in this run | 1.245 ms |

Slot comparison preserves values but normalizes case, whitespace and е/ё.
Raw decisions/arguments and timings: [intent_results.json](../benchmarks/intent_results.json).
Real completion-by-title includes the extra service lookup and will take longer.

## Whisper small vs base

Both models processed **the same 40 WAV files**, one measured pass per model after
one untimed warmup. Each model was loaded once. The configured model was verified
as `small`; the test downloaded `base` into the same persistent model cache without
changing `.env` or the default.

Audio: macOS Milena synthetic Russian speech, rate 170, mono PCM16 at 16 kHz.
Files were generated once and their hashes verified before each transcription.
[Audio manifest](../benchmarks/audio_manifest.json) records references, duration
and hashes. These clean synthetic samples do not measure accents, microphone noise
or real-speaker accuracy. There was no microphone or OpenRouter work in this STT
benchmark. A live check exposed the singular «Покажи устройство» transcription; the final router accepts this untargeted read-only variant. Downstream scores below use the final rules; saved transcripts are unedited.

Environment: existing Linux x86_64 Core container, CPU int8, two CPU threads,
fixed Russian, beam size 1, VAD enabled, no word timestamps, temperature 0 and
condition_on_previous_text=False. Timing includes audio decode, VAD and inference,
excludes model startup and disk read. Startup is reported separately.

| Metric | small (current) | base (smaller) |
|---|---:|---:|
| Average STT | 3,229.6 ms | 1,054.0 ms |
| Median STT | 3,095.0 ms | 1,003.3 ms |
| Model startup | 1,324.5 ms | 342.8 ms |
| Exact normalized transcript accuracy | 34/40 — 85% | 26/40 — 65% |
| Word error rate | 11/150 — 7.33% | 28/150 — 18.67% |
| Downstream local intent accuracy, including fallback | 37/40 — 92.5% | 31/40 — 77.5% |
| Correct local intent + slots on actionable commands | 27/30 — 90% | 21/30 — 70% |
| Incorrect locally accepted actions in this corpus | 0 | 0 |

Exact transcript comparison ignores punctuation, case and е/ё. WER is total word
edit distance divided by total reference words; it counts insertions, deletions
and substitutions. Downstream evaluation passes saved transcripts into the same
local router and fixtures. Incorrect/missing recognition commonly results in
fallback, which reintroduces remote latency even when no wrong local action occurs.
Raw transcripts and per-command timing: [stt_results.json](../benchmarks/stt_results.json).

**Decision: keep Whisper small.** Base was 3.06× faster but lost 20 percentage
points in exact transcription and correct local intent/slots. This small synthetic
corpus does not justify trading away that accuracy. Human microphone recordings
would be needed before changing the production default.

## Deployed voice acceptance

After the final router was deployed, three requests using corpus audio 000
(«Покажи устройства», transcribed as «Покажи устройство.») returned HTTP 200 in
**2710 / 2752 / 2772 ms**. Each reported route_source=local, confidence=0.99,
one devices.list execution, zero router completions and zero final completions.
Core local routing took 2.10–2.55 ms; STT took 2683–2751 ms. These are ready-file
HTTP measurements, not microphone-stop totals. [Raw results](../benchmarks/live_local_voice.jsonl).

A live Chrome MediaRecorder WebM check with the synthetic microphone source
displayed **Local route**, 0 LLM calls and **2481 ms after recording ended**.
STT took 2446 ms, local routing 2.67 ms, the tool 2.30 ms, and browser finalization
13 ms. TTS remains not configured. [Browser timing snapshot](../benchmarks/live_local_browser.json).

Validation: **134 backend tests**, **one frontend unit test**, and **all 13 Chrome
scenarios** passed, including the existing real task-creation/history scenario.
No existing scenario was removed. The original one-LLM/TTS test explicitly injects
no local router so it continues covering the fallback; separate new tests verify
zero LLM calls on local execution. Frontend, Docker and Python distribution builds
passed. Core and Control Center were rebuilt/restarted at localhost:8080.

## Reproduction commands

From the repository root, with project dependencies installed:

```sh
.venv/bin/python scripts/benchmark_intents.py --output benchmarks/intent_results.json
# macOS: requires access to the host speech service
.venv/bin/python scripts/synthesize_voice_corpus.py
# Explicitly provision only the alternative model; no configuration changes
docker compose exec -T delta-core python -c "from faster_whisper.utils import download_model; download_model('base', cache_dir='/models/whisper')"
docker compose cp .runtime/voice-corpus delta-core:/tmp/voice-corpus
docker compose cp benchmarks/russian_commands.json delta-core:/tmp/russian_commands.json
docker compose cp scripts/benchmark_stt_corpus.py delta-core:/tmp/benchmark_stt_corpus.py
docker compose exec -T delta-core python /tmp/benchmark_stt_corpus.py --corpus /tmp/russian_commands.json --audio-dir /tmp/voice-corpus --models small base --output /tmp/stt_results.json
docker compose cp delta-core:/tmp/stt_results.json benchmarks/stt_results.json
.venv/bin/python scripts/analyze_stt_intents.py
```

Synthesized audio stays in ignored `.runtime/`; texts, reference hashes, results
and scripts are versionable. Different macOS voice versions may generate different
waveforms: preserve one generated set for both model runs and record its manifest.
For real microphone benchmarking, supply matching WAV files and update the manifest
with their source, rate metadata, references and hashes before running the script.
