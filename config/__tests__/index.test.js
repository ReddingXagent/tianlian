// config/__tests__/index.test.js
const config = require('../index');

describe('Config', () => {
  // ========== API_BASE_URL ==========
  describe('API_BASE_URL', () => {
    it('should be defined', () => {
      expect(config.API_BASE_URL).toBeDefined();
    });

    it('should be a string', () => {
      expect(typeof config.API_BASE_URL).toBe('string');
    });

    it('should start with http', () => {
      expect(config.API_BASE_URL).toMatch(/^https?:\/\//);
    });

    it('should include /api/v1 path', () => {
      expect(config.API_BASE_URL).toContain('/api/v1');
    });

    it('should have correct value for current environment', () => {
      // Dev env returns localhost
      expect(config.API_BASE_URL).toBe('http://localhost:8000/api/v1');
    });
  });

  // ========== MAP_KEY ==========
  describe('MAP_KEY', () => {
    it('should be defined', () => {
      expect(config.MAP_KEY).toBeDefined();
    });

    it('should be a string', () => {
      expect(typeof config.MAP_KEY).toBe('string');
    });

    it('should not be empty', () => {
      expect(config.MAP_KEY.length).toBeGreaterThan(0);
    });
  });

  // ========== REQUEST_TIMEOUT ==========
  describe('REQUEST_TIMEOUT', () => {
    it('should be defined', () => {
      expect(config.REQUEST_TIMEOUT).toBeDefined();
    });

    it('should be a positive number', () => {
      expect(typeof config.REQUEST_TIMEOUT).toBe('number');
      expect(config.REQUEST_TIMEOUT).toBeGreaterThan(0);
    });

    it('should be 15000', () => {
      expect(config.REQUEST_TIMEOUT).toBe(15000);
    });
  });

  // ========== CHARGING_POLL_INTERVAL ==========
  describe('CHARGING_POLL_INTERVAL', () => {
    it('should be defined', () => {
      expect(config.CHARGING_POLL_INTERVAL).toBeDefined();
    });

    it('should be a positive number', () => {
      expect(typeof config.CHARGING_POLL_INTERVAL).toBe('number');
      expect(config.CHARGING_POLL_INTERVAL).toBeGreaterThan(0);
    });

    it('should be 3000', () => {
      expect(config.CHARGING_POLL_INTERVAL).toBe(3000);
    });
  });

  // ========== ORDER_STATUS ==========
  describe('ORDER_STATUS', () => {
    it('should be defined', () => {
      expect(config.ORDER_STATUS).toBeDefined();
    });

    it('should be an object', () => {
      expect(typeof config.ORDER_STATUS).toBe('object');
    });

    it('should have all expected status keys', () => {
      expect(config.ORDER_STATUS).toHaveProperty('CHARGING');
      expect(config.ORDER_STATUS).toHaveProperty('FINISHED');
      expect(config.ORDER_STATUS).toHaveProperty('CANCELLED');
      expect(config.ORDER_STATUS).toHaveProperty('PENDING');
    });

    it('should have correct status values', () => {
      expect(config.ORDER_STATUS.CHARGING).toBe('charging');
      expect(config.ORDER_STATUS.FINISHED).toBe('finished');
      expect(config.ORDER_STATUS.CANCELLED).toBe('cancelled');
      expect(config.ORDER_STATUS.PENDING).toBe('pending');
    });

    it('should have unique status values', () => {
      const values = Object.values(config.ORDER_STATUS);
      const unique = new Set(values);
      expect(unique.size).toBe(values.length);
    });
  });

  // ========== CHARGE_STATUS_MAP ==========
  describe('CHARGE_STATUS_MAP', () => {
    it('should be defined', () => {
      expect(config.CHARGE_STATUS_MAP).toBeDefined();
    });

    it('should be an object', () => {
      expect(typeof config.CHARGE_STATUS_MAP).toBe('object');
    });

    it('should have all expected status keys', () => {
      expect(config.CHARGE_STATUS_MAP).toHaveProperty('idle');
      expect(config.CHARGE_STATUS_MAP).toHaveProperty('charging');
      expect(config.CHARGE_STATUS_MAP).toHaveProperty('offline');
      expect(config.CHARGE_STATUS_MAP).toHaveProperty('fault');
    });

    it('should have correct Chinese labels', () => {
      expect(config.CHARGE_STATUS_MAP.idle).toBe('空闲');
      expect(config.CHARGE_STATUS_MAP.charging).toBe('充电中');
      expect(config.CHARGE_STATUS_MAP.offline).toBe('离线');
      expect(config.CHARGE_STATUS_MAP.fault).toBe('故障');
    });
  });

  // ========== COUPON_STATUS ==========
  describe('COUPON_STATUS', () => {
    it('should be defined', () => {
      expect(config.COUPON_STATUS).toBeDefined();
    });

    it('should have all expected keys', () => {
      expect(config.COUPON_STATUS).toHaveProperty('UNUSED');
      expect(config.COUPON_STATUS).toHaveProperty('USED');
      expect(config.COUPON_STATUS).toHaveProperty('EXPIRED');
    });

    it('should have correct values', () => {
      expect(config.COUPON_STATUS.UNUSED).toBe('unused');
      expect(config.COUPON_STATUS.USED).toBe('used');
      expect(config.COUPON_STATUS.EXPIRED).toBe('expired');
    });
  });

  // ========== COUPON_TYPE ==========
  describe('COUPON_TYPE', () => {
    it('should have all expected types', () => {
      expect(config.COUPON_TYPE).toHaveProperty('AMOUNT');
      expect(config.COUPON_TYPE).toHaveProperty('DISCOUNT');
      expect(config.COUPON_TYPE).toHaveProperty('FREIGHT');
    });

    it('should have correct values', () => {
      expect(config.COUPON_TYPE.AMOUNT).toBe('amount');
      expect(config.COUPON_TYPE.DISCOUNT).toBe('discount');
      expect(config.COUPON_TYPE.FREIGHT).toBe('freight');
    });
  });

  // ========== POINTS_RULES ==========
  describe('POINTS_RULES', () => {
    it('should be defined', () => {
      expect(config.POINTS_RULES).toBeDefined();
    });

    it('should have all expected rules', () => {
      expect(config.POINTS_RULES).toHaveProperty('SIGN_IN_DAILY');
      expect(config.POINTS_RULES).toHaveProperty('CHARGE_PER_YUAN');
      expect(config.POINTS_RULES).toHaveProperty('INVITE_FRIEND');
      expect(config.POINTS_RULES).toHaveProperty('REVIEW_ORDER');
    });

    it('should have positive values', () => {
      Object.values(config.POINTS_RULES).forEach(v => {
        expect(v).toBeGreaterThan(0);
      });
    });

    it('should have SIGN_IN_DAILY = 5', () => {
      expect(config.POINTS_RULES.SIGN_IN_DAILY).toBe(5);
    });
  });

  // ========== NOTIFICATION_TYPES ==========
  describe('NOTIFICATION_TYPES', () => {
    it('should be defined', () => {
      expect(config.NOTIFICATION_TYPES).toBeDefined();
    });

    it('should have all expected types', () => {
      expect(config.NOTIFICATION_TYPES).toHaveProperty('CHARGE_FINISH');
      expect(config.NOTIFICATION_TYPES).toHaveProperty('CHARGE_START');
      expect(config.NOTIFICATION_TYPES).toHaveProperty('PAYMENT_SUCCESS');
      expect(config.NOTIFICATION_TYPES).toHaveProperty('COUPON_EXPIRE');
      expect(config.NOTIFICATION_TYPES).toHaveProperty('SYSTEM');
      expect(config.NOTIFICATION_TYPES).toHaveProperty('PROMOTION');
    });

    it('should have unique type values', () => {
      const values = Object.values(config.NOTIFICATION_TYPES);
      const unique = new Set(values);
      expect(unique.size).toBe(values.length);
    });
  });

  // ========== STATION_FILTERS ==========
  describe('STATION_FILTERS', () => {
    it('should be defined', () => {
      expect(config.STATION_FILTERS).toBeDefined();
    });

    it('should have SORT_BY with expected keys', () => {
      expect(config.STATION_FILTERS.SORT_BY).toHaveProperty('DISTANCE');
      expect(config.STATION_FILTERS.SORT_BY).toHaveProperty('PRICE');
      expect(config.STATION_FILTERS.SORT_BY).toHaveProperty('RATING');
    });

    it('should have GUN_TYPE with AC and DC', () => {
      expect(config.STATION_FILTERS.GUN_TYPE).toHaveProperty('AC');
      expect(config.STATION_FILTERS.GUN_TYPE).toHaveProperty('DC');
      expect(config.STATION_FILTERS.GUN_TYPE.AC).toBe('ac');
      expect(config.STATION_FILTERS.GUN_TYPE.DC).toBe('dc');
    });
  });

  // ========== 配置导出完整性 ==========
  describe('export completeness', () => {
    it('should export all expected keys', () => {
      const keys = Object.keys(config);
      expect(keys).toContain('API_BASE_URL');
      expect(keys).toContain('MAP_KEY');
      expect(keys).toContain('REQUEST_TIMEOUT');
      expect(keys).toContain('CHARGING_POLL_INTERVAL');
      expect(keys).toContain('ORDER_STATUS');
      expect(keys).toContain('CHARGE_STATUS_MAP');
      expect(keys).toContain('COUPON_STATUS');
      expect(keys).toContain('COUPON_TYPE');
      expect(keys).toContain('POINTS_RULES');
      expect(keys).toContain('NOTIFICATION_TYPES');
      expect(keys).toContain('STATION_FILTERS');
    });

    it('should have at least 11 top-level keys', () => {
      expect(Object.keys(config).length).toBeGreaterThanOrEqual(11);
    });

    it('should not have undefined values', () => {
      Object.entries(config).forEach(([, value]) => {
        expect(value).toBeDefined();
      });
    });
  });
});
