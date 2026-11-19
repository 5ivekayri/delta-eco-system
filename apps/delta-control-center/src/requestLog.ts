export interface InferenceRequest {
  provider: 'openrouter'|'local'|'mock'|'bridge_unknown'; model: string|null;
  role: string; duration_ms: number; outcome: string; attempts?: number; fallback?: boolean;
}
export interface RequestLogEntry {
  id: number; time: string; kind: string; status: number; duration_ms: number;
  calls?: InferenceRequest[];
}
let entries: RequestLogEntry[] = [];
let sequence = 0;
const listeners = new Set<()=>void>();
export const loggingEnabled = () => sessionStorage.getItem('delta-llm-log') === 'true';
const notify = () => listeners.forEach(listener=>listener());
export function setLogging(enabled: boolean) {
  sessionStorage.setItem('delta-llm-log', String(enabled));
  notify();
}
export function clearRequestLog() {entries = []; notify();}
export function addRequestLog(kind: string, status: number, duration_ms: number, calls?: InferenceRequest[]) {
  if (!loggingEnabled()) return;
  entries = [{id: ++sequence, time: new Date().toLocaleTimeString('ru-RU'), kind, status, duration_ms, calls}, ...entries].slice(0,50);
  notify();
}
export const getRequestLog = () => entries;
export function subscribeRequestLog(listener: ()=>void) {listeners.add(listener); return ()=>{listeners.delete(listener);};}
