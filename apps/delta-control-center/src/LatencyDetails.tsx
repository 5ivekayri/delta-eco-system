import {VoiceTimings} from './api';

export function LatencyDetails({timings}: {timings:VoiceTimings}) {
  const ms = (value:number|undefined) => value === undefined ? '—' : `${Math.round(value)} ms`;
  return <details className="voice-latency"><summary>Voice latency · {timings.execution_path} · {ms(timings.total_ms ?? timings.server_total_ms)}</summary>
    <dl>
      <div><dt>Route</dt><dd>{timings.route_source === 'local' ? 'Local route' : 'LLM route'}</dd></div>
      <div><dt>Local router ms</dt><dd>{ms(timings.local_router_ms)} · confidence {timings.confidence === undefined ? '—' : `${Math.round(timings.confidence * 100)}%`}</dd></div>
      <div><dt>Audio upload</dt><dd>{ms(timings.client_upload_ms)} (browser), {ms(timings.upload_ms)} (Core)</dd></div>
      <div><dt>STT ms</dt><dd>{ms(timings.stt_ms)}</dd></div>
      <div><dt>Router ms</dt><dd>{ms(timings.router_ms)} · {timings.router_calls} calls</dd></div>
      <div><dt>Tool ms</dt><dd>{ms(timings.tool_ms)}</dd></div>
      <div><dt>Response generation ms</dt><dd>{ms(timings.response_generation_ms)} · {timings.response_generation_calls} LLM calls</dd></div>
      <div><dt>TTS ms</dt><dd>{timings.tts_status==='not_configured' ? 'Not configured' : ms(timings.tts_ms)+' · '+timings.tts_status}</dd></div>
      <div><dt>Total ms</dt><dd>{ms(timings.total_ms)} after recording ends</dd></div>
      <div><dt>Server total</dt><dd>{ms(timings.server_total_ms)}</dd></div>
      <div><dt>Recording finalization</dt><dd>{ms(timings.finalization_ms)}</dd></div>
    </dl>
  </details>;
}
