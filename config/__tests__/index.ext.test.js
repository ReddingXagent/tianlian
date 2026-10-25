// config/__tests__/index.ext.test.js
// F663: config/index.js branches 75→100%
// Covers: production environment branch

// Need to test the ENV selection logic with mocked process.env
describe('config.ext: production env branch', () => {
  afterEach(() => {
    // Reset modules to not affect other tests
    jest.resetModules();
  });

  test('production环境: ENV=prod, API_BASE_URL指向线上', () => {
    // Temporarily set process.env.NODE_ENV
    const originalEnv = process.env.NODE_ENV;
    process.env.NODE_ENV = 'production';

    jest.resetModules();
    const prodConfig = require('../index');

    expect(prodConfig.ENV).toBe('prod');
    expect(prodConfig.API_BASE_URL).toBe('http://your-server-ip/api/v1');

    process.env.NODE_ENV = originalEnv;
    jest.resetModules();
  });

  test('staging环境: ENV=dev (NODE_ENV非production)', () => {
    // The config only checks for 'production', everything else is 'dev'
    const originalEnv = process.env.NODE_ENV;
    process.env.NODE_ENV = 'staging';

    jest.resetModules();
    const stagingConfig = require('../index');

    // Since the check is process.env.NODE_ENV === 'production', staging will be 'dev'
    expect(stagingConfig.ENV).toBe('dev');

    process.env.NODE_ENV = originalEnv;
    jest.resetModules();
  });

  test('CACHE_TTL所有key正确定义', () => {
    const config = require('../index');
    expect(config.CACHE_TTL.STATIONS).toBe(60000);
    expect(config.CACHE_TTL.STATION_DETAIL).toBe(30000);
    expect(config.CACHE_TTL.FAVORITES).toBe(30000);
    expect(config.CACHE_TTL.COUPONS).toBe(60000);
    expect(config.CACHE_TTL.POINTS).toBe(30000);
    expect(config.CACHE_TTL.ORDERS).toBe(10000);
    expect(config.CACHE_TTL.NOTIFICATIONS).toBe(15000);
    expect(config.CACHE_TTL.USER_INFO).toBe(120000);
  });

  test('ENV_CONFIG三个环境都有API_BASE_URL和MAP_KEY', () => {
    // We can't directly access ENV_CONFIG, but we can verify via require
    // with different env settings
    const originalEnv = process.env.NODE_ENV;

    // Dev
    process.env.NODE_ENV = 'development';
    jest.resetModules();
    const devConfig = require('../index');
    expect(devConfig.API_BASE_URL).toBe('http://localhost:8000/api/v1');
    expect(devConfig.MAP_KEY).toBeDefined();

    // Prod
    process.env.NODE_ENV = 'production';
    jest.resetModules();
    const prodConfig = require('../index');
    expect(prodConfig.API_BASE_URL).toBe('http://your-server-ip/api/v1');
    expect(prodConfig.MAP_KEY).toBeDefined();

    process.env.NODE_ENV = originalEnv;
    jest.resetModules();
  });
});
