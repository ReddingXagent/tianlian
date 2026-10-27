/**
 * 待审核退款 — 审核通过/驳回
 */
import React, { useEffect, useState, useCallback } from 'react';
import {
  Table, Tag, Button, Card, Space, Input, Modal, Form, message,
  Statistic, Row, Col, Popconfirm,
} from 'antd';
import {
  ReloadOutlined, SearchOutlined, CheckOutlined, CloseOutlined,
  ClockCircleOutlined, DollarOutlined,
} from '@ant-design/icons';
import api from '../../../api';
import { getCurrentUser } from '../../../utils/auth';

const { TextArea: AntTextArea } = Input;

/** 从 auth context（登录态）获取当前审核人 ID；后端 login 返回的 id 为字符串，需转数字 */
function getCurrentReviewerId(): number | null {
  const user = getCurrentUser();
  return user?.id != null ? Number(user.id) : null;
}

interface RefundRecord {
  id: number;
  order_id: number;
  user_id: number | null;
  refund_amount: number;
  reason: string;
  status: string | null;
  reviewer_id: number | null;
  reviewed_at: string | null;
  refunded_at: string | null;
  reject_reason: string | null;
  created_at: string | null;
  updated_at: string | null;
}

const REFUND_STATUS_MAP: Record<string, { color: string; text: string }> = {
  pending: { color: 'orange', text: '待审核' },
  approved: { color: 'blue', text: '已批准' },
  rejected: { color: 'red', text: '已驳回' },
  refunded: { color: 'green', text: '已退款' },
};

