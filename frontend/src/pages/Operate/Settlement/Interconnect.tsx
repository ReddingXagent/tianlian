/**
 * 天链 V3 — 互联互通结算页
 */
import React, { useEffect, useState, useCallback } from 'react';
import { Table, Tag, Button, Space, Select, Modal, Form, Input, InputNumber, message } from 'antd';
import { ReloadOutlined, PlusOutlined } from '@ant-design/icons';
import { interconnectAPI } from '../../../api/settlement';

const STATUS_MAP: Record<string, { color: string; text: string }> = {
  pending: { color: 'orange', text: '待结算' },
  settled: { color: 'green', text: '已结算' },
};

interface ICItem {
  id: number;
  platform_id: string;
  platform_name: string | null;
  start_date: string;
  end_date: string;
  total_orders: number;
  total_energy_kwh: number;
  total_amount: number;
  revenue_share_ratio: number;
  our_revenue: number;
  partner_revenue: number;
  settlement_amount: number;
  status: string;
  settled_at: string | null;
}

const InterconnectPage: React.FC = () => {
  const [data, setData] = useState<ICItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [modalOpen, setModalOpen] = useState(false);
  const [form] = Form.useForm();

  const loadData = useCallback(async (p = page) => {
    setLoading(true);
    try {
      const { data: res } = await interconnectAPI.list({ page: p, page_size: 20 });
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

  const handleSettle = async (id: number) => {
    try {
      await interconnectAPI.settle(id, { operator: '运营员' });
      message.success('结算已完成');
      loadData();
    } catch {
      message.error('操作失败');
    }
  };

  const handleCreate = async () => {
    try {
      const vals = await form.validateFields();
      await interconnectAPI.create({
        platform_id: vals.platform_id,
        platform_name: vals.platform_name,
        start_date: vals.start_date?.format?.('YYYY-MM-DD') || vals.start_date,
        end_date: vals.end_date?.format?.('YYYY-MM-DD') || vals.end_date,
        total_orders: vals.total_orders,
        total_amount: vals.total_amount,
        revenue_share_ratio: vals.revenue_share_ratio,
      });
      message.success('结算记录已创建');
      setModalOpen(false);
      form.resetFields();
      loadData();
    } catch {
      message.error('创建失败');
    }
  };

  const columns = [
    { title: '平台', dataIndex: 'platform_name', key: 'platform_name', width: 120, render: (v: string, r: ICItem) => v || r.platform_id },
    { title: '周期', key: 'period', width: 180, render: (_: unknown, r: ICItem) => `${r.start_date} ~ ${r.end_date}` },
    { title: '订单数', dataIndex: 'total_orders', key: 'total_orders', width: 70, align: 'right' as const },
    { title: '总金额', dataIndex: 'total_amount', key: 'total_amount', width: 100, align: 'right' as const, render: (v: number) => `¥${(v ?? 0).toFixed(2)}` },
    { title: '分成比', dataIndex: 'revenue_share_ratio', key: 'revenue_share_ratio', width: 70, align: 'right' as const, render: (v: number) => `${(v * 100).toFixed(1)}%` },
    { title: '我方收入', dataIndex: 'our_revenue', key: 'our_revenue', width: 100, align: 'right' as const, render: (v: number) => <span style={{ color: '#34a853', fontWeight: 600 }}>¥{(v ?? 0).toFixed(2)}</span> },
    { title: '合作方', dataIndex: 'partner_revenue', key: 'partner_revenue', width: 90, align: 'right' as const, render: (v: number) => `¥${(v ?? 0).toFixed(2)}` },
    { title: '状态', dataIndex: 'status', key: 'status', width: 80, render: (v: string) => <Tag color={STATUS_MAP[v]?.color || 'default'}>{STATUS_MAP[v]?.text || v}</Tag> },
    {
      title: '操作', key: 'action', width: 70,
      render: (_: unknown, r: ICItem) => r.status === 'pending'
        ? <Button size="small" type="link" onClick={() => handleSettle(r.id)}>结算</Button>
        : <span style={{ color: '#999', fontSize: 12 }}>已结算</span>,
    },
  ];

  return (
    <div>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between' }}>
        <Space>
          <Select style={{ width: 140 }} placeholder="平台筛选" allowClear />
          <Select style={{ width: 120 }} placeholder="状态" allowClear options={[{ value: 'pending', label: '待结算' }, { value: 'settled', label: '已结算' }]} />
        </Space>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={() => loadData()}>刷新</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setModalOpen(true)}>新增结算</Button>
        </Space>
      </div>

      <Table columns={columns} dataSource={data} rowKey="id" loading={loading} size="small"
        pagination={{ current: page, total, pageSize: 20, onChange: (p) => { setPage(p); loadData(p); } }}
      />

      <Modal title="新增互联互通结算" open={modalOpen} onOk={handleCreate} onCancel={() => setModalOpen(false)} destroyOnHidden width={520}>
        <Form form={form} layout="vertical">
          <Form.Item name="platform_id" label="平台标识" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="platform_name" label="平台名称"><Input /></Form.Item>
          <Space.Compact style={{ width: '100%' }}>
            <Form.Item name="start_date" label="开始日期" rules={[{ required: true }]} style={{ width: '50%', paddingRight: 8 }}>
              <Input type="date" />
            </Form.Item>
            <Form.Item name="end_date" label="结束日期" rules={[{ required: true }]} style={{ width: '50%' }}>
              <Input type="date" />
            </Form.Item>
          </Space.Compact>
          <Form.Item name="total_orders" label="订单数"><InputNumber style={{ width: '100%' }} /></Form.Item>
          <Form.Item name="total_amount" label="总金额"><InputNumber style={{ width: '100%' }} step={0.01} /></Form.Item>
          <Form.Item name="revenue_share_ratio" label="分成比例(如0.7=70%)"><InputNumber style={{ width: '100%' }} step={0.01} min={0} max={1} /></Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default InterconnectPage;
