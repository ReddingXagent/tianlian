/**
 * 布局组件 - 权限模型改造版（2026-05-21）
 * 
 * 基于 ThingsBoard 的 Map<Authority, MenuReference[]> 权限模型
 * 根据 entry_type (platform | ops) 动态生成菜单
 * 
 * 历史修改记录：
 * - 04-27 凌晨版本（移除Header、侧边栏滚动、底部状态区重构）
 * - 05-21 权限模型改造（双菜单系统 + 入口类型驱动）
 * - 06-16 侧栏配色统一：背景色改为 #faf5f4 与内容区协调
 * - 07-05 Phase5 UI/UX优化：使用 CSS 变量实现暗色模式支持
 */
import React, { useState, useEffect, useMemo } from 'react';
import { clearAuth } from '../../utils/authStorage';
import { colors, spacing, borderRadius, transition, breakpoints } from '../../styles/ui-constants';
import { useIsMobile } from '../../hooks/useIsMobile';
import { Layout, Menu, Avatar, Dropdown, Badge, Drawer, Button } from 'antd';
import {
  UserOutlined,
  SettingOutlined,
  LogoutOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  BellOutlined,
  MenuOutlined,
} from '@ant-design/icons';
import { useNavigate, useLocation, Outlet } from 'react-router-dom';
import { alarmAPI } from '../../api';
import ThemeToggle from '../ThemeToggle'; // <-- Theme toggle component for UI/UX improvement
import { getUserType } from '../../utils/auth';
import { broadcastAuthChange } from '../../utils/authEvents';
import { getMenuItems, getSystemTitle, type MenuItem } from '../../config/menuConfig';
import PageTransition from '../PageTransition';

const { Sider, Content } = Layout;

/**
 * 据 pathname+search 计算需展开的父级子菜单 key。
 * 先将叶子 key 解析为 pathname+query 与当前 location 整体比对（精确匹配），
 * 仅当无精确命中时才降级按 pathname 匹配（取菜单序在前的唯一父级）。
 * 整体比对用于同 pathname 双挂载场景：/tenants/data?type=ops_company 挂"运营公司管理"、
 * ?type=maintenance_team 挂"运维团队管理"，归属由 query 决定；无 type 降级取前者。
 * 修复直接 URL 进入子菜单页(如 /operate/users、/teams/engineers、/tenants/data)时
 * 父级子菜单不展开、选中项不可见的问题(原 defaultOpenKeys 仅在 /rbac 展开)。
 */
function computeOpenKeys(pathname: string, search: string, items: MenuItem[]): string[] {
  const locQuery = new URLSearchParams(search).toString();
  const exact = (child: MenuItem) => {
    const [path, query = ''] = child.key.split('?');
    return path === pathname && new URLSearchParams(query).toString() === locQuery;
  };
  const byPath = (child: MenuItem) => {
    const leaf = child.key.split('?')[0];
    return pathname === leaf || pathname.startsWith(leaf + '/');
  };
  // 第一轮：pathname+query 整体精确匹配，所有命中的父级全部展开
  const exactHits = items
    .filter((item) => item.children && item.children.length > 0)
    .filter((item) => item.children!.some(exact));
  if (exactHits.length > 0) return exactHits.map((item) => item.key);
  // 降级：仅按 pathname（URL 无 query 或 query 与任何挂载都不一致），取菜单序在前的唯一父级
  for (const item of items) {
    if (item.children && item.children.length > 0 && item.children.some(byPath)) {
      return [item.key];
    }
  }
  return [];
}

