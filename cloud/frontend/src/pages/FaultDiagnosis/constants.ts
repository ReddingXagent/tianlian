/**
 * AI 智能诊断 — 严重度/状态 颜色与文案映射
 */

export const severityColors: Record<string, string> = {
  low: 'green',
  medium: 'orange',
  high: 'red',
  critical: 'darkred',
};

export const severityText: Record<string, string> = {
  low: '低',
  medium: '中',
  high: '高',
  critical: '紧急',
};

export const statusColors: Record<string, string> = {
  pending: 'default',
  running: 'processing',
  completed: 'success',
  failed: 'error',
};
