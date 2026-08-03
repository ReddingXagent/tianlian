import { parseScanPayload } from '../scanCode';

describe('parseScanPayload', () => {
  it('returns plain charger code as-is', () => {
    expect(parseScanPayload('CH-001')).toBe('CH-001');
  });

  it('uppercases lowercase codes', () => {
    expect(parseScanPayload('ch-002')).toBe('CH-002');
  });

  it('trims surrounding whitespace', () => {
    expect(parseScanPayload('  CH-003  ')).toBe('CH-003');
  });

  it('extracts code from URL payload', () => {
    expect(parseScanPayload('https://charge.tianlian.com/charger/CH-001')).toBe('CH-001');
  });

  it('extracts code from URL with query and hash', () => {
    expect(parseScanPayload('https://x.com/charger/CH-003?from=qr#top')).toBe('CH-003');
  });

  it('handles URL with trailing slash', () => {
    expect(parseScanPayload('https://x.com/charger/CH-004/')).toBe('CH-004');
  });

  it('falls back to last path segment when no code pattern', () => {
    expect(parseScanPayload('https://x.com/abc')).toBe('abc');
  });

  it('decodes percent-encoded last segment', () => {
    expect(parseScanPayload('https://x.com/CH%2D005')).toBe('CH-005');
  });

  it('extracts code embedded in custom scheme payload', () => {
    expect(parseScanPayload('tianlian://scan?code=CH-006')).toBe('CH-006');
  });

  it('returns raw payload when no pattern and not URL', () => {
    expect(parseScanPayload('HELLO')).toBe('HELLO');
  });

  it('returns null for empty or whitespace-only payload', () => {
    expect(parseScanPayload('')).toBeNull();
    expect(parseScanPayload('   ')).toBeNull();
  });
});
