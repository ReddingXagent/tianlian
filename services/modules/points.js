// services/modules/points.js - 积分接口 (对齐 /business/points)
const { request } = require('./client');
const { mapPoints } = require('./mappers');
const { getCurrentUserId } = require('./auth');

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

module.exports = { getPoints, getPointsHistory, dailySignIn, redeemPoints };
