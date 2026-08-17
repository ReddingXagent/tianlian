// services/modules/coupon.js - 优惠券接口 (对齐 /business/coupons)
const { request } = require('./client');
const { mapCoupon, mapPagination, COUPON_STATUS_TO_BACKEND } = require('./mappers');
const { getCurrentUserId } = require('./auth');

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

module.exports = { getCoupons, claimCoupon };
