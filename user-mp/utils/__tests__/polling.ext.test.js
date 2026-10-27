// utils/__tests__/polling.ext.test.js
// F663: polling.js branches 87→100%
const { createPolling, createPagePolling } = require('../polling');

function tick() {
  return new Promise(resolve => { jest.requireActual('timers').setTimeout(resolve, 0); });
}

describe('polling.ext: branches 87→100%', () => {
  beforeEach(() => {
    jest.useFakeTimers();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  // L15: interval default 5000, L17: shouldStop default null
  test('全默认参数创建轮询 (interval=5000, shouldStop=null)', async () => {
    const fn = jest.fn().mockResolvedValue(undefined);
    // Call with empty options - defaults apply
    const polling = createPolling(fn, {});

    polling.start();
    await tick();
    expect(fn).toHaveBeenCalledTimes(1);

    // With default interval=5000, advance 5000ms
    jest.advanceTimersByTime(5000);
    await tick();
    expect(fn).toHaveBeenCalledTimes(2);

    polling.stop();
  });

  // L50: stop() when timer is null (before execute sets it)
  test('stop: timer=null时不崩溃', () => {
    const fn = jest.fn().mockResolvedValue(undefined);
    const polling = createPolling(fn, { interval: 1000 });

    // Start and immediately stop before any timer is set
    // start() calls execute() synchronously which calls fn() async
    // timer won't be set until after the microtask completes
    polling.start();
    // Don't await tick - stop immediately
    polling.stop();
    expect(polling.isActive()).toBe(false);
  });

  // L92: createPagePolling options default {}
  test('createPagePolling: 无options参数 → 默认{}', () => {
    const fn = jest.fn().mockResolvedValue(undefined);
    const page = {};

    // Call without options argument
    createPagePolling(page, fn);

    expect(() => page.onShow()).not.toThrow();
    expect(() => page.onHide()).not.toThrow();
    expect(() => page.onUnload()).not.toThrow();
  });

  // Cover: createPagePolling with no original lifecycle hooks
  test('createPagePolling: 页面无原有钩子时不崩溃', () => {
    const fn = jest.fn().mockResolvedValue(undefined);
    const page = {};

    createPagePolling(page, fn, { interval: 1000 });

    expect(() => page.onShow()).not.toThrow();
    expect(() => page.onHide()).not.toThrow();
    expect(() => page.onUnload()).not.toThrow();
  });

  // Cover: shouldStop=null branch (no shouldStop function)
  test('shouldStop=null: 不检查停止条件', async () => {
    const fn = jest.fn().mockResolvedValue(undefined);
    const polling = createPolling(fn, { interval: 1000 });

    polling.start();
    await tick();

    jest.advanceTimersByTime(1000);
    await tick();
    expect(fn).toHaveBeenCalledTimes(2);

    polling.stop();
  });

  // Cover: maxInterval cap
  test('退避不超过maxInterval上限', async () => {
    const fn = jest.fn().mockRejectedValue(new Error('fail'));
    const polling = createPolling(fn, {
      interval: 1000,
      maxRetries: 10,
      backoffFactor: 10,
      maxInterval: 5000
    });

    polling.start();
    await tick();

    jest.advanceTimersByTime(5000);
    await tick();
    expect(fn).toHaveBeenCalledTimes(2);

    jest.advanceTimersByTime(5000);
    await tick();
    expect(fn).toHaveBeenCalledTimes(3);

    polling.stop();
  });
});
