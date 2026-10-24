/**
 * 天链 V3 - 系统配置页面常量
 */

export const ACTION_CONFIG: Record<string, { color: string; text: string }> = {
  login: { color: 'blue', text: '登录' },
  logout: { color: 'default', text: '登出' },
  create: { color: 'green', text: '创建' },
  update: { color: 'orange', text: '更新' },
  delete: { color: 'red', text: '删除' },
  export: { color: 'purple', text: '导出' },
  dispatch: { color: 'cyan', text: '派发' },
};

export const MODULE_MAP: Record<string, string> = {
  auth: '认证', users: '用户', stations: '站点', devices: '设备',
  alarms: '告警', workorders: '工单', knowledge: '知识库',
  reports: '报表', config: '配置', gateways: '网关', rbac: '权限',
  notification_rules: '通知规则',
};

export const RESOURCE_LABEL: Record<string, string> = {
  device: '设备管理', workorder: '工单管理', alarm: '告警管理',
  station: '站点管理', user: '用户管理', report: '报表',
  audit: '审计日志', system: '系统管理',
};

export const ROLE_COLOR_MAP: Record<string, string> = {
  admin: 'red', operator: 'blue', viewer: 'default', auditor: 'orange',
};

export const ROLE_TEXT_MAP: Record<string, string> = {
  admin: '管理员', operator: '运维操作员', viewer: '只读用户', auditor: '审计员',
};
