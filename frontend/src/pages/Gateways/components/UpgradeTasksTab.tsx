/**
 * 升级任务 Tab — 升级任务列表表格 + 创建入口
 */
import React from 'react';
import { useTranslation } from 'react-i18next';
import {
  Table, Button, Space, Tag, Popconfirm, Alert, Empty, Spin, Progress, message,
} from 'antd';
import { SyncOutlined, ReloadOutlined } from '@ant-design/icons';
import { taskStatusColorMap } from '../constants';
import type { Gateway } from '../../../types';

interface UpgradeTasksTabProps {
  upgradeTasks: Gateway[];
  loading: boolean;
  error: string | null;
  onRefresh: () => void;
}

const UpgradeTasksTab: React.FC<UpgradeTasksTabProps> = ({ upgradeTasks, loading, error, onRefresh }) => {
  const { t } = useTranslation();

  // 升级任务表格列
  const taskColumns = [
    {
      title: t('pages.gateways.task_id'),
      dataIndex: 'id',
      key: 'id',
      width: 100,
    },
    {
      title: t('pages.gateways.gateway_id'),
      dataIndex: 'gateway_id',
      key: 'gateway_id',
      width: 100,
    },
    {
      title: t('pages.gateways.firmware_id'),
      dataIndex: 'firmware_id',
      key: 'firmware_id',
      width: 100,
    },
    {
      title: t('app.status'),
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: string) => (
        <Tag color={taskStatusColorMap[status] || 'default'}>
          {status === 'pending' ? t('pages.gateways.task_pending') : status === 'running' ? t('pages.gateways.task_running') : status === 'success' ? t('pages.gateways.task_success') : status === 'failed' ? t('pages.gateways.task_failed') : status === 'cancelled' ? t('pages.gateways.task_cancelled') : status}
        </Tag>
      ),
    },
    {
      title: t('pages.gateways.progress'),
      dataIndex: 'progress',
      key: 'progress',
      width: 150,
      render: (progress: number) => (
        <Progress
          percent={progress || 0}
          size="small"
          status={progress === 100 ? 'success' : progress > 0 ? 'active' : undefined}
        />
      ),
    },
    {
      title: t('app.created_at'),
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (time: string) => time ? new Date(time).toLocaleString('zh-CN') : '-',
    },
    {
      title: t('app.action'),
      key: 'action',
      width: 140,
      render: (record: Gateway) => (
        <Space size="small">
          {record.status === 'pending' && (
            <Popconfirm title="确认启动此升级任务?" onConfirm={() => message.success('升级任务已启动')}>
              <Button size="small" type="primary">启动</Button>
            </Popconfirm>
          )}
          {record.status === 'running' && (
            <Popconfirm title="确认取消此升级任务?" onConfirm={() => message.success('升级任务已取消')}>
              <Button size="small" danger>取消</Button>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ];

  return (
    <div>
      {error && <Alert type="error" message={error} closable style={{ marginBottom: 16 }} />}
      <Space style={{ marginBottom: 16 }} wrap>
        <Button type="primary" icon={<SyncOutlined />}>
          创建升级任务
        </Button>
        <Button icon={<ReloadOutlined />} onClick={onRefresh}>刷新</Button>
      </Space>
      <Spin spinning={loading}>
        <div className="table-scroll-x">
        <Table
          dataSource={upgradeTasks}
          columns={taskColumns}
          rowKey="id"
          pagination={{ pageSize: 10, showSizeChanger: true }}
          locale={{ emptyText: <Empty description={t('pages.gateways.task_no_data')} /> }}
        />
        </div>
      </Spin>
    </div>
  );
};

export default UpgradeTasksTab;
