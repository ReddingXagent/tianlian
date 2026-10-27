// utils/__tests__/branding.test.js - 动态品牌渲染工具测试
const {
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
} = require('../branding');

describe('Branding Utils', () => {
  describe('isValidHexColor', () => {
    it('接受标准 #RRGGBB 格式', () => {
      expect(isValidHexColor('#00A86B')).toBe(true);
      expect(isValidHexColor('#FF5733')).toBe(true);
    });

    it('接受缩写 #RGB 格式', () => {
      expect(isValidHexColor('#0F0')).toBe(true);
      expect(isValidHexColor('#abc')).toBe(true);
    });

    it('拒绝非法格式', () => {
      expect(isValidHexColor('00A86B')).toBe(false);
      expect(isValidHexColor('#GGG')).toBe(false);
      expect(isValidHexColor('#12345')).toBe(false);
      expect(isValidHexColor('')).toBe(false);
      expect(isValidHexColor(null)).toBe(false);
      expect(isValidHexColor(undefined)).toBe(false);
      expect(isValidHexColor(123)).toBe(false);
    });
  });

  describe('normalizeBranding', () => {
    it('正常解析完整 branding 对象', () => {
      const result = normalizeBranding({
        operator_name: '国家电网',
        theme_color: '#1A5276',
        source: 'operator'
      });
      expect(result.operatorName).toBe('国家电网');
      expect(result.themeColor).toBe('#1A5276');
      expect(result.source).toBe('operator');
      expect(result.isCustom).toBe(true);
    });

    it('source=default 时 isCustom=false', () => {
      const result = normalizeBranding({
        operator_name: '天链',
        theme_color: '#00A86B',
        source: 'default'
      });
      expect(result.isCustom).toBe(false);
    });

    it('非法 theme_color 时使用兜底色', () => {
      const result = normalizeBranding({
        operator_name: '测试',
        theme_color: 'not-a-color',
        source: 'custom'
      });
      expect(result.themeColor).toBe(FALLBACK_COLOR);
    });

    it('null/undefined 输入返回默认品牌', () => {
      expect(normalizeBranding(null)).toEqual({
        ...DEFAULT_BRANDING,
        isCustom: false
      });
      expect(normalizeBranding(undefined)).toEqual({
        ...DEFAULT_BRANDING,
        isCustom: false
      });
    });

    it('空对象输入使用默认值填充', () => {
      const result = normalizeBranding({});
      expect(result.operatorName).toBe(DEFAULT_BRANDING.operatorName);
      expect(result.themeColor).toBe(DEFAULT_BRANDING.themeColor);
      expect(result.source).toBe(DEFAULT_BRANDING.source);
    });

    it('缺失 operator_name 时使用默认值', () => {
      const result = normalizeBranding({ theme_color: '#FF0000', source: 'operator' });
      expect(result.operatorName).toBe(DEFAULT_BRANDING.operatorName);
      expect(result.themeColor).toBe('#FF0000');
      expect(result.isCustom).toBe(true);
    });
  });

  describe('getStationBranding', () => {
    it('从站点对象提取 branding', () => {
      const station = {
        id: 1,
        name: '测试站',
        branding: {
          operator_name: '特来电',
          theme_color: '#0066CC',
          source: 'operator'
        }
      };
      const result = getStationBranding(station);
      expect(result.operatorName).toBe('特来电');
      expect(result.themeColor).toBe('#0066CC');
      expect(result.isCustom).toBe(true);
    });

    it('无 branding 字段返回默认品牌', () => {
      const station = { id: 2, name: '裸站' };
      const result = getStationBranding(station);
      expect(result.operatorName).toBe(DEFAULT_BRANDING.operatorName);
      expect(result.isCustom).toBe(false);
    });

    it('null station 返回默认品牌', () => {
      const result = getStationBranding(null);
      expect(result.operatorName).toBe(DEFAULT_BRANDING.operatorName);
      expect(result.themeColor).toBe(DEFAULT_BRANDING.themeColor);
    });
  });

  describe('hexToRgba', () => {
    it('正确转换 #RRGGBB → rgba()', () => {
      expect(hexToRgba('#00A86B', 0.1)).toBe('rgba(0, 168, 107, 0.1)');
      expect(hexToRgba('#FFFFFF', 0.5)).toBe('rgba(255, 255, 255, 0.5)');
      expect(hexToRgba('#000000', 0)).toBe('rgba(0, 0, 0, 0)');
    });

    it('正确转换 #RGB 缩写格式', () => {
      expect(hexToRgba('#0F0', 1)).toBe('rgba(0, 255, 0, 1)');
      expect(hexToRgba('#abc', 0.3)).toBe('rgba(170, 187, 204, 0.3)');
    });

    it('非法颜色使用兜底色', () => {
      expect(hexToRgba('invalid', 0.5)).toBe('rgba(0, 168, 107, 0.5)');
    });
  });

  describe('云端契约兼容（真实API返回结构）', () => {
    it('匹配冒烟测试 branding 默认结构', () => {
      // 真实云端返回: {"branding": {"operator_name": "天链", "theme_color": "#00A86B", "source": "default"}}
      const cloudBranding = {
        operator_name: '天链',
        theme_color: '#00A86B',
        source: 'default'
      };
      const result = normalizeBranding(cloudBranding);
      expect(result.operatorName).toBe('天链');
      expect(result.themeColor).toBe('#00A86B');
      expect(result.source).toBe('default');
      expect(result.isCustom).toBe(false);
    });

    it('匹配自定义运营商 branding 结构', () => {
      const cloudBranding = {
        operator_name: '南方电网',
        theme_color: '#1A5276',
        source: 'operator'
      };
      const result = normalizeBranding(cloudBranding);
      expect(result.operatorName).toBe('南方电网');
      expect(result.isCustom).toBe(true);
    });
  });

  // ========== 租户级品牌测试 ==========

  describe('TENANT_BRANDING_CACHE_KEY', () => {
    it('导出为非空字符串', () => {
      expect(typeof TENANT_BRANDING_CACHE_KEY).toBe('string');
      expect(TENANT_BRANDING_CACHE_KEY.length).toBeGreaterThan(0);
    });
  });

  describe('applyBrandingToApp', () => {
    let setNavColorSpy;

    beforeEach(() => {
      setNavColorSpy = jest.fn();
      global.wx = { setNavigationBarColor: setNavColorSpy };
    });

    afterEach(() => {
      delete global.wx;
    });

    it('使用有效 themeColor 调用 wx.setNavigationBarColor', () => {
      applyBrandingToApp({ themeColor: '#1A5276' });
      expect(setNavColorSpy).toHaveBeenCalledWith({
        frontColor: '#ffffff',
        backgroundColor: '#1A5276'
      });
    });

    it('使用兜底色当 themeColor 无效', () => {
      applyBrandingToApp({ themeColor: 'invalid' });
      expect(setNavColorSpy).toHaveBeenCalledWith({
        frontColor: '#ffffff',
        backgroundColor: FALLBACK_COLOR
      });
    });

    it('空 branding 静默跳过', () => {
      applyBrandingToApp(null);
      applyBrandingToApp(undefined);
      applyBrandingToApp({});
      expect(setNavColorSpy).not.toHaveBeenCalled();
    });

    it('wx 不存在时静默不抛异常', () => {
      delete global.wx;
      expect(() => applyBrandingToApp({ themeColor: '#FF0000' })).not.toThrow();
    });
  });

  describe('cacheTenantBranding / getCachedTenantBranding', () => {
    let storage;

    beforeEach(() => {
      storage = {};
      global.wx = {
        setStorageSync: jest.fn((key, val) => { storage[key] = val; }),
        getStorageSync: jest.fn((key) => storage[key] || '')
      };
    });

    afterEach(() => {
      delete global.wx;
    });

    it('缓存 → 读回 round-trip', () => {
      const branding = { operator_name: '测试租户', theme_color: '#123456', source: 'operator' };
      cacheTenantBranding(branding, 60000);
      const cached = getCachedTenantBranding();
      expect(cached).toEqual(branding);
    });

    it('过期缓存返回 null', () => {
      cacheTenantBranding({ source: 'test' }, -1000); // 已过期
      expect(getCachedTenantBranding()).toBeNull();
    });

    it('无缓存返回 null', () => {
      expect(getCachedTenantBranding()).toBeNull();
    });

    it('wx 不存在时 getCachedTenantBranding 返回 null', () => {
      delete global.wx;
      expect(getCachedTenantBranding()).toBeNull();
    });

    it('wx 不存在时 cacheTenantBranding 不抛异常', () => {
      delete global.wx;
      expect(() => cacheTenantBranding({ source: 'test' })).not.toThrow();
    });
  });

  describe('loadAndApplyTenantBranding', () => {
    let setNavColorSpy;
    let storage;

    beforeEach(() => {
      storage = {};
      setNavColorSpy = jest.fn();
      global.wx = {
        setNavigationBarColor: setNavColorSpy,
        setStorageSync: jest.fn((key, val) => { storage[key] = val; }),
        getStorageSync: jest.fn((key) => storage[key] || '')
      };
    });

    afterEach(() => {
      delete global.wx;
      jest.resetModules();
    });

    it('空 tenantId 返回 null', async () => {
      const result = await loadAndApplyTenantBranding(null);
      expect(result).toBeNull();
    });

    it('undefined tenantId 返回 null', async () => {
      const result = await loadAndApplyTenantBranding(undefined);
      expect(result).toBeNull();
    });

    it('tenantId=0 不被当作 falsy 跳过（边界）', async () => {
      jest.resetModules();
      jest.doMock('../../services/api', () => ({
        getTenantBranding: jest.fn().mockResolvedValue({
          data: { operator_name: '租户0', theme_color: '#AABBCC', source: 'operator' }
        })
      }));
      jest.doMock('../../config/index', () => ({ CACHE_TTL: { TENANT_BRANDING: 300000 } }));
      const brandingMod = require('../branding');
      const result = await brandingMod.loadAndApplyTenantBranding(0);
      expect(result).not.toBeNull();
      expect(result.operatorName).toBe('租户0');
    });

    it('成功时缓存并应用品牌', async () => {
      jest.resetModules();
      const mockGetTenantBranding = jest.fn().mockResolvedValue({
        data: { operator_name: '南方电网', theme_color: '#1A5276', source: 'operator' }
      });
      jest.doMock('../../services/api', () => ({ getTenantBranding: mockGetTenantBranding }));
      jest.doMock('../../config/index', () => ({ CACHE_TTL: { TENANT_BRANDING: 300000 } }));
      const brandingMod = require('../branding');
      const result = await brandingMod.loadAndApplyTenantBranding('t001');
      expect(mockGetTenantBranding).toHaveBeenCalledWith('t001');
      expect(result.operatorName).toBe('南方电网');
      expect(result.themeColor).toBe('#1A5276');
      expect(result.isCustom).toBe(true);
      expect(setNavColorSpy).toHaveBeenCalled();
    });

    it('API 失败时返回 null 不抛异常', async () => {
      jest.resetModules();
      jest.doMock('../../services/api', () => ({
        getTenantBranding: jest.fn().mockRejectedValue(new Error('NETWORK'))
      }));
      jest.doMock('../../config/index', () => ({ CACHE_TTL: { TENANT_BRANDING: 300000 } }));
      const brandingMod = require('../branding');
      const result = await brandingMod.loadAndApplyTenantBranding('t002');
      expect(result).toBeNull();
    });

    it('空 data 返回 null', async () => {
      jest.resetModules();
      jest.doMock('../../services/api', () => ({
        getTenantBranding: jest.fn().mockResolvedValue({ data: null })
      }));
      jest.doMock('../../config/index', () => ({ CACHE_TTL: { TENANT_BRANDING: 300000 } }));
      const brandingMod = require('../branding');
      const result = await brandingMod.loadAndApplyTenantBranding('t003');
      expect(result).toBeNull();
    });
  });
});
