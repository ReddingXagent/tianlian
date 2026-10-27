// utils/polling.js - 智能轮询工具
// 自适应间隔 + 失败退避 + 自动停止

/**
 * 创建智能轮询
 * @param {Function} fn - 轮询函数（返回 Promise）
 * @param {object} options
 * @param {number} options.interval - 正常轮询间隔（毫秒）
 * @param {number} options.maxRetries - 连续失败最大次数（默认3）
 * @param {number} options.backoffFactor - 退避因子（默认1.5）
 * @param {number} options.maxInterval - 最大间隔（默认30秒）
 * @param {Function} options.shouldStop - 返回 true 时停止轮询
 * @returns {object} { start, stop, isActive }
 */
function createPolling(fn, options = {}) {
  const {
    interval = 5000,
    maxRetries = 3,
    backoffFactor = 1.5,
    maxInterval = 30000,
    shouldStop = null
  } = options;

  let timer = null;
  let retryCount = 0;
  let currentInterval = interval;
  let active = false;

  function start() {
    if (active) return;
    active = true;
    retryCount = 0;
    currentInterval = interval;
    execute();
  }

  function stop() {
    active = false;
    if (timer) {
      clearTimeout(timer);
      timer = null;
    }
  }

  function isActive() {
    return active;
  }

  async function execute() {
    if (!active) return;

    try {
      await fn();
      // 成功：重置间隔和重试计数
      retryCount = 0;
      currentInterval = interval;
    } catch (err) {
      retryCount++;
      if (retryCount >= maxRetries) {
        stop();
        if (options.onMaxRetries) options.onMaxRetries(retryCount);
        return;
      }
      // 指数退避
      currentInterval = Math.min(
        currentInterval * backoffFactor,
        maxInterval
      );
    }

    // 检查是否应该停止
    if (shouldStop && shouldStop()) {
      stop();
      return;
    }

    if (active) {
      timer = setTimeout(execute, currentInterval);
    }
  }

  return { start, stop, isActive };
}

/**
 * 页面级轮询 Mixin
 * 自动在 onHide/onUnload 时停止，onShow 时恢复
 * @param {Function} fn - 轮询函数
 * @param {object} options - 同 createPolling
 * @returns {object} polling 实例
 */
function createPagePolling(pageInstance, fn, options = {}) {
  const polling = createPolling(fn, options);

  const originalOnShow = pageInstance.onShow;
  const originalOnHide = pageInstance.onHide;
  const originalOnUnload = pageInstance.onUnload;

  pageInstance.onShow = function () {
    if (!polling.isActive()) {
      polling.start();
    }
    if (originalOnShow) originalOnShow.call(this);
  };

  pageInstance.onHide = function () {
    polling.stop();
    if (originalOnHide) originalOnHide.call(this);
  };

  pageInstance.onUnload = function () {
    polling.stop();
    if (originalOnUnload) originalOnUnload.call(this);
  };

  return polling;
}

module.exports = {
  createPolling,
  createPagePolling
};
