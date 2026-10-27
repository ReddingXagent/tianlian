/**
 * cache.ext3 — cover default-arg branch L139 (ttl = 30000 default)
 */
const { cachedRequest } = require('../cache');

describe('cache.ext3 — default ttl branch', () => {
  it('uses default ttl=30000 when ttl not provided', async () => {
    const apiFn = jest.fn().mockResolvedValue({ data: 'default-ttl' });
    const result = await cachedRequest(apiFn, [], { cacheKey: 'test-default-ttl' });
    expect(result).toEqual({ data: 'default-ttl' });
    // Second call should hit cache (default 30s TTL)
    const result2 = await cachedRequest(apiFn, [], { cacheKey: 'test-default-ttl' });
    expect(result2).toEqual({ data: 'default-ttl' });
    expect(apiFn).toHaveBeenCalledTimes(1);
  });
});
