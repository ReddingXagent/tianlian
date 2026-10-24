/**
 * 天链 V3 — 预约费定价（押金/费率/爽约罚款）
 */
import React, { useEffect, useState, useCallback } from 'react';
import {
  Table, Tag, Button, Modal, Form, Select, Space, message,
  Popconfirm, InputNumber, Switch, DatePicker,
} from 'antd';
import {
  PlusOutlined, EditOutlined, DeleteOutlined, ReloadOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import { reservationFeeAPI } from '../../../api/pricing';
import { fetchAllPages } from '../../../api/fetchAll';

const POLICIES: Record<string, string> = {
  slot_based: '按时段计费',
  flat: '固定费用',
};

interface ReservationItem {
  id: number;
  station_id: number;
  deposit_amount: number;
  reservation_policy: string;
  fee_amount: number;
  no_show_penalty: number;
  effective_date: string;
  expire_date?: string;
  is_active: boolean;
}

const ReservationPricing: React.FC = () => {
  const [data, setData] = useState<ReservationItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editingItem, setEditingItem] = useState<ReservationItem | null>(null);
  const [form] = Form.useForm();

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      // 卡 fb183aaf: page_size 恰 100 上限会静默截断 → fetchAllPages 循环拉全量
      const items = await fetchAllPages<ReservationItem>(reservationFeeAPI.list);
      setData(items);
    } catch {
      setData([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      const payload = {
        ...values,
        effective_date: values.effective_date ? dayjs(values.effective_date).format('YYYY-MM-DD') : undefined,
        expire_date: values.expire_date ? dayjs(values.expire_date).format('YYYY-MM-DD') : undefined,
      };
      if (editingItem) {
        await reservationFeeAPI.update(editingItem.id, payload);
        message.success('预约费定价已更新');
      } else {
        await reservationFeeAPI.create(payload);
        message.success('预约费定价已创建');
      }
      setModalOpen(false);
      form.resetFields();
      setEditingItem(null);
      loadData();
    } catch (err: any) {
      if (err?.errorFields) return;
      message.error('操作失败');
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await reservationFeeAPI.delete(id);
      message.success('已删除');
      loadData();
    } catch {
      message.error('删除失败');
    }
  };

  const columns = [
    { title: 'ID', dataIndex: 'id', key: 'id', width: 60 },
    { title: '站点ID', dataIndex: 'station_id', key: 'station_id', width: 80 },
    {
      title: '押金(元)', dataIndex: 'deposit_amount', key: 'deposit_amount', width: 100, align: 'right' as const,
      render: (v: number) => <span>¥ {v?.toFixed(2)}</span>,
    },
    {
      title: '预约策略', dataIndex: 'reservation_policy', key: 'reservation_policy', width: 120,
      render: (v: string) => <Tag color="geekblue">{POLICIES[v] || v}</Tag>,
    },
    {
      title: '预约费(元)', dataIndex: 'fee_amount', key: 'fee_amount', width: 100, align: 'right' as const,
      render: (v: number) => <span style={{ fontWeight: 600 }}>¥ {v?.toFixed(2)}</span>,
    },
    {
      title: '爽约罚款(元)', dataIndex: 'no_show_penalty', key: 'no_show_penalty', width: 110, align: 'right' as const,
      render: (v: number) => <span style={{ color: '#ea4335' }}>¥ {v?.toFixed(2)}</span>,
    },
    { title: '生效日期', dataIndex: 'effective_date', key: 'effective_date', width: 110 },
    {
      title: '状态', dataIndex: 'is_active', key: 'is_active', width: 80,
      render: (v: boolean) => <Tag color={v ? 'green' : 'default'}>{v ? '启用' : '停用'}</Tag>,
    },
    {
      title: '操作', key: 'action', width: 140,
      render: (_: unknown, record: ReservationItem) => (
        <Space>
          <Button size="small" icon={<EditOutlined />} onClick={() => {
            setEditingItem(record);
            form.setFieldsValue({
              ...record,
              effective_date: record.effective_date ? dayjs(record.effective_date) : undefined,
              expire_date: record.expire_date ? dayjs(record.expire_date) : undefined,
            });
            setModalOpen(true);
          }}>编辑</Button>
          <Popconfirm title="确认删除？" onConfirm={() => handleDelete(record.id)}>
            <Button size="small" danger icon={<DeleteOutlined />}>删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'flex-end' }}>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={loadData}>刷新</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => {
            setEditingItem(null);
            form.resetFields();
            form.setFieldsValue({ is_active: true, deposit_amount: 0, fee_amount: 0, no_show_penalty: 0 });
            setModalOpen(true);
          }}>新增预约费</Button>
        </Space>
      </div>
      <Table
        columns={columns}
        dataSource={data}
        rowKey="id"
        loading={loading}
        pagination={{ pageSize: 10, showSizeChanger: true, showTotal: (t: number) => `共 ${t} 条` }}
      />
      <Modal
        title={editingItem ? '编辑预约费定价' : '新增预约费定价'}
        open={modalOpen}
        onOk={handleSubmit}
        onCancel={() => { setModalOpen(false); form.resetFields(); setEditingItem(null); }}
        width={520}
        destroyOnHidden
      >
        <Form form={form} layout="vertical">
          <Form.Item name="station_id" label="站点ID" rules={[{ required: true, message: '请输入站点ID' }]}>
            <InputNumber style={{ width: '100%' }} min={1} />
          </Form.Item>
          <Form.Item name="reservation_policy" label="预约策略" rules={[{ required: true, message: '请选择预约策略' }]}>
            <Select placeholder="选择预约策略">
              {Object.entries(POLICIES).map(([k, v]) => (
                <Select.Option key={k} value={k}>{v}</Select.Option>
              ))}
            </Select>
          </Form.Item>
          <Form.Item name="deposit_amount" label="押金(元)" initialValue={0}>
            <InputNumber style={{ width: '100%' }} min={0} step={0.01} precision={2} />
          </Form.Item>
          <Form.Item name="fee_amount" label="预约费(元)" initialValue={0}>
            <InputNumber style={{ width: '100%' }} min={0} step={0.01} precision={2} />
          </Form.Item>
          <Form.Item name="no_show_penalty" label="爽约罚款(元)" initialValue={0}>
            <InputNumber style={{ width: '100%' }} min={0} step={0.01} precision={2} />
          </Form.Item>
          <Form.Item name="effective_date" label="生效日期" rules={[{ required: true, message: '请选择生效日期' }]}>
            <DatePicker style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="expire_date" label="失效日期">
            <DatePicker style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="is_active" label="启用" valuePropName="checked" initialValue={true}>
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
};

export default ReservationPricing;
