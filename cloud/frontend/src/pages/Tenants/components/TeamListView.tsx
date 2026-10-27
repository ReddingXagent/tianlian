/**
 * Tab1: 团队列表（表格视图，CRUD 操作）
 * 运维团队列表增加'所属运营公司'列：有 parent_team_id 显示运营公司名，无则显示 Tag('独立')
 */
import React from 'react';
import { useTranslation } from 'react-i18next';
import { Table, Button, Space, Tag, Tooltip, Popconfirm, Input } from 'antd';
import {
  PlusOutlined, ReloadOutlined, DeleteOutlined, EditOutlined,
  SearchOutlined, CheckCircleOutlined, StopOutlined,
} from '@ant-design/icons';
import { getStatusMap } from '../utils';
import type { Tenant } from '../types';

const TeamListView: React.FC<{
  tenants: Tenant[];
  loading: boolean;
  searchText: string;
  needsParentTeam?: boolean;
  onSearchChange: (v: string) => void;
  onRefresh: () => void;
  onOpenCreate: () => void;
  onOpenEdit: (t: Tenant) => void;
  onToggleStatus: (t: Tenant) => void;
  onDelete: (id: number) => void;
  onViewDetail: (t: Tenant) => void;
}> = ({ tenants, loading, searchText, needsParentTeam, onSearchChange, onRefresh, onOpenCreate, onOpenEdit, onToggleStatus, onDelete, onViewDetail }) => {
  const { t } = useTranslation();
  const statusMap = getStatusMap(t);

  const columns = [
    {
      title: t('pages.tenants.team_name'), dataIndex: 'name', key: 'name',
      render: (name: string, record: Tenant) => (
        <Button type="link" style={{ padding: 0 }} onClick={() => onViewDetail(record)}>{name}</Button>
      ),
    },
    { title: t('pages.tenants.code'), dataIndex: 'code', key: 'code', width: 90 },
    // 运维团队列表增加'所属运营公司'列
    ...(needsParentTeam ? [{
      title: '所属运营公司', key: 'parent_team_name', width: 120,
      render: (_: unknown, record: Tenant) => {
        if (record.parent_team_name) return record.parent_team_name;
        if (record.parent_team_id) return `#${record.parent_team_id}`;
        return <Tag>独立</Tag>;
      },
    }] : []),
    { title: t('pages.tenants.contact'), dataIndex: 'contact', key: 'contact', width: 90 },
    {
      title: t('app.status'), dataIndex: 'status', key: 'status', width: 80,
      render: (s: string) => <Tag color={statusMap[s]?.color}>{statusMap[s]?.text || s}</Tag>,
    },
    { title: t('pages.tenants.stations_count'), dataIndex: 'station_count', key: 'station_count', width: 75 },
    { title: t('pages.tenants.devices_count'), dataIndex: 'device_count', key: 'device_count', width: 75 },
    { title: t('pages.tenants.members'), dataIndex: 'member_count', key: 'member_count', width: 60 },
    { title: t('pages.tenants.workorders_month'), dataIndex: 'workorder_count', key: 'workorder_count', width: 85 },
    {
      title: t('pages.tenants.expired_at'), dataIndex: 'expired_at', key: 'expired_at', width: 110,
      render: (d: string) => {
        const days = Math.ceil((new Date(d).getTime() - Date.now()) / 86400000);
        return <span style={{ color: days < 30 ? '#ea4335' : days < 90 ? '#f5a623' : undefined }}>{d}</span>;
      },
    },
    {
      title: '操作', key: 'action', width: 160,
      render: (_: unknown, record: Tenant) => (
        <Space size="small">
          <Tooltip title={t('app.edit')}><Button icon={<EditOutlined />} size="small" onClick={() => onOpenEdit(record)} /></Tooltip>
          {record.status === 'disabled' ? (
            <Tooltip title={t('pages.tenants.enable_account')}><Button icon={<CheckCircleOutlined />} size="small" type="primary" onClick={() => onToggleStatus(record)} /></Tooltip>
          ) : (
            <Tooltip title={t('pages.tenants.disable_account')}><Button icon={<StopOutlined />} size="small" danger onClick={() => onToggleStatus(record)} /></Tooltip>
          )}
          <Popconfirm title={t('pages.tenants.confirm_delete')} onConfirm={() => onDelete(record.id)}>
            <Button icon={<DeleteOutlined />} size="small" danger />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <>
      <Space style={{ marginBottom: 16, flexWrap: 'wrap' }}>
        <Input placeholder={t('pages.tenants.search_placeholder')} prefix={<SearchOutlined />} value={searchText} onChange={e => onSearchChange(e.target.value)} style={{ width: 250 }} allowClear />
        <Button type="primary" icon={<PlusOutlined />} onClick={onOpenCreate}>{t('pages.tenants.add')}</Button>
        <Button icon={<ReloadOutlined />} onClick={onRefresh}>{t('app.refresh')}</Button>
      </Space>
      <Table dataSource={tenants} columns={columns} rowKey="id" loading={loading} pagination={{ pageSize: 10 }} />
    </>
  );
};

export default TeamListView;
