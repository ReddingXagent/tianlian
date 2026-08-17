// services/modules/energy.js - 能源概览接口 (真云端可用)
const { request } = require('./client');

/**
 * 获取光储充经营概览 → GET /energy/summary
 * 返回: 总发电量/总充电量/总收入/今日数据等
 */
function getEnergySummary() {
  return request('/energy/summary');
}

module.exports = { getEnergySummary };
