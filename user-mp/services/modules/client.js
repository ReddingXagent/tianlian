// services/modules/client.js - HTTP请求封装 + token管理
const config = require('../../config/index');

const BASE_URL = config.API_BASE_URL;
const TIMEOUT = config.REQUEST_TIMEOUT;
const MAX_RETRY = 1; // 网络层重试次数 (非幂等请求不重试)

/**
 * 通用请求封装
 * @param {string} url - 接口路径（不含base）
 * @param {object} options - 请求选项 (form=true 时走 x-www-form-urlencoded)
 * @returns {Promise}
 */
function request(url, options = {}) {
  const {
    method = 'GET',
    data = {},
    header = {},
    showLoading = false,
    loadingText = '加载中...',
    form = false
  } = options;

  const token = wx.getStorageSync('token');

  // form模式: 对象 → urlencoded 字符串 (对齐OAuth2PasswordRequestForm)
  let payload = data;
  let contentType = 'application/json';
  if (form) {
    contentType = 'application/x-www-form-urlencoded';
    payload = Object.keys(data)
      .filter((k) => data[k] !== undefined && data[k] !== null)
      .map((k) => `${encodeURIComponent(k)}=${encodeURIComponent(data[k])}`)
      .join('&');
  }

  const isIdempotent = method === 'GET' || method === 'HEAD';

  function doRequest(attempt) {
    return new Promise((resolve, reject) => {
      if (showLoading) {
        wx.showLoading({ title: loadingText, mask: true });
      }

      wx.request({
        url: `${BASE_URL}${url}`,
        method,
        data: payload,
        timeout: TIMEOUT,
        header: {
          'Content-Type': contentType,
          ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
          ...header
        },
        success(res) {
          const { statusCode, data: resData } = res;

          if (statusCode === 200) {
            if (resData.code === 0 || resData.code === 200) {
              resolve(resData);
            } else if (resData.code === 401) {
              wx.removeStorageSync('token');
              wx.showToast({ title: '登录已过期，请重新登录', icon: 'none' });
              reject(new Error('TOKEN_EXPIRED'));
            } else {
              wx.showToast({ title: resData.message || '请求失败', icon: 'none' });
              reject(new Error(resData.message || 'REQUEST_ERROR'));
            }
          } else if (statusCode === 401) {
            wx.removeStorageSync('token');
            wx.showToast({ title: '登录已过期', icon: 'none' });
            reject(new Error('TOKEN_EXPIRED'));
          } else if (statusCode >= 500 && isIdempotent && attempt < MAX_RETRY) {
            const t = setTimeout(() => doRequest(attempt + 1).then(resolve, reject), 1000);
            if (t && typeof t.unref === 'function') t.unref();
          } else {
            wx.showToast({ title: `请求失败(${statusCode})`, icon: 'none' });
            reject(new Error(`HTTP ${statusCode}`));
          }
        },
        fail(err) {
          if (isIdempotent && attempt < MAX_RETRY) {
            const t = setTimeout(() => doRequest(attempt + 1).then(resolve, reject), 1000);
            if (t && typeof t.unref === 'function') t.unref();
          } else {
            const msg = err.errMsg.includes('timeout') ? '请求超时' : '网络异常';
            wx.showToast({ title: msg, icon: 'none' });
            reject(err);
          }
        },
        complete() {
          if (showLoading) {
            wx.hideLoading();
          }
        }
      });
    });
  }

  return doRequest(0);
}

module.exports = { request, BASE_URL };