const AdminLayout: React.FC = () => {
  const [collapsed, setCollapsed] = useState(false);
  const [alarmCount, setAlarmCount] = useState(0);
  const [drawerVisible, setDrawerVisible] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();

  // 根据用户类型获取菜单
  const userType = getUserType();
  const menuItems = useMemo(() => getMenuItems(userType), [userType]);
  const systemTitle = useMemo(() => getSystemTitle(userType, collapsed), [userType, collapsed]);

  // 受控展开子菜单：初始据当前 pathname 展开对应父级(直接 URL 进入子页时父级可见)，
  // 用户手动展开/折叠经 onOpenChange 持久化；导航到新子页时其父级自动并入。
  const autoOpenKeys = useMemo(
    () => computeOpenKeys(location.pathname, location.search, menuItems),
    [location.pathname, location.search, menuItems],
  );
  const [openKeys, setOpenKeys] = useState<string[]>(autoOpenKeys);
  useEffect(() => {
    // pathname 变化时并入新父级；已含全部时返回原引用，避免无谓重渲染
    setOpenKeys((prev) => {
      const missing = autoOpenKeys.filter((k) => !prev.includes(k));
      return missing.length === 0 ? prev : [...prev, ...missing];
    });
  }, [autoOpenKeys]);

  // 响应式断点（统一走 useIsMobile hook，不写死 px，复用 ui-constants.breakpoints）
  const isMobile = useIsMobile();
  const isTablet = useIsMobile(breakpoints.tablet) && !isMobile;

  // 平板端默认折叠侧边栏
  useEffect(() => {
    if (isTablet && !collapsed) {
      setCollapsed(true);
    }
  }, [isTablet]);

  // 获取活跃告警数量
  useEffect(() => {
    const fetchAlarmCount = async () => {
      try {
        const res: { data?: { active?: number } } = await alarmAPI.stats();
        setAlarmCount(res.data?.active || 0);
      } catch { /* 静默 */ }
    };
    fetchAlarmCount();
    const timer = setInterval(fetchAlarmCount, 30000);
    return () => clearInterval(timer);
  }, []);

  const userMenuItems = [
    { key: 'profile', icon: <UserOutlined />, label: '个人中心' },
    { key: 'settings', icon: <SettingOutlined />, label: '系统设置' },
    { type: 'divider' as const },
    { key: 'logout', icon: <LogoutOutlined />, label: '退出登录', danger: true },
  ];

  const handleMenuClick = ({ key }: { key: string }) => {
    navigate(key);
  };

  const handleUserMenuClick = ({ key }: { key: string }) => {
    switch (key) {
      case 'profile':
        navigate('/rbac/users');
        break;
      case 'settings':
        navigate('/config');
        break;
      case 'logout':
        clearAuth();
        localStorage.removeItem('entry_type');
        broadcastAuthChange(); // 通知天链助手等全局组件清空缓存, 防跨账户残留
        navigate('/login');
        break;
    }
  };

  // 键盘快捷键
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Ctrl+B 切换侧边栏折叠
      if ((e.ctrlKey || e.metaKey) && e.key === 'b') {
        e.preventDefault();
        setCollapsed(prev => !prev);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  const handleAlarmClick = () => navigate('/alarms');

  const handleMenuClickMobile = ({ key }: { key: string }) => {
    navigate(key);
    setDrawerVisible(false);
  };

  // 侧边栏内容 - 背景色使用 CSS 变量 var(--bg-layout) 与内容区统一，支持暗色模式
  const sidebarContent = (
    <>
      <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', background: 'var(--bg-layout)' }}>
        {/* Logo区域 */}
        <div
          style={{
            height: 64,
            flexShrink: 0,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            borderBottom: '1px solid var(--border-color)',
          }}
        >
          <h1
            style={{
              color: 'var(--text-primary)',
              margin: 0,
              fontSize: collapsed && !isMobile ? 16 : 18,
              fontWeight: 'bold',
              whiteSpace: 'nowrap',
            }}
          >
            {systemTitle}
          </h1>
        </div>

        {/* 菜单滚动区域 */}
        <div
          className="sidebar-menu-scroll"
          style={{
            flex: 1,
            maxHeight: collapsed && !isMobile ? 'calc(100vh - 64px - 48px)' : 'calc(100vh - 64px - 52px)',
            overflow: 'hidden auto',
            overflowX: 'hidden',
          }}
        >
          <Menu
            theme="light"
            mode="inline"
            selectedKeys={[location.pathname + location.search]}
            openKeys={openKeys}
            onOpenChange={(keys) => setOpenKeys(keys as string[])}
            items={menuItems as any}
            onClick={isMobile ? handleMenuClickMobile : handleMenuClick}
            style={{ background: 'transparent', borderRight: 0, height: 'auto' }}
          />
        </div>

        {/* 底部状态区 */}
        <div
          className="sidebar-bottom-actions"
          style={{
            flexShrink: 0,
            flexGrow: 0,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            background: 'var(--bg-layout)',
            position: 'relative',
            zIndex: 10,
          }}
        >
          <div style={{ height: 1, background: 'var(--border-color)', width: '100%' }} />
          <div
            style={{
              display: 'flex',
              flexDirection: 'row',
              alignItems: 'center',
              justifyContent: collapsed && !isMobile ? 'center' : 'flex-start',
              width: '100%',
              padding: collapsed && !isMobile ? '6px' : '6px 16px',
            }}
          >
            <Dropdown menu={{ items: userMenuItems, onClick: handleUserMenuClick }} placement="bottomRight">
              <Avatar
                icon={<UserOutlined />}
                style={{ background: 'var(--bg-secondary)', color: 'var(--text-tertiary)', cursor: 'pointer' }}
              />
            </Dropdown>
            {/* Theme toggle – added in Phase5 UI/UX optimization */}
            <div style={{ marginLeft: 12, marginRight: 12 }}>
              <ThemeToggle compact />
            </div>
            <div style={{ marginLeft: 'auto' }} onClick={handleAlarmClick}>
              <Badge count={alarmCount > 0 ? alarmCount : null} size="small" style={{ background: 'var(--error-color)' }}>
                <BellOutlined
                  style={{ fontSize: 18, color: alarmCount > 0 ? 'var(--error-color)' : 'var(--text-tertiary)', cursor: 'pointer' }}
                />
              </Badge>
            </div>
          </div>
        </div>
      </div>

      {/* 折叠按钮 - 侧边栏右侧边框内部垂直居中 */}
      {!isMobile && (
        <div
          onClick={() => setCollapsed(!collapsed)}
          style={{
            position: 'absolute',
            right: 8,
            top: '50%',
            transform: 'translateY(-50%)',
            cursor: 'pointer',
            color: 'var(--text-tertiary)',
            fontSize: 14,
            width: 28,
            height: 28,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            background: 'var(--bg-secondary)',
            borderRadius: 6,
            zIndex: 1001,
            border: 'none',
            transition: 'all 0.2s',
          }}
          onMouseEnter={(e) => { e.currentTarget.style.background = 'var(--bg-primary)'; e.currentTarget.style.color = 'var(--text-primary)'; }}
          onMouseLeave={(e) => { e.currentTarget.style.background = 'var(--bg-secondary)'; e.currentTarget.style.color = 'var(--text-tertiary)'; }}
          role="button"
          tabIndex={0}
          aria-label={collapsed ? '展开侧边栏 (Ctrl+B)' : '折叠侧边栏 (Ctrl+B)'}
          onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setCollapsed(!collapsed); } }}
        >
          {collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
        </div>
      )}
    </>
  );

  return (
    <Layout style={{ minHeight: '100vh' }}>
      {isMobile ? (
        <Drawer
          placement="left"
          closable={false}
          onClose={() => setDrawerVisible(false)}
          open={drawerVisible}
          width={220}
          styles={{ body: { padding: 0, background: 'var(--bg-layout)' }, header: { display: 'none' } }}
        >
          {sidebarContent}
        </Drawer>
      ) : (
        <Sider
          collapsible
          collapsed={collapsed}
          onCollapse={setCollapsed}
          trigger={null}
          width={220}
          collapsedWidth={80}
          theme="light"
          style={{
            background: 'var(--bg-layout)',
            height: '100vh',
            position: 'fixed',
            left: 0,
            top: 0,
            zIndex: 1002,
            overflow: 'hidden',
          }}
        >
          {sidebarContent}
        </Sider>
      )}

      <Layout style={{
        background: 'var(--bg-layout)',
        marginLeft: isMobile ? 0 : (collapsed ? 80 : 220),
        transition: 'margin-left 0.2s ease',
      }}>
        <Content style={{ margin: 0, padding: 0, background: 'var(--bg-layout)', minHeight: '100vh', overflow: 'hidden' }}>
          {isMobile && (
            <div style={{ position: 'sticky', top: 0, zIndex: 100, background: 'var(--bg-layout)', padding: '12px 16px', display: 'flex', alignItems: 'center', borderBottom: '1px solid var(--border-color)' }}>
              <Button
                type="text"
                icon={<MenuOutlined style={{ color: 'var(--text-primary)', fontSize: 20 }} />}
                onClick={() => setDrawerVisible(true)}
                style={{ marginRight: 12 }}
              />
              <h1 style={{ color: 'var(--text-primary)', margin: 0, fontSize: 18, fontWeight: 'bold' }}>
                {systemTitle}
              </h1>
            </div>
          )}
          <PageTransition effect="fade">
            <Outlet />
          </PageTransition>
        </Content>
      </Layout>
    </Layout>
  );
};

export default AdminLayout;
