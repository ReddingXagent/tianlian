/**
 * UI 常量定义 - 统一组件库规范
 * 用于确保设计系统一致性
 */

// 颜色变量 (来自 index.css 的 CSS 变量)
export const colors = {
  // 主题色
  primary: 'var(--primary-color)',
  primaryHover: 'var(--primary-hover)',
  primaryActive: 'var(--primary-active)',
  
  // 功能色
  success: 'var(--success-color)',
  warning: 'var(--warning-color)',
  error: 'var(--error-color)',
  
  // 背景色
  bgPrimary: 'var(--bg-primary)',
  bgSecondary: 'var(--bg-secondary)',
  bgCard: 'var(--bg-card)',
  bgLayout: 'var(--bg-layout)',
  
  // 文字颜色
  textPrimary: 'var(--text-primary)',
  textSecondary: 'var(--text-secondary)',
  textTertiary: 'var(--text-tertiary)',
  
  // 边框
  borderColor: 'var(--border-color)',
  
  // 阴影
  shadowSm: 'var(--shadow-sm)',
  shadowMd: 'var(--shadow-md)',
  shadowLg: 'var(--shadow-lg)',
} as const;

// 圆角
export const borderRadius = {
  sm: 'var(--radius-sm)',
  md: 'var(--radius-md)',
  lg: 'var(--radius-lg)',
} as const;

// 间距
export const spacing = {
  xs: 'var(--spacing-xs)',
  sm: 'var(--spacing-sm)',
  md: 'var(--spacing-md)',
  lg: 'var(--spacing-lg)',
  xl: 'var(--spacing-xl)',
} as const;

// 过渡动画
export const transition = {
  fast: 'var(--transition-fast)',
  normal: 'var(--transition-normal)',
  slow: 'var(--transition-slow)',
} as const;

// 响应式断点
export const breakpoints = {
  mobile: 768,
  tablet: 1024,
  desktop: 1200,
} as const;

// 触控最小尺寸
export const touchMinSize = 44; // px

// 动画变体
export const motion = {
  fadeInUp: {
    from: { opacity: 0, transform: 'translateY(20px)' },
    to: { opacity: 1, transform: 'translateY(0)' },
  },
} as const;