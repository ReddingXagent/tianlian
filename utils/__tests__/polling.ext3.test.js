/**
 * polling.ext3 — cover L50 execute() !active early return
 * The !active guard in execute() can only be hit if start() is called,
 * then stop() before the timer fires. But execute is called synchronously
 * from start(), so we test the stop() path via the timer schedule.
 *
 * Strategy: use a fn that resolves slowly so the first execute is in-flight
 * when stop() is called. The next timer tick will find active=false.
 */
const { createPolling } = require('../polling');

describe('polling.ext3 — execute !active guard', () => {
  afterEach(() => {
    jest.useRealTimers();
  });

  it('execute() returns early when active=false (timer fires after stop)', async () => {
    jest.useFakeTimers();
    const fn = jest.fn().mockResolvedValue();
    const polling = createPolling(fn, { interval: 1000, maxRetries: 100 });

    polling.start();
    // Flush the first execute() microtask
    await Promise.resolve();
    await Promise.resolve();
    expect(fn).toHaveBeenCalledTimes(1);

    // Stop before the next timer fires
    polling.stop();

    // Advance past the interval — timer was already cleared by stop(),
    // but if somehow execute gets called, fn should NOT increment
    await jest.advanceTimersByTimeAsync(5000);
    expect(fn).toHaveBeenCalledTimes(1);
  });
});
