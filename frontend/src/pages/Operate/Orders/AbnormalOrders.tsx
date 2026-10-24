/**
 * 异常订单 — 故障中断/离线补传/对账不平
 *
 * 操作闭环 (卡 f730f63c):
 * - 详情: 复用 OrderDetailDrawer (含充电曲线 + 5项费用明细)
 * - 重试计费: 仅 failed 订单, 调 retry-charge 重算账单
 * - 标记处理: refunded/written_off/false_alarm + 备注
 * - 转退款: 已付款(paid_amount>0)单, 调 refunds 模块创建退款申请
 * 已处理单(abnormal_handle_type 非空)仅显示详情 + "已处理" Tag。
 */
import React, { useEffect, useState, useCallback } from 'react';
import {
  Table, Tag, Button, Card, Space, Input, Statistic, Row, Col,
  Modal, Form, Select, InputNumber, message, Popconfirm,
} from 'antd';
import {
  ReloadOutlined, SearchOutlined, WarningOutlined,
  ThunderboltOutlined, DisconnectOutlined, EyeOutlined,
  RedoOutlined, CheckCircleOutlined, TransactionOutlined,
} from '@ant-design/icons';
import { operateOrderAPI, refundAPI } from '../../../api/operate';
import OrderDetailDrawer from './OrderDetail';

const { TextArea } = Input;

interface OrderRow {
  id: number;
  order_no: string;
  station_name: string;
  plate_number: string;
  user_type: string | null;
  charged_kwh: number;
  total_amount: number;
  paid_amount: number;
  discount_amount: number;
  order_status: string | null;
  payment_status: string | null;
  payment_method: string | null;
  duration_minutes: number;
  abnormal_handle_type: string | null;
  created_at: string | null;
}

const ABNORMAL_STATUS_MAP: Record<string, { color: string; text: string; icon: React.ReactNode }> = {
  failed: { color: 'red', text: '故障中断', icon: <ThunderboltOutlined /> },
  cancelled: { color: 'orange', text: '异常取消', icon: <DisconnectOutlined /> },
};

const HANDLE_TYPE_OPTIONS = [
  { value: 'refunded', label: '已退款' },
  { value: 'written_off', label: '核销' },
  { value: 'false_alarm', label: '误报' },
];

const HANDLE_TYPE_LABEL: Record<string, string> = {
  refunded: '已退款',
  written_off: '核销',
  false_alarm: '误报',
};

