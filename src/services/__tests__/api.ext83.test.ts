/**
 * api ext83 — cover api.ts:159 request interceptor rejection handler (final uncovered line)
 * White-box: directly invoke the registered request interceptor rejected handler
 */
import MockAdapter from 'axios-mock-adapter';
import api from '../api';

jest.mock('expo-secure-store', () => ({
  getItemAsync: jest.fn(),
  setItemAsync: jest.fn(),
  deleteItemAsync: jest.fn(),
}));

const mockAxios = new MockAdapter(api);
afterAll(() => mockAxios.restore());

// api module has been imported, the interceptor registration happened; but interceptor
// registration happened against the real axios instance inside module — access it:
const reqInterceptors = (api.interceptors.request as unknown as {
  handlers: { rejected: (e: unknown) => Promise<never> }[];
}).handlers;
const requestRejected = reqInterceptors[reqInterceptors.length - 1].rejected;

describe('api ext83 — request interceptor rejection handler (line 159)', () => {
  it('propagates the rejection untouched (Promise.reject passthrough)', async () => {
    const err = new Error('upstream interceptor failure');
    await expect(requestRejected(err)).rejects.toBe(err);
  });

  it('propagates non-Error rejection values as-is', async () => {
    await expect(requestRejected('string-error')).rejects.toBe('string-error');
  });

  it('propagates undefined rejection without swallowing', async () => {
    await expect(requestRejected(undefined)).rejects.toBeUndefined();
  });
});
