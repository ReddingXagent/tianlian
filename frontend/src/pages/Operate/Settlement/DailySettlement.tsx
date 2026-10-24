/**
 * 天链 V3 — 日结汇总页
 */
import React, { useEffect, useState, useCallback } from 'react';
import {
  Card, Table, Tag, Button, Space, DatePicker, message,
  Modal, Form, Input, InputNumber, Select,
} from 'antd';
import { ReloadOutlined, PlusOutlined, CheckCircleOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import { dailySettlementAPI } from '../../../api/settlement';

const { RangePicker } = DatePicker;

const STATUS_MAP: Record<string, { color: string; text: string }> = {
  pending: { color: 'orange', text: '待确认' },
  confirmed: { color: 'green', text: '已确认' },
};

interface DailySettlementItem {
  id: number;
  settlement_date: string;
  station_id: number | null;
  total_orders: number;
  total_energy_kwh: number;
  total_charge_fee: number;
  total_service_fee: number;
  total_parking_fee: number;
  total_occupancy_fee: number;
  total_reservation_fee: number;
  total_amount: number;
  total_paid: number;
  total_discount: number;
  total_refund: number;
  status: string;
  confirmed_at: string | null;
  remark: string | null;
}

const DailySettlementPage: React.FC = () => {
  const [data, setData] = useState<DailySettlementItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [modalOpen, setModalOpen] = useState(false);
  const [form] = Form.useForm();

  const loadData = useCallback(async (p = page) => {
    setLoading(true);
    try {
      const { data: res } = await dailySettlementAPI.list({ page: p, page_size: 20 });
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

  const handleConfirm = async (id: number) => {
    try {
      await dailySettlementAPI.confirm(id);
      message.success('日结已确认');
      loadData();
    } catch {
      message.error('确认失败');
    }
  };

  const handleGenerate = async () => {
    try {
      const vals = await form.validateFields();
      await dailySettlementAPI.generate({
        settlement_date: vals.settlement_date.format('YYYY-MM-DD'),
        total_orders: vals.total_orders,
        total_charge_fee: vals.total_charge_fee,
        total_service_fee: vals.total_service_fee,
        total_amount: vals.total_amount,
        remark: vals.remark,
      });
      message.success('日结记录已生成');
      setModalOpen(false);
      form.resetFields();
      loadData();
    } catch {
      message.error('生成失败');
    }
  };

  const columns = [
    { title: '日期', dataIndex: 'settlement_date', key: 'settlement_date', width: 110 },
    { title: '站点', dataIndex: 'station_id', key: 'station_id', width: 80, render: (v: number | null) => v ? `站点#${v}` : '全平台' },
    { title: '订单数', dataIndex: 'total_orders', key: 'total_orders', width: 70, align: 'right' as const },
    { title: '充电量(kWh)', dataIndex: 'total_energy_kwh', key: 'total_energy_kwh', width: 110, align: 'right' as const, render: (v: number) => v?.toFixed(2) ?? '0.00' },
    { title: '电费', dataIndex: 'total_charge_fee', key: 'total_charge_fee', width: 90, align: 'right' as const, render: (v: number) => `¥${(v ?? 0).toFixed(2)}` },
    { title: '服务费', dataIndex: 'total_service_fee', key: 'total_service_fee', width: 90, align: 'right' as const, render: (v: number) => `¥${(v ?? 0).toFixed(2)}` },
    { title: '应收', dataIndex: 'total_amount', key: 'total_amount', width: 100, align: 'right' as const, render: (v: number) => <span style={{ fontWeight: 600 }}>¥{(v ?? 0).toFixed(2)}</span> },
    { title: '实收', dataIndex: 'total_paid', key: 'total_paid', width: 100, align: 'right' as const, render: (v: number) => <span style={{ color: '#34a853' }}>¥{(v ?? 0).toFixed(2)}</span> },
    { title: '退款', dataIndex: 'total_refund', key: 'total_refund', width: 90, align: 'right' as const, render: (v: number) => v ? <span style={{ color: '#f5222d' }}>¥{v.toFixed(2)}</span> : '-' },
    { title: '状态', dataIndex: 'status', key: 'status', width: 80, render: (v: string) => <Tag color={STATUS_MAP[v]?.color || 'default'}>{STATUS_MAP[v]?.text || v}</Tag> },
    {
      title: '操作', key: 'action', width: 80,
      render: (_: unknown, r: DailySettlementItem) => r.status === 'pending'
        ? <Button size="small" type="link" icon={<CheckCircleOutlined />} onClick={() => handleConfirm(r.id)}>确认</Button>
        : <span style={{ color: '#999', fontSize: 12 }}>{r.confirmed_at ? dayjs(r.confirmed_at).format('MM-DD HH:mm') : ''}</span>,
    },
  ];

  return (
    <div>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between' }}>
        <Space>
          <RangePicker />
          <Select style={{ width: 120 }} placeholder="状态筛选" allowClear
            options={[{ value: 'pending', label: '待确认' }, { value: 'confirmed', label: '已确认' }]}
          />
        </Space>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={() => loadData()}>刷新</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setModalOpen(true)}>生成日结</Button>
        </Space>
      </div>

      <Table
        columns={columns}
        dataSource={data}
        rowKey="id"
        loading={loading}
        size="small"
        pagination={{
          current: page, total, pageSize: 20,
          onChange: (p) => { setPage(p); loadData(p); },
          showTotal: (t) => `共 ${t} 条`,
        }}
      />

      <Modal title="生成日结" open={modalOpen} onOk={handleGenerate} onCancel={() => setModalOpen(false)} destroyOnHidden>
        <Form form={form} layout="vertical">
          <Form.Item name="settlement_date" label="结算日期" rules={[{ required: true }]}>
            <DatePicker style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="total_orders" label="总订单数"><InputNumber style={{ width: '100%' }} /></Form.Item>
          <Form.Item name="total_charge_fee" label="总电费(元)"><InputNumber style={{ width: '100%' }} step={0.01} /></Form.Item>
          <Form.Item name="total_service_fee" label="总服务费(元)"><InputNumber style={{ width: '100%' }} step={0.01} /></Form.Item>
          <Form.Item name="total_amount" label="应收总额(元)"><InputNumber style={{ width: '100%' }} step={0.01} /></Form.Item>
          <Form.Item name="remark" label="备注"><Input.TextArea rows={2} /></Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default DailySettlementPage;
