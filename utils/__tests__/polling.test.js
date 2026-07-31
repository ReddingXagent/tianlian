// utils/__tests__/polling.test.js - 智能轮询测试
const { createPolling } = require('../polling');

/**
 * 在 jest.useFakeTimers() 环境下，async 函数中的 await 创建 microtask。
 * advanceTimersByTime 触发 setTimeout callback 后，callback 内部的
 * await fn() 会创建 microtask，需要额外 flush 才能让后续的 setTimeout 注册。
 */
function tick() {
  return new Promise(resolve => jest.requireActual('timers').setTimeout(resolve, 0));
}

describe('createPolling', () => {
  beforeEach(() => {
    jest.useFakeTimers();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  test('start 后立即执行一次', () => {
    const fn = jest.fn().mockResolvedValue(undefined);
    const polling = createPolling(fn, { interval: 1000 });

    polling.start();
    expect(fn).toHaveBeenCalledTimes(1);

    polling.stop();
  });

  test('stop 后不再执行', () => {
    const fn = jest.fn().mockResolvedValue(undefined);
    const polling = createPolling(fn, { interval: 1000 });

    polling.start();
    expect(fn).toHaveBeenCalledTimes(1);

    polling.stop();
    jest.advanceTimersByTime(5000);
    expect(fn).toHaveBeenCalledTimes(1); // 仍然只有1次
  });

  test('按 interval 定时执行', async () => {
    const fn = jest.fn().mockResolvedValue(undefined);
    const polling = createPolling(fn, { interval: 2000 });

    polling.start();
    expect(fn).toHaveBeenCalledTimes(1);
    await tick(); // flush microtask from first execute() -> setTimeout registered

    // 第1次 interval 触发
    jest.advanceTimersByTime(2000);
    // execute() runs, calls await fn() synchronously (resolved promise),
    // then calls setTimeout. But the await creates a microtask that needs
    // flushing before the next setTimeout is accessible.
    await tick();
    expect(fn).toHaveBeenCalledTimes(2);

    // 第2次 interval 触发
    jest.advanceTimersByTime(2000);
    await tick();
    expect(fn).toHaveBeenCalledTimes(3);

    polling.stop();
  });

  test('失败后指数退避', async () => {
    const fn = jest.fn()
      .mockRejectedValueOnce(new Error('fail'))
      .mockRejectedValueOnce(new Error('fail'))
      .mockResolvedValue(undefined);

    const polling = createPolling(fn, {
      interval: 1000,
      maxRetries: 5,
      backoffFactor: 2,
      maxInterval: 10000
    });

    polling.start();
    expect(fn).toHaveBeenCalledTimes(1);
    await tick();

    // 退避: 2000ms 后重试
    jest.advanceTimersByTime(2000);
    await tick();
    expect(fn).toHaveBeenCalledTimes(2);

    // 退避: 4000ms 后重试
    jest.advanceTimersByTime(4000);
    await tick();
    expect(fn).toHaveBeenCalledTimes(3); // 第3次成功

    polling.stop();
  });

  test('达到 maxRetries 后停止并回调', async () => {
    const fn = jest.fn().mockRejectedValue(new Error('always fail'));
    const onMaxRetries = jest.fn();
    const polling = createPolling(fn, {
      interval: 1000,
      maxRetries: 3,
      onMaxRetries
    });

    polling.start();
    expect(fn).toHaveBeenCalledTimes(1);
    await tick();

    // 退避后第2次 (1000 * 1.5 = 1500ms)
    jest.advanceTimersByTime(1500);
    await tick();
    expect(fn).toHaveBeenCalledTimes(2);

    // 退避后第3次 (1500 * 1.5 = 2250ms) -> retryCount=3 >= maxRetries=3, stop
    jest.advanceTimersByTime(2250);
    await tick();
    // After tick(), the microtask from the rejected await fn() flushes,
    // and the catch block calls stop() + onMaxRetries
    expect(fn).toHaveBeenCalledTimes(3);

    // 应该停止了
    expect(onMaxRetries).toHaveBeenCalledWith(3);
    expect(polling.isActive()).toBe(false);
  });

  test('shouldStop 返回 true 时停止', async () => {
    const fn = jest.fn().mockResolvedValue(undefined);
    let stopFlag = false;

    const polling = createPolling(fn, {
      interval: 1000,
      shouldStop: () => stopFlag
    });

    polling.start();
    expect(fn).toHaveBeenCalledTimes(1);
    await tick();

    stopFlag = true;
    jest.advanceTimersByTime(1000);
    // advanceTimersByTime fires setTimeout -> execute() -> fn() called 2nd time
    // -> shouldStop returns true -> stop() is called.
    // The shouldStop check happens AFTER fn() call, so fn IS called 2nd time.
    await tick();
    expect(fn).toHaveBeenCalledTimes(2);
    // After stop(), isActive should be false and no more timers should fire
    jest.advanceTimersByTime(5000);
    await tick();
    expect(fn).toHaveBeenCalledTimes(2); // 不应再执行
    expect(polling.isActive()).toBe(false);
  });

  test('成功后重置间隔', async () => {
    const fn = jest.fn()
      .mockRejectedValueOnce(new Error('fail'))
      .mockResolvedValue(undefined);

    const polling = createPolling(fn, {
      interval: 1000,
      maxRetries: 5,
      backoffFactor: 2,
      maxInterval: 10000
    });

    polling.start();
    expect(fn).toHaveBeenCalledTimes(1);
    await tick();

    // 退避: 2000ms
    jest.advanceTimersByTime(2000);
    await tick();
    expect(fn).toHaveBeenCalledTimes(2); // 第2次成功

    // 重置后间隔应为 1000ms
    jest.advanceTimersByTime(1000);
    await tick();
    expect(fn).toHaveBeenCalledTimes(3);

    polling.stop();
  });

  test('start 多次调用安全', () => {
    const fn = jest.fn().mockResolvedValue(undefined);
    const polling = createPolling(fn, { interval: 1000 });

    polling.start();
    polling.start(); // 不应触发第二次

    expect(fn).toHaveBeenCalledTimes(1);

    polling.stop();
  });

  test('isActive 反映状态', () => {
    const fn = jest.fn().mockResolvedValue(undefined);
    const polling = createPolling(fn, { interval: 1000 });

    expect(polling.isActive()).toBe(false);

    polling.start();
    expect(polling.isActive()).toBe(true);

    polling.stop();
    expect(polling.isActive()).toBe(false);
  });
});

describe('createPagePolling', () => {
  const { createPagePolling } = require('../polling');

  beforeEach(() => {
    jest.useFakeTimers();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  test('onShow 启动轮询, onHide/onUnload 停止', () => {
    const fn = jest.fn().mockResolvedValue(undefined);
    const page = {};
    const polling = createPagePolling(page, fn, { interval: 1000 });

    expect(polling.isActive()).toBe(false);

    page.onShow();
    expect(polling.isActive()).toBe(true);
    expect(fn).toHaveBeenCalledTimes(1);

    page.onHide();
    expect(polling.isActive()).toBe(false);

    page.onShow();
    expect(polling.isActive()).toBe(true);

    page.onUnload();
    expect(polling.isActive()).toBe(false);
  });

  test('onShow 不重复启动已活跃的轮询', () => {
    const fn = jest.fn().mockResolvedValue(undefined);
    const page = {};
    createPagePolling(page, fn, { interval: 1000 });

    page.onShow();
    page.onShow(); // 第二次不应触发新的 execute
    expect(fn).toHaveBeenCalledTimes(1);

    page.onUnload();
  });

  test('保留并调用页面原有生命周期钩子', () => {
    const fn = jest.fn().mockResolvedValue(undefined);
    const origShow = jest.fn();
    const origHide = jest.fn();
    const origUnload = jest.fn();
    const page = { onShow: origShow, onHide: origHide, onUnload: origUnload };
    createPagePolling(page, fn, { interval: 1000 });

    page.onShow();
    page.onHide();
    page.onUnload();

    expect(origShow).toHaveBeenCalledTimes(1);
    expect(origHide).toHaveBeenCalledTimes(1);
    expect(origUnload).toHaveBeenCalledTimes(1);
  });
});