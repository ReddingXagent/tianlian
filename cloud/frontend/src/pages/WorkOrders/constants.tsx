/**
 * 工单管理页面 — 展示常量（级别/状态/类型 → 颜色、文案、图标）
 */
import React from 'react';
import {
  ClockCircleOutlined, UserOutlined, ThunderboltOutlined,
  CheckCircleOutlined, CloseCircleOutlined, CheckSquareOutlined,
} from '@ant-design/icons';

export const levelColors: Record<string, string> = {
  low: 'blue', warning: 'orange', medium: 'orange', high: 'red', urgent: 'magenta',
};

export const statusColors: Record<string, string> = {
  pending: 'orange', accepted: 'blue', processing: 'blue',
  pending_verify: 'gold', completed: 'green', cancelled: 'default', verified: 'green',
};

export const statusLabels: Record<string, string> = {
  pending: '待派单', accepted: '已接单', processing: '处理中',
  pending_verify: '待验收', completed: '已完成', cancelled: '已取消', verified: '已验收',
};

export const statusIcons: Record<string, React.ReactNode> = {
  pending: <ClockCircleOutlined />, accepted: <UserOutlined />,
  processing: <ThunderboltOutlined />, completed: <CheckCircleOutlined />,
  cancelled: <CloseCircleOutlined />, verified: <CheckSquareOutlined />,
};

export const typeLabels: Record<string, string> = {
  repair: '维修', inspection: '巡检', installation: '安装', maintenance: '保养',
};
