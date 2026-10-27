/**
 * 天链 V3 — 云服务配置 (SPEC §2.4 物联网接入)
 * 公有云/私有云对接配置(存储桶 + 数据同步策略)
 *   - 列表(配置名称/提供商/存储桶/同步策略/状态) + 按提供商/策略/状态筛选
 *   - 新增/编辑 Modal + 连通性测试(模拟)
 */
import React, { useEffect, useState, useCallback } from 'react';
import {
  Table, Tag, Button, Modal, Form, Input, Select, Space, message,
  Popconfirm,
} from 'antd';
import {
  PlusOutlined, EditOutlined, DeleteOutlined, ReloadOutlined,
  SearchOutlined, ApiOutlined,
} from '@ant-design/icons';
import { cloudConfigAPI } from '../../api/admin';
import { fetchAllPages } from '../../api/fetchAll';

interface CloudConfigItem {
  id: number;
  config_name: string;
  provider: string;
  config_json?: { region?: string; endpoint?: string } | null;
  bucket?: string | null;
  sync_strategy: string;
  status: string;
  remark?: string | null;
  created_at?: string;
  updated_at?: string;
}

const PROVIDER_OPTIONS = [
  { value: 'cloud-a', label: '云服务商' },
  { value: 'cloud-b', label: '服务商B云' },
  { value: 'aws', label: 'AWS' },
  { value: 'private', label: '私有云' },
];
const STRATEGY_OPTIONS = [
  { value: 'realtime', label: '实时同步' },
  { value: 'hourly', label: '每小时' },
  { value: 'daily', label: '每天' },
];
const STATUS_OPTIONS = [
  { value: 'active', label: '启用' },
  { value: 'inactive', label: '停用' },
];

const providerLabel = (v: string) => PROVIDER_OPTIONS.find(o => o.value === v)?.label || v;
const providerColor: Record<string, string> = { cloud_provider: 'orange', vendor_b: 'blue', aws: 'geekblue', private: 'default' };
const strategyLabel = (v: string) => STRATEGY_OPTIONS.find(o => o.value === v)?.label || v;

