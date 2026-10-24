/**
 * 天链 V3 - 系统配置页面 (SPEC第10章 + admin spec §2.3)
 *
 * 配置多租户化 (卡 d0c431d0): Tab 渲染按当前用户 team_type 过滤。
 *   - platform         通知/日志/全局/支付/发票/权限配置 + 运维专属占位
 *   - ops_company      通知/日志/全局/支付/发票 (本团队数据)
 *   - maintenance_team 通知/日志/全局 + 运维专属占位
 *   - fleet            通知 + 车队专属占位
 *
 * 数据隔离由后端 (cf614348 scope 矩阵) + X-Team-Id header 负责,
 * 前端只按 team_type 呈现可见 Tab, 并由全局响应拦截器兜底 403。
 *
 * 各 Tab 的 UI 与数据逻辑拆分至 ./components 与 ./hooks。
 */
import React, { useMemo } from 'react';
import { Card, Tabs } from 'antd';
import {
  SafetyCertificateOutlined, NotificationOutlined, HistoryOutlined,
  SettingOutlined, CreditCardOutlined, FileTextOutlined,
  CarOutlined, ToolOutlined,
} from '@ant-design/icons';
import { getCurrentUser } from '../../utils/auth';
import RbacTab from './components/RbacTab';
import NotificationTab from './components/NotificationTab';
import AuditLogTab from './components/AuditLogTab';
import GlobalConfigTab from './components/GlobalConfigTab';
import PaymentTab from './components/PaymentTab';
import InvoiceTab from './components/InvoiceTab';
import PlaceholderTab from './components/PlaceholderTab';
import { getVisibleTabKeys, resolveTeamType, type ConfigTabKey } from './configTabs';

/** 全部 Tab 定义: key → (label, children) */
const ALL_TABS: Record<ConfigTabKey, { label: React.ReactNode; children: React.ReactNode }> = {
  rbac: {
    label: <span><SafetyCertificateOutlined /> 权限配置</span>,
    children: <RbacTab />,
  },
  notification: {
    label: <span><NotificationOutlined /> 通知配置</span>,
    children: <NotificationTab />,
  },
  audit: {
    label: <span><HistoryOutlined /> 日志审计</span>,
    children: <AuditLogTab />,
  },
  global: {
    label: <span><SettingOutlined /> 全局配置</span>,
    children: <GlobalConfigTab />,
  },
  payment: {
    label: <span><CreditCardOutlined /> 支付通道</span>,
    children: <PaymentTab />,
  },
  invoice: {
    label: <span><FileTextOutlined /> 发票配置</span>,
    children: <InvoiceTab />,
  },
  fleet_panel: {
    label: <span><CarOutlined /> 车队专属</span>,
    children: (
      <PlaceholderTab
        title="车队专属配置"
        description="车队相关的专属配置项正在建设中, 内容由后续卡片提供。"
      />
    ),
  },
  ops_panel: {
    label: <span><ToolOutlined /> 运维专属</span>,
    children: (
      <PlaceholderTab
        title="运维专属配置"
        description="运维团队相关的专属配置项正在建设中, 内容由后续卡片提供。"
      />
    ),
  },
};

const ConfigPage: React.FC = () => {
  // team_type 在登录态写入 localStorage (admin_user), 用户上下文不变即稳定。
  const visibleKeys = useMemo<ConfigTabKey[]>(
    () => getVisibleTabKeys(resolveTeamType(getCurrentUser())),
    [],
  );

  const tabItems = useMemo(
    () => visibleKeys.map(key => ({ key, label: ALL_TABS[key].label, children: ALL_TABS[key].children })),
    [visibleKeys],
  );

  return (
    <div className="page-container">
      <Card>
        <Tabs items={tabItems} defaultActiveKey={visibleKeys[0]} />
      </Card>
    </div>
  );
};

export default ConfigPage;
