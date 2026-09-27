"""Request-scoped monotonic timings; no prompts, audio or credentials in telemetry."""
from contextlib import contextmanager
from dataclasses import dataclass, field
from time import perf_counter


@dataclass
class VoiceTimings:
    started: float = field(default_factory=perf_counter)
    upload_ms: float = 0.0
    stt_ms: float = 0.0
    router_ms: float = 0.0
    local_router_ms: float = 0.0
    route_source: str = 'llm'
    confidence: float = 0.0
    tool_ms: float = 0.0
    response_generation_ms: float = 0.0
    tts_ms: float = 0.0
    router_calls: int = 0
    response_generation_calls: int = 0
    execution_path: str = 'smart'
    tts_status: str = 'not_configured'

    @contextmanager
    def measure(self, name):
        start = perf_counter()
        try:
            yield
        finally:
            setattr(self, name, getattr(self, name) + (perf_counter() - start) * 1000)

    def snapshot(self):
        return {**{name: round(getattr(self, name), 2) for name in (
            'upload_ms', 'stt_ms', 'router_ms', 'local_router_ms', 'tool_ms', 'response_generation_ms', 'tts_ms')},
            'route_source': self.route_source, 'confidence': self.confidence,
            'server_total_ms': round((perf_counter() - self.started) * 1000, 2),
            'router_calls': self.router_calls, 'response_generation_calls': self.response_generation_calls,
            'execution_path': self.execution_path, 'tts_status': self.tts_status}
