/**
 * 天链 V3 — 市政监管平台配置管理
 * 各城市监管平台的接入配置 CRUD (上报策略/间隔/心跳)
 */
import React, { useEffect, useState, useCallback } from 'react';
import {
  Table, Tag, Button, Modal, Form, Input, Select, Space, message,
  Popconfirm, InputNumber, Switch,
} from 'antd';
import {
  PlusOutlined, EditOutlined, DeleteOutlined, ReloadOutlined,
} from '@ant-design/icons';
import { supervisionAPI } from '../../../api/operateExternal';
import { fetchAllPages } from '../../../api/fetchAll';

interface SupervisionConfigItem {
  id: number;
  city: string;
  platform_url: string;
  auth_config?: Record<string, unknown> | null;
  report_strategy: string;
  report_interval_seconds: number;
  station_endpoints?: Record<string, unknown> | null;
  heartbeat_enabled: number;
  status: string;
  remark?: string | null;
  created_at?: string;
  updated_at?: string;
}

const STRATEGY_OPTIONS = [
  { value: 'scheduled', label: '定时上报' },
  { value: 'realtime', label: '实时上报' },
];

const STATUS_OPTIONS = [
  { value: 'active', label: '启用' },
  { value: 'inactive', label: '停用' },
];

const strategyLabel = (v: string) => STRATEGY_OPTIONS.find(o => o.value === v)?.label || v;

const SupervisionConfigs: React.FC = () => {
  const [data, setData] = useState<SupervisionConfigItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editingItem, setEditingItem] = useState<SupervisionConfigItem | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [form] = Form.useForm();

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      // 卡 fb183aaf: page_size 恰 100 上限会静默截断 → fetchAllPages 循环拉全量
      const items = await fetchAllPages<SupervisionConfigItem>(supervisionAPI.list);
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
      setSubmitting(true);
      const payload = { ...values, heartbeat_enabled: values.heartbeat_enabled ? 1 : 0 };
      if (editingItem) {
        await supervisionAPI.update(editingItem.id, payload);
        message.success('监管配置已更新');
      } else {
        await supervisionAPI.create(payload);
        message.success('监管配置已创建');
      }
      setModalOpen(false);
      form.resetFields();
      setEditingItem(null);
      loadData();
    } catch (err: any) {
      if (err?.errorFields) return;
      message.error('操作失败：' + (err?.response?.data?.detail || err?.message));
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await supervisionAPI.delete(id);
      message.success('已删除');
      loadData();
    } catch (err: any) {
      message.error('删除失败：' + (err?.response?.data?.detail || err?.message));
    }
  };

  const columns = [
    { title: 'ID', dataIndex: 'id', key: 'id', width: 60 },
    { title: '城市', dataIndex: 'city', key: 'city', width: 100 },
    { title: '监管平台URL', dataIndex: 'platform_url', key: 'platform_url', width: 240, ellipsis: true },
    {
      title: '上报策略', dataIndex: 'report_strategy', key: 'report_strategy', width: 100,
      render: (v: string) => <Tag color="blue">{strategyLabel(v)}</Tag>,
    },
    {
      title: '上报间隔', dataIndex: 'report_interval_seconds', key: 'report_interval_seconds', width: 100, align: 'right' as const,
      render: (v: number) => `${v || 0} 秒`,
    },
    {
      title: '心跳', dataIndex: 'heartbeat_enabled', key: 'heartbeat_enabled', width: 70,
      render: (v: number) => <Tag color={v ? 'green' : 'default'}>{v ? '开' : '关'}</Tag>,
    },
    {
      title: '状态', dataIndex: 'status', key: 'status', width: 80,
      render: (v: string) => <Tag color={v === 'active' ? 'green' : 'default'}>{v === 'active' ? '启用' : '停用'}</Tag>,
    },
    {
      title: '操作', key: 'action', width: 160, fixed: 'right' as const,
      render: (_: unknown, record: SupervisionConfigItem) => (
        <Space>
          <Button size="small" icon={<EditOutlined />} onClick={() => {
            setEditingItem(record);
            form.setFieldsValue({ ...record, heartbeat_enabled: !!record.heartbeat_enabled });
            setModalOpen(true);
          }}>编辑</Button>
          <Popconfirm title="确认删除该监管配置？" okText="确定" cancelText="取消" onConfirm={() => handleDelete(record.id)}>
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
            form.setFieldsValue({
              report_strategy: 'scheduled',
              report_interval_seconds: 60,
              heartbeat_enabled: true,
              status: 'active',
            });
            setModalOpen(true);
          }}>新增配置</Button>
        </Space>
      </div>
      <Table
        columns={columns}
        dataSource={data}
        rowKey="id"
        loading={loading}
        scroll={{ x: 1000 }}
        pagination={{ pageSize: 10, showSizeChanger: true, showTotal: (t: number) => `共 ${t} 条` }}
      />
      <Modal
        title={editingItem ? '编辑监管平台配置' : '新增监管平台配置'}
        open={modalOpen}
        onOk={handleSubmit}
        confirmLoading={submitting}
        onCancel={() => { setModalOpen(false); form.resetFields(); setEditingItem(null); }}
        width={600}
        destroyOnHidden
      >
        <Form form={form} layout="vertical">
          <Form.Item name="city" label="对接城市" rules={[{ required: true, message: '请输入城市' }]}>
            <Input placeholder="如 郑州市" />
          </Form.Item>
          <Form.Item name="platform_url" label="监管平台URL" rules={[{ required: true, message: '请输入平台URL' }]}>
            <Input placeholder="https://gov.example.cn/charge" />
          </Form.Item>
          <Form.Item name="report_strategy" label="上报策略" rules={[{ required: true, message: '请选择上报策略' }]}>
            <Select options={STRATEGY_OPTIONS} />
          </Form.Item>
          <Form.Item name="report_interval_seconds" label="定时上报间隔(秒)" rules={[{ required: true, message: '请输入上报间隔' }]}>
            <InputNumber style={{ width: '100%' }} min={10} step={10} placeholder="如 60" />
          </Form.Item>
          <Form.Item name="heartbeat_enabled" label="心跳保活" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item name="status" label="状态" rules={[{ required: true, message: '请选择状态' }]}>
            <Select options={STATUS_OPTIONS} />
          </Form.Item>
          <Form.Item name="remark" label="备注">
            <Input.TextArea rows={2} placeholder="选填" />
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
};

export default SupervisionConfigs;
