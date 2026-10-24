/**
 * 天链 V3 — 时段定义管理（尖/峰/平/谷模板 CRUD）
 */
import React, { useEffect, useState, useCallback } from 'react';
import {
  Card, Table, Tag, Button, Modal, Form, Input, Select, Space, message,
  Popconfirm, InputNumber, Switch,
} from 'antd';
import {
  PlusOutlined, EditOutlined, DeleteOutlined, ReloadOutlined,
} from '@ant-design/icons';
import { timeSlotAPI } from '../../../api/pricing';
import { fetchAllPages } from '../../../api/fetchAll';

/* ── 常量 ── */
const PERIOD_TYPES: Record<string, { label: string; color: string }> = {
  peak: { label: '尖', color: 'red' },
  sharp: { label: '峰', color: 'orange' },
  flat: { label: '平', color: 'blue' },
  valley: { label: '谷', color: 'green' },
};

interface TimeSlot {
  id: number;
  name: string;
  period_type: string;
  start_time: string;
  end_time: string;
  description?: string;
  is_active: boolean;
  sort_order: number;
  created_at?: string;
}

const TimeSlotDefinitions: React.FC = () => {
  const [data, setData] = useState<TimeSlot[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editingItem, setEditingItem] = useState<TimeSlot | null>(null);
  const [form] = Form.useForm();

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      // 卡 fb183aaf: page_size 恰 100 上限会静默截断 → fetchAllPages 循环拉全量
      const items = await fetchAllPages<TimeSlot>(timeSlotAPI.list);
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
      if (editingItem) {
        await timeSlotAPI.update(editingItem.id, values);
        message.success('时段定义已更新');
      } else {
        await timeSlotAPI.create(values);
        message.success('时段定义已创建');
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
      await timeSlotAPI.delete(id);
      message.success('已删除');
      loadData();
    } catch (err: any) {
      message.error('删除失败：' + (err?.response?.data?.detail || err?.message));
    }
  };

  const columns = [
    { title: '名称', dataIndex: 'name', key: 'name', width: 140 },
    {
      title: '时段类型', dataIndex: 'period_type', key: 'period_type', width: 100,
      render: (v: string) => {
        const pt = PERIOD_TYPES[v];
        return pt ? <Tag color={pt.color}>{pt.label}</Tag> : <Tag>{v}</Tag>;
      },
    },
    { title: '开始时间', dataIndex: 'start_time', key: 'start_time', width: 100 },
    { title: '结束时间', dataIndex: 'end_time', key: 'end_time', width: 100 },
    { title: '排序', dataIndex: 'sort_order', key: 'sort_order', width: 60, align: 'right' as const },
    {
      title: '状态', dataIndex: 'is_active', key: 'is_active', width: 80,
      render: (v: boolean) => <Tag color={v ? 'green' : 'default'}>{v ? '启用' : '停用'}</Tag>,
    },
    { title: '描述', dataIndex: 'description', key: 'description', ellipsis: true },
    {
      title: '操作', key: 'action', width: 140,
      render: (_: unknown, record: TimeSlot) => (
        <Space>
          <Button size="small" icon={<EditOutlined />} onClick={() => {
            setEditingItem(record);
            form.setFieldsValue(record);
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
            form.setFieldsValue({ is_active: true, sort_order: 0 });
            setModalOpen(true);
          }}>新增时段</Button>
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
        title={editingItem ? '编辑时段定义' : '新增时段定义'}
        open={modalOpen}
        onOk={handleSubmit}
        onCancel={() => { setModalOpen(false); form.resetFields(); setEditingItem(null); }}
        width={520}
        destroyOnHidden
      >
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="名称" rules={[{ required: true, message: '请输入名称' }]}>
            <Input placeholder="如 尖时段1" />
          </Form.Item>
          <Form.Item name="period_type" label="时段类型" rules={[{ required: true, message: '请选择时段类型' }]}>
            <Select placeholder="选择时段类型">
              {Object.entries(PERIOD_TYPES).map(([k, v]) => (
                <Select.Option key={k} value={k}>{v.label}（{k}）</Select.Option>
              ))}
            </Select>
          </Form.Item>
          <Form.Item name="start_time" label="开始时间" rules={[{ required: true, message: '请输入开始时间' }]}>
            <Input placeholder="HH:MM 如 10:00" />
          </Form.Item>
          <Form.Item name="end_time" label="结束时间" rules={[{ required: true, message: '请输入结束时间' }]}>
            <Input placeholder="HH:MM 如 12:00" />
          </Form.Item>
          <Form.Item name="sort_order" label="排序" initialValue={0}>
            <InputNumber min={0} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="is_active" label="启用" valuePropName="checked" initialValue={true}>
            <Switch />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={2} placeholder="可选描述" />
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
};

export default TimeSlotDefinitions;
