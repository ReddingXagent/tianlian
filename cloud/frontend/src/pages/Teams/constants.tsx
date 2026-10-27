/**
 * 团队管理页面 — 常量映射（状态/角色 → 颜色、文案、图标；区域选项）
 */
import React from 'react';
import { CrownOutlined, ToolOutlined, UserOutlined } from '@ant-design/icons';

export const statusColorMap: Record<string, string> = { active: 'green', inactive: 'default' };
export const statusTextMap: Record<string, string> = { active: '启用', inactive: '停用' };
export const roleColorMap: Record<string, string> = { admin: 'red', engineer: 'blue', technician: 'green' };
export const roleTextMap: Record<string, string> = { admin: '管理员', engineer: '工程师', technician: '技术员' };
export const roleIconMap: Record<string, React.ReactNode> = {
  admin: <CrownOutlined />,
  engineer: <ToolOutlined />,
  technician: <UserOutlined />,
};

// 区域码映射
export const regionOptions = [
  { value: 'HN', label: '河南' },
  { value: 'GD', label: '广东' },
  { value: 'JS', label: '江苏' },
  { value: 'SD', label: '山东' },
  { value: 'ZJ', label: '浙江' },
  { value: 'FJ', label: '福建' },
  { value: 'SC', label: '四川' },
  { value: 'HB', label: '湖北' },
  { value: 'BJ', label: '北京' },
  { value: 'SH', label: '上海' },
  { value: 'GX', label: '广西' },
  { value: 'SN', label: '陕西' },
  { value: 'CQ', label: '重庆' },
  { value: 'LN', label: '辽宁' },
];
