// utils/branding.js - 动态品牌渲染工具
// 消费云端 stations.branding 字段 + 租户级 GET /tenants/{id}/branding

/** 默认品牌配置（云端无 branding 时的降级方案） */
const DEFAULT_BRANDING = {
  operatorName: '天链',
  themeColor: '#00A86B',
  source: 'default'
};

/** 租户品牌缓存 storage key */
const TENANT_BRANDING_CACHE_KEY = 'tenant_branding';

/** 兜底安全色（theme_color 格式非法时使用） */
const FALLBACK_COLOR = '#00A86B';

/**
 * 校验十六进制颜色字符串
 * @param {string} color - 待校验的颜色值
 * @returns {boolean}
 */
function isValidHexColor(color) {
  if (typeof color !== 'string' || !color) return false;
  return /^#([0-9A-Fa-f]{3}|[0-9A-Fa-f]{6})$/.test(color);
}

/**
 * 将 snake_case branding 对象归一化为前端友好格式
 * @param {object} raw - 云端 branding 原始对象
 * @param {string} raw.operator_name - 运营商名称
 * @param {string} raw.theme_color - 主题色 (#RRGGBB 或 #RGB)
 * @param {string} raw.source - 来源标识 (default/operator/custom)
 * @returns {{operatorName: string, themeColor: string, source: string, isCustom: boolean}}
 */
function normalizeBranding(raw) {
  if (!raw || typeof raw !== 'object') {
    return { ...DEFAULT_BRANDING, isCustom: false };
  }

  const themeColor = isValidHexColor(raw.theme_color)
    ? raw.theme_color
    : FALLBACK_COLOR;

  const operatorName = raw.operator_name || DEFAULT_BRANDING.operatorName;
  const source = raw.source || DEFAULT_BRANDING.source;

  return {
    operatorName,
    themeColor,
    source,
    isCustom: source !== 'default'
  };
}

/**
 * 从站点对象提取品牌信息
 * @param {object} station - 站点数据（含可选 branding 字段）
 * @returns {{operatorName: string, themeColor: string, source: string, isCustom: boolean}}
 */
function getStationBranding(station) {
  if (!station || !station.branding) {
    return { ...DEFAULT_BRANDING, isCustom: false };
  }
  return normalizeBranding(station.branding);
}

/**
 * 生成主题色 RGBA 变体（用于浅色背景）
 * @param {string} hex - 十六进制颜色 (#RRGGBB)
 * @param {number} alpha - 透明度 0-1
 * @returns {string} rgba(r,g,b,a) 格式
 */
function hexToRgba(hexInput, alpha) {
  let hex = hexInput;
  if (!isValidHexColor(hex)) {
    hex = FALLBACK_COLOR;
  }
  let b, g, r;
  if (hex.length === 4) {
    b = parseInt(hex[3] + hex[3], 16);
    g = parseInt(hex[2] + hex[2], 16);
    r = parseInt(hex[1] + hex[1], 16);
  } else {
    b = parseInt(hex.slice(5, 7), 16);
    g = parseInt(hex.slice(3, 5), 16);
    r = parseInt(hex.slice(1, 3), 16);
  }
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

/**
 * 将品牌配置应用到小程序导航栏
 * @param {{operatorName: string, themeColor: string, source: string}} branding
 */
function applyBrandingToApp(branding) {
  if (!branding || !branding.themeColor) return;
  const color = isValidHexColor(branding.themeColor) ? branding.themeColor : FALLBACK_COLOR;
  try {
    wx.setNavigationBarColor({
      frontColor: '#ffffff',
      backgroundColor: color
    });
  } catch (e) {
    // 非小程序环境（如测试）静默
  }
}

/**
 * 从 storage 读取缓存的租户品牌
 * @returns {object|null}
 */
function getCachedTenantBranding() {
  try {
    const cached = wx.getStorageSync(TENANT_BRANDING_CACHE_KEY);
    if (!cached) return null;
    // 检查 TTL
    if (cached.expiredAt && Date.now() > cached.expiredAt) return null;
    return cached.data || null;
  } catch (e) {
    return null;
  }
}

/**
 * 缓存租户品牌到 storage
 * @param {object} branding - 品牌数据
 * @param {number} ttl - 缓存有效期(ms)
 */
function cacheTenantBranding(branding, ttl) {
  try {
    wx.setStorageSync(TENANT_BRANDING_CACHE_KEY, {
      data: branding,
      cachedAt: Date.now(),
      expiredAt: Date.now() + (ttl || 300000)
    });
  } catch (e) {
    // 静默
  }
}

/**
 * 拉取租户品牌 → 缓存 → 应用到导航栏
 * 启动时或租户切换时调用，不抛异常（失败静默降级）
 * @param {string|number} tenantId - 租户ID
 * @returns {Promise<object|null>} 归一化后的品牌配置，失败返回 null
 */
function loadAndApplyTenantBranding(tenantId) {
  if (!tenantId && tenantId !== 0) return Promise.resolve(null);

  // 懒加载避免循环依赖 (branding.js ↔ api.js)
  // eslint-disable-next-line global-require
  const lazyApi = require('../services/api');
  // eslint-disable-next-line global-require
  const lazyConfig = require('../config/index');

  return lazyApi.getTenantBranding(tenantId)
    .then((res) => {
      const raw = (res && res.data) || null;
      if (!raw) return null;

      // 缓存原始 branding 数据
      const ttl = (lazyConfig.CACHE_TTL && lazyConfig.CACHE_TTL.TENANT_BRANDING) || 300000;
      cacheTenantBranding(raw, ttl);

      // 归一化并应用
      const normalized = normalizeBranding(raw);
      applyBrandingToApp(normalized);
      return normalized;
    })
    .catch((err) => {
      console.warn('[branding] loadAndApplyTenantBranding failed:', err);
      return null;
    });
}

module.exports = {
  DEFAULT_BRANDING,
  FALLBACK_COLOR,
  TENANT_BRANDING_CACHE_KEY,
  isValidHexColor,
  normalizeBranding,
  getStationBranding,
  hexToRgba,
  applyBrandingToApp,
  getCachedTenantBranding,
  cacheTenantBranding,
  loadAndApplyTenantBranding
};
