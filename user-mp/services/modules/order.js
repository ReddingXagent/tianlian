// services/modules/order.js - 订单+支付接口 (对齐 /business/charging-orders)
const { request } = require('./client');
const { mapOrder, mapPagination, ORDER_STATUS_TO_BACKEND } = require('./mappers');
const { getCurrentUserId } = require('./auth');

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
  return request('/charging-orders', { data: query }).then((res) => ({
    ...res,
    data: mapPagination(res.data, mapOrder)
  }));
}

/**
 * 获取订单详情
 */
function getOrderDetail(orderId) {
  return request(`/charging-orders/${orderId}`).then((res) => ({
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
  return request(`/charging-orders/${orderId}/pay`, {
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

module.exports = { getOrders, getOrderDetail, reviewOrder, createPayment, queryPaymentStatus };
