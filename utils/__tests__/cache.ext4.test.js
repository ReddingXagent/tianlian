/**
 * cache.ext4 — cover default-arg branch: args=[] when omitted
 * Istanbul branch 13[0] tracks the `args = []` default parameter.
 * All existing tests pass args explicitly, so the default path is uncovered.
 */
const { cachedRequest } = require('../cache');

describe('cache.ext4 — omitted args default', () => {
  it('cachedRequest uses default args=[] when second arg is undefined', async () => {
    const apiFn = jest.fn().mockResolvedValue('no-args');
    // Explicitly pass undefined to trigger default-arg for args
    const result = await cachedRequest(apiFn, undefined, { cacheKey: 'omit-args', ttl: 5000 });
    expect(result).toBe('no-args');
    expect(apiFn).toHaveBeenCalledWith(); // called with no spread args
  });

  it('cachedRequest works with only apiFn (both args and options defaulted)', async () => {
    const apiFn = jest.fn().mockResolvedValue('bare');
    const result = await cachedRequest(apiFn);
    expect(result).toBe('bare');
    expect(apiFn).toHaveBeenCalledTimes(1);
  });
});
