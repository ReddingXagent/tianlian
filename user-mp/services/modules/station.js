// services/modules/station.js - 站点接口 (真云端可用)
const { request } = require('./client');

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

module.exports = {
  getStations,
  getNearbyStations,
  getStationDetail,
  searchStations,
  filterStations
};
