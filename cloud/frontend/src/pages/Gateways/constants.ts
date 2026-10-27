/**
 * 网关管理页面 — 常量（区域选项 + 各资源状态颜色映射）
 */

// 区域码映射
export const regionOptions = [
  { value: 'HN', label: '河南' },
  { value: 'GD', label: '广东' },
  { value: 'JS', label: '江苏' },
  { value: 'SD', label: '山东' },
  { value: 'ZJ', label: '浙江' },
  { value: 'FJ', label: '福建' },
  { value: 'SC', label: '四川' },
  { value: 'HB', label: '湖北' },
  { value: 'BJ', label: '北京' },
  { value: 'SH', label: '上海' },
  { value: 'GX', label: '广西' },
  { value: 'SN', label: '陕西' },
  { value: 'CQ', label: '重庆' },
  { value: 'LN', label: '辽宁' },
];

// 状态颜色映射
export const statusColorMap: Record<string, string> = {
  online: 'green',
  offline: 'default',
  maintenance: 'orange',
  fault: 'red',
};

export const snStatusColorMap: Record<string, string> = {
  generated: 'default',
  written: 'blue',
  activated: 'green',
  locked: 'orange',
  recalled: 'red',
};

export const fwStatusColorMap: Record<string, string> = {
  draft: 'default',
  released: 'green',
  deprecated: 'red',
};

export const taskStatusColorMap: Record<string, string> = {
  pending: 'default',
  running: 'blue',
  success: 'green',
  failed: 'red',
  cancelled: 'orange',
};