const PendingRefundsPage: React.FC = () => {
  const [refunds, setRefunds] = useState<RefundRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [keyword, setKeyword] = useState('');
  const [rejectModalOpen, setRejectModalOpen] = useState(false);
  const [currentRefund, setCurrentRefund] = useState<RefundRecord | null>(null);
  const [rejectForm] = Form.useForm();

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      // 获取所有 pending 状态的退款 — 遍历近期订单
      // 由于后端无全局退款列表端点，我们通过订单查询获取
      // 使用 operate/orders 获取近期订单，再查退款记录
      const { data: orderData } = await api.get('/operate/orders', {
        params: { payment_status: 'refunding', page: 1, page_size: 50 },
      });
      const orderItems: any[] = (orderData as any)?.items || [];

      const allRefunds: RefundRecord[] = [];
      await Promise.allSettled(
        orderItems.map(async (order) => {
          try {
            const { data: refundData } = await api.get(`/orders/${order.id}/refunds`);
            const items: any[] = Array.isArray(refundData) ? refundData : [];
            items.forEach(r => {
              if (r.status === 'pending') {
                allRefunds.push({
                  ...r,
                  order_no: order.order_no,
                  station_name: order.station_name,
                  plate_number: order.plate_number,
                  total_amount: order.total_amount,
                  paid_amount: order.paid_amount,
                });
              }
            });
          } catch { /* skip */ }
        })
      );

      setRefunds(allRefunds);
    } catch {
      setRefunds([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const handleApprove = async (record: RefundRecord) => {
    try {
      await api.post(`/orders/${record.order_id}/refunds/${record.id}/approve`, {
        reviewer_id: getCurrentReviewerId(),
      });
      message.success('退款已批准');
      loadData();
    } catch (err: any) {
      message.error('操作失败: ' + (err?.response?.data?.detail || err?.message));
    }
  };

  const handleReject = async () => {
    try {
      const values = await rejectForm.validateFields();
      if (!currentRefund) return;
      await api.post(`/orders/${currentRefund.order_id}/refunds/${currentRefund.id}/reject`, {
        reviewer_id: getCurrentReviewerId(),
        reject_reason: values.reject_reason,
      });
      message.success('退款已驳回');
      setRejectModalOpen(false);
      rejectForm.resetFields();
      setCurrentRefund(null);
      loadData();
    } catch (err: any) {
      if (err?.errorFields) return;
      message.error('操作失败: ' + (err?.response?.data?.detail || err?.message));
    }
  };

  const stats = {
    total: refunds.length,
    totalAmount: refunds.reduce((s, r) => s + (r.refund_amount || 0), 0),
  };

  const filteredRefunds = keyword
    ? refunds.filter(r => String(r.order_id).includes(keyword) || r.reason?.includes(keyword))
    : refunds;

  const columns = [
    { title: '退款ID', dataIndex: 'id', key: 'id', width: 80 },
    { title: '订单号', dataIndex: 'order_no', key: 'order_no', width: 170, render: (v: string) => v ? <Tag color="blue">{v}</Tag> : '-' },
    { title: '站点', dataIndex: 'station_name', key: 'station_name', width: 120, ellipsis: true },
    {
      title: '退款金额', dataIndex: 'refund_amount', key: 'refund_amount', width: 110, align: 'right' as const,
      render: (v: number) => <span style={{ color: '#ea4335', fontWeight: 600 }}>¥{(v || 0).toFixed(2)}</span>,
    },
    { title: '退款原因', dataIndex: 'reason', key: 'reason', ellipsis: true },
    {
      title: '状态', dataIndex: 'status', key: 'status', width: 90,
      render: (v: string | null) => v ? <Tag color={REFUND_STATUS_MAP[v]?.color || 'default'}>{REFUND_STATUS_MAP[v]?.text || v}</Tag> : '-',
    },
    {
      title: '申请时间', dataIndex: 'created_at', key: 'created_at', width: 150,
      render: (v: string | null) => v ? new Date(v).toLocaleString('zh-CN') : '-',
    },
    {
      title: '操作', key: 'action', width: 160,
      render: (_: unknown, record: RefundRecord) => (
        <Space>
          <Popconfirm title="确认批准此退款？" onConfirm={() => handleApprove(record)}>
            <Button size="small" type="primary" icon={<CheckOutlined />}>批准</Button>
          </Popconfirm>
          <Button
            size="small"
            danger
            icon={<CloseOutlined />}
            onClick={() => { setCurrentRefund(record); setRejectModalOpen(true); }}
          >驳回</Button>
        </Space>
      ),
    },
  ];

  return (
    <>
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={12} sm={8}>
          <Card><Statistic title="待审核退款" value={stats.total} prefix={<ClockCircleOutlined />} valueStyle={{ color: '#faad14' }} /></Card>
        </Col>
        <Col xs={12} sm={8}>
          <Card><Statistic title="退款总金额" value={stats.totalAmount} precision={2} prefix={<><DollarOutlined /> ¥</>} valueStyle={{ color: '#ea4335' }} /></Card>
        </Col>
        <Col xs={12} sm={8}>
          <Card><Statistic title="涉及订单" value={new Set(refunds.map(r => r.order_id)).size} /></Card>
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
            <Button icon={<ReloadOutlined />} onClick={loadData}>刷新</Button>
          </Space>
        }
      >
        <Table
          columns={columns}
          dataSource={filteredRefunds}
          rowKey="id"
          loading={loading}
          pagination={{ pageSize: 10, showSizeChanger: true, showTotal: (t: number) => `共 ${t} 条` }}
          scroll={{ x: 1000 }}
        />
      </Card>

      <Modal
        title="驳回退款"
        open={rejectModalOpen}
        onOk={handleReject}
        onCancel={() => { setRejectModalOpen(false); rejectForm.resetFields(); setCurrentRefund(null); }}
        destroyOnHidden
      >
        <Form form={rejectForm} layout="vertical">
          <Form.Item name="reject_reason" label="驳回原因" rules={[{ required: true, message: '请输入驳回原因' }]}>
            <AntTextArea rows={3} placeholder="请输入驳回原因" />
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
};

export default PendingRefundsPage;
