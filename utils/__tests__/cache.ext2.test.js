// F664: cache.js branch coverage — lines 28-29 (TTL expired deletion path)
const { LRUCache, cache } = require('../cache');

afterAll(() => {
  cache.clear();
});

describe('cache.ext2: TTL expired deletion path (L28-29)', () => {
  beforeEach(() => {
    cache.clear();
  });

  test('get: entry with expired TTL → delete + return null (sync)', () => {
    const c = new LRUCache(5);
    c.set('expiring', 'val', 1000);
    // Manually backdate the expireAt to simulate expiration synchronously
    const entry = c.cache.get('expiring');
    entry.expireAt = Date.now() - 1; // already expired
    // get() should delete and return null
    expect(c.get('expiring')).toBeNull();
    // Verify it was deleted from cache
    expect(c.cache.has('expiring')).toBe(false);
  });

  test('get: entry.expireAt truthy but not yet expired → LRU reorder, no delete', () => {
    const c = new LRUCache(5);
    c.set('fresh', 'val', 5000);
    // expireAt is in the future
    const entry = c.cache.get('fresh');
    expect(entry.expireAt).toBeGreaterThan(Date.now());
    // get() should return value (not expired)
    expect(c.get('fresh')).toBe('val');
    // Key should still exist
    expect(c.cache.has('fresh')).toBe(true);
  });

  test('get: entry with ttl=0 (expireAt=0) → LRU reorder but no timer refresh', () => {
    const c = new LRUCache(5);
    c.set('permanent', 'val', 0);
    // expireAt should be 0
    const entry = c.cache.get('permanent');
    expect(entry.expireAt).toBe(0);
    // get() should return value
    expect(c.get('permanent')).toBe('val');
    // No timer should exist for this key
    expect(c.timers.permanent).toBeUndefined();
  });
});
