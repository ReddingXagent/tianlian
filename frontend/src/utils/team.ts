/**
 * 天链 V3 — 团队上下文工具
 *
 * 运营平台按团队隔离数据。当前团队 ID 持久化在 localStorage,
 * 由 axios 请求拦截器以 `X-Team-Id` header 注入到每个请求。
 * team_id = 0 表示平台默认 (全平台视图)。
 */

/** localStorage 持久化 key */
export const TEAM_ID_STORAGE_KEY = 'current_team_id';

/** 平台默认团队 ID (未选择团队时的全平台视图) */
export const PLATFORM_TEAM_ID = 0;

/** 读取当前团队 ID; 缺省或非法时回退到平台默认 (0) */
export function getCurrentTeamId(): number {
  const raw = localStorage.getItem(TEAM_ID_STORAGE_KEY);
  if (raw === null) return PLATFORM_TEAM_ID;
  const id = Number(raw);
  return Number.isInteger(id) && id >= 0 ? id : PLATFORM_TEAM_ID;
}

/** 设置当前团队 ID; 非法值 (负数 / 非整数) 静默忽略 */
export function setCurrentTeamId(id: number): void {
  if (Number.isInteger(id) && id >= 0) {
    localStorage.setItem(TEAM_ID_STORAGE_KEY, String(id));
  }
}
