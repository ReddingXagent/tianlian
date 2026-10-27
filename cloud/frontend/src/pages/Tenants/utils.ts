/**
 * 运维团队管理 — 状态色映射工厂
 */

export const getStatusMap = (t: (k: string) => string): Record<string, { color: string; text: string }> => ({
  active: { color: 'green', text: t('pages.tenants.status_active') },
  trial: { color: 'blue', text: t('pages.tenants.status_trial') },
  expired: { color: 'red', text: t('pages.tenants.status_expired') },
  disabled: { color: 'default', text: t('pages.tenants.status_disabled') },
});
