/**
 * 天链 V3 — 服务费定价（按电量/按次, 区分用户类型）
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
import { serviceFeeAPI } from '../../../api/pricing';
import { fetchAllPages } from '../../../api/fetchAll';

const USER_TYPES: Record<string, string> = {
  app: 'APP用户',
  card: '刷卡用户',
  vin: 'VIN码用户',
  interconnect: '互联互通',
  enterprise: '企业用户',
};

const FEE_TYPES: Record<string, string> = {
  fixed: '固定费用',
  percent: '按比例(元/kWh)',
};

interface ServiceFeeItem {
  id: number;
  station_id: number;
  user_type: string;
  fee_type: string;
  fee_value: number;
  effective_date: string;
  expire_date?: string;
  is_active: boolean;
}

const ServicePricing: React.FC = () => {
  const [data, setData] = useState<ServiceFeeItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editingItem, setEditingItem] = useState<ServiceFeeItem | null>(null);
  const [form] = Form.useForm();

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      // 卡 fb183aaf: page_size 恰 100 上限会静默截断 → fetchAllPages 循环拉全量
      const items = await fetchAllPages<ServiceFeeItem>(serviceFeeAPI.list);
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
        await serviceFeeAPI.update(editingItem.id, payload);
        message.success('服务费定价已更新');
      } else {
        await serviceFeeAPI.create(payload);
        message.success('服务费定价已创建');
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
      await serviceFeeAPI.delete(id);
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
      title: '用户类型', dataIndex: 'user_type', key: 'user_type', width: 110,
      render: (v: string) => <Tag color="purple">{USER_TYPES[v] || v}</Tag>,
    },
    {
      title: '费用类型', dataIndex: 'fee_type', key: 'fee_type', width: 130,
      render: (v: string) => <Tag color="cyan">{FEE_TYPES[v] || v}</Tag>,
    },
    {
      title: '费用值', dataIndex: 'fee_value', key: 'fee_value', width: 110, align: 'right' as const,
      render: (v: number, r: ServiceFeeItem) => (
        <span style={{ fontWeight: 600 }}>
          {r.fee_type === 'fixed' ? `¥ ${v?.toFixed(2)}` : `${v?.toFixed(4)} 元/kWh`}
        </span>
      ),
    },
    { title: '生效日期', dataIndex: 'effective_date', key: 'effective_date', width: 110 },
    { title: '失效日期', dataIndex: 'expire_date', key: 'expire_date', width: 110, render: (v: string) => v || '-' },
    {
      title: '状态', dataIndex: 'is_active', key: 'is_active', width: 80,
      render: (v: boolean) => <Tag color={v ? 'green' : 'default'}>{v ? '启用' : '停用'}</Tag>,
    },
    {
      title: '操作', key: 'action', width: 140,
      render: (_: unknown, record: ServiceFeeItem) => (
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
            form.setFieldsValue({ is_active: true, fee_value: 0 });
            setModalOpen(true);
          }}>新增服务费</Button>
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
        title={editingItem ? '编辑服务费定价' : '新增服务费定价'}
        open={modalOpen}
        onOk={handleSubmit}
        onCancel={() => { setModalOpen(false); form.resetFields(); setEditingItem(null); }}
        width={560}
        destroyOnHidden
      >
        <Form form={form} layout="vertical">
          <Form.Item name="station_id" label="站点ID" rules={[{ required: true, message: '请输入站点ID' }]}>
            <InputNumber style={{ width: '100%' }} min={1} />
          </Form.Item>
          <Form.Item name="user_type" label="用户类型" rules={[{ required: true, message: '请选择用户类型' }]}>
            <Select placeholder="选择用户类型">
              {Object.entries(USER_TYPES).map(([k, v]) => (
                <Select.Option key={k} value={k}>{v}</Select.Option>
              ))}
            </Select>
          </Form.Item>
          <Form.Item name="fee_type" label="费用类型" rules={[{ required: true, message: '请选择费用类型' }]}>
            <Select placeholder="选择费用类型">
              {Object.entries(FEE_TYPES).map(([k, v]) => (
                <Select.Option key={k} value={k}>{v}</Select.Option>
              ))}
            </Select>
          </Form.Item>
          <Form.Item name="fee_value" label="费用值" rules={[{ required: true, message: '请输入费用值' }]}>
            <InputNumber style={{ width: '100%' }} min={0} step={0.01} precision={4} />
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

export default ServicePricing;
