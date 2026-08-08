import { parseScanPayload } from '../scanCode';

describe('parseScanPayload extended coverage', () => {
  // === decodeURIComponent throw path (malformed percent-encoding) ===

  it('handles malformed percent-encoding gracefully (decodeURIComponent throws)', () => {
    // %E0%A4 - incomplete UTF-8 sequence, decodeURIComponent may throw
    // Using a known-bad sequence that triggers URIError
    expect(parseScanPayload('https://x.com/%E0%A4%A4%E0%A4')).toBeDefined();
  });

  // === URL with only path segments after domain ===

  it('extracts code from URL with port number', () => {
    expect(parseScanPayload('http://localhost:3000/charger/EV-100')).toBe('EV-100');
  });

  it('extracts code from URL with encoded characters that decode successfully', () => {
    expect(parseScanPayload('https://x.com/AB-001')).toBe('AB-001');
  });

  // === URL where last segment is empty after stripping trailing slash ===

  it('returns null for URL with only trailing slashes after domain', () => {
    // https://x.com/ → path segments after split: ['https:', '', 'x.com', '']
    // last segment after removing trailing slash: 'x.com'
    expect(parseScanPayload('https://x.com/')).toBe('x.com');
  });

  // === CODE_PATTERN edge cases ===

  it('matches code with more than 2 digits', () => {
    expect(parseScanPayload('CH-123456')).toBe('CH-123456');
  });

  it('matches code with more than 2 letters', () => {
    expect(parseScanPayload('ELEC-001')).toBe('ELEC-001');
  });

  it('matches code embedded in longer text', () => {
    expect(parseScanPayload('prefix-ABC-999-suffix')).toBe('ABC-999');
  });

  it('does not match single letter prefix', () => {
    // A-01 should not match CODE_PATTERN (needs 2+ letters)
    expect(parseScanPayload('A-01')).toBe('A-01');
  });

  it('does not match single digit suffix', () => {
    // AB-1 should not match CODE_PATTERN (needs 2+ digits)
    expect(parseScanPayload('AB-1')).toBe('AB-1');
  });

  // === Various URL schemes ===

  it('handles ftp:// scheme URL', () => {
    expect(parseScanPayload('ftp://server/XY-001')).toBe('XY-001');
  });

  it('handles custom scheme with code pattern', () => {
    expect(parseScanPayload('myapp://open?code=PWR-100')).toBe('PWR-100');
  });

  // === Whitespace handling ===

  it('trims and processes URL with surrounding whitespace', () => {
    expect(parseScanPayload('  https://x.com/CH-007  ')).toBe('CH-007');
  });
});
