# Voice pipeline

Target implementation for phases 6–7. No continuous listening or wake word.

1. Browser requests microphone permission only after a user click.
2. MediaRecorder captures a supported format (`audio/webm`, `audio/ogg` or browser-supported MP4). The browser stops tracks after recording/cancel/unmount.
3. `POST /api/v1/assistant/voice` receives multipart audio and optional current device context. Core checks upload size and rejects empty/invalid audio.
4. STTProvider transcribes locally. WhisperSTTProvider uses faster-whisper; blocking inference runs outside the async event loop.
5. Transcript enters the same Assistant path as text. LLM selects validated registered tools; Core dispatches and records results.
6. TTSProvider synthesizes the final text. PiperTTSProvider loads an explicitly configured local voice model and produces WAV. No user-controlled shell command is constructed.
7. Response contains transcript, assistant text, tool calls/results, `audio_available` and audio data/reference. Browser plays it and releases object URLs afterwards.

## Providers and setup

Whisper and Piper run locally after model provisioning. Model downloads are a setup step; inference does not require a paid STT service. Model files, licenses, sizes and exact commands must be documented when the providers are implemented. Voice dependencies belong to an optional installation extra/container configuration. Default configuration must report missing models honestly.

MockSTTProvider and MockTTSProvider exist for deterministic tests without a microphone or model files. The UI must not imply real speech recognition or audible speech synthesis when a mock is selected.

## Failure behavior

- Microphone denied/unavailable: show an actionable message; text remains usable.
- STT unavailable: structured `STT_UNAVAILABLE`; never silently substitute a fixed transcript and execute it as the user's request.
- Empty transcript: ask for another recording; execute no tool.
- LLM unavailable: `LLM_UNAVAILABLE`; no inferred success.
- Tool error: preserve error and partial results in response/activity.
- Piper unavailable: keep successful tool results and text; set `audio_available=false` and report `TTS_UNAVAILABLE`.
- Playback blocked: offer a user-initiated play button without rerunning the assistant/tool.

States: Idle, Listening, Transcribing, Thinking, Executing Tool, Speaking, Error. These describe operations, not hidden chain-of-thought. Do not invent server progress when only a synchronous response is available.

## Acceptance

Mock pipeline tests validate audio request→transcript→tool→response→TTS invocation. Separate real-model checks must establish actual recognition and audible synthesized output; mocks alone do not satisfy voice acceptance.
