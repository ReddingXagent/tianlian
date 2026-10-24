/**
 * 天链 V3 — 监管数据上报状态
 * 查看各城市监管平台的上报记录, 失败/待处理记录可手动重试
 */
import React, { useEffect, useState, useCallback } from 'react';
import { Table, Tag, Button, Space, message } from 'antd';
import { ReloadOutlined, RedoOutlined } from '@ant-design/icons';
import { regulatoryReportAPI } from '../../../api/operateExternal';
import { fetchAllPages } from '../../../api/fetchAll';

interface ReportItem {
  id: number;
  config_id: number;
  city: string;
  report_type: string;
  report_content?: Record<string, unknown> | null;
  status: string;
  retry_count: number;
  error_message?: string | null;
  reported_at?: string;
  created_at?: string;
}

const REPORT_TYPE_MAP: Record<string, string> = {
  station: '站点信息',
  device: '设备信息',
  order: '订单数据',
  heartbeat: '心跳保活',
};

const STATUS_MAP: Record<string, { color: string; text: string }> = {
  success: { color: 'green', text: '成功' },
  failed: { color: 'red', text: '失败' },
  pending: { color: 'orange', text: '待处理' },
};

const SupervisionReports: React.FC = () => {
  const [data, setData] = useState<ReportItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [retryingId, setRetryingId] = useState<number | null>(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      // 卡 fb183aaf: page_size 恰 100 上限会静默截断 → fetchAllPages 循环拉全量
      const items = await fetchAllPages<ReportItem>(regulatoryReportAPI.list);
      setData(items);
    } catch {
      setData([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const handleRetry = async (id: number) => {
    setRetryingId(id);
    try {
      await regulatoryReportAPI.retry(id);
      message.success('重试已完成');
      loadData();
    } catch (err: any) {
      message.error('重试失败：' + (err?.response?.data?.detail || err?.message));
    } finally {
      setRetryingId(null);
    }
  };

  const columns = [
    { title: 'ID', dataIndex: 'id', key: 'id', width: 60 },
    { title: '城市', dataIndex: 'city', key: 'city', width: 90 },
    {
      title: '上报类型', dataIndex: 'report_type', key: 'report_type', width: 110,
      render: (v: string) => <Tag color="blue">{REPORT_TYPE_MAP[v] || v}</Tag>,
    },
    {
      title: '状态', dataIndex: 'status', key: 'status', width: 90,
      render: (v: string) => <Tag color={STATUS_MAP[v]?.color || 'default'}>{STATUS_MAP[v]?.text || v}</Tag>,
    },
    { title: '重试次数', dataIndex: 'retry_count', key: 'retry_count', width: 90, align: 'right' as const },
    {
      title: '错误信息', dataIndex: 'error_message', key: 'error_message', width: 240, ellipsis: true,
      render: (v: string) => v || '-',
    },
    { title: '上报时间', dataIndex: 'reported_at', key: 'reported_at', width: 160, render: (v: string) => v || '-' },
    {
      title: '操作', key: 'action', width: 100, fixed: 'right' as const,
      render: (_: unknown, record: ReportItem) =>
        record.status === 'success' ? (
          <span style={{ color: '#999' }}>-</span>
        ) : (
          <Button
            size="small"
            icon={<RedoOutlined />}
            loading={retryingId === record.id}
            onClick={() => handleRetry(record.id)}
          >重试</Button>
        ),
    },
  ];

  return (
    <>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'flex-end' }}>
        <Button icon={<ReloadOutlined />} onClick={loadData}>刷新</Button>
      </div>
      <Table
        columns={columns}
        dataSource={data}
        rowKey="id"
        loading={loading}
        scroll={{ x: 1100 }}
        pagination={{ pageSize: 10, showSizeChanger: true, showTotal: (t: number) => `共 ${t} 条` }}
      />
    </>
  );
};

export default SupervisionReports;
