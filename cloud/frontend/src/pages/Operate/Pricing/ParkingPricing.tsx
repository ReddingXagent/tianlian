/**
 * 天链 V3 — 停车费定价（免费时长/小时费率/封顶/夜间费率）
 */
import React, { useEffect, useState, useCallback } from 'react';
import {
  Table, Tag, Button, Modal, Form, Input, Select, Space, message,
  Popconfirm, InputNumber, Switch, DatePicker,
} from 'antd';
import {
  PlusOutlined, EditOutlined, DeleteOutlined, ReloadOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import { parkingPriceAPI } from '../../../api/pricing';
import { fetchAllPages } from '../../../api/fetchAll';

interface ParkingItem {
  id: number;
  station_id: number;
  free_minutes: number;
  hourly_rate: number;
  daily_cap?: number;
  enable_night_rate: boolean;
  night_rate?: number;
  night_start?: string;
  night_end?: string;
  effective_date: string;
  expire_date?: string;
  is_active: boolean;
}

const ParkingPricing: React.FC = () => {
  const [data, setData] = useState<ParkingItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editingItem, setEditingItem] = useState<ParkingItem | null>(null);
  const [form] = Form.useForm();

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      // 卡 fb183aaf: page_size 恰 100 上限会静默截断 → fetchAllPages 循环拉全量
      const items = await fetchAllPages<ParkingItem>(parkingPriceAPI.list);
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
        await parkingPriceAPI.update(editingItem.id, payload);
        message.success('停车费定价已更新');
      } else {
        await parkingPriceAPI.create(payload);
        message.success('停车费定价已创建');
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
      await parkingPriceAPI.delete(id);
      message.success('已删除');
      loadData();
    } catch {
      message.error('删除失败');
    }
  };

  const columns = [
    { title: 'ID', dataIndex: 'id', key: 'id', width: 60 },
    { title: '站点ID', dataIndex: 'station_id', key: 'station_id', width: 80 },
    { title: '免费(分)', dataIndex: 'free_minutes', key: 'free_minutes', width: 90, align: 'right' as const },
    {
      title: '小时费率', dataIndex: 'hourly_rate', key: 'hourly_rate', width: 100, align: 'right' as const,
      render: (v: number) => <span style={{ fontWeight: 600 }}>¥ {v?.toFixed(2)}/h</span>,
    },
    {
      title: '日封顶', dataIndex: 'daily_cap', key: 'daily_cap', width: 100, align: 'right' as const,
      render: (v: number) => v != null ? `¥ ${v.toFixed(2)}` : '-',
    },
    {
      title: '夜间费率', key: 'night', width: 140,
      render: (_: unknown, r: ParkingItem) =>
        r.enable_night_rate ? (
          <span>¥ {r.night_rate?.toFixed(2) || 0} <span style={{ color: '#999', fontSize: 12 }}>({r.night_start || '?'}~{r.night_end || '?'})</span></span>
        ) : <Tag>未启用</Tag>,
    },
    { title: '生效日期', dataIndex: 'effective_date', key: 'effective_date', width: 110 },
    {
      title: '状态', dataIndex: 'is_active', key: 'is_active', width: 80,
      render: (v: boolean) => <Tag color={v ? 'green' : 'default'}>{v ? '启用' : '停用'}</Tag>,
    },
    {
      title: '操作', key: 'action', width: 140,
      render: (_: unknown, record: ParkingItem) => (
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
            form.setFieldsValue({ is_active: true, free_minutes: 0, enable_night_rate: false });
            setModalOpen(true);
          }}>新增停车费</Button>
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
        title={editingItem ? '编辑停车费定价' : '新增停车费定价'}
        open={modalOpen}
        onOk={handleSubmit}
        onCancel={() => { setModalOpen(false); form.resetFields(); setEditingItem(null); }}
        width={600}
        destroyOnHidden
      >
        <Form form={form} layout="vertical">
          <Form.Item name="station_id" label="站点ID" rules={[{ required: true, message: '请输入站点ID' }]}>
            <InputNumber style={{ width: '100%' }} min={1} />
          </Form.Item>
          <Form.Item name="free_minutes" label="免费时长(分钟)" initialValue={0}>
            <InputNumber style={{ width: '100%' }} min={0} />
          </Form.Item>
          <Form.Item name="hourly_rate" label="小时费率(元/h)" rules={[{ required: true, message: '请输入小时费率' }]}>
            <InputNumber style={{ width: '100%' }} min={0} step={0.5} precision={2} />
          </Form.Item>
          <Form.Item name="daily_cap" label="日封顶(元)">
            <InputNumber style={{ width: '100%' }} min={0} precision={2} placeholder="可选" />
          </Form.Item>
          <Form.Item name="enable_night_rate" label="启用夜间费率" valuePropName="checked" initialValue={false}>
            <Switch />
          </Form.Item>
          <Form.Item name="night_rate" label="夜间费率(元/h)">
            <InputNumber style={{ width: '100%' }} min={0} step={0.5} precision={2} placeholder="启用夜间时填写" />
          </Form.Item>
          <Form.Item name="night_start" label="夜间开始">
            <Input placeholder="HH:MM 如 22:00" />
          </Form.Item>
          <Form.Item name="night_end" label="夜间结束">
            <Input placeholder="HH:MM 如 06:00" />
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

export default ParkingPricing;
