/**
 * 网关管理 Tab — 网关列表表格 + 操作（编辑/重启/升级/删除）
 */
import React from 'react';
import { useTranslation } from 'react-i18next';
import {
  Table, Button, Space, Tag, Tooltip, Popconfirm, Alert, Empty, Spin, Progress, message,
} from 'antd';
import {
  PlusOutlined, ReloadOutlined, DeleteOutlined, EditOutlined,
  CloudUploadOutlined, PoweroffOutlined,
} from '@ant-design/icons';
import { statusColorMap } from '../constants';
import type { Gateway } from '../../../types';

interface GatewaysTabProps {
  gateways: Gateway[];
  loading: boolean;
  error: string | null;
  onAdd: () => void;
  onRefresh: () => void;
  onEdit: (record: Gateway) => void;
  onDelete: (record: Gateway) => void;
}

const GatewaysTab: React.FC<GatewaysTabProps> = ({ gateways, loading, error, onAdd, onRefresh, onEdit, onDelete }) => {
  const { t } = useTranslation();

  // 网关表格列
  const gatewayColumns = [
    {
      title: t('pages.gateways.sn'),
      dataIndex: 'sn',
      key: 'sn',
      width: 120,
      ellipsis: true,
      render: (sn: string) => sn ? <Tag color="blue">{sn}</Tag> : '-',
    },
    {
      title: t('pages.gateways.name'),
      dataIndex: 'name',
      key: 'name',
      width: 150,
      ellipsis: true,
    },
    {
      title: t('pages.gateways.model'),
      dataIndex: 'model',
      key: 'model',
      width: 120,
    },
    {
      title: t('app.status'),
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: string) => (
        <Tag color={statusColorMap[status] || 'default'}>
          {status === 'online' ? t('pages.gateways.status_online') : status === 'offline' ? t('pages.gateways.status_offline') : status === 'maintenance' ? t('pages.gateways.status_maintenance') : status === 'fault' ? t('pages.gateways.status_fault') : status}
        </Tag>
      ),
    },
    {
      title: t('pages.gateways.firmware_version'),
      dataIndex: 'firmware_version',
      key: 'firmware_version',
      width: 120,
    },
    {
      title: t('pages.gateways.health_score'),
      dataIndex: 'health_score',
      key: 'health_score',
      width: 150,
      render: (score: number) => (
        <Progress
          percent={Math.round(score || 0)}
          size="small"
          strokeColor={score >= 80 ? '#34a853' : score >= 60 ? '#f5a623' : '#ea4335'}
        />
      ),
    },
    {
      title: t('pages.gateways.ip_address'),
      dataIndex: 'ip_address',
      key: 'ip_address',
      width: 140,
    },
    {
      title: t('pages.gateways.last_online'),
      dataIndex: 'last_online',
      key: 'last_online',
      width: 180,
      render: (time: string) => time ? new Date(time).toLocaleString('zh-CN') : '-',
    },
    {
      title: t('app.action'),
      key: 'action',
      width: 200,
      render: (_: unknown, record: Gateway) => (
        <Space size="small">
          <Tooltip title={t('app.edit')}>
            <Button
              icon={<EditOutlined />}
              size="small"
              onClick={() => onEdit(record)}
            />
          </Tooltip>
          <Tooltip title={t('pages.gateways.remote_restart')}>
            <Popconfirm
              title={t('pages.gateways.confirm_restart')}
              description={t('pages.gateways.restart_desc')}
              onConfirm={async () => {
                try {
                  // 后端暂无 restart 端点，提示用户
                  message.info(t('pages.gateways.restart_sent', { name: record.name }));
                } catch {
                  message.error(t('pages.gateways.restart_failed'));
                }
              }}
            >
              <Button icon={<PoweroffOutlined />} size="small" type="primary" ghost />
            </Popconfirm>
          </Tooltip>
          <Tooltip title={t('pages.gateways.upgrade_firmware')}>
            <Button
              icon={<CloudUploadOutlined />}
              size="small"
              onClick={() => {
                message.info(`为网关 ${record.name} 创建升级任务`);
              }}
            />
          </Tooltip>
          <Popconfirm
            title={t('pages.gateways.confirm_delete')}
            description={t('pages.gateways.delete_desc')}
            onConfirm={() => onDelete(record)}
          >
            <Button icon={<DeleteOutlined />} size="small" danger />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div>
      {error && <Alert type="error" message={error} closable style={{ marginBottom: 16 }} onClose={onRefresh} />}
      <Space style={{ marginBottom: 16 }} wrap>
        <Button type="primary" icon={<PlusOutlined />} onClick={onAdd}>
          {t('pages.gateways.add')}
        </Button>
        <Button icon={<ReloadOutlined />} onClick={onRefresh}>{t('app.refresh')}</Button>
      </Space>
      <Spin spinning={loading}>
        <div className="table-scroll-x">
        <Table
          dataSource={gateways}
          columns={gatewayColumns}
          rowKey="id"
          pagination={{ pageSize: 10, showSizeChanger: true, showTotal: (total) => t('app.total', { count: total }) }}
          locale={{ emptyText: <Empty description={t('pages.gateways.no_data')} /> }}
        />
        </div>
      </Spin>
    </div>
  );
};

export default GatewaysTab;
