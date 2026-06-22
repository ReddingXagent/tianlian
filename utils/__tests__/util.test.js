// utils/__tests__/util.test.js
const util = require('../util');

describe('Util', () => {
  // ========== formatTime ==========
  describe('formatTime', () => {
    it('should format date with default format YYYY-MM-DD HH:mm:ss', () => {
      const date = new Date(2025, 0, 15, 8, 5, 3); // Jan 15, 2025 08:05:03
      const result = util.formatTime(date);
      expect(result).toBe('2025-01-15 08:05:03');
    });

    it('should format date with custom format', () => {
      const date = new Date(2025, 5, 1, 14, 30, 45); // Jun 1, 2025 14:30:45
      expect(util.formatTime(date, 'YYYY-MM-DD')).toBe('2025-06-01');
      expect(util.formatTime(date, 'HH:mm')).toBe('14:30');
      expect(util.formatTime(date, 'YYYY/MM/DD HH:mm:ss')).toBe('2025/06/01 14:30:45');
    });

    it('should accept timestamp (number)', () => {
      const ts = new Date(2025, 2, 10, 12, 0, 0).getTime();
      const result = util.formatTime(ts);
      expect(result).toBe('2025-03-10 12:00:00');
    });

    it('should accept ISO string', () => {
      const result = util.formatTime('2025-07-20T09:15:30');
      expect(result).toBe('2025-07-20 09:15:30');
    });

    it('should return empty string for falsy input', () => {
      expect(util.formatTime(null)).toBe('');
      expect(util.formatTime(undefined)).toBe('');
      expect(util.formatTime('')).toBe('');
      expect(util.formatTime(0)).toBe('');
    });

    it('should return empty string for invalid date', () => {
      expect(util.formatTime('not-a-date')).toBe('');
      expect(util.formatTime('2025-13-45')).toBe('');
    });

    it('should pad single-digit values with zero', () => {
      const date = new Date(2025, 0, 5, 3, 7, 9);
      expect(util.formatTime(date)).toBe('2025-01-05 03:07:09');
    });

    it('should handle midnight correctly', () => {
      const date = new Date(2025, 11, 31, 0, 0, 0);
      expect(util.formatTime(date)).toBe('2025-12-31 00:00:00');
    });
  });

  // ========== formatMoney ==========
  describe('formatMoney', () => {
    it('should convert cents to yuan with 2 decimal places', () => {
      expect(util.formatMoney(100)).toBe('1.00');
      expect(util.formatMoney(2550)).toBe('25.50');
      expect(util.formatMoney(1)).toBe('0.01');
      expect(util.formatMoney(0)).toBe('0.00');
    });

    it('should handle large amounts', () => {
      expect(util.formatMoney(100000)).toBe('1000.00');
      expect(util.formatMoney(999999)).toBe('9999.99');
    });

    it('should return 0.00 for null/undefined', () => {
      expect(util.formatMoney(null)).toBe('0.00');
      expect(util.formatMoney(undefined)).toBe('0.00');
    });

    it('should handle negative amounts', () => {
      expect(util.formatMoney(-500)).toBe('-5.00');
    });
  });

  // ========== calcDistance ==========
  describe('calcDistance', () => {
    it('should return 0 for same coordinates', () => {
      const dist = util.calcDistance(30.5, 120.5, 30.5, 120.5);
      expect(dist).toBeCloseTo(0, 5);
    });

    it('should calculate distance between two known points', () => {
      // Beijing (39.9042, 116.4074) to Shanghai (31.2304, 121.4737)
      // ~1068 km
      const dist = util.calcDistance(39.9042, 116.4074, 31.2304, 121.4737);
      expect(dist).toBeGreaterThan(1050);
      expect(dist).toBeLessThan(1100);
    });

    it('should calculate short distance correctly', () => {
      // ~1.11 km apart (0.01 degree lat ≈ 1.11 km)
      const dist = util.calcDistance(30.5, 120.5, 30.51, 120.5);
      expect(dist).toBeGreaterThan(1.0);
      expect(dist).toBeLessThan(1.2);
    });

    it('should handle equatorial coordinates', () => {
      const dist = util.calcDistance(0, 0, 0, 1);
      // 1 degree longitude at equator ≈ 111.32 km
      expect(dist).toBeGreaterThan(110);
      expect(dist).toBeLessThan(112);
    });

    it('should handle polar coordinates', () => {
      const dist = util.calcDistance(89, 0, 90, 0);
      // 1 degree latitude ≈ 111.32 km
      expect(dist).toBeGreaterThan(110);
      expect(dist).toBeLessThan(112);
    });

    it('should return a number', () => {
      const dist = util.calcDistance(30, 120, 31, 121);
      expect(typeof dist).toBe('number');
      expect(dist).toBeGreaterThan(0);
    });
  });

  // ========== formatDuration ==========
  describe('formatDuration', () => {
    it('should format minutes to hours and minutes', () => {
      expect(util.formatDuration(90)).toBe('1小时30分钟');
      expect(util.formatDuration(125)).toBe('2小时5分钟');
    });

    it('should format exact hours', () => {
      expect(util.formatDuration(60)).toBe('1小时');
      expect(util.formatDuration(120)).toBe('2小时');
      expect(util.formatDuration(180)).toBe('3小时');
    });

    it('should format minutes only (< 60)', () => {
      expect(util.formatDuration(30)).toBe('30分钟');
      expect(util.formatDuration(1)).toBe('1分钟');
      expect(util.formatDuration(59)).toBe('59分钟');
    });

    it('should return 0分钟 for zero or falsy', () => {
      expect(util.formatDuration(0)).toBe('0分钟');
      expect(util.formatDuration(null)).toBe('0分钟');
      expect(util.formatDuration(undefined)).toBe('0分钟');
    });

    it('should return 0分钟 for negative values', () => {
      expect(util.formatDuration(-10)).toBe('0分钟');
    });

    it('should handle large values', () => {
      expect(util.formatDuration(1440)).toBe('24小时');
      expect(util.formatDuration(1500)).toBe('25小时');
    });

    it('should floor fractional minutes', () => {
      expect(util.formatDuration(90.7)).toBe('1小时30分钟');
    });
  });

  // ========== formatPrice ==========
  describe('formatPrice', () => {
    it('should format with ¥ symbol', () => {
      expect(util.formatPrice(25.5)).toBe('¥25.50');
      expect(util.formatPrice(100)).toBe('¥100.00');
      expect(util.formatPrice(0)).toBe('¥0.00');
    });

    it('should return ¥0.00 for null/undefined', () => {
      expect(util.formatPrice(null)).toBe('¥0.00');
      expect(util.formatPrice(undefined)).toBe('¥0.00');
    });

    it('should handle string numbers', () => {
      expect(util.formatPrice('25.5')).toBe('¥25.50');
    });
  });

  // ========== formatDistance ==========
  describe('formatDistance', () => {
    it('should show meters for < 1km', () => {
      expect(util.formatDistance(0.5)).toBe('500m');
      expect(util.formatDistance(0.05)).toBe('50m');
      expect(util.formatDistance(0.999)).toBe('999m');
    });

    it('should show km with 1 decimal for >= 1km', () => {
      expect(util.formatDistance(1)).toBe('1.0km');
      expect(util.formatDistance(5.67)).toBe('5.7km');
      expect(util.formatDistance(100)).toBe('100.0km');
    });

    it('should return 未知 for null/undefined', () => {
      expect(util.formatDistance(null)).toBe('未知');
      expect(util.formatDistance(undefined)).toBe('未知');
    });
  });

  // ========== formatPower ==========
  describe('formatPower', () => {
    it('should format kWh with 2 decimals', () => {
      expect(util.formatPower(5.2)).toBe('5.20 kWh');
      expect(util.formatPower(10)).toBe('10.00 kWh');
    });

    it('should return 0 kWh for null/undefined', () => {
      expect(util.formatPower(null)).toBe('0 kWh');
      expect(util.formatPower(undefined)).toBe('0 kWh');
    });
  });

  // ========== maskPhone ==========
  describe('maskPhone', () => {
    it('should mask middle 4 digits', () => {
      expect(util.maskPhone('13812345678')).toBe('138****5678');
      expect(util.maskPhone('15900001111')).toBe('159****1111');
    });

    it('should return original for non-11-digit', () => {
      expect(util.maskPhone('12345')).toBe('12345');
      expect(util.maskPhone(null)).toBe(null);
      expect(util.maskPhone('')).toBe('');
    });
  });

  // ========== generateId ==========
  describe('generateId', () => {
    it('should generate unique IDs', () => {
      const id1 = util.generateId();
      const id2 = util.generateId();
      expect(id1).not.toBe(id2);
    });

    it('should contain timestamp and random part', () => {
      const id = util.generateId();
      expect(id).toContain('_');
      const [ts, rand] = id.split('_');
      expect(Number(ts)).toBeGreaterThan(0);
      expect(rand.length).toBeGreaterThan(0);
    });
  });

  // ========== debounce ==========
  describe('debounce', () => {
    jest.useFakeTimers();

    it('should delay function execution', () => {
      const fn = jest.fn();
      const debounced = util.debounce(fn, 500);

      debounced();
      expect(fn).not.toHaveBeenCalled();

      jest.advanceTimersByTime(500);
      expect(fn).toHaveBeenCalledTimes(1);
    });

    it('should reset timer on repeated calls', () => {
      const fn = jest.fn();
      const debounced = util.debounce(fn, 500);

      debounced();
      jest.advanceTimersByTime(300);
      debounced();
      jest.advanceTimersByTime(300);
      expect(fn).not.toHaveBeenCalled();
      jest.advanceTimersByTime(200);
      expect(fn).toHaveBeenCalledTimes(1);
    });

    it('should pass arguments to original function', () => {
      const fn = jest.fn();
      const debounced = util.debounce(fn, 300);

      debounced('hello', 42);
      jest.advanceTimersByTime(300);
      expect(fn).toHaveBeenCalledWith('hello', 42);
    });

    it('should use default delay of 300ms', () => {
      const fn = jest.fn();
      const debounced = util.debounce(fn);

      debounced();
      jest.advanceTimersByTime(299);
      expect(fn).not.toHaveBeenCalled();
      jest.advanceTimersByTime(1);
      expect(fn).toHaveBeenCalledTimes(1);
    });
  });

  // ========== throttle ==========
  describe('throttle', () => {
    jest.useFakeTimers();

    it('should execute immediately on first call', () => {
      const fn = jest.fn();
      const throttled = util.throttle(fn, 500);

      throttled();
      expect(fn).toHaveBeenCalledTimes(1);
    });

    it('should not execute again within interval', () => {
      const fn = jest.fn();
      const throttled = util.throttle(fn, 500);

      throttled();
      throttled();
      throttled();
      expect(fn).toHaveBeenCalledTimes(1);
    });

    it('should execute again after interval', () => {
      const fn = jest.fn();
      const throttled = util.throttle(fn, 500);

      throttled();
      jest.advanceTimersByTime(600);
      throttled();
      expect(fn).toHaveBeenCalledTimes(2);
    });

    it('should pass arguments to original function', () => {
      const fn = jest.fn();
      const throttled = util.throttle(fn, 300);

      throttled('a', 'b');
      expect(fn).toHaveBeenCalledWith('a', 'b');
    });

    it('should use default interval of 300ms', () => {
      const fn = jest.fn();
      const throttled = util.throttle(fn);

      throttled();
      jest.advanceTimersByTime(200);
      throttled();
      expect(fn).toHaveBeenCalledTimes(1);
      jest.advanceTimersByTime(100);
      throttled();
      expect(fn).toHaveBeenCalledTimes(2);
    });
  });
});
