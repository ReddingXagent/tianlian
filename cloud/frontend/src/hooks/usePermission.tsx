/**
 * 权限 Hook — 从 JWT token 中读取用户权限列表
 * 
 * 用法:
 *   const canDelete = usePermission('device:delete');
 *   const canManage = usePermission(['device:edit', 'device:delete']); // 任一即可
 */
import { useMemo } from 'react';
import { getToken } from '../utils/authStorage';
import { getUserType } from '../utils/auth';

/** 解码 JWT payload（不验签，仅读取 claims） */
function decodeTokenPermissions(): string[] {
  try {
    const token = getToken();
    if (!token) return [];
    const payload = token.split('.')[1];
    if (!payload) return [];
    const decoded = JSON.parse(atob(payload.replace(/-/g, '+').replace(/_/g, '/')));
    return Array.isArray(decoded.permissions) ? decoded.permissions : [];
  } catch {
    return [];
  }
}

/** 缓存权限列表，避免每次 render 都解码 */
let _cachedPermissions: string[] | null = null;
let _cachedToken: string | null = null;

function getPermissions(): string[] {
  const token = getToken();
  if (_cachedPermissions && _cachedToken === token) {
    return _cachedPermissions;
  }
  _cachedToken = token;
  _cachedPermissions = decodeTokenPermissions();
  return _cachedPermissions;
}

/** 清除缓存（登出时调用） */
export function clearPermissionCache(): void {
  _cachedPermissions = null;
  _cachedToken = null;
}

/**
 * 检查当前用户是否拥有指定权限
 * @param permission - 单个权限字符串或权限数组（数组时任一匹配即返回 true）
 * @returns boolean
 */
export const usePermission = (permission: string | string[]): boolean => {
  return useMemo(() => {
    // admin 拥有所有权限
    const userType = getUserType();
    if (userType === 'admin') return true;

    const perms = getPermissions();
    if (perms.length === 0) {
      // token 中无权限信息时，降级为基于角色的粗粒度控制
      // 非 admin 默认允许（避免误拦），后续可收紧
      return true;
    }

    if (Array.isArray(permission)) {
      return permission.some(p => perms.includes(p));
    }
    return perms.includes(permission);
  }, [permission]);
};

export default usePermission;