const CloudPage: React.FC = () => {
  const [data, setData] = useState<CloudConfigItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editingItem, setEditingItem] = useState<CloudConfigItem | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [testingId, setTestingId] = useState<number | null>(null);
  const [filters, setFilters] = useState<{ provider?: string; sync_strategy?: string; status?: string; keyword?: string }>({});
  const [form] = Form.useForm();

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const items = await fetchAllPages<CloudConfigItem>((params) => cloudConfigAPI.list({
        ...filters,
        page: params.page as number,
        page_size: params.page_size as number,
      }));
      setData(items);
    } catch (err: any) {
      message.error('加载云服务配置列表失败：' + (err?.response?.data?.detail || err?.message));
      setData([]);
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => { loadData(); }, [loadData]);

  const handleTest = async (id: number) => {
    setTestingId(id);
    try {
      const { data: res } = await cloudConfigAPI.test(id);
      const r = (res as any) ?? {};
      if (r.reachable && r.storage_ok) {
        message.success('连通性测试通过：存储桶可访问，同步端点可达');
      } else {
        message.error('连通性测试失败：存储桶或同步端点不可达');
      }
    } catch (err: any) {
      message.error('连通性测试失败：' + (err?.response?.data?.detail || err?.message));
    } finally {
      setTestingId(null);
    }
  };

  const openCreate = () => {
    setEditingItem(null);
    form.resetFields();
    form.setFieldsValue({ provider: 'cloud-a', sync_strategy: 'hourly', status: 'active' });
    setModalOpen(true);
  };

  const openEdit = (record: CloudConfigItem) => {
    setEditingItem(record);
    form.setFieldsValue({
      config_name: record.config_name,
      provider: record.provider,
      region: record.config_json?.region,
      endpoint: record.config_json?.endpoint,
      bucket: record.bucket,
      sync_strategy: record.sync_strategy,
      status: record.status,
      remark: record.remark,
    });
    setModalOpen(true);
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      setSubmitting(true);
      const payload: Record<string, unknown> = {
        config_name: values.config_name,
        provider: values.provider,
        bucket: values.bucket,
        sync_strategy: values.sync_strategy,
        status: values.status,
        remark: values.remark,
      };
      if (values.region || values.endpoint) {
        payload.config_json = { region: values.region, endpoint: values.endpoint };
      }
      if (editingItem) {
        await cloudConfigAPI.update(editingItem.id, payload);
        message.success('云服务配置已更新');
      } else {
        await cloudConfigAPI.create(payload);
        message.success('云服务配置已创建');
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
      await cloudConfigAPI.delete(id);
      message.success('已删除');
      loadData();
    } catch (err: any) {
      message.error('删除失败：' + (err?.response?.data?.detail || err?.message));
    }
  };

  const columns = [
    { title: 'ID', dataIndex: 'id', key: 'id', width: 60 },
    { title: '配置名称', dataIndex: 'config_name', key: 'config_name', width: 180 },
    {
      title: '提供商', dataIndex: 'provider', key: 'provider', width: 100,
      render: (v: string) => <Tag color={providerColor[v] || 'blue'}>{providerLabel(v)}</Tag>,
    },
    { title: '存储桶', dataIndex: 'bucket', key: 'bucket', width: 170, ellipsis: true },
    {
      title: '同步策略', dataIndex: 'sync_strategy', key: 'sync_strategy', width: 110,
      render: (v: string) => strategyLabel(v),
    },
    {
      title: '状态', dataIndex: 'status', key: 'status', width: 80,
      render: (v: string) => <Tag color={v === 'active' ? 'green' : 'default'}>{v === 'active' ? '启用' : '停用'}</Tag>,
    },
    {
      title: '操作', key: 'action', width: 260, fixed: 'right' as const,
      render: (_: unknown, record: CloudConfigItem) => (
        <Space>
          <Button
            size="small" icon={<ApiOutlined />}
            loading={testingId === record.id}
            onClick={() => handleTest(record.id)}
          >连通性测试</Button>
          <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(record)}>编辑</Button>
          <Popconfirm title="确认删除该云服务配置？" okText="确定" cancelText="取消" onConfirm={() => handleDelete(record.id)}>
            <Button size="small" danger icon={<DeleteOutlined />}>删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <>
      <div className="page-container">
        <Space style={{ marginBottom: 16, width: '100%', justifyContent: 'space-between' }} wrap>
          <Space wrap>
            <Select
              allowClear placeholder="提供商" style={{ width: 130 }}
              options={PROVIDER_OPTIONS}
              value={filters.provider}
              onChange={(v) => setFilters(f => ({ ...f, provider: v || undefined }))}
            />
            <Select
              allowClear placeholder="同步策略" style={{ width: 130 }}
              options={STRATEGY_OPTIONS}
              value={filters.sync_strategy}
              onChange={(v) => setFilters(f => ({ ...f, sync_strategy: v || undefined }))}
            />
            <Select
              allowClear placeholder="状态" style={{ width: 120 }}
              options={STATUS_OPTIONS}
              value={filters.status}
              onChange={(v) => setFilters(f => ({ ...f, status: v || undefined }))}
            />
            <Input
              allowClear placeholder="配置名称关键字" style={{ width: 180 }}
              value={filters.keyword}
              onChange={(e) => setFilters(f => ({ ...f, keyword: e.target.value || undefined }))}
              onPressEnter={loadData}
            />
            <Button icon={<SearchOutlined />} type="primary" onClick={loadData}>查询</Button>
          </Space>
          <Space>
            <Button icon={<ReloadOutlined />} onClick={loadData}>刷新</Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>新增配置</Button>
          </Space>
        </Space>
        <Table
          columns={columns}
          dataSource={data}
          rowKey="id"
          loading={loading}
          scroll={{ x: 1100 }}
          pagination={{ pageSize: 10, showSizeChanger: true, showTotal: (t: number) => `共 ${t} 条` }}
        />
      </div>
      <Modal
        title={editingItem ? '编辑云服务配置' : '新增云服务配置'}
        open={modalOpen}
        onOk={handleSubmit}
        confirmLoading={submitting}
        onCancel={() => { setModalOpen(false); form.resetFields(); setEditingItem(null); }}
        width={600}
        destroyOnHidden
      >
        <Form form={form} layout="vertical">
          <Form.Item name="config_name" label="配置名称" rules={[{ required: true, message: '请输入配置名称' }]}>
            <Input placeholder="如 云服务商生产环境" />
          </Form.Item>
          <Form.Item name="provider" label="云提供商" rules={[{ required: true, message: '请选择提供商' }]}>
            <Select options={PROVIDER_OPTIONS} placeholder="选择提供商" />
          </Form.Item>
          <Form.Item name="region" label="区域(Region)">
            <Input placeholder="如 cn-hangzhou" />
          </Form.Item>
          <Form.Item name="endpoint" label="接入端点(Endpoint)">
            <Input placeholder="如 oss-cn-hangzhou.cloud_providercs.com" />
          </Form.Item>
          <Form.Item name="bucket" label="存储桶(Bucket)">
            <Input placeholder="如 tianlian-prod" />
          </Form.Item>
          <Form.Item name="sync_strategy" label="数据同步策略" rules={[{ required: true, message: '请选择同步策略' }]}>
            <Select options={STRATEGY_OPTIONS} />
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

export default CloudPage;
