// services/api.js - API服务层
const config = require('../config/index');

const BASE_URL = config.API_BASE_URL;
const TIMEOUT = config.REQUEST_TIMEOUT;

/**
 * 通用请求封装
 * @param {string} url - 接口路径（不含base）
 * @param {object} options - 请求选项
 * @returns {Promise}
 */
function request(url, options = {}) {
  const {
    method = 'GET',
    data = {},
    header = {},
    showLoading = false,
    loadingText = '加载中...'
  } = options;

  // 获取token
  const token = wx.getStorageSync('token');

  return new Promise((resolve, reject) => {
    if (showLoading) {
      wx.showLoading({ title: loadingText, mask: true });
    }

    wx.request({
      url: `${BASE_URL}${url}`,
      method,
      data,
      timeout: TIMEOUT,
      header: {
        'Content-Type': 'application/json',
        ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
        ...header
      },
      success(res) {
        const { statusCode, data: resData } = res;

        if (statusCode === 200) {
          if (resData.code === 0 || resData.code === 200) {
            resolve(resData);
          } else if (resData.code === 401) {
            // token过期
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
        } else {
          wx.showToast({ title: `请求失败(${statusCode})`, icon: 'none' });
          reject(new Error(`HTTP ${statusCode}`));
        }
      },
      fail(err) {
        const msg = err.errMsg.includes('timeout') ? '请求超时' : '网络异常';
        wx.showToast({ title: msg, icon: 'none' });
        reject(err);
      },
      complete() {
        if (showLoading) {
          wx.hideLoading();
        }
      }
    });
  });
}

// ========== 认证接口 ==========

/**
 * 微信登录
 * @param {string} code - wx.login返回的code
 */
function login(code) {
  return request('/auth/login', {
    method: 'POST',
    data: { code },
    showLoading: true,
    loadingText: '登录中...'
  });
}

/**
 * 获取用户信息
 */
function getUserInfo() {
  return request('/user/info');
}

/**
 * 更新用户信息
 * @param {object} data - 用户信息
 */
function updateUserInfo(data) {
  return request('/user/info', {
    method: 'PUT',
    data
  });
}

// ========== 站点接口 ==========

/**
 * 获取附近站点
 * @param {number} lat - 纬度
 * @param {number} lng - 经度
 * @param {number} radius - 搜索半径（米）
 */
function getNearbyStations(lat, lng, radius = 5000) {
  return request('/stations/nearby', {
    method: 'GET',
    data: { lat, lng, radius }
  });
}

/**
 * 获取站点详情
 * @param {string} stationId - 站点ID
 */
function getStationDetail(stationId) {
  return request(`/stations/${stationId}`);
}

/**
 * 搜索站点
 * @param {string} keyword - 搜索关键词
 */
function searchStations(keyword) {
  return request('/stations/search', {
    method: 'GET',
    data: { keyword }
  });
}

/**
 * 筛选站点
 * @param {object} params - 筛选参数 { lat, lng, gunType, sortBy, radius, page, pageSize }
 */
function filterStations(params = {}) {
  const { lat, lng, gunType, sortBy, radius = 5000, page = 1, pageSize = 20 } = params;
  return request('/stations/filter', {
    method: 'GET',
    data: { lat, lng, gunType, sortBy, radius, page, pageSize }
  });
}

// ========== 收藏接口 ==========

/**
 * 获取收藏站点列表
 */
function getFavorites() {
  return request('/user/favorites');
}

/**
 * 添加收藏站点
 * @param {string} stationId - 站点ID
 */
function addFavorite(stationId) {
  return request('/user/favorites', {
    method: 'POST',
    data: { stationId }
  });
}

/**
 * 取消收藏站点
 * @param {string} stationId - 站点ID
 */
function removeFavorite(stationId) {
  return request(`/user/favorites/${stationId}`, {
    method: 'DELETE'
  });
}

// ========== 扫码/充电接口 ==========

/**
 * 扫码启动充电
 * @param {string} chargerId - 充电桩ID
 */
function startCharging(chargerId) {
  return request('/charging/start', {
    method: 'POST',
    data: { chargerId },
    showLoading: true,
    loadingText: '启动中...'
  });
}

/**
 * 获取充电实时数据
 * @param {string} sessionId - 充电会话ID
 */
function getChargingStatus(sessionId) {
  return request(`/charging/status/${sessionId}`);
}

/**
 * 停止充电
 * @param {string} sessionId - 充电会话ID
 */
function stopCharging(sessionId) {
  return request('/charging/stop', {
    method: 'POST',
    data: { sessionId },
    showLoading: true,
    loadingText: '停止中...'
  });
}

// ========== 订单接口 ==========

/**
 * 获取订单列表
 * @param {object} params - 查询参数 { page, pageSize, status }
 */
function getOrders(params = {}) {
  const { page = 1, pageSize = 10, status } = params;
  return request('/orders', {
    method: 'GET',
    data: { page, pageSize, ...(status ? { status } : {}) }
  });
}

/**
 * 获取订单详情
 * @param {string} orderId - 订单ID
 */
function getOrderDetail(orderId) {
  return request(`/orders/${orderId}`);
}

/**
 * 评价订单
 * @param {string} orderId - 订单ID
 * @param {number} rating - 评分 1-5
 * @param {string} comment - 评价内容
 */
function reviewOrder(orderId, rating, comment) {
  return request(`/orders/${orderId}/review`, {
    method: 'POST',
    data: { rating, comment }
  });
}

// ========== 支付接口 ==========

/**
 * 创建支付
 * @param {string} orderId - 订单ID
 */
function createPayment(orderId) {
  return request('/payment/create', {
    method: 'POST',
    data: { orderId },
    showLoading: true,
    loadingText: '获取支付信息...'
  });
}

/**
 * 查询支付状态
 * @param {string} orderId - 订单ID
 */
function queryPaymentStatus(orderId) {
  return request(`/payment/status/${orderId}`);
}

// ========== 钱包接口 ==========

/**
 * 获取钱包信息
 */
function getWallet() {
  return request('/wallet/info');
}

/**
 * 充值
 * @param {number} amount - 充值金额（元）
 */
function recharge(amount) {
  return request('/wallet/recharge', {
    method: 'POST',
    data: { amount }
  });
}

/**
 * 获取交易记录
 * @param {number} page - 页码
 */
function getTransactions(page = 1) {
  return request('/wallet/transactions', {
    method: 'GET',
    data: { page, pageSize: 20 }
  });
}

// ========== 优惠券接口 ==========

/**
 * 获取优惠券列表
 * @param {string} status - 状态筛选: unused/used/expired
 */
function getCoupons(status) {
  return request('/coupons', {
    method: 'GET',
    data: status ? { status } : {}
  });
}

/**
 * 领取优惠券
 * @param {string} couponCode - 优惠券码
 */
function claimCoupon(couponCode) {
  return request('/coupons/claim', {
    method: 'POST',
    data: { couponCode },
    showLoading: true,
    loadingText: '领取中...'
  });
}

/**
 * 使用优惠券
 * @param {string} couponId - 优惠券ID
 * @param {string} orderId - 订单ID
 */
function useCoupon(couponId, orderId) {
  return request('/coupons/use', {
    method: 'POST',
    data: { couponId, orderId }
  });
}

// ========== 积分接口 ==========

/**
 * 获取积分信息
 */
function getPoints() {
  return request('/points/info');
}

/**
 * 获取积分记录
 * @param {number} page - 页码
 */
function getPointsHistory(page = 1) {
  return request('/points/history', {
    method: 'GET',
    data: { page, pageSize: 20 }
  });
}

/**
 * 每日签到
 */
function dailySignIn() {
  return request('/points/sign-in', {
    method: 'POST',
    showLoading: true,
    loadingText: '签到中...'
  });
}

/**
 * 积分兑换
 * @param {string} rewardId - 兑换项ID
 */
function redeemPoints(rewardId) {
  return request('/points/redeem', {
    method: 'POST',
    data: { rewardId },
    showLoading: true,
    loadingText: '兑换中...'
  });
}

// ========== 通知接口 ==========

/**
 * 获取通知列表
 * @param {number} page - 页码
 * @param {string} type - 通知类型筛选
 */
function getNotifications(page = 1, type) {
  return request('/notifications', {
    method: 'GET',
    data: { page, pageSize: 20, ...(type ? { type } : {}) }
  });
}

/**
 * 标记通知已读
 * @param {string} notificationId - 通知ID
 */
function markNotificationRead(notificationId) {
  return request(`/notifications/${notificationId}/read`, {
    method: 'POST'
  });
}

/**
 * 标记全部已读
 */
function markAllNotificationsRead() {
  return request('/notifications/read-all', {
    method: 'POST'
  });
}

/**
 * 获取未读通知数量
 */
function getUnreadNotificationCount() {
  return request('/notifications/unread-count');
}

module.exports = {
  request,
  login,
  getUserInfo,
  updateUserInfo,
  getNearbyStations,
  getStationDetail,
  searchStations,
  filterStations,
  getFavorites,
  addFavorite,
  removeFavorite,
  startCharging,
  getChargingStatus,
  stopCharging,
  getOrders,
  getOrderDetail,
  reviewOrder,
  createPayment,
  queryPaymentStatus,
  getWallet,
  recharge,
  getTransactions,
  getCoupons,
  claimCoupon,
  useCoupon,
  getPoints,
  getPointsHistory,
  dailySignIn,
  redeemPoints,
  getNotifications,
  markNotificationRead,
  markAllNotificationsRead,
  getUnreadNotificationCount
};
