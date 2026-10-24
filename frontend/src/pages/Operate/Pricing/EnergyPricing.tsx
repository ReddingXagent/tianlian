/**
 * 天链 V3 — 充电费定价（尖峰平谷时段+电价 CRUD, 按站点粒度）
 */
import React, { useEffect, useState, useCallback } from 'react';
import {
  Card, Table, Tag, Button, Modal, Form, Input, Select, Space, message,
  Popconfirm, InputNumber, Switch, DatePicker,
} from 'antd';
import {
  PlusOutlined, EditOutlined, DeleteOutlined, ReloadOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import { energyPriceAPI, timeSlotAPI } from '../../../api/pricing';
import { fetchAllPages } from '../../../api/fetchAll';

interface EnergyPriceItem {
  id: number;
  station_id: number;
  slot_id: number;
  price_per_kwh: number;
  effective_date: string;
  expire_date?: string;
  is_active: boolean;
}

interface SlotOption { id: number; name: string; period_type: string }

const EnergyPricing: React.FC = () => {
  const [data, setData] = useState<EnergyPriceItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editingItem, setEditingItem] = useState<EnergyPriceItem | null>(null);
  const [slots, setSlots] = useState<SlotOption[]>([]);
  const [form] = Form.useForm();

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      // 卡 fb183aaf: page_size 恰 100 上限会静默截断 → fetchAllPages 循环拉全量
      const items = await fetchAllPages<EnergyPriceItem>(energyPriceAPI.list);
      setData(items);
    } catch {
      setData([]);
    } finally {
      setLoading(false);
    }
  }, []);

  const loadSlots = useCallback(async () => {
    try {
      // 卡 fb183aaf: page_size 恰 100 上限会静默截断 → fetchAllPages 循环拉全量
      const items = await fetchAllPages<SlotOption>(timeSlotAPI.list, { is_active: true });
      setSlots(items);
    } catch {
      setSlots([]);
    }
  }, []);

  useEffect(() => { loadData(); loadSlots(); }, [loadData, loadSlots]);

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      const payload = {
        ...values,
        effective_date: values.effective_date ? dayjs(values.effective_date).format('YYYY-MM-DD') : undefined,
        expire_date: values.expire_date ? dayjs(values.expire_date).format('YYYY-MM-DD') : undefined,
      };
      if (editingItem) {
        await energyPriceAPI.update(editingItem.id, payload);
        message.success('充电费定价已更新');
      } else {
        await energyPriceAPI.create(payload);
        message.success('充电费定价已创建');
      }
      setModalOpen(false);
      form.resetFields();
      setEditingItem(null);
      loadData();
    } catch (err: any) {
      if (err?.errorFields) return;
      message.error('操作失败：' + (err?.response?.data?.detail || err?.message));
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await energyPriceAPI.delete(id);
      message.success('已删除');
      loadData();
    } catch (err: any) {
      message.error('删除失败');
    }
  };

  const slotName = (slotId: number) => {
    const s = slots.find(x => x.id === slotId);
    return s ? `${s.name}（${s.period_type}）` : `#${slotId}`;
  };

  const columns = [
    { title: 'ID', dataIndex: 'id', key: 'id', width: 60 },
    { title: '站点ID', dataIndex: 'station_id', key: 'station_id', width: 80 },
    {
      title: '时段', dataIndex: 'slot_id', key: 'slot_id', width: 140,
      render: (v: number) => <Tag color="blue">{slotName(v)}</Tag>,
    },
    {
      title: '电价(元/kWh)', dataIndex: 'price_per_kwh', key: 'price_per_kwh', width: 130, align: 'right' as const,
      render: (v: number) => <span style={{ fontWeight: 600, color: '#1890ff' }}>¥ {v?.toFixed(4)}</span>,
    },
    { title: '生效日期', dataIndex: 'effective_date', key: 'effective_date', width: 110 },
    { title: '失效日期', dataIndex: 'expire_date', key: 'expire_date', width: 110, render: (v: string) => v || '-' },
    {
      title: '状态', dataIndex: 'is_active', key: 'is_active', width: 80,
      render: (v: boolean) => <Tag color={v ? 'green' : 'default'}>{v ? '启用' : '停用'}</Tag>,
    },
    {
      title: '操作', key: 'action', width: 140,
      render: (_: unknown, record: EnergyPriceItem) => (
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
            form.setFieldsValue({ is_active: true, price_per_kwh: 0 });
            setModalOpen(true);
          }}>新增电价</Button>
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
        title={editingItem ? '编辑充电费定价' : '新增充电费定价'}
        open={modalOpen}
        onOk={handleSubmit}
        onCancel={() => { setModalOpen(false); form.resetFields(); setEditingItem(null); }}
        width={560}
        destroyOnHidden
      >
        <Form form={form} layout="vertical">
          <Form.Item name="station_id" label="站点ID" rules={[{ required: true, message: '请输入站点ID' }]}>
            <InputNumber style={{ width: '100%' }} min={1} placeholder="站点ID" />
          </Form.Item>
          <Form.Item name="slot_id" label="时段" rules={[{ required: true, message: '请选择时段' }]}>
            <Select placeholder="选择时段" showSearch optionFilterProp="label">
              {slots.map(s => (
                <Select.Option key={s.id} value={s.id} label={`${s.name}（${s.period_type}）`}>
                  {s.name}（{s.period_type}）
                </Select.Option>
              ))}
            </Select>
          </Form.Item>
          <Form.Item name="price_per_kwh" label="电价(元/kWh)" rules={[{ required: true, message: '请输入电价' }]}>
            <InputNumber style={{ width: '100%' }} min={0} step={0.01} precision={4} placeholder="如 1.2000" />
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

export default EnergyPricing;
