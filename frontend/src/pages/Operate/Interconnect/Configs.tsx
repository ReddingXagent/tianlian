/**
 * 天链 V3 — 互联互通平台配置管理
 * 对接外部充电平台(华为/国网/南网/特来电)的接入配置 CRUD + 联调测试
 */
import React, { useEffect, useState, useCallback } from 'react';
import {
  Card, Table, Tag, Button, Modal, Form, Input, Select, Space, message,
  Popconfirm, InputNumber,
} from 'antd';
import {
  PlusOutlined, EditOutlined, DeleteOutlined, ReloadOutlined, ApiOutlined,
} from '@ant-design/icons';
import { interconnectAPI } from '../../../api/operateExternal';
import { fetchAllPages } from '../../../api/fetchAll';

interface InterconnectConfigItem {
  id: number;
  platform_name: string;
  platform_code: string;
  api_base_url: string;
  auth_type: string;
  auth_params?: Record<string, unknown> | null;
  revenue_share_ratio: number;
  data_sync_interval: number;
  status: string;
  remark?: string | null;
  created_at?: string;
  updated_at?: string;
}

const PLATFORM_OPTIONS = [
  { value: 'huawei', label: '华为云充电' },
  { value: 'sgcc', label: '国家电网' },
  { value: 'csg', label: '南方电网' },
  { value: 'teld', label: '特来电' },
  { value: 'other', label: '其他平台' },
];

const AUTH_OPTIONS = [
  { value: 'apikey', label: 'API Key' },
  { value: 'oauth', label: 'OAuth 2.0' },
];

const STATUS_OPTIONS = [
  { value: 'active', label: '启用' },
  { value: 'inactive', label: '停用' },
];

const platformLabel = (code: string) => PLATFORM_OPTIONS.find(o => o.value === code)?.label || code;
const authLabel = (code: string) => AUTH_OPTIONS.find(o => o.value === code)?.label || code;

