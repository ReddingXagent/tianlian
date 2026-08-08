// F664: polling.js branch coverage — L15 (no options arg) + L50 (execute after stop)
const { createPolling } = require('../polling');

function tick() {
  return new Promise(resolve => { jest.requireActual('timers').setTimeout(resolve, 0); });
}

describe('polling.ext2: uncovered branches', () => {
  beforeEach(() => {
    jest.useFakeTimers();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  // L15: createPolling called with no options arg → default {} applies
  test('createPolling(fn) with no options → all defaults', async () => {
    const fn = jest.fn().mockResolvedValue(undefined);
    const polling = createPolling(fn); // no second arg
    polling.start();
    await tick();
    expect(fn).toHaveBeenCalledTimes(1);
    polling.stop();
  });

  // L50: execute() called when !active → early return
  test('execute returns early when not active', async () => {
    const fn = jest.fn().mockResolvedValue(undefined);
    const polling = createPolling(fn, { interval: 1000 });

    // Don't start — execute won't be called
    // Start then immediately stop, then the queued execute fires with active=false
    polling.start();
    polling.stop();
    // Allow any pending microtasks to flush
    await tick();
    // fn may have been called once during start(), but after stop no more calls
    const callCount = fn.mock.calls.length;
    jest.advanceTimersByTime(5000);
    await tick();
    expect(fn.mock.calls.length).toBe(callCount); // no additional calls
  });
});
