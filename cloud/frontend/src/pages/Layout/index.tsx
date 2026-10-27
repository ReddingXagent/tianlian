/**
 * 主布局组件 - 分组菜单版
 * 添加暗色主题切换 + 响应式设计 + 分组菜单
 */
import React, { useState, useEffect, useCallback } from 'react';
import { clearAuth } from '../../utils/authStorage';
import { useTranslation } from 'react-i18next';
import { Layout, Menu, Avatar, Dropdown, theme, Badge, Button } from 'antd';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import {
  DashboardOutlined,
  DesktopOutlined,
  HomeOutlined,
  FileTextOutlined,
  BellOutlined,
  UserOutlined,
  LogoutOutlined,
  SettingOutlined,
  SunOutlined,
  MoonOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  BookOutlined,
  BarChartOutlined,
  CloudServerOutlined,
  TeamOutlined,
  EnvironmentOutlined,
  ToolOutlined,
  MonitorOutlined,
  HeartOutlined,
  ControlOutlined,
  SecurityScanOutlined,
  NotificationOutlined,
  MedicineBoxOutlined,
  ScanOutlined,
  LineChartOutlined,
  ThunderboltOutlined,
  ApiOutlined,
  GlobalOutlined,
  SafetyCertificateOutlined,
  RobotOutlined,
  ProjectOutlined,
  ClockCircleOutlined,
  FileSearchOutlined,
  KeyOutlined,
  AuditOutlined,
  SafetyOutlined,
} from '@ant-design/icons';
import { broadcastAuthChange } from '../../utils/authEvents';

const { Header, Sider, Content } = Layout;

const useMenuItems = (t: (key: string) => string) => [
  {
    key: 'ops-center',
    icon: <DashboardOutlined />,
    label: t('nav.ops_center'),
    children: [
      { key: '/dashboard', icon: <DashboardOutlined />, label: t('nav.dashboard') },
      { key: '/ops-dashboard', icon: <MonitorOutlined />, label: t('nav.ops_dashboard') },
      { key: '/energy-report', icon: <LineChartOutlined />, label: t('nav.energy_report') },
    ],
  },
  {
    key: 'smart-diagnosis',
    icon: <RobotOutlined />,
    label: t('nav.smart_diagnosis'),
    children: [
      { key: '/monitor', icon: <MonitorOutlined />, label: t('nav.realtime_monitor') },
      { key: '/diagnosis', icon: <MedicineBoxOutlined />, label: t('nav.intelligent_diagnosis') },
      { key: '/smart-diagnosis', icon: <SafetyCertificateOutlined />, label: t('nav.fault_diagnosis') },
      { key: '/log-analysis', icon: <FileSearchOutlined />, label: t('nav.log_analysis') },
      { key: '/health', icon: <HeartOutlined />, label: t('nav.health_monitor') },
      { key: '/alarms', icon: <BellOutlined />, label: t('nav.alarm_management') },
      { key: '/alarm-notices', icon: <NotificationOutlined />, label: t('nav.alarm_notices') },
      { key: '/notification-rules', icon: <NotificationOutlined />, label: t('nav.notification_rules') },
      { key: '/healing', icon: <ThunderboltOutlined />, label: t('nav.alarm_healing') },
      { key: '/predictive-maintenance', icon: <ProjectOutlined />, label: t('nav.predictive_maintenance') },
    ],
  },
  {
    key: 'device-management',
    icon: <DesktopOutlined />,
    label: t('nav.device_management'),
    children: [
      { key: '/devices', icon: <DesktopOutlined />, label: t('nav.devices') },
      { key: '/stations', icon: <HomeOutlined />, label: t('nav.stations') },
      { key: '/map', icon: <EnvironmentOutlined />, label: t('nav.station_map') },
      { key: '/gateways', icon: <CloudServerOutlined />, label: t('nav.gateways') },
      { key: '/scan', icon: <ScanOutlined />, label: t('nav.scan_repair') },
    ],
  },
  {
    key: 'work-orders',
    icon: <FileTextOutlined />,
    label: t('nav.work_orders'),
    children: [
      { key: '/workorders', icon: <FileTextOutlined />, label: t('nav.workorder_management') },
      { key: '/runbook', icon: <BookOutlined />, label: t('nav.runbook') },
      { key: '/runbook-approval', icon: <AuditOutlined />, label: t('nav.runbook_approval') },
      { key: '/on-call', icon: <ClockCircleOutlined />, label: t('nav.on_call') },
      { key: '/reports', icon: <BarChartOutlined />, label: t('nav.report_export') },
      { key: '/report-mgmt', icon: <FileSearchOutlined />, label: t('nav.report_management') },
    ],
  },
  {
    key: 'advanced',
    icon: <GlobalOutlined />,
    label: t('nav.advanced'),
    children: [
      { key: '/digital-twin', icon: <ApiOutlined />, label: t('nav.digital_twin') },
      { key: '/vpp', icon: <ThunderboltOutlined />, label: t('nav.vpp') },
      { key: '/remote-control', icon: <ControlOutlined />, label: t('nav.remote_control') },
    ],
  },
  {
    key: 'system-management',
    icon: <SettingOutlined />,
    label: t('nav.system_management'),
    children: [
      { key: '/teams', icon: <TeamOutlined />, label: t('nav.team_management') },
      { key: '/users', icon: <UserOutlined />, label: t('nav.user_management') },
      { key: '/security', icon: <SecurityScanOutlined />, label: t('nav.security_management') },
      { key: '/rbac', icon: <ToolOutlined />, label: t('nav.rbac') },
      { key: '/api-keys', icon: <KeyOutlined />, label: t('nav.api_keys') },
      { key: '/ssl-certificates', icon: <SafetyOutlined />, label: t('nav.ssl_certificates') },
      { key: '/knowledge', icon: <BookOutlined />, label: t('nav.knowledge_base') },
      { key: '/config', icon: <SettingOutlined />, label: t('nav.system_config') },
    ],
  },
];

const AppLayout: React.FC = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();
  const menuItems = useMenuItems(t);
  const { token } = theme.useToken();
  const { colorBgContainer, borderRadiusLG } = token;
  const [isDark, setIsDark] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const [openKeys, setOpenKeys] = useState<string[]>(['ops-center', 'smart-diagnosis', 'device-management', 'work-orders', 'advanced', 'system-management']);

  // 读取主题设置
  useEffect(() => {
    const savedTheme = localStorage.getItem('theme');
    if (savedTheme === 'dark') {
      setIsDark(true);
      document.documentElement.setAttribute('data-theme', 'dark');
    }
  }, []);

  // 根据当前路由自动打开对应分组
  useEffect(() => {
    const currentGroup = menuItems.find(group => 
      group.children?.some(child => child.key === location.pathname)
    );
    if (currentGroup && !openKeys.includes(currentGroup.key)) {
      setOpenKeys([...openKeys, currentGroup.key]);
    }
  }, [location.pathname]);

  // 切换主题
  const toggleTheme = () => {
    const newTheme = !isDark;
    setIsDark(newTheme);
    localStorage.setItem('theme', newTheme ? 'dark' : 'light');
    document.documentElement.setAttribute('data-theme', newTheme ? 'dark' : 'light');
  };

  const userMenuItems = [
    { key: 'profile', icon: <UserOutlined />, label: t('nav.profile') },
    { key: 'settings', icon: <SettingOutlined />, label: t('nav.settings') },
    { type: 'divider' as const },
    { key: 'logout', icon: <LogoutOutlined />, label: t('nav.logout') },
  ];

  const handleMenuClick = ({ key }: { key: string }) => {
    if (key === 'logout') {
      clearAuth();
      broadcastAuthChange(); // 通知天链助手等全局组件清空缓存, 防跨账户残留
      navigate('/login');
    } else {
      navigate(key);
    }
  };

  const handleOpenChange = (keys: string[]) => {
    setOpenKeys(keys);
  };

  // 计算当前背景色
  const bgColor = isDark ? token.colorBgLayout : colorBgContainer;
  const siderBg = isDark ? token.colorBgLayout : '#1e1918';
  const headerBg = isDark ? token.colorBgLayout : colorBgContainer;

  // 获取当前菜单标题
  const getCurrentMenuLabel = () => {
    for (const group of menuItems) {
      if (group.children) {
        const child = group.children.find(c => c.key === location.pathname);
        if (child) return child.label;
      }
    }
    return t('nav.dashboard');
  };

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider 
        theme={isDark ? 'dark' : 'dark'} 
        width={240} 
        collapsible
        collapsed={collapsed}
        onCollapse={setCollapsed}
        trigger={null}
        style={{ 
          background: siderBg,
          position: 'fixed',
          left: 0,
          top: 0,
          bottom: 0,
          zIndex: 100,
        }}
      >
        {/* Logo 区域 */}
        <div style={{ 
          height: 64, 
          display: 'flex', 
          alignItems: 'center', 
          justifyContent: collapsed ? 'center' : 'center',
          color: '#fff',
          fontSize: collapsed ? 14 : 18,
          fontWeight: 'bold',
          borderBottom: '1px solid rgba(255,255,255,0.1)',
          transition: 'all 0.3s',
          overflow: 'hidden',
          whiteSpace: 'nowrap',
        }}>
          <span style={{ 
            fontSize: 24,
            marginRight: collapsed ? 0 : 8,
          }}>⚡</span>
          {!collapsed && <span>{t('app.name')}</span>}
        </div>
        
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[location.pathname]}
          openKeys={collapsed ? [] : openKeys}
          onOpenChange={handleOpenChange}
          items={menuItems}
          onClick={handleMenuClick}
          style={{ borderRight: 0, background: 'transparent' }}
        />
        
        {/* 折叠按钮 */}
        <div 
          onClick={() => setCollapsed(!collapsed)}
          style={{
            position: 'absolute',
            bottom: 16,
            left: '50%',
            transform: 'translateX(-50%)',
            cursor: 'pointer',
            color: 'rgba(255,255,255,0.65)',
            fontSize: 16,
            padding: 8,
            borderRadius: 8,
            transition: 'all 0.3s',
          }}
          className="card-hover"
        >
          {collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
        </div>
      </Sider>
      
      <Layout style={{ marginLeft: collapsed ? 80 : 240, transition: 'margin-left 0.3s' }}>
        <Header style={{ 
          padding: '0 24px', 
          background: headerBg, 
          display: 'flex', 
          justifyContent: 'space-between',
          alignItems: 'center',
          boxShadow: '0 1px 4px rgba(0,0,0,0.08)',
          position: 'sticky',
          top: 0,
          zIndex: 99,
        }}>
          {/* 左侧：页面标题 */}
          <div style={{ color: 'var(--text-primary)', fontWeight: 500 }}>
            {getCurrentMenuLabel()}
          </div>
          
          {/* 右侧：通知 + 主题切换 + 用户 */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            {/* 通知 */}
            <Badge count={8} size="small">
              <Button 
                type="text" 
                icon={<BellOutlined />}
                style={{ fontSize: 18 }}
              />
            </Badge>
            
            {/* 主题切换 */}
            <Button
              type="text"
              icon={isDark ? <SunOutlined /> : <MoonOutlined />}
              onClick={toggleTheme}
              style={{ fontSize: 18 }}
            />
            
            {/* 用户菜单 */}
            <Dropdown menu={{ items: userMenuItems, onClick: handleMenuClick }} placement="bottomRight">
              <div style={{ 
                cursor: 'pointer', 
                display: 'flex', 
                alignItems: 'center', 
                gap: 8,
                padding: '4px 8px',
                borderRadius: 8,
                transition: 'background 0.3s',
              }}
              className="card-hover"
              >
                <Avatar icon={<UserOutlined />} style={{ background: isDark ? '#ff5a36' : '#ff5a36' }} />
                <span style={{ color: 'var(--text-primary)' }}>{t('nav.admin')}</span>
              </div>
            </Dropdown>
          </div>
        </Header>
        
        <Content style={{ 
          margin: 16, 
          padding: 24, 
          background: isDark ? token.colorBgContainer : colorBgContainer, 
          borderRadius: borderRadiusLG,
          minHeight: 'calc(100vh - 64px - 32px)',
          transition: 'all 0.3s',
        }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
};

export default AppLayout;