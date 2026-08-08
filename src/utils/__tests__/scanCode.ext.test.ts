import { parseScanPayload } from '../scanCode';

describe('scanCode.ext — branch coverage', () => {
  // ── decodeURIComponent fallback (catch branch, L31) ───────
  it('falls back to raw last segment when decodeURIComponent throws', () => {
    // %E0%B4 is an invalid UTF-8 sequence → decodeURIComponent throws
    const result = parseScanPayload('https://x.com/charger/%E0%B4');
    // Should hit the catch block and return the raw (non-decoded) segment
    expect(result).toBe('%E0%B4');
  });

  // ── URL with empty last segment after stripping ──────────
  it('returns original data for URL with only slashes', () => {
    const result = parseScanPayload('https://x.com/');
    // After processing, last segment becomes 'x.com'
    expect(result).toBe('x.com');
  });

  // ── URL with only protocol and slashes ───────────────────
  it('returns data for plain URL without path', () => {
    const result = parseScanPayload('https://example.com');
    // No path beyond domain → last segment is 'example.com'
    expect(result).toBe('example.com');
  });

  // ── valid decodeURIComponent ─────────────────────────────
  it('decodes percent-encoded last segment', () => {
    const result = parseScanPayload('https://x.com/charger/CH%2D001');
    expect(result).toBe('CH-001');
  });

  // ── code match takes priority over URL path ──────────────
  it('extracts code pattern even from URL', () => {
    const result = parseScanPayload('https://x.com/charger/DC-005?from=qr');
    expect(result).toBe('DC-005');
  });

  // ── plain string returns as-is ───────────────────────────
  it('returns plain string trimmed', () => {
    expect(parseScanPayload('  hello world  ')).toBe('hello world');
  });

  // ── empty returns null ────────────────────────────────────
  it('returns null for empty string', () => {
    expect(parseScanPayload('')).toBeNull();
  });

  // ── whitespace only returns null ──────────────────────────
  it('returns null for whitespace only', () => {
    expect(parseScanPayload('   ')).toBeNull();
  });

  // ── code match toUpperCase ────────────────────────────────
  it('uppercases code match', () => {
    expect(parseScanPayload('ab-123')).toBe('AB-123');
  });

  // ── URL with query but no code pattern ───────────────────
  it('extracts path segment from URL with query params', () => {
    expect(parseScanPayload('https://x.com/station/ZH-ABC')).toBe('ZH-ABC');
  });

  // ── non-URL with no code → original ──────────────────────
  it('returns original for non-URL non-code string', () => {
    expect(parseScanPayload('random-string')).toBe('random-string');
  });

  // ── custom scheme URL ─────────────────────────────────────
  it('handles custom scheme URL', () => {
    expect(parseScanPayload('myapp://charge/AB-999')).toBe('AB-999');
  });
});
