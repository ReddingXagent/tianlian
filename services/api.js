// services/api.js - barrel re-export (原598行单体→12模块+barrel)
// 闭环战役B3: 充电/订单/优惠券/积分 全量对齐真后端 /business 经营域契约
// 真云端冒烟实测(8.134.106.166): 登录走OAuth2 form-urlencoded, 全站snake_case+{code,message,data}信封

const { request } = require('./modules/client');
const {
  mapOrder,
  mapCoupon,
  mapPoints,
  mapPagination,
  ORDER_STATUS_TO_UI,
  ORDER_STATUS_TO_BACKEND,
  COUPON_STATUS_TO_BACKEND
} = require('./modules/mappers');
const {
  login,
  wxLogin,
  logout,
  getCurrentUser,
  getCurrentUserId,
  getUserInfo,
  updateUserInfo
} = require('./modules/auth');
const {
  getStations,
  getNearbyStations,
  getStationDetail,
  searchStations,
  filterStations
} = require('./modules/station');
const { getFavorites, addFavorite, removeFavorite } = require('./modules/favorites');
const { startCharging, getChargingStatus, stopCharging } = require('./modules/charging');
const {
  getOrders,
  getOrderDetail,
  reviewOrder,
  createPayment,
  queryPaymentStatus
} = require('./modules/order');
const { getWallet, recharge, getTransactions } = require('./modules/wallet');
const { getCoupons, claimCoupon } = require('./modules/coupon');
const { getPoints, getPointsHistory, dailySignIn, redeemPoints } = require('./modules/points');
const { getEnergySummary } = require('./modules/energy');
const { getTenantBranding } = require('./modules/tenant');
const {
  getNotifications,
  markNotificationRead,
  markAllNotificationsRead,
  getUnreadNotificationCount
} = require('./modules/notification');

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
