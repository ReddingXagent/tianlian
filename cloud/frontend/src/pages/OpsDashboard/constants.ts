/**
 * 运维大屏颜色常量与拓扑样式
 */

export const COLORS = {
  bg: '#0a0e27',
  bgCard: 'rgba(6, 30, 65, 0.85)',
  border: 'rgba(32, 160, 255, 0.3)',
  accent: '#20a0ff',
  text: 'rgba(255, 255, 255, 0.9)',
  textDim: 'rgba(255, 255, 255, 0.5)',
  success: '#34d058',
  warning: '#faad14',
  danger: '#f5222d',
  info: '#20a0ff',
  purple: '#722ed1',
  station: '#20a0ff',
  gateway: '#722ed1',
  deviceOnline: '#34d058',
  deviceOffline: '#8c8c8c',
  deviceFault: '#f5222d',
};

export const STATUS_COLORS: Record<string, string> = {
  online: COLORS.deviceOnline,
  normal: COLORS.success,
  warning: COLORS.warning,
  fault: COLORS.danger,
  critical: COLORS.danger,
  offline: COLORS.deviceOffline,
};

export const TOPOLOGY_STYLES: Record<string, { color: string; radius: number; icon: string }> = {
  station: { color: COLORS.station, radius: 28, icon: '🏢' },
  gateway: { color: COLORS.gateway, radius: 20, icon: '📡' },
  device: { color: COLORS.deviceOnline, radius: 14, icon: '⚡' },
};