const AbnormalOrdersPage: React.FC = () => {
  const [orders, setOrders] = useState<OrderRow[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [keyword, setKeyword] = useState('');

  // 详情抽屉
  const [detailOpen, setDetailOpen] = useState(false);
  const [detailOrder, setDetailOrder] = useState<OrderRow | null>(null);

  // 标记处理 Modal
  const [resolveOpen, setResolveOpen] = useState(false);
  const [resolveTarget, setResolveTarget] = useState<OrderRow | null>(null);
  const [resolveSubmitting, setResolveSubmitting] = useState(false);
  const [resolveForm] = Form.useForm();

  // 转退款 Modal
  const [refundOpen, setRefundOpen] = useState(false);
  const [refundTarget, setRefundTarget] = useState<OrderRow | null>(null);
  const [refundSubmitting, setRefundSubmitting] = useState(false);
  const [refundForm] = Form.useForm();

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      // 拉取失败和取消的订单
      const params: Record<string, unknown> = { page, page_size: pageSize };
      if (keyword) params.keyword = keyword;

      const [failedRes, cancelledRes] = await Promise.allSettled([
        operateOrderAPI.list({ ...params, status: 'failed' }),
        operateOrderAPI.list({ ...params, status: 'cancelled' }),
      ]);

      const items: OrderRow[] = [];
      if (failedRes.status === 'fulfilled') {
        const d = (failedRes.value.data as any);
        items.push(...(d?.items || []));
      }
      if (cancelledRes.status === 'fulfilled') {
        const d = (cancelledRes.value.data as any);
        items.push(...(d?.items || []));
      }

      setOrders(items);
      setTotal(items.length);
    } catch {
      setOrders([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, keyword]);

  useEffect(() => { loadData(); }, [loadData]);

  // ─── 操作处理 ───

  const openDetail = (record: OrderRow) => {
    setDetailOrder(record);
    setDetailOpen(true);
  };

  const handleRetry = async (record: OrderRow) => {
    try {
      await operateOrderAPI.retryCharge(record.id);
      message.success('重试计费完成');
      loadData();
    } catch (err: any) {
      message.error('重试计费失败: ' + (err?.response?.data?.detail || err?.message));
    }
  };

  const openResolve = (record: OrderRow) => {
    setResolveTarget(record);
    resolveForm.resetFields();
    setResolveOpen(true);
  };

  const handleResolveSubmit = async () => {
    try {
      const values = await resolveForm.validateFields();
      if (!resolveTarget) return;
      setResolveSubmitting(true);
      await operateOrderAPI.resolve(resolveTarget.id, {
        handle_type: values.handle_type,
        remark: values.remark,
      });
      message.success('已标记处理');
      setResolveOpen(false);
      loadData();
    } catch (err: any) {
      if (err?.errorFields) return; // 表单校验失败, 不提示
      message.error('标记失败: ' + (err?.response?.data?.detail || err?.message));
    } finally {
      setResolveSubmitting(false);
    }
  };

  const openRefund = (record: OrderRow) => {
    setRefundTarget(record);
    refundForm.resetFields();
    // 预填退款金额 = 实付金额
    refundForm.setFieldsValue({ refund_amount: record.paid_amount });
    setRefundOpen(true);
  };

  const handleRefundSubmit = async () => {
    try {
      const values = await refundForm.validateFields();
      if (!refundTarget) return;
      setRefundSubmitting(true);
      await refundAPI.create(refundTarget.id, {
        refund_amount: values.refund_amount,
        reason: values.reason,
      });
      message.success('退款申请已提交, 请到「退款」Tab 审核');
      setRefundOpen(false);
      loadData();
    } catch (err: any) {
      if (err?.errorFields) return;
      message.error('提交退款失败: ' + (err?.response?.data?.detail || err?.message));
    } finally {
      setRefundSubmitting(false);
    }
  };

  const stats = {
    total: orders.length,
    failed: orders.filter(o => o.order_status === 'failed').length,
    cancelled: orders.filter(o => o.order_status === 'cancelled').length,
    totalLoss: orders.reduce((s, o) => s + (o.total_amount || 0), 0),
  };

  const columns = [
    {
      title: '订单号', dataIndex: 'order_no', key: 'order_no', width: 170,
      render: (v: string) => <Tag color="red">{v}</Tag>,
    },
    { title: '站点', dataIndex: 'station_name', key: 'station_name', width: 130, ellipsis: true },
    { title: '车牌号', dataIndex: 'plate_number', key: 'plate_number', width: 100 },
    {
      title: '异常类型', dataIndex: 'order_status', key: 'order_status', width: 110,
      render: (v: string | null, record: OrderRow) => {
        if (!v) return '-';
        const meta = ABNORMAL_STATUS_MAP[v];
        return (
          <Space size={4}>
            <Tag color={meta?.color || 'default'}>
              {meta?.icon} {meta?.text || v}
            </Tag>
            {record.abnormal_handle_type && (
              <Tag color="green" icon={<CheckCircleOutlined />}>
                {HANDLE_TYPE_LABEL[record.abnormal_handle_type] || record.abnormal_handle_type}
              </Tag>
            )}
          </Space>
        );
      },
    },
    {
      title: '充电量', dataIndex: 'charged_kwh', key: 'charged_kwh', width: 90, align: 'right' as const,
      render: (v: number) => v ? `${v.toFixed(2)} kWh` : '-',
    },
    {
      title: '涉及金额', dataIndex: 'total_amount', key: 'total_amount', width: 110, align: 'right' as const,
      render: (v: number) => <span style={{ color: '#ea4335', fontWeight: 600 }}>¥{(v || 0).toFixed(2)}</span>,
    },
    {
      title: '已付', dataIndex: 'paid_amount', key: 'paid_amount', width: 100, align: 'right' as const,
      render: (v: number) => v > 0 ? <span style={{ color: '#34a853' }}>¥{v.toFixed(2)}</span> : <Tag>未付款</Tag>,
    },
    {
      title: '充电时长', dataIndex: 'duration_minutes', key: 'duration_minutes', width: 90,
      render: (v: number) => v ? `${v} 分钟` : '-',
    },
    {
      title: '创建时间', dataIndex: 'created_at', key: 'created_at', width: 150,
      render: (v: string | null) => v ? new Date(v).toLocaleString('zh-CN') : '-',
    },
    {
      title: '操作', key: 'action', width: 240, fixed: 'right' as const,
      render: (_: unknown, record: OrderRow) => {
        const handled = !!record.abnormal_handle_type;
        const isFailed = record.order_status === 'failed';
        const canRefund = (record.paid_amount || 0) > 0;
        return (
          <Space size="small" wrap>
            <Button size="small" icon={<EyeOutlined />} onClick={() => openDetail(record)}>详情</Button>
            {handled ? null : (
              <>
                {isFailed && (
                  <Popconfirm title="确认对该故障订单重试计费？" onConfirm={() => handleRetry(record)}>
                    <Button size="small" type="primary" ghost icon={<RedoOutlined />}>重试计费</Button>
                  </Popconfirm>
                )}
                <Button size="small" onClick={() => openResolve(record)}>标记处理</Button>
                {canRefund && (
                  <Button size="small" danger ghost icon={<TransactionOutlined />} onClick={() => openRefund(record)}>转退款</Button>
                )}
              </>
            )}
          </Space>
        );
      },
    },
  ];

  return (
    <>
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={12} sm={6}>
          <Card><Statistic title="异常订单总数" value={stats.total} prefix={<WarningOutlined />} valueStyle={{ color: '#ea4335' }} /></Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card><Statistic title="故障中断" value={stats.failed} prefix={<ThunderboltOutlined />} valueStyle={{ color: '#ff4d4f' }} /></Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card><Statistic title="异常取消" value={stats.cancelled} prefix={<DisconnectOutlined />} valueStyle={{ color: '#faad14' }} /></Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card><Statistic title="涉及金额" value={stats.totalLoss} precision={2} prefix="¥" valueStyle={{ color: '#ea4335' }} /></Card>
        </Col>
      </Row>

      <Card
        extra={
          <Space>
            <Input
              placeholder="搜索订单号/车牌号"
              prefix={<SearchOutlined />}
              value={keyword}
              onChange={e => setKeyword(e.target.value)}
              onPressEnter={() => { setPage(1); loadData(); }}
              style={{ width: 200 }}
              allowClear
            />
            <Button icon={<ReloadOutlined />} onClick={() => { setPage(1); loadData(); }}>刷新</Button>
          </Space>
        }
      >
        <Table
          columns={columns}
          dataSource={orders}
          rowKey="id"
          loading={loading}
          pagination={{
            current: page,
            pageSize,
            total,
            showSizeChanger: true,
            showTotal: (t: number) => `共 ${t} 条`,
            onChange: (p: number, ps: number) => { setPage(p); setPageSize(ps); },
          }}
          scroll={{ x: 1200 }}
        />
      </Card>

      {/* 详情抽屉 — 复用 OrderDetail(含充电曲线 + 5项费用明细) */}
      <OrderDetailDrawer open={detailOpen} order={detailOrder} onClose={() => setDetailOpen(false)} />

      {/* 标记处理 Modal */}
      <Modal
        title={`标记处理 - ${resolveTarget?.order_no || ''}`}
        open={resolveOpen}
        onOk={handleResolveSubmit}
        confirmLoading={resolveSubmitting}
        onCancel={() => setResolveOpen(false)}
        destroyOnHidden
      >
        <Form form={resolveForm} layout="vertical">
          <Form.Item
            name="handle_type"
            label="处理类型"
            rules={[{ required: true, message: '请选择处理类型' }]}
          >
            <Select options={HANDLE_TYPE_OPTIONS} placeholder="选择处理类型" />
          </Form.Item>
          <Form.Item name="remark" label="处理备注">
            <TextArea rows={3} placeholder="可选: 处理说明" maxLength={500} showCount />
          </Form.Item>
        </Form>
      </Modal>

      {/* 转退款 Modal — 预填实付金额, 调 refunds 模块 */}
      <Modal
        title={`转退款 - ${refundTarget?.order_no || ''}`}
        open={refundOpen}
        onOk={handleRefundSubmit}
        confirmLoading={refundSubmitting}
        onCancel={() => setRefundOpen(false)}
        destroyOnHidden
      >
        <Form form={refundForm} layout="vertical">
          <Form.Item
            name="refund_amount"
            label="退款金额(元)"
            rules={[
              { required: true, message: '请输入退款金额' },
              { type: 'number', min: 0.01, message: '退款金额须大于 0' },
            ]}
          >
            <InputNumber style={{ width: '100%' }} precision={2} min={0.01} max={refundTarget?.paid_amount} />
          </Form.Item>
          <Form.Item
            name="reason"
            label="退款原因"
            rules={[{ required: true, message: '请输入退款原因' }, { max: 500 }]}
          >
            <TextArea rows={3} placeholder="退款原因(提交后到「退款」Tab 审核)" maxLength={500} showCount />
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
};

export default AbnormalOrdersPage;
