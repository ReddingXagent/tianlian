/**
 * 天链 V3 — 支付对账页
 */
import React, { useEffect, useState, useCallback } from 'react';
import { Card, Table, Tag, Button, Space, Select, message, Modal, Form, Input, InputNumber } from 'antd';
import { ReloadOutlined, PlusOutlined, CheckCircleOutlined } from '@ant-design/icons';
import { reconciliationAPI } from '../../../api/settlement';

const STATUS_MAP: Record<string, { color: string; text: string }> = {
  pending: { color: 'orange', text: '待对账' },
  reconciled: { color: 'green', text: '已对账' },
};

const CHANNEL_MAP: Record<string, string> = {
  im_b: 'IM-B支付', alipay: '支付宝', unionpay: '银联',
};

interface RecItem {
  id: number;
  settlement_date: string;
  payment_channel: string;
  platform_orders_count: number;
  platform_amount: number;
  payment_orders_count: number;
  payment_amount: number;
  difference_count: number;
  difference_amount: number;
  difference_detail: string | null;
  status: string;
  reconciled_at: string | null;
  reconciled_by: string | null;
}

const ReconciliationPage: React.FC = () => {
  const [data, setData] = useState<RecItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [modalOpen, setModalOpen] = useState(false);
  const [form] = Form.useForm();

  const loadData = useCallback(async (p = page) => {
    setLoading(true);
    try {
      const { data: res } = await reconciliationAPI.list({ page: p, page_size: 20 });
      const d = (res as any)?.data ?? res;
      setData(d?.items ?? []);
      setTotal(d?.total ?? 0);
    } catch {
      setData([]);
    } finally {
      setLoading(false);
    }
  }, [page]);

  useEffect(() => { loadData(); }, [loadData]);

  const handleReconcile = async (id: number) => {
    try {
      await reconciliationAPI.reconcile(id, { operator: '运营员' });
      message.success('对账已完成');
      loadData();
    } catch {
      message.error('操作失败');
    }
  };

  const handleCreate = async () => {
    try {
      const vals = await form.validateFields();
      await reconciliationAPI.create({
        settlement_date: vals.settlement_date.format('YYYY-MM-DD'),
        payment_channel: vals.payment_channel,
        platform_orders_count: vals.platform_orders_count,
        platform_amount: vals.platform_amount,
        payment_orders_count: vals.payment_orders_count,
        payment_amount: vals.payment_amount,
        difference_count: vals.difference_count,
        difference_amount: vals.difference_amount,
      });
      message.success('对账记录已创建');
      setModalOpen(false);
      form.resetFields();
      loadData();
    } catch {
      message.error('创建失败');
    }
  };

  const columns = [
    { title: '日期', dataIndex: 'settlement_date', key: 'settlement_date', width: 110 },
    { title: '渠道', dataIndex: 'payment_channel', key: 'payment_channel', width: 90, render: (v: string) => CHANNEL_MAP[v] || v },
    { title: '平台订单', dataIndex: 'platform_orders_count', key: 'platform_orders_count', width: 80, align: 'right' as const },
    { title: '平台金额', dataIndex: 'platform_amount', key: 'platform_amount', width: 100, align: 'right' as const, render: (v: number) => `¥${(v ?? 0).toFixed(2)}` },
    { title: '渠道订单', dataIndex: 'payment_orders_count', key: 'payment_orders_count', width: 80, align: 'right' as const },
    { title: '渠道金额', dataIndex: 'payment_amount', key: 'payment_amount', width: 100, align: 'right' as const, render: (v: number) => `¥${(v ?? 0).toFixed(2)}` },
    { title: '差异数', dataIndex: 'difference_count', key: 'difference_count', width: 70, align: 'right' as const, render: (v: number) => v ? <span style={{ color: '#f5222d' }}>{v}</span> : '0' },
    { title: '差异额', dataIndex: 'difference_amount', key: 'difference_amount', width: 90, align: 'right' as const, render: (v: number) => v ? <span style={{ color: '#f5222d' }}>¥{v.toFixed(2)}</span> : '-' },
    { title: '状态', dataIndex: 'status', key: 'status', width: 80, render: (v: string) => <Tag color={STATUS_MAP[v]?.color || 'default'}>{STATUS_MAP[v]?.text || v}</Tag> },
    {
      title: '操作', key: 'action', width: 80,
      render: (_: unknown, r: RecItem) => r.status === 'pending'
        ? <Button size="small" type="link" onClick={() => handleReconcile(r.id)}>对账</Button>
        : <span style={{ color: '#999', fontSize: 12 }}>{r.reconciled_by ?? ''}</span>,
    },
  ];

  return (
    <div>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between' }}>
        <Space>
          <Select style={{ width: 140 }} placeholder="支付渠道" allowClear
            options={[{ value: 'im_b', label: 'IM-B支付' }, { value: 'alipay', label: '支付宝' }, { value: 'unionpay', label: '银联' }]}
          />
          <Select style={{ width: 120 }} placeholder="状态" allowClear
            options={[{ value: 'pending', label: '待对账' }, { value: 'reconciled', label: '已对账' }]}
          />
        </Space>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={() => loadData()}>刷新</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setModalOpen(true)}>新增对账</Button>
        </Space>
      </div>

      <Table columns={columns} dataSource={data} rowKey="id" loading={loading} size="small"
        pagination={{ current: page, total, pageSize: 20, onChange: (p) => { setPage(p); loadData(p); } }}
      />

      <Modal title="新增对账记录" open={modalOpen} onOk={handleCreate} onCancel={() => setModalOpen(false)} destroyOnHidden>
        <Form form={form} layout="vertical">
          <Form.Item name="settlement_date" label="对账日期" rules={[{ required: true }]}>
            <Input type="date" style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="payment_channel" label="支付渠道" rules={[{ required: true }]}>
            <Select options={[{ value: 'im_b', label: 'IM-B支付' }, { value: 'alipay', label: '支付宝' }, { value: 'unionpay', label: '银联' }]} />
          </Form.Item>
          <Form.Item name="platform_orders_count" label="平台订单数"><InputNumber style={{ width: '100%' }} /></Form.Item>
          <Form.Item name="platform_amount" label="平台流水金额"><InputNumber style={{ width: '100%' }} step={0.01} /></Form.Item>
          <Form.Item name="payment_orders_count" label="渠道订单数"><InputNumber style={{ width: '100%' }} /></Form.Item>
          <Form.Item name="payment_amount" label="渠道流水金额"><InputNumber style={{ width: '100%' }} step={0.01} /></Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default ReconciliationPage;
