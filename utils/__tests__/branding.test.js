// utils/__tests__/branding.test.js - 动态品牌渲染工具测试
const {
  DEFAULT_BRANDING,
  FALLBACK_COLOR,
  isValidHexColor,
  normalizeBranding,
  getStationBranding,
  hexToRgba
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
});