const InterconnectConfigs: React.FC = () => {
  const [data, setData] = useState<InterconnectConfigItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editingItem, setEditingItem] = useState<InterconnectConfigItem | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [testingId, setTestingId] = useState<number | null>(null);
  const [form] = Form.useForm();

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      // 卡 fb183aaf: page_size 恰 100 上限会静默截断 → fetchAllPages 循环拉全量
      const items = await fetchAllPages<InterconnectConfigItem>(interconnectAPI.list);
      setData(items);
    } catch {
      setData([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const handleTest = async (id: number) => {
    setTestingId(id);
    try {
      const { data: res } = await interconnectAPI.test(id);
      const r = (res as any) ?? {};
      if (r.reachable && r.auth_ok) {
        message.success('联调测试通过：地址可达，认证有效');
      } else {
        message.error('联调测试失败：地址不可达或认证无效');
      }
    } catch (err: any) {
      message.error('联调测试失败：' + (err?.response?.data?.detail || err?.message));
    } finally {
      setTestingId(null);
    }
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      setSubmitting(true);
      if (editingItem) {
        await interconnectAPI.update(editingItem.id, values);
        message.success('平台配置已更新');
      } else {
        await interconnectAPI.create(values);
        message.success('平台配置已创建');
      }
      setModalOpen(false);
      form.resetFields();
      setEditingItem(null);
      loadData();
    } catch (err: any) {
      if (err?.errorFields) return; // 表单校验错误，不提示
      message.error('操作失败：' + (err?.response?.data?.detail || err?.message));
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await interconnectAPI.delete(id);
      message.success('已删除');
      loadData();
    } catch (err: any) {
      message.error('删除失败：' + (err?.response?.data?.detail || err?.message));
    }
  };

  const columns = [
    { title: 'ID', dataIndex: 'id', key: 'id', width: 60 },
    { title: '平台名称', dataIndex: 'platform_name', key: 'platform_name', width: 150 },
    {
      title: '平台编码', dataIndex: 'platform_code', key: 'platform_code', width: 110,
      render: (v: string) => <Tag color="blue">{platformLabel(v)}</Tag>,
    },
    { title: 'API地址', dataIndex: 'api_base_url', key: 'api_base_url', width: 220, ellipsis: true },
    {
      title: '认证方式', dataIndex: 'auth_type', key: 'auth_type', width: 100,
      render: (v: string) => authLabel(v),
    },
    {
      title: '分成比例', dataIndex: 'revenue_share_ratio', key: 'revenue_share_ratio', width: 100, align: 'right' as const,
      render: (v: number) => <span style={{ color: '#34a853', fontWeight: 600 }}>{((v || 0) * 100).toFixed(1)}%</span>,
    },
    {
      title: '同步间隔', dataIndex: 'data_sync_interval', key: 'data_sync_interval', width: 100, align: 'right' as const,
      render: (v: number) => `${v || 0} 秒`,
    },
    {
      title: '状态', dataIndex: 'status', key: 'status', width: 80,
      render: (v: string) => <Tag color={v === 'active' ? 'green' : 'default'}>{v === 'active' ? '启用' : '停用'}</Tag>,
    },
    {
      title: '操作', key: 'action', width: 220, fixed: 'right' as const,
      render: (_: unknown, record: InterconnectConfigItem) => (
        <Space>
          <Button
            size="small"
            icon={<ApiOutlined />}
            loading={testingId === record.id}
            onClick={() => handleTest(record.id)}
          >联调测试</Button>
          <Button size="small" icon={<EditOutlined />} onClick={() => {
            setEditingItem(record);
            form.setFieldsValue(record);
            setModalOpen(true);
          }}>编辑</Button>
          <Popconfirm title="确认删除该平台配置？" okText="确定" cancelText="取消" onConfirm={() => handleDelete(record.id)}>
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
              platform_code: 'huawei',
              auth_type: 'apikey',
              revenue_share_ratio: 0.7,
              data_sync_interval: 300,
              status: 'active',
            });
            setModalOpen(true);
          }}>新增平台</Button>
        </Space>
      </div>
      <Table
        columns={columns}
        dataSource={data}
        rowKey="id"
        loading={loading}
        scroll={{ x: 1100 }}
        pagination={{ pageSize: 10, showSizeChanger: true, showTotal: (t: number) => `共 ${t} 条` }}
      />
      <Modal
        title={editingItem ? '编辑平台配置' : '新增平台配置'}
        open={modalOpen}
        onOk={handleSubmit}
        confirmLoading={submitting}
        onCancel={() => { setModalOpen(false); form.resetFields(); setEditingItem(null); }}
        width={600}
        destroyOnHidden
      >
        <Form form={form} layout="vertical">
          <Form.Item name="platform_name" label="平台名称" rules={[{ required: true, message: '请输入平台名称' }]}>
            <Input placeholder="如 华为云充电" />
          </Form.Item>
          <Form.Item name="platform_code" label="平台编码" rules={[{ required: true, message: '请选择平台编码' }]}>
            <Select options={PLATFORM_OPTIONS} placeholder="选择平台" />
          </Form.Item>
          <Form.Item name="api_base_url" label="API接入地址" rules={[{ required: true, message: '请输入API地址' }]}>
            <Input placeholder="https://api.example.com" />
          </Form.Item>
          <Form.Item name="auth_type" label="认证方式" rules={[{ required: true, message: '请选择认证方式' }]}>
            <Select options={AUTH_OPTIONS} />
          </Form.Item>
          <Form.Item name="revenue_share_ratio" label="我方分成比例(0-1)" rules={[{ required: true, message: '请输入分成比例' }]}>
            <InputNumber style={{ width: '100%' }} min={0} max={1} step={0.05} precision={2} placeholder="如 0.7 表示70%" />
          </Form.Item>
          <Form.Item name="data_sync_interval" label="数据同步间隔(秒)" rules={[{ required: true, message: '请输入同步间隔' }]}>
            <InputNumber style={{ width: '100%' }} min={10} step={60} placeholder="如 300" />
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

export default InterconnectConfigs;
