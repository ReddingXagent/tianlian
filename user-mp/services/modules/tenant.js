// services/modules/tenant.js - 租户品牌接口 (对齐 GET /tenants/{id}/branding)
const { request } = require('./client');

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

module.exports = { getTenantBranding };
