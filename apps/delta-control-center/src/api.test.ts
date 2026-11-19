import { afterEach, expect, it, vi } from 'vitest';
import { request } from './api';
afterEach(() => vi.unstubAllGlobals());
it('sends CSRF header without legacy token and propagates structured API errors', async () => {
  vi.stubGlobal('sessionStorage', {getItem: () => 'test-token'});
  const fetchMock = vi.fn().mockResolvedValue({ok: false, json: async () => ({message: 'Device offline'})});
  vi.stubGlobal('fetch', fetchMock);
  await expect(request('/core/api/v1/devices')).rejects.toThrow('Device offline');
  expect(fetchMock.mock.calls[0][1].headers.get('Authorization')).toBeNull();
  expect(fetchMock.mock.calls[0][1].headers.get('X-Delta-Request')).toBe('1');
});

it('opts into metadata only while logging is enabled', async () => {
  const {clearRequestLog,getRequestLog,setLogging} = await import('./requestLog');
  const storage = new Map<string,string>();
  vi.stubGlobal('sessionStorage', {getItem:(key:string)=>storage.get(key),setItem:(key:string,value:string)=>storage.set(key,value)});
  clearRequestLog();
  const fetchMock = vi.fn().mockResolvedValue({ok:true,status:200,json:async()=>({timings:{llm_requests:[{provider:'local',model:'Qwen',duration_ms:12,outcome:'ok',role:'assistant'}]}})});
  vi.stubGlobal('fetch',fetchMock);
  const path='/core/api/v1/assistant/message';
  await request(path);
  expect(fetchMock.mock.calls[0][1].headers.has('X-Delta-LLM-Log')).toBe(false);
  expect(getRequestLog()).toHaveLength(0);
  setLogging(true);
  await request(path);
  expect(fetchMock.mock.calls[1][1].headers.get('X-Delta-LLM-Log')).toBe('1');
  expect(getRequestLog()[0].calls?.[0].provider).toBe('local');
  setLogging(false);
  await request(path);
  expect(getRequestLog()).toHaveLength(1);
  expect(fetchMock.mock.calls[2][1].headers.has('X-Delta-LLM-Log')).toBe(false);
});
