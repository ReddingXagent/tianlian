/**
 * src/theme/colors.ts — 语义调色板 (深色模式 Phase 1, station-app 深色优先版)
 *
 * 本 App 出厂即深色设计(teal #4ECDC4 品牌 + 深海军蓝底), 故:
 * - colorsDark = 现有视觉零变化(出厂色即语义色)
 * - colorsLight = 新增浅色皮肤(白底+深 teal, teal 原值在白底对比度1.9:1不可读, 降档至 #0e8a80)
 * primary(品牌 teal)随模式分档, 与 ops/user 两仓的固定 primary 策略不同。
 */
export type ColorScheme = 'light' | 'dark';

export interface ThemeColors {
  primary: string;       // 品牌 teal: dark=#4ECDC4 / light=#0e8a80
  onPrimary: string;     // primary 上的前景: dark=深海军蓝 / light=白
  pageBg: string;        // 页面底: dark=#0f0f23 / light=#f5f6fa
  cardBg: string;        // 卡面: dark=#1a1a2e / light=#fff
  inputBg: string;       // 输入框底
  textPrimary: string;
  textSecondary: string;
  textMuted: string;
  border: string;
  divider: string;
  error: string;
  success: string;
  warning: string;
  errorBg: string;
  infoBg: string;
  successBg: string;
  warningBg: string;
  info: string;
  neutralBg: string;
  neutralText: string;
  purple: string;
  purpleBg: string;
  warningAmber: string;
  warningAmberBg: string;
  /** 图表线条色族(line-chart/趋势图): dark 高饱和亮色 / light 常规 Material */
  chartPurple: string;
  chartOrange: string;
  /** AI 气泡: dark 深青卡片 / light 浅 teal 底 */
  aiBg: string;
  aiBorder: string;
}

export const colorsLight: ThemeColors = {
  primary: '#0e8a80',
  onPrimary: '#fff',
  pageBg: '#f5f6fa',
  cardBg: '#fff',
  inputBg: '#fafafa',
  textPrimary: '#333',
  textSecondary: '#666',
  textMuted: '#999',
  border: '#ddd',
  divider: '#f0f0f0',
  error: '#c62828',
  success: '#2e7d32',
  warning: '#e65100',
  errorBg: '#fce4ec',
  infoBg: '#e3f2fd',
  successBg: '#e8f5e9',
  warningBg: '#fff3e0',
  info: '#1565c0',
  neutralBg: '#f5f5f5',
  neutralText: '#616161',
  purple: '#7b1fa2',
  purpleBg: '#f3e5f5',
  warningAmber: '#f57f17',
  warningAmberBg: '#fff8e1',
  chartPurple: '#7b1fa2',
  chartOrange: '#ef6c00',
  aiBg: '#e0f2f1',
  aiBorder: '#b2dfdb',
};

export const colorsDark: ThemeColors = {
  primary: '#4ECDC4',
  onPrimary: '#0f0f23',
  pageBg: '#0f0f23',
  cardBg: '#1a1a2e',
  inputBg: '#1a1a2e',
  textPrimary: '#fff',
  textSecondary: '#888',
  textMuted: '#666',
  border: '#333',
  divider: '#2a2a3e',
  error: '#e74c3c',
  success: '#27ae60',
  warning: '#f39c12',
  errorBg: '#3a1a24',
  infoBg: '#1a2b3e',
  successBg: '#1c2b1c',
  warningBg: '#33291c',
  info: '#3498db',
  neutralBg: '#2a2a3e',
  neutralText: '#888',
  purple: '#7b1fa2',
  purpleBg: '#2e2135',
  warningAmber: '#f39c12',
  warningAmberBg: '#332f1e',
  chartPurple: '#9b59b6',
  chartOrange: '#ef6c00',
  aiBg: '#16323a',
  aiBorder: '#2a4a52',
};
