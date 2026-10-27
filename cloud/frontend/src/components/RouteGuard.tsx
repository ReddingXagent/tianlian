import { Navigate, useLocation } from 'react-router-dom';
import { Result, Button } from 'antd';
import { getToken } from '../utils/authStorage';
import { getUserType, getUserRole, canAccessRoute, getDefaultRoute } from '../utils/auth';

interface RouteGuardProps {
  children: React.ReactNode;
  allowedUserTypes?: string[];
}

/**
 * 路由守卫组件 - 天链V3 四入口权限模型
 * 
 * 权限规则：
 * 1. 未登录 → 跳登录页
 * 2. 用户类型不匹配 → 跳对应首页
 * 3. 路由权限检查失败 → 跳默认页
 */
const RouteGuard: React.FC<RouteGuardProps> = ({ children, allowedUserTypes }) => {
  const location = useLocation();
  const token = getToken();
  const userType = getUserType();
  const userRole = getUserRole();

  // 登录页和扫码页不需要守卫
  if (location.pathname === '/login' || location.pathname === '/scan') {
    return <>{children}</>;
  }

  // 未登录 → 跳登录页
  if (!token) {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }

  // 用户类型检查
  if (allowedUserTypes && allowedUserTypes.length > 0) {
    if (!allowedUserTypes.includes(userType)) {
      // 入口不匹配，重定向到正确的首页
      return <Navigate to={getDefaultRoute()} replace />;
    }
  }

  // 通用路由权限检查
  if (!canAccessRoute(location.pathname)) {
    if (location.pathname.startsWith('/rbac') || location.pathname.startsWith('/audit-log')) {
      return (
        <Result
          status="403"
          title="403 权限不足"
          subTitle={`当前角色 (${userRole}) 无法访问此页面`}
          extra={
            <Button type="primary" onClick={() => window.location.href = getDefaultRoute()}>
              返回首页
            </Button>
          }
        />
      );
    }
    return <Navigate to={getDefaultRoute()} replace />;
  }

  return <>{children}</>;
};

export default RouteGuard;