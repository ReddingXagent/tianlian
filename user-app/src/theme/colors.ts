/**
 * src/theme/colors.ts — 语义调色板 (F2783 深色模式 Phase 1)
 *
 * Light/Dark 双套语义色。primary(品牌主蓝)在两种模式下保持一致 —— 品牌强调色
 * 在深浅背景上均可用, 只有中性色(背景/文字/边框)随系统主题翻转。
 * 多租户品牌色 brand 不在此写死, 由 useTheme 从 brandingStore.themeColor 注入。
 */
export type ColorScheme = 'light' | 'dark';

export interface ThemeColors {
  primary: string;
  onPrimary: string;
  pageBg: string;
  cardBg: string;
  inputBg: string;
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
}

export const colorsLight: ThemeColors = {
  primary: '#1a73e8',
  onPrimary: '#fff',
  pageBg: '#f5f6fa',
  cardBg: '#fff',
  inputBg: '#fafafa',
  textPrimary: '#333',
  textSecondary: '#999',
  textMuted: '#ccc',
  border: '#eee',
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
};

export const colorsDark: ThemeColors = {
  primary: '#1a73e8',
  onPrimary: '#fff',
  pageBg: '#121212',
  cardBg: '#1e1e1e',
  inputBg: '#2a2a2a',
  textPrimary: '#e0e0e0',
  textSecondary: '#9e9e9e',
  textMuted: '#666',
  border: '#333',
  divider: '#2a2a2a',
  error: '#ef9a9a',
  success: '#81c784',
  warning: '#ffb74d',
  errorBg: '#3e1a1a',
  infoBg: '#1a2b3e',
  successBg: '#1c2b1c',
  warningBg: '#33291c',
  info: '#64b5f6',
  neutralBg: '#2a2a2a',
  neutralText: '#9e9e9e',
  purple: '#ce93d8',
  purpleBg: '#2e2135',
  warningAmber: '#ffca28',
  warningAmberBg: '#332f1e',
};