/**
 * 菜单配置 - 天链V3 四入口权限模型（2026-07-02）
 *
 * 四种用户类型对应四套菜单：
 *   admin (系统管理员) → SaaS平台管理 + 公共服务
 *   engineer (运维工程师) → 站点/设备/告警/工单等生产运维
 *   operator (运营人员) → 运营分析/报表/数据看板
 *   fleet (车队管理) → 车队调度/充电运营/车辆监控
 */
import React from 'react';
import {
  AlertOutlined,
  ApiOutlined,
  AppstoreOutlined,
  BankOutlined,
  BarChartOutlined,
  BookOutlined,
  CarOutlined,
  CheckSquareOutlined,
  CloudOutlined,
  CloudServerOutlined,
  DashboardOutlined,
  DatabaseOutlined,
  DesktopOutlined,
  DollarOutlined,
  EnvironmentOutlined,
  FileDoneOutlined,
  FileSearchOutlined,
  FileTextOutlined,
  FundOutlined,
  FundProjectionScreenOutlined,
  GiftOutlined,
  GoldOutlined,
  HeartOutlined,
  HistoryOutlined,
  KeyOutlined,
  LineChartOutlined,
  LinkOutlined,
  LockOutlined,
  MessageOutlined,
  NotificationOutlined,
  PieChartOutlined,
  ProfileOutlined,
  QrcodeOutlined,
  ReconciliationOutlined,
  RobotOutlined,
  RollbackOutlined,
  SafetyCertificateOutlined,
  SafetyOutlined,
  SettingOutlined,
  ShoppingCartOutlined,
  SunOutlined,
  SwapOutlined,
  TeamOutlined,
  ThunderboltOutlined,
  ToolOutlined,
  UserOutlined,
  ClockCircleOutlined,
} from '@ant-design/icons';
import type { UserType } from '../utils/auth';

export interface MenuItem {
  key: string;
  icon?: React.ReactNode;
  label: string;
  children?: MenuItem[];
}

/**
 * 系统管理员菜单（平台管理）
 * 核心职责：管理SaaS系统 + 运维团队 + 公共服务
 */
const adminMenuItems: MenuItem[] = [
  { key: '/platform/dashboard', icon: <CloudServerOutlined />, label: '平台概览' },
  { key: '/owner-cockpit', icon: <FundProjectionScreenOutlined />, label: '经营驾驶舱' },
  // 运营公司管理（TeamType=OPS_COMPANY）
  {
    key: '/ops-company-management',
    icon: <BankOutlined />,
    label: '运营公司管理',
    children: [
      { key: '/tenants?type=ops_company', icon: <BankOutlined />, label: '运营公司列表' },
      { key: '/tenants/data?type=ops_company', icon: <BarChartOutlined />, label: '运营数据分析' },
    ],
  },
  // 运维团队管理（TeamType=MAINTENANCE_TEAM）
  {
    key: '/maintenance-team',
    icon: <TeamOutlined />,
    label: '运维团队管理',
    children: [
      { key: '/tenants?type=maintenance_team', icon: <TeamOutlined />, label: '运维团队列表' },
      { key: '/tenants/data?type=maintenance_team', icon: <BarChartOutlined />, label: '运维数据分析' },
      { key: '/tenants/accounts?type=maintenance_team', icon: <UserOutlined />, label: '团队账户' },
    ],
  },
  {
    key: '/public-services',
    icon: <AppstoreOutlined />,
    label: '公共服务',
    children: [
      { key: '/gateway', icon: <ApiOutlined />, label: '网关管理' },
      { key: '/device-library', icon: <DatabaseOutlined />, label: '设备库' },
      { key: '/device-protocols', icon: <FileTextOutlined />, label: '设备协议' },
      { key: '/protocols', icon: <ApiOutlined />, label: '协议管理' },
      { key: '/knowledge', icon: <BookOutlined />, label: '知识库' },
    ],
  },
  {
    key: '/rbac',
    icon: <UserOutlined />,
    label: '平台账户',
    children: [
      { key: '/rbac/users', icon: <UserOutlined />, label: '管理员账户' },
      { key: '/rbac/roles', icon: <KeyOutlined />, label: '角色权限' },
    ],
  },
  { key: '/config', icon: <SettingOutlined />, label: '系统配置' },
  { key: '/data-ops', icon: <DatabaseOutlined />, label: '数据管理' },
  { key: '/ai-model_config', icon: <RobotOutlined />, label: 'AI模型配置' },
  { key: '/audit-log', icon: <HistoryOutlined />, label: '审计日志' },
  {
    key: '/security-group',
    icon: <SafetyCertificateOutlined />,
    label: '安全管理',
    children: [
      { key: '/ssl-certificates', icon: <SafetyCertificateOutlined />, label: 'SSL证书管理' },
      { key: '/security', icon: <LockOutlined />, label: '安全配置' },
      { key: '/log-analysis', icon: <FileSearchOutlined />, label: '审计日志分析' },
    ],
  },
  {
    key: '/notification-group',
    icon: <NotificationOutlined />,
    label: '消息通知',
    children: [
      { key: '/message-center', icon: <MessageOutlined />, label: '消息中心' },
      { key: '/notification-rules', icon: <NotificationOutlined />, label: '通知规则' },
    ],
  },
  {
    key: '/iot-group',
    icon: <ApiOutlined />,
    label: '物联网接入',
    children: [
      { key: '/terminals', icon: <ApiOutlined />, label: '终端管理' },
      { key: '/edge-gateways', icon: <CloudServerOutlined />, label: '边缘网关' },
      { key: '/cloud', icon: <CloudOutlined />, label: '云服务配置' },
    ],
  },
  {
    key: '/external-group',
    icon: <LinkOutlined />,
    label: '外部对接',
    children: [
      { key: '/links', icon: <LinkOutlined />, label: '互联互通' },
      { key: '/admin/supervision', icon: <BankOutlined />, label: '市政监管' },
    ],
  },
  { key: '/api-keys', icon: <ApiOutlined />, label: '开放平台 · API密钥管理' },
  { key: '/runbook-approval', icon: <RollbackOutlined />, label: '运维审批 · Runbook审批' },
];

/**
 * 运维工程师菜单（生产运维）
 * 核心职责：站点设备管理 + 告警工单 + 巡检排班 + 故障诊断
 */
const engineerMenuItems: MenuItem[] = [
  { key: '/dashboard', icon: <DashboardOutlined />, label: '运维总览' },
  { key: '/stations', icon: <EnvironmentOutlined />, label: '站点管理' },
  { key: '/devices', icon: <DesktopOutlined />, label: '设备管理' },
  { key: '/devices/v2g', icon: <ThunderboltOutlined />, label: 'V2G设备' },
  { key: '/alarms', icon: <AlertOutlined />, label: '告警管理' },
  { key: '/workorders', icon: <CheckSquareOutlined />, label: '工单管理' },
  { key: '/workorder-stats', icon: <BarChartOutlined />, label: '工单统计' },
  { key: '/inspection-ops', icon: <ToolOutlined />, label: '巡检运维' },
  { key: '/on-call', icon: <ClockCircleOutlined />, label: '值班排班' },
  { key: '/healing', icon: <SafetyOutlined />, label: '告警自愈' },
  { key: '/runbook', icon: <FileDoneOutlined />, label: 'Runbook管理' },
  { key: '/telemetry', icon: <BarChartOutlined />, label: '遥测数据' },
  { key: '/fault-diagnosis', icon: <AlertOutlined />, label: '故障诊断' },
  { key: '/knowledge', icon: <BookOutlined />, label: '知识库' },
  { key: '/health', icon: <HeartOutlined />, label: '健康管理' },
  { key: '/energy-report', icon: <ThunderboltOutlined />, label: '能耗分析' },
  { key: '/predictive-maintenance', icon: <LineChartOutlined />, label: '预测维护' },
  {
    key: '/ops-team',
    icon: <TeamOutlined />,
    label: '团队管理',
    children: [
      { key: '/teams', icon: <TeamOutlined />, label: '团队列表' },
      { key: '/teams/engineers', icon: <ToolOutlined />, label: '工程师管理' },
      { key: '/rbac/users', icon: <UserOutlined />, label: '成员管理' },
      { key: '/rbac/roles', icon: <KeyOutlined />, label: '角色权限' },
    ],
  },
  {
    key: '/advanced-ops',
    icon: <FundProjectionScreenOutlined />,
    label: '高级运维',
    children: [
      { key: '/ops-dashboard', icon: <DashboardOutlined />, label: '运维仪表板' },
      { key: '/analytics-dashboard', icon: <FundProjectionScreenOutlined />, label: 'AI分析仪表板' },
      { key: '/digital-twin', icon: <AppstoreOutlined />, label: '数字孪生' },
      { key: '/vpp', icon: <PieChartOutlined />, label: '虚拟电厂' },
    ],
  },
];

/**
 * 运营人员菜单（运营分析）
 * 核心职责：运营数据可视化 + 报表分析 + 决策支持
 */
const operatorMenuItems: MenuItem[] = [
  { key: '/operate', icon: <DashboardOutlined />, label: '运营首页' },
  { key: '/owner-cockpit', icon: <FundProjectionScreenOutlined />, label: '经营驾驶舱' },
  {
    key: '/operate-marketing',
    icon: <GiftOutlined />,
    label: '运营管理',
    children: [
      { key: '/operate/stations', icon: <EnvironmentOutlined />, label: '站点管理' },
      { key: '/operate/devices', icon: <DesktopOutlined />, label: '设备管理' },
      { key: '/operate/v2g', icon: <ThunderboltOutlined />, label: 'V2G运营' },
      { key: '/operate/users', icon: <UserOutlined />, label: '用户管理' },
      { key: '/operate/discounts', icon: <DollarOutlined />, label: '折扣管理' },
      { key: '/operate/coupons', icon: <GiftOutlined />, label: '优惠券' },
      { key: '/operate/points', icon: <GoldOutlined />, label: '积分' },
      { key: '/operate/fleet', icon: <CarOutlined />, label: '车队管理' },
    ],
  },
  {
    key: '/operate-core',
    icon: <DollarOutlined />,
    label: '运营核心',
    children: [
      { key: '/operate/pricing', icon: <DollarOutlined />, label: '费用定价' },
      { key: '/operate/orders', icon: <ShoppingCartOutlined />, label: '订单管理' },
      { key: '/operate/refunds', icon: <SwapOutlined />, label: '退款管理' },
      { key: '/operate/qrcodes', icon: <QrcodeOutlined />, label: '二维码管理' },
      { key: '/operate/recharge-approval', icon: <DollarOutlined />, label: '充值审核' },
    ],
  },
  {
    key: '/operate-finance',
    icon: <ReconciliationOutlined />,
    label: '财务结算',
    children: [
      { key: '/operate/invoices', icon: <ProfileOutlined />, label: '发票管理' },
      { key: '/operate/settlement', icon: <ReconciliationOutlined />, label: '结算对账' },
    ],
  },
  { key: '/operate/analytics', icon: <FundOutlined />, label: '运营分析' },
  { key: '/analytics-dashboard', icon: <LineChartOutlined />, label: 'AI运维分析' },
  { key: '/message-center', icon: <MessageOutlined />, label: '消息通知' },
  {
    key: '/data-analysis',
    icon: <BarChartOutlined />,
    label: '数据分析',
    children: [
      { key: '/reports/utilization', icon: <BarChartOutlined />, label: '设备利用率' },
      { key: '/reports/efficiency', icon: <ThunderboltOutlined />, label: '充电效率' },
      { key: '/reports/generation', icon: <SunOutlined />, label: '发电效率' },
    ],
  },
  { key: '/energy-report', icon: <ThunderboltOutlined />, label: '能耗分析' },
  { key: '/reports', icon: <BarChartOutlined />, label: '报表导出' },
  { key: '/report-mgmt', icon: <FileTextOutlined />, label: '运维报告' },
  { key: '/vpp', icon: <PieChartOutlined />, label: '虚拟电厂' },
  { key: '/digital-twin', icon: <AppstoreOutlined />, label: '数字孪生' },
  { key: '/stations', icon: <EnvironmentOutlined />, label: '站点总览' },
  { key: '/devices', icon: <DesktopOutlined />, label: '设备总览' },
  { key: '/alarms', icon: <AlertOutlined />, label: '告警总览' },
];

/**
 * 车队管理菜单（用户团体）
 * 核心职责：车队企业 / 车辆 / 司机 / 资金 / 碳排放 / 充电调度 / 结算
 * 不涉场站经营及维护
 */
const fleetMenuItems: MenuItem[] = [
  { key: '/fleet', icon: <CarOutlined />, label: '车队总览' },
  { key: '/fleet?tab=vehicles', icon: <CarOutlined />, label: '车辆管理' },
  { key: '/fleet?tab=drivers', icon: <UserOutlined />, label: '司机管理' },
  { key: '/fleet?tab=funds', icon: <FundOutlined />, label: '资金账户' },
  { key: '/fleet?tab=recharge', icon: <DollarOutlined />, label: '充值' },
  { key: '/fleet?tab=carbon', icon: <LineChartOutlined />, label: '碳排放管理' },
  { key: '/fleet?tab=settlement', icon: <ReconciliationOutlined />, label: '费用结算' },
];

/** 根据用户类型获取菜单 */
export function getMenuItems(userType: UserType): MenuItem[] {
  switch (userType) {
    case 'admin': return adminMenuItems;
    case 'engineer': return engineerMenuItems;
    case 'operator': return operatorMenuItems;
    case 'fleet': return fleetMenuItems;
    default: return engineerMenuItems;
  }
}

/** 获取系统标题 */
export function getSystemTitle(userType: UserType, collapsed: boolean): string {
  const titles: Record<UserType, string> = {
    admin: '天链平台管理',
    engineer: '天链运维管理系统',
    operator: '天链运营分析系统',
    fleet: '天链车队管理系统',
  };
  const full = titles[userType] || '天链光储充运维系统';
  return collapsed ? '天链' : full;
}
