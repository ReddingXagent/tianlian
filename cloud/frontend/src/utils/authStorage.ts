/**
 * authStorage - 认证存储 portal 隔离（2026-10-09 丁哥需求: 同一浏览器同时登录运营和运维账户）
 *
 * 之前所有用户共用 admin_token/admin_user → 后登录覆盖先登录。
 * 现在: URL 在 /operate/* 下 = 运营 portal, 读写独立的 *_operate key;
 *       其他路径 = 主 portal(运维/管理), 沿用原 key(旧会话零破坏)。
 * 读取 fallback 主 key, 保证升级后已登录用户不掉线。
 */

export type Portal = 'main' | 'operate';

/** 当前 URL 所属 portal */
export function currentPortal(): Portal {
  return typeof location !== 'undefined' && location.pathname.startsWith('/operate')
    ? 'operate'
    : 'main';
}

export function authKeys(portal: Portal = currentPortal()) {
  return portal === 'operate'
    ? { token: 'admin_token_operate', user: 'admin_user_operate', role: 'user_role_operate' }
    : { token: 'admin_token', user: 'admin_user', role: 'user_role' };
}

// 标签页会话(sessionStorage 天然按tab隔离): tab内跨portal路由跳转身份恒定, 不闪退
const SS_TOKEN = 'tl_tab_token';
const SS_USER = 'tl_tab_user';

export function getToken(portal?: Portal): string | null {
  const ss = sessionStorage.getItem(SS_TOKEN);
  if (ss) return ss;
  const k = authKeys(portal);
  return localStorage.getItem(k.token) || localStorage.getItem('admin_token');
}

export function getUserRaw(portal?: Portal): string | null {
  const ss = sessionStorage.getItem(SS_USER);
  if (ss) return ss;
  const k = authKeys(portal);
  return localStorage.getItem(k.user) || localStorage.getItem('admin_user');
}

export function getUser(portal?: Portal): any | null {
  try {
    const s = getUserRaw(portal);
    return s ? JSON.parse(s) : null;
  } catch {
    return null;
  }
}

/** 登录写入: portal 需显式传入(登录页场景 URL 尚未进入 /operate)
 * 同时写本tab的sessionStorage(跨portal跳转不闪退) + localStorage(刷新/重开tab按URL恢复) */
export function setAuth(token: string, user: unknown, portal: Portal = 'main') {
  const k = authKeys(portal);
  sessionStorage.setItem(SS_TOKEN, token);
  sessionStorage.setItem(SS_USER, JSON.stringify(user));
  localStorage.setItem(k.token, token);
  localStorage.setItem(k.user, JSON.stringify(user));
}

/** 退出/401 清除: 清本tab会话+当前 portal(不影响另一入口的会话) */
export function clearAuth(portal?: Portal) {
  const k = authKeys(portal);
  sessionStorage.removeItem(SS_TOKEN);
  sessionStorage.removeItem(SS_USER);
  localStorage.removeItem(k.token);
  localStorage.removeItem(k.user);
  localStorage.removeItem(k.role);
}
