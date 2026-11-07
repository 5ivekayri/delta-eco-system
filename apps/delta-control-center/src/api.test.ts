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
