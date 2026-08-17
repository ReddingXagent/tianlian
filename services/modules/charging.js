// services/modules/charging.js - 扫码/充电接口 (对齐 /business 经营域)
const { request } = require('./client');
const { mapOrder } = require('./mappers');
const { getCurrentUserId } = require('./auth');

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

module.exports = { startCharging, getChargingStatus, stopCharging };
