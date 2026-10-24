/**
 * 天链 V3 — 占桩费定价（免罚时长/罚金费率/封顶）
 */
import React, { useEffect, useState, useCallback } from 'react';
import {
  Table, Tag, Button, Modal, Form, Space, message,
  Popconfirm, InputNumber, Switch, DatePicker,
} from 'antd';
import {
  PlusOutlined, EditOutlined, DeleteOutlined, ReloadOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import { occupancyFeeAPI } from '../../../api/pricing';
import { fetchAllPages } from '../../../api/fetchAll';

interface OccupancyItem {
  id: number;
  station_id: number;
  grace_minutes: number;
  rate_per_minute: number;
  max_fee?: number;
  effective_date: string;
  expire_date?: string;
  is_active: boolean;
}

const OccupancyPricing: React.FC = () => {
  const [data, setData] = useState<OccupancyItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editingItem, setEditingItem] = useState<OccupancyItem | null>(null);
  const [form] = Form.useForm();

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      // 卡 fb183aaf: page_size 恰 100 上限会静默截断 → fetchAllPages 循环拉全量
      const items = await fetchAllPages<OccupancyItem>(occupancyFeeAPI.list);
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
        await occupancyFeeAPI.update(editingItem.id, payload);
        message.success('占桩费定价已更新');
      } else {
        await occupancyFeeAPI.create(payload);
        message.success('占桩费定价已创建');
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
      await occupancyFeeAPI.delete(id);
      message.success('已删除');
      loadData();
    } catch {
      message.error('删除失败');
    }
  };

  const columns = [
    { title: 'ID', dataIndex: 'id', key: 'id', width: 60 },
    { title: '站点ID', dataIndex: 'station_id', key: 'station_id', width: 80 },
    { title: '免罚(分)', dataIndex: 'grace_minutes', key: 'grace_minutes', width: 90, align: 'right' as const },
    {
      title: '罚金费率(元/分)', dataIndex: 'rate_per_minute', key: 'rate_per_minute', width: 130, align: 'right' as const,
      render: (v: number) => <span style={{ fontWeight: 600, color: '#faad14' }}>¥ {v?.toFixed(4)}</span>,
    },
    {
      title: '封顶(元)', dataIndex: 'max_fee', key: 'max_fee', width: 100, align: 'right' as const,
      render: (v: number) => v != null ? `¥ ${v.toFixed(2)}` : '-',
    },
    { title: '生效日期', dataIndex: 'effective_date', key: 'effective_date', width: 110 },
    { title: '失效日期', dataIndex: 'expire_date', key: 'expire_date', width: 110, render: (v: string) => v || '-' },
    {
      title: '状态', dataIndex: 'is_active', key: 'is_active', width: 80,
      render: (v: boolean) => <Tag color={v ? 'green' : 'default'}>{v ? '启用' : '停用'}</Tag>,
    },
    {
      title: '操作', key: 'action', width: 140,
      render: (_: unknown, record: OccupancyItem) => (
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
            form.setFieldsValue({ is_active: true, grace_minutes: 15, rate_per_minute: 0 });
            setModalOpen(true);
          }}>新增占桩费</Button>
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
        title={editingItem ? '编辑占桩费定价' : '新增占桩费定价'}
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
          <Form.Item name="grace_minutes" label="免罚时长(分钟)" initialValue={15}>
            <InputNumber style={{ width: '100%' }} min={0} />
          </Form.Item>
          <Form.Item name="rate_per_minute" label="罚金费率(元/分钟)" rules={[{ required: true, message: '请输入罚金费率' }]}>
            <InputNumber style={{ width: '100%' }} min={0} step={0.01} precision={4} />
          </Form.Item>
          <Form.Item name="max_fee" label="封顶金额(元)">
            <InputNumber style={{ width: '100%' }} min={0} precision={2} placeholder="可选" />
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

export default OccupancyPricing;
