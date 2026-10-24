/**
 * SN 码管理 Tab — SN 码列表表格 + 生成入口
 */
import React from 'react';
import { useTranslation } from 'react-i18next';
import {
  Table, Button, Space, Tag, Popconfirm, Alert, Empty, Spin, message,
} from 'antd';
import { PlusOutlined, ReloadOutlined, LockOutlined } from '@ant-design/icons';
import { snStatusColorMap } from '../constants';
import type { Gateway } from '../../../types';

interface SnCodesTabProps {
  snCodes: Gateway[];
  loading: boolean;
  error: string | null;
  onOpenGenerate: () => void;
  onRefresh: () => void;
}

const SnCodesTab: React.FC<SnCodesTabProps> = ({ snCodes, loading, error, onOpenGenerate, onRefresh }) => {
  const { t } = useTranslation();

  // SN码表格列
  const snColumns = [
    {
      title: 'SN码',
      dataIndex: 'sn',
      key: 'sn',
      width: 150,
      ellipsis: true,
      render: (sn: string) => sn ? <Tag color="blue">{sn}</Tag> : '-',
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
        <Tag color={snStatusColorMap[status] || 'default'}>
          {status === 'generated' ? t('pages.gateways.sn_generated') : status === 'written' ? t('pages.gateways.sn_written') : status === 'activated' ? t('pages.gateways.sn_activated') : status === 'locked' ? t('pages.gateways.sn_locked') : status === 'recalled' ? t('pages.gateways.sn_recalled') : status}
        </Tag>
      ),
    },
    {
      title: t('pages.gateways.batch_no'),
      dataIndex: 'batch_no',
      key: 'batch_no',
      width: 120,
    },
    {
      title: t('pages.gateways.region'),
      dataIndex: 'region',
      key: 'region',
      width: 80,
      render: (region: string) => region || '-',
    },
    {
      title: t('pages.gateways.related_gateway'),
      dataIndex: 'gateway_id',
      key: 'gateway_id',
      width: 100,
      render: (id: number) => id || '-',
    },
    {
      title: t('pages.gateways.generated_at'),
      dataIndex: 'generated_at',
      key: 'generated_at',
      width: 180,
      render: (time: string) => time ? new Date(time).toLocaleString('zh-CN') : '-',
    },
    {
      title: t('app.action'),
      key: 'action',
      width: 180,
      render: (record: Gateway) => (
        <Space size="small">
          {record.status === 'generated' && (
            <Button size="small" onClick={() => message.info(`SN码 ${record.sn} 写入功能`)}>写入</Button>
          )}
          {record.status === 'written' && (
            <Button size="small" type="primary" onClick={() => message.info(`SN码 ${record.sn} 激活功能`)}>激活</Button>
          )}
          {record.status === 'activated' && (
            <Popconfirm title="确认锁定此SN码?" onConfirm={() => message.success('SN码已锁定')}>
              <Button size="small" icon={<LockOutlined />} />
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
        <Button type="primary" icon={<PlusOutlined />} onClick={onOpenGenerate}>
          生成SN码
        </Button>
        <Button icon={<ReloadOutlined />} onClick={onRefresh}>刷新</Button>
      </Space>
      <Spin spinning={loading}>
        <div className="table-scroll-x">
        <Table
          dataSource={snCodes}
          columns={snColumns}
          rowKey="id"
          pagination={{ pageSize: 10, showSizeChanger: true }}
          locale={{ emptyText: <Empty description={t('pages.gateways.sn_no_data')} /> }}
        />
        </div>
      </Spin>
    </div>
  );
};

export default SnCodesTab;
