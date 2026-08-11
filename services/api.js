// services/api.js - API服务层
// 闭环战役B3: 充电/订单/优惠券/积分 全量对齐真后端 /business 经营域契约
// 真云端冒烟实测(8.134.106.166): 登录走OAuth2 form-urlencoded, 全站snake_case+{code,message,data}信封
const config = require('../config/index');

const BASE_URL = config.API_BASE_URL;
const TIMEOUT = config.REQUEST_TIMEOUT;

/**
 * 通用请求封装
 * @param {string} url - 接口路径（不含base）
 * @param {object} options - 请求选项 (form=true 时走 x-www-form-urlencoded)
 * @returns {Promise}
 */
const MAX_RETRY = 1; // 网络层重试次数 (非幂等请求不重试)

function request(url, options = {}) {
  const {
    method = 'GET',
    data = {},
    header = {},
    showLoading = false,
    loadingText = '加载中...',
    form = false
  } = options;

  // 获取token
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

  // 幂等方法才允许重试
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
          } else if (statusCode >= 500 && isIdempotent && attempt < MAX_RETRY) {
            // 5xx 服务端错误, 幂等请求自动重试一次
            const t = setTimeout(() => doRequest(attempt + 1).then(resolve, reject), 1000);
            // Node.js 环境 unref 避免阻止 Jest worker 退出; 微信小程序环境无副作用
            if (t && typeof t.unref === 'function') t.unref();
          } else {
            wx.showToast({ title: `请求失败(${statusCode})`, icon: 'none' });
            reject(new Error(`HTTP ${statusCode}`));
          }
        },
        fail(err) {
          if (isIdempotent && attempt < MAX_RETRY) {
            // 网络层失败, 幂等请求自动重试一次
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

// ========== 归一化层 (后端snake_case → 前端camelCase) ==========

// 订单状态: 后端 charging/settled/paid ↔ UI charging/pending/finished
const ORDER_STATUS_TO_UI = { charging: 'charging', settled: 'pending', paid: 'finished' };
const ORDER_STATUS_TO_BACKEND = { charging: 'charging', pending: 'settled', finished: 'paid' };
// 优惠券状态: 后端 active/used/expired ↔ UI unused/used/expired
const COUPON_STATUS_TO_BACKEND = { unused: 'active', used: 'used', expired: 'expired' };

function mapOrder(o) {
  if (!o) return o;
  return {
    id: String(o.id),
    sessionId: String(o.id), // 兼容充电页 sessionId 语义
    orderNo: o.order_no,
    stationId: o.station_id,
    deviceId: o.device_id,
    userId: o.user_id,
    status: ORDER_STATUS_TO_UI[o.status] || o.status,
    rawStatus: o.status,
    energyKwh: o.energy_kwh,
    durationMin: o.duration_min,
    amount: o.amount,
    discountAmount: o.discount_amount,
    finalAmount: o.final_amount,
    pointsEarned: o.points_earned,
    paidAt: o.paid_at
  };
}

function mapCoupon(c) {
  if (!c) return c;
  return {
    id: String(c.id),
    code: c.code,
    name: c.name,
    type: c.coupon_type,
    value: c.value,
    minAmount: c.min_amount,
    status: c.status === 'active' ? 'unused' : c.status,
    rawStatus: c.status,
    expireAt: c.expire_at
  };
}

function mapPoints(p) {
  if (!p) return p;
  return {
    userId: p.user_id,
    balance: p.balance,
    history: (p.recent || []).map((r) => ({
      delta: r.delta,
      reason: r.reason,
      createdAt: r.created_at
    }))
  };
}

function mapPagination(d, mapper) {
  return {
    items: (d.items || []).map(mapper),
    total: d.total || 0,
    page: d.page || 1,
    pageSize: d.page_size || 20
  };
}

// ========== 认证接口 (对齐真后端 OAuth2 form-urlencoded) ==========

/**
 * 用户名密码登录 (后端 /auth/login 走 OAuth2PasswordRequestForm)
 * 登录成功自动落盘 token + userInfo
 */
function login(username, password) {
  return request('/auth/login', {
    method: 'POST',
    form: true,
    data: { username, password },
    showLoading: true,
    loadingText: '登录中...'
  }).then((res) => {
    const d = res.data || {};
    if (d.token) {
      wx.setStorageSync('token', d.token);
    }
    if (d.user) {
      wx.setStorageSync('userInfo', d.user);
    }
    return res;
  });
}

/** 微信登录 (后端暂无wx登录端点, 保留占位, 走用户名密码登录) */
function wxLogin() {
  return Promise.reject(new Error('请使用用户名密码登录'));
}

function logout() {
  wx.removeStorageSync('token');
  wx.removeStorageSync('userInfo');
}

function getCurrentUser() {
  return wx.getStorageSync('userInfo') || null;
}

function getCurrentUserId() {
  const u = getCurrentUser();
  return u && u.id !== undefined && u.id !== null ? u.id : null;
}

/**
 * 获取用户信息 → GET /auth/me (后端返回当前用户+权限列表)
 * 同时更新本地缓存
 */
function getUserInfo() {
  return request('/auth/me').then((res) => {
    if (res.data) {
      wx.setStorageSync('userInfo', res.data);
    }
    return res;
  });
}

/**
 * 更新用户信息 (后端暂无 PUT/PATCH 端点, 走本地缓存更新)
 */
function updateUserInfo(data) {
  const user = getCurrentUser();
  if (user) {
    const updated = { ...user, ...data };
    wx.setStorageSync('userInfo', updated);
    return Promise.resolve({ code: 200, data: updated });
  }
  return Promise.reject(new Error('未登录'));
}

// ========== 租户品牌接口 (对齐 GET /tenants/{id}/branding) ==========

/**
 * 获取租户品牌配置 → GET /tenants/{id}/branding
 * @param {string|number} tenantId - 租户ID
 * @returns {Promise} 品牌数据 { operator_name, theme_color, source, logo_url? }
 */
function getTenantBranding(tenantId) {
  return request(`/tenants/${tenantId}/branding`, {
    data: {},
    showLoading: false
  });
}

// ========== 站点接口 (真云端可用) ==========

/**
 * 站点列表 (真云端 GET /stations, 分页 snake_case 参数)
 */
function getStations(params = {}) {
  const { page = 1, pageSize = 20 } = params;
  return request('/stations', {
    data: { page, page_size: pageSize }
  });
}

/**
 * 获取附近站点 (后端无nearby端点, 降级为列表)
 */
function getNearbyStations() {
  return getStations();
}

/**
 * 获取站点详情
 */
function getStationDetail(stationId) {
  return request(`/stations/${stationId}`);
}

/**
 * 搜索站点 (后端无search端点, 降级为列表)
 */
function searchStations() {
  return getStations();
}

/**
 * 筛选站点 (后端无filter端点, 降级为列表)
 */
function filterStations(params = {}) {
  const { page = 1, pageSize = 20 } = params;
  return getStations({ page, pageSize });
}

// ========== 收藏接口 (后端暂无, 本地存储降级) ==========

function getFavorites() {
  return Promise.resolve({ code: 200, data: wx.getStorageSync('favorites') || [] });
}

function addFavorite(stationId) {
  const favs = wx.getStorageSync('favorites') || [];
  if (!favs.includes(stationId)) {
    favs.push(stationId);
    wx.setStorageSync('favorites', favs);
  }
  return Promise.resolve({ code: 200, data: { stationId } });
}

function removeFavorite(stationId) {
  const favs = (wx.getStorageSync('favorites') || []).filter((id) => id !== stationId);
  wx.setStorageSync('favorites', favs);
  return Promise.resolve({ code: 200, data: { stationId } });
}

// ========== 扫码/充电接口 (对齐 /business 经营域) ==========

/**
 * 扫码启动充电 → POST /business/charging-orders/start-by-sn
 * @param {string} chargerId - 充电桩SN或code (扫码内容)
 */
function startCharging(chargerId) {
  return request('/business/charging-orders/start-by-sn', {
    method: 'POST',
    data: { charger_sn: chargerId, user_id: getCurrentUserId() },
    showLoading: true,
    loadingText: '启动中...'
  }).then((res) => ({ ...res, data: mapOrder(res.data) }));
}

/**
 * 获取充电订单状态 → GET /business/charging-orders/{id}
 * @param {string|number} sessionId - 订单ID
 */
function getChargingStatus(sessionId) {
  return request(`/business/charging-orders/${sessionId}`).then((res) => ({
    ...res,
    data: mapOrder(res.data)
  }));
}

/**
 * 停止充电 → POST /business/charging-orders/{id}/complete (charging → settled)
 * @param {string|number} sessionId - 订单ID
 * @param {number} energyKwh - 充电电量(度), 缺省0(桩端计量未接入)
 * @param {number} durationMin - 充电时长(分钟)
 */
function stopCharging(sessionId, energyKwh = 0, durationMin = 0) {
  return request(`/business/charging-orders/${sessionId}/complete`, {
    method: 'POST',
    data: { energy_kwh: energyKwh, duration_min: durationMin },
    showLoading: true,
    loadingText: '停止中...'
  }).then((res) => ({ ...res, data: mapOrder(res.data) }));
}

// ========== 订单接口 (对齐 /business/charging-orders) ==========

/**
 * 获取订单列表
 * @param {object} params - { page, pageSize, status(UI态), userId }
 */
function getOrders(params = {}) {
  const { page = 1, pageSize = 10, status, userId } = params;
  const uid = userId !== undefined ? userId : getCurrentUserId();
  const backendStatus = status ? ORDER_STATUS_TO_BACKEND[status] || status : null;
  const query = { page, page_size: pageSize };
  if (uid !== null && uid !== undefined) query.user_id = uid;
  if (backendStatus) query.status = backendStatus;
  return request('/business/charging-orders', { data: query }).then((res) => ({
    ...res,
    data: mapPagination(res.data, mapOrder)
  }));
}

/**
 * 获取订单详情
 */
function getOrderDetail(orderId) {
  return request(`/business/charging-orders/${orderId}`).then((res) => ({
    ...res,
    data: mapOrder(res.data)
  }));
}

/**
 * 评价订单 (后端暂无端点)
 */
function reviewOrder() {
  return Promise.reject(new Error('FEATURE_UNAVAILABLE'));
}

// ========== 支付接口 (对齐 /business 支付结算) ==========

/**
 * 支付订单 → POST /business/charging-orders/{id}/pay (settled → paid + 积分发放)
 *
 * 后端返回 payParams 可能包含:
 * - 直连模式: timeStamp, nonceStr, package, signType, paySign
 * - 服务商模式: 额外透传 sp_mchid, sub_mchid 等字段 (前端无需感知, wx.requestPayment 自动处理)
 *
 * @param {string|number} orderId - 订单ID
 * @param {string} couponCode - 可选优惠券码
 */
function createPayment(orderId, couponCode) {
  return request(`/business/charging-orders/${orderId}/pay`, {
    method: 'POST',
    data: { coupon_code: couponCode || null },
    showLoading: true,
    loadingText: '支付中...'
  }).then((res) => ({ ...res, data: mapOrder(res.data) }));
}

/**
 * 查询支付状态 (订单详情即支付状态: status=finished 为已支付)
 */
function queryPaymentStatus(orderId) {
  return getOrderDetail(orderId);
}

// ========== 钱包接口 (后端暂无, 占位) ==========

function getWallet() {
  return Promise.reject(new Error('FEATURE_UNAVAILABLE'));
}

function recharge() {
  return Promise.reject(new Error('FEATURE_UNAVAILABLE'));
}

function getTransactions() {
  return Promise.reject(new Error('FEATURE_UNAVAILABLE'));
}

// ========== 优惠券接口 (对齐 /business/coupons) ==========

/**
 * 获取优惠券列表
 * @param {string} status - UI状态: unused/used/expired
 */
function getCoupons(status) {
  const query = {};
  const uid = getCurrentUserId();
  if (uid !== null && uid !== undefined) query.user_id = uid;
  if (status) query.status = COUPON_STATUS_TO_BACKEND[status] || status;
  return request('/business/coupons', { data: query }).then((res) => ({
    ...res,
    data: mapPagination(res.data, mapCoupon)
  }));
}

/**
 * 领取优惠券 → POST /business/coupons/claim (无主券绑定到当前用户)
 * @param {string} couponCode - 优惠券码
 */
function claimCoupon(couponCode) {
  return request('/business/coupons/claim', {
    method: 'POST',
    data: { code: couponCode, user_id: getCurrentUserId() },
    showLoading: true,
    loadingText: '领取中...'
  });
}

// ========== 积分接口 (对齐 /business/points) ==========

/**
 * 获取积分余额+最近流水
 */
function getPoints(userId) {
  const uid = userId !== undefined ? userId : getCurrentUserId();
  if (uid === null || uid === undefined) {
    return Promise.reject(new Error('NO_USER'));
  }
  return request('/business/points', { data: { user_id: uid } }).then((res) => ({
    ...res,
    data: mapPoints(res.data)
  }));
}

/**
 * 获取积分记录 (后端积分流水随 /business/points 返回)
 */
function getPointsHistory(userId) {
  return getPoints(userId).then((res) => ({ ...res, data: res.data.history }));
}

/**
 * 每日签到 (后端暂无端点)
 */
function dailySignIn() {
  return Promise.reject(new Error('FEATURE_UNAVAILABLE'));
}

/**
 * 积分兑换 (后端暂无端点)
 */
function redeemPoints() {
  return Promise.reject(new Error('FEATURE_UNAVAILABLE'));
}

// ========== 能源概览接口 (真云端可用) ==========

/**
 * 获取光储充经营概览 → GET /energy/summary
 * 返回: 总发电量/总充电量/总收入/今日数据等
 */
function getEnergySummary() {
  return request('/energy/summary');
}

// ========== 通知接口 (后端暂无, 占位) ==========

function getNotifications() {
  return Promise.resolve({ code: 200, data: { items: [], total: 0 } });
}

function markNotificationRead() {
  return Promise.resolve({ code: 200, data: null });
}

function markAllNotificationsRead() {
  return Promise.resolve({ code: 200, data: null });
}

function getUnreadNotificationCount() {
  return Promise.resolve({ code: 200, data: { count: 0 } });
}

module.exports = {
  request,
  // 归一化
  mapOrder,
  mapCoupon,
  mapPoints,
  mapPagination,
  ORDER_STATUS_TO_UI,
  ORDER_STATUS_TO_BACKEND,
  COUPON_STATUS_TO_BACKEND,
  // 认证
  login,
  wxLogin,
  logout,
  getCurrentUser,
  getCurrentUserId,
  getUserInfo,
  updateUserInfo,
  // 站点
  getStations,
  getNearbyStations,
  getStationDetail,
  searchStations,
  filterStations,
  // 收藏
  getFavorites,
  addFavorite,
  removeFavorite,
  // 充电
  startCharging,
  getChargingStatus,
  stopCharging,
  // 订单
  getOrders,
  getOrderDetail,
  reviewOrder,
  // 支付
  createPayment,
  queryPaymentStatus,
  // 钱包
  getWallet,
  recharge,
  getTransactions,
  // 优惠券
  getCoupons,
  claimCoupon,
  // 积分
  getPoints,
  getPointsHistory,
  dailySignIn,
  redeemPoints,
  // 能源概览
  getEnergySummary,
  // 租户品牌
  getTenantBranding,
  // 通知
  getNotifications,
  markNotificationRead,
  markAllNotificationsRead,
  getUnreadNotificationCount
};
