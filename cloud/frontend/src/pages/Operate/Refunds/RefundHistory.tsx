/**
 * 退款记录 — 全部退款历史
 */
import React, { useEffect, useState, useCallback } from 'react';
import {
  Table, Tag, Button, Card, Space, Input, Select, Statistic, Row, Col, message,
} from 'antd';
import {
  ReloadOutlined, SearchOutlined,
  CheckCircleOutlined, CloseCircleOutlined, ClockCircleOutlined,
} from '@ant-design/icons';
import { refundAPI } from '../../../api/operate';
import { fetchAllPages } from '../../../api/fetchAll';

interface RefundRecord {
  id: number;
  order_id: number;
  order_no?: string;
  station_name?: string;
  user_id: number | null;
  refund_amount: number;
  reason: string;
  status: string | null;
  reviewer_id: number | null;
  reviewed_at: string | null;
  refunded_at: string | null;
  reject_reason: string | null;
  created_at: string | null;
}

const REFUND_STATUS_MAP: Record<string, { color: string; text: string }> = {
  pending: { color: 'orange', text: '待审核' },
  approved: { color: 'blue', text: '已批准' },
  rejected: { color: 'red', text: '已驳回' },
  refunded: { color: 'green', text: '已退款' },
};

const RefundHistoryPage: React.FC = () => {
  const [refunds, setRefunds] = useState<RefundRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [keyword, setKeyword] = useState('');
  const [statusFilter, setStatusFilter] = useState<string | undefined>(undefined);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      // 卡 34ec1d55: 全局退款记录端点分页拉全量, 替代「先拉全部订单再逐单 GET /orders/{id}/refunds」
      // 的 N+1 千请求轰炸。order_no/station_name 由后端 JOIN 返回。
      const allRefunds = await fetchAllPages<RefundRecord>(
        (params) => refundAPI.listAll(params),
      );
      setRefunds(allRefunds);
    } catch {
      setRefunds([]);
      message.error('退款记录加载失败，请稍后重试');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const stats = {
    total: refunds.length,
    approved: refunds.filter(r => r.status === 'approved' || r.status === 'refunded').length,
    rejected: refunds.filter(r => r.status === 'rejected').length,
    totalAmount: refunds.filter(r => r.status === 'refunded').reduce((s, r) => s + (r.refund_amount || 0), 0),
  };

  let displayRefunds = refunds;
  if (statusFilter) displayRefunds = displayRefunds.filter(r => r.status === statusFilter);
  if (keyword) displayRefunds = displayRefunds.filter(r => r.order_no?.includes(keyword) || r.reason?.includes(keyword));

  const columns = [
    { title: '退款ID', dataIndex: 'id', key: 'id', width: 80 },
    { title: '订单号', dataIndex: 'order_no', key: 'order_no', width: 170, render: (v: string) => v ? <Tag color="blue">{v}</Tag> : '-' },
    { title: '站点', dataIndex: 'station_name', key: 'station_name', width: 120, ellipsis: true },
    {
      title: '退款金额', dataIndex: 'refund_amount', key: 'refund_amount', width: 110, align: 'right' as const,
      render: (v: number) => <span style={{ fontWeight: 600, color: '#ea4335' }}>¥{(v || 0).toFixed(2)}</span>,
    },
    { title: '退款原因', dataIndex: 'reason', key: 'reason', ellipsis: true },
    {
      title: '状态', dataIndex: 'status', key: 'status', width: 90,
      render: (v: string | null) => v ? <Tag color={REFUND_STATUS_MAP[v]?.color || 'default'}>{REFUND_STATUS_MAP[v]?.text || v}</Tag> : '-',
    },
    {
      title: '审核时间', dataIndex: 'reviewed_at', key: 'reviewed_at', width: 150,
      render: (v: string | null) => v ? new Date(v).toLocaleString('zh-CN') : '-',
    },
    {
      title: '退款到账', dataIndex: 'refunded_at', key: 'refunded_at', width: 150,
      render: (v: string | null) => v ? new Date(v).toLocaleString('zh-CN') : '-',
    },
    {
      title: '驳回原因', dataIndex: 'reject_reason', key: 'reject_reason', width: 150, ellipsis: true,
      render: (v: string | null) => v || '-',
    },
  ];

  return (
    <>
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={12} sm={6}>
          <Card><Statistic title="退款总数" value={stats.total} /></Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card><Statistic title="已批准/退款" value={stats.approved} valueStyle={{ color: '#34a853' }} prefix={<CheckCircleOutlined />} /></Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card><Statistic title="已驳回" value={stats.rejected} valueStyle={{ color: '#ea4335' }} prefix={<CloseCircleOutlined />} /></Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card><Statistic title="退款总额" value={stats.totalAmount} precision={2} prefix="¥" valueStyle={{ color: '#faad14' }} /></Card>
        </Col>
      </Row>

      <Card
        extra={
          <Space>
            <Input
              placeholder="搜索订单号/原因"
              prefix={<SearchOutlined />}
              value={keyword}
              onChange={e => setKeyword(e.target.value)}
              style={{ width: 200 }}
              allowClear
            />
            <Select
              placeholder="退款状态"
              value={statusFilter}
              onChange={setStatusFilter}
              allowClear
              style={{ width: 120 }}
              options={Object.entries(REFUND_STATUS_MAP).map(([k, v]) => ({ label: v.text, value: k }))}
            />
            <Button icon={<ReloadOutlined />} onClick={loadData}>刷新</Button>
          </Space>
        }
      >
        <Table
          columns={columns}
          dataSource={displayRefunds}
          rowKey="id"
          loading={loading}
          pagination={{ pageSize: 10, showSizeChanger: true, showTotal: (t: number) => `共 ${t} 条` }}
          scroll={{ x: 1100 }}
        />
      </Card>
    </>
  );
};

export default RefundHistoryPage;
