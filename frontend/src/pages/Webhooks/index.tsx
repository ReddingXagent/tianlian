/**
 * 天链 V3 - Webhook 管理页面 (SPEC §2.6)
 *
 * 出站事件回调配置:
 *   - Webhook 列表 (名称/URL/事件类型/状态/操作)
 *   - 创建/编辑 Modal
 *   - 投递日志 Drawer
 *   - 测试发送
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
  Card, Table, Button, Space, Tag, Modal, Form, Input, Select,
  Switch, InputNumber, message, Popconfirm, Drawer, Tooltip, Descriptions,
  Row, Col, Timeline, Badge,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import {
  PlusOutlined, ReloadOutlined, EditOutlined, DeleteOutlined,
  ThunderboltOutlined, HistoryOutlined, ApiOutlined,
} from '@ant-design/icons';
import api from '../../api';

const { Option } = Select;
const { TextArea } = Input;

// ─── 类型 ───

interface WebhookItem {
  id: number;
  name: string;
  url: string;
  event_types: string[];
  secret?: string;
  retry_count: number;
  retry_interval: number;
  timeout: number;
  enabled: boolean;
  description?: string;
  created_at?: string;
  updated_at?: string;
}

interface DeliveryItem {
  id: number;
  webhook_id: number;
  event_type?: string;
  payload?: any;
  status_code?: number;
  response_body?: string;
  status: 'success' | 'failed' | 'pending' | 'retrying';
  duration_ms?: number;
  attempt: number;
  error_message?: string;
  created_at?: string;
}

// ─── 事件类型配置 ───

const EVENT_TYPES = [
  { value: 'alert', label: '告警', color: 'red' },
  { value: 'ticket', label: '工单', color: 'orange' },
  { value: 'order', label: '订单', color: 'blue' },
  { value: 'device', label: '设备状态', color: 'green' },
];

const EVENT_MAP = Object.fromEntries(EVENT_TYPES.map(e => [e.value, e]));

const STATUS_COLORS: Record<string, string> = {
  success: 'green',
  failed: 'red',
  pending: 'default',
  retrying: 'orange',
};

// ─── Webhook API ───

const webhookAPI = {
  list: (params?: Record<string, unknown>) => api.get('/webhooks', { params }),
  get: (id: number) => api.get(`/webhooks/${id}`),
  create: (data: Record<string, unknown>) => api.post('/webhooks', data),
  update: (id: number, data: Record<string, unknown>) => api.put(`/webhooks/${id}`, data),
  delete: (id: number) => api.delete(`/webhooks/${id}`),
  toggle: (id: number, enabled: boolean) => api.put(`/webhooks/${id}/toggle`, { enabled }),
  test: (id: number) => api.post(`/webhooks/${id}/test`),
  deliveries: (id: number, params?: Record<string, unknown>) => api.get(`/webhooks/${id}/deliveries`, { params }),
};

// ─── 组件 ───

const WebhooksPage: React.FC = () => {
  const [data, setData] = useState<WebhookItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);

  // 搜索/筛选
  const [keyword, setKeyword] = useState('');
  const [filterEnabled, setFilterEnabled] = useState<boolean | undefined>();

  // Modal
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<WebhookItem | null>(null);
  const [form] = Form.useForm();
  const [submitting, setSubmitting] = useState(false);

  // Drawer - 投递日志
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [drawerWebhook, setDrawerWebhook] = useState<WebhookItem | null>(null);
  const [deliveries, setDeliveries] = useState<DeliveryItem[]>([]);
  const [deliveryTotal, setDeliveryTotal] = useState(0);
  const [deliveryLoading, setDeliveryLoading] = useState(false);
  const [deliveryPage, setDeliveryPage] = useState(1);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, unknown> = { page, page_size: pageSize };
      if (keyword) params.keyword = keyword;
      if (filterEnabled !== undefined) params.enabled = filterEnabled;
      const resp = await webhookAPI.list(params);
      const d = resp.data?.data ?? {};
      setData(d.items ?? []);
      setTotal(d.total ?? 0);
    } catch {
      message.error('加载 Webhook 列表失败');
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, keyword, filterEnabled]);

  useEffect(() => { fetchData(); }, [fetchData]);

  // ─── CRUD ───

  const handleCreate = () => {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({
      retry_count: 3,
      retry_interval: 60,
      timeout: 10,
      enabled: true,
    });
    setModalOpen(true);
  };

  const handleEdit = (record: WebhookItem) => {
    setEditing(record);
    form.setFieldsValue({
      name: record.name,
      url: record.url,
      event_types: record.event_types,
      secret: record.secret,
      retry_count: record.retry_count,
      retry_interval: record.retry_interval,
      timeout: record.timeout,
      enabled: record.enabled,
      description: record.description,
    });
    setModalOpen(true);
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      setSubmitting(true);
      if (editing) {
        await webhookAPI.update(editing.id, values);
        message.success('Webhook 更新成功');
      } else {
        await webhookAPI.create(values);
        message.success('Webhook 创建成功');
      }
      setModalOpen(false);
      fetchData();
    } catch (err: any) {
      if (err?.errorFields) return; // 表单校验错误
      message.error(err?.response?.data?.message || '操作失败');
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await webhookAPI.delete(id);
      message.success('Webhook 已删除');
      fetchData();
    } catch {
      message.error('删除失败');
    }
  };

  const handleToggle = async (record: WebhookItem, enabled: boolean) => {
    try {
      await webhookAPI.toggle(record.id, enabled);
      message.success(`Webhook 已${enabled ? '启用' : '停用'}`);
      fetchData();
    } catch {
      message.error('操作失败');
    }
  };

  const handleTest = async (record: WebhookItem) => {
    const hide = message.loading('正在发送测试事件...', 0);
    try {
      const resp = await webhookAPI.test(record.id);
      hide();
      const delivery = resp.data?.data;
      if (delivery?.status === 'success') {
        message.success(`测试发送成功 (${delivery.status_code}, ${delivery.duration_ms}ms)`);
      } else {
        message.warning(`测试发送返回: ${delivery?.status_code ?? 'N/A'} (${delivery?.status})`);
      }
      fetchData();
    } catch {
      hide();
      message.error('测试发送失败');
    }
  };

  // ─── 投递日志 ───

  const fetchDeliveries = useCallback(async (webhookId: number, dpage = 1) => {
    setDeliveryLoading(true);
    try {
      const resp = await webhookAPI.deliveries(webhookId, { page: dpage, page_size: 20 });
      const d = resp.data?.data ?? {};
      setDeliveries(d.items ?? []);
      setDeliveryTotal(d.total ?? 0);
    } catch {
      message.error('加载投递日志失败');
    } finally {
      setDeliveryLoading(false);
    }
  }, []);

  const handleViewDeliveries = (record: WebhookItem) => {
    setDrawerWebhook(record);
    setDrawerOpen(true);
    setDeliveryPage(1);
    fetchDeliveries(record.id, 1);
  };

  // ─── 表格列 ───

  const columns: ColumnsType<WebhookItem> = [
    {
      title: '名称',
      dataIndex: 'name',
      key: 'name',
      width: 160,
      ellipsis: true,
      render: (text, record) => (
        <Space>
          <ApiOutlined style={{ color: '#1890ff' }} />
          <span style={{ fontWeight: 500 }}>{text}</span>
          {!record.enabled && <Tag color="default">已停用</Tag>}
        </Space>
      ),
    },
    {
      title: '回调 URL',
      dataIndex: 'url',
      key: 'url',
      ellipsis: true,
      render: (url: string) => (
        <Tooltip title={url}>
          <a href={url} target="_blank" rel="noreferrer" style={{ color: 'var(--text-secondary)' }}>
            {url}
          </a>
        </Tooltip>
      ),
    },
    {
      title: '事件类型',
      dataIndex: 'event_types',
      key: 'event_types',
      width: 220,
      render: (types: string[]) => (
        <Space size={[4, 4]} wrap>
          {(types || []).map(t => (
            <Tag key={t} color={EVENT_MAP[t]?.color || 'default'}>
              {EVENT_MAP[t]?.label || t}
            </Tag>
          ))}
          {(!types || types.length === 0) && <span style={{ color: 'var(--text-tertiary)' }}>—</span>}
        </Space>
      ),
    },
    {
      title: '重试',
      key: 'retry',
      width: 90,
      render: (_, record) => `${record.retry_count}次/${record.retry_interval}s`,
    },
    {
      title: '超时',
      dataIndex: 'timeout',
      key: 'timeout',
      width: 70,
      render: (v: number) => `${v}s`,
    },
    {
      title: '状态',
      dataIndex: 'enabled',
      key: 'enabled',
      width: 80,
      render: (enabled: boolean, record) => (
        <Switch
          size="small"
          checked={enabled}
          onChange={(checked) => handleToggle(record, checked)}
        />
      ),
    },
    {
      title: '操作',
      key: 'actions',
      width: 200,
      fixed: 'right' as const,
      render: (_, record) => (
        <Space size="small">
          <Tooltip title="测试发送">
            <Button
              type="text"
              size="small"
              icon={<ThunderboltOutlined />}
              onClick={() => handleTest(record)}
            />
          </Tooltip>
          <Tooltip title="投递日志">
            <Button
              type="text"
              size="small"
              icon={<HistoryOutlined />}
              onClick={() => handleViewDeliveries(record)}
            />
          </Tooltip>
          <Tooltip title="编辑">
            <Button
              type="text"
              size="small"
              icon={<EditOutlined />}
              onClick={() => handleEdit(record)}
            />
          </Tooltip>
          <Popconfirm
            title="确认删除"
            description={`删除 Webhook "${record.name}" 及其所有投递日志？`}
            onConfirm={() => handleDelete(record.id)}
            okText="删除"
            cancelText="取消"
            okButtonProps={{ danger: true }}
          >
            <Button type="text" size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  // ─── 投递日志列 ───

  const deliveryColumns: ColumnsType<DeliveryItem> = [
    {
      title: '时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (v: string) => v ? new Date(v).toLocaleString('zh-CN') : '—',
    },
    {
      title: '事件',
      dataIndex: 'event_type',
      key: 'event_type',
      width: 80,
      render: (v: string) => v ? <Tag color={EVENT_MAP[v]?.color || 'default'}>{EVENT_MAP[v]?.label || v}</Tag> : '—',
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: string) => (
        <Badge status={STATUS_COLORS[status] === 'green' ? 'success' : STATUS_COLORS[status] === 'red' ? 'error' : 'default'} text={status} />
      ),
    },
    {
      title: 'HTTP码',
      dataIndex: 'status_code',
      key: 'status_code',
      width: 80,
      render: (v: number) => v ? (
        <span style={{ color: v < 400 ? '#52c41a' : '#ff4d4f' }}>{v}</span>
      ) : '—',
    },
    {
      title: '耗时',
      dataIndex: 'duration_ms',
      key: 'duration_ms',
      width: 80,
      render: (v: number) => v != null ? `${v}ms` : '—',
    },
    {
      title: '第N次',
      dataIndex: 'attempt',
      key: 'attempt',
      width: 60,
    },
    {
      title: '错误信息',
      dataIndex: 'error_message',
      key: 'error_message',
      ellipsis: true,
      render: (v: string) => v ? <Tooltip title={v}><span style={{ color: '#ff4d4f' }}>{v}</span></Tooltip> : '—',
    },
  ];

  // ─── 渲染 ───

  return (
    <div style={{ padding: '24px' }}>
      <Card
        title={
          <Space>
            <ApiOutlined style={{ fontSize: 20, color: '#1890ff' }} />
            <span>Webhook 管理</span>
          </Space>
        }
        extra={
          <Space>
            <Input.Search
              placeholder="搜索名称/URL"
              allowClear
              style={{ width: 220 }}
              onSearch={(v) => { setKeyword(v); setPage(1); }}
            />
            <Select
              placeholder="状态筛选"
              allowClear
              style={{ width: 120 }}
              onChange={(v) => { setFilterEnabled(v); setPage(1); }}
            >
              <Option value={true}>已启用</Option>
              <Option value={false}>已停用</Option>
            </Select>
            <Button icon={<ReloadOutlined />} onClick={fetchData}>刷新</Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={handleCreate}>新建 Webhook</Button>
          </Space>
        }
      >
        <Table<WebhookItem>
          rowKey="id"
          columns={columns}
          dataSource={data}
          loading={loading}
          scroll={{ x: 1000 }}
          pagination={{
            current: page,
            pageSize,
            total,
            showSizeChanger: true,
            showTotal: (t) => `共 ${t} 条`,
            onChange: (p, ps) => { setPage(p); setPageSize(ps); },
          }}
          size="middle"
        />
      </Card>

      {/* 创建/编辑 Modal */}
      <Modal
        title={editing ? '编辑 Webhook' : '新建 Webhook'}
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        onOk={handleSubmit}
        confirmLoading={submitting}
        okText={editing ? '保存' : '创建'}
        cancelText="取消"
        width={640}
        destroyOnHidden
      >
        <Form form={form} layout="vertical" preserve={false}>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item
                name="name"
                label="名称"
                rules={[{ required: true, message: '请输入 Webhook 名称' }]}
              >
                <Input placeholder="如: 告警回调" maxLength={100} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item
                name="url"
                label="回调 URL"
                rules={[
                  { required: true, message: '请输入回调 URL' },
                  { type: 'url', message: '请输入合法的 URL' },
                ]}
              >
                <Input placeholder="https://example.com/webhook" />
              </Form.Item>
            </Col>
          </Row>

          <Form.Item name="event_types" label="订阅事件类型">
            <Select mode="multiple" placeholder="选择要订阅的事件">
              {EVENT_TYPES.map(e => (
                <Option key={e.value} value={e.value}>
                  <Tag color={e.color} style={{ marginRight: 0 }}>{e.label}</Tag>
                </Option>
              ))}
            </Select>
          </Form.Item>

          <Form.Item name="secret" label="签名密钥 (HMAC-SHA256)" tooltip="用于对请求体进行 HMAC-SHA256 签名，放在 X-Webhook-Signature 头中">
            <Input.Password placeholder="留空则不签名" />
          </Form.Item>

          <Row gutter={16}>
            <Col span={8}>
              <Form.Item name="retry_count" label="重试次数">
                <InputNumber min={0} max={10} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="retry_interval" label="重试间隔 (秒)">
                <InputNumber min={1} max={3600} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="timeout" label="超时 (秒)">
                <InputNumber min={1} max={120} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>

          <Form.Item name="description" label="描述">
            <TextArea rows={2} placeholder="可选备注信息" maxLength={500} />
          </Form.Item>

          <Form.Item name="enabled" label="启用" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>

      {/* 投递日志 Drawer */}
      <Drawer
        title={
          <Space>
            <HistoryOutlined />
            <span>投递日志 — {drawerWebhook?.name}</span>
          </Space>
        }
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        width={900}
      >
        {drawerWebhook && (
          <>
            <Descriptions size="small" column={3} bordered style={{ marginBottom: 16 }}>
              <Descriptions.Item label="URL" span={3}>{drawerWebhook.url}</Descriptions.Item>
              <Descriptions.Item label="重试">{drawerWebhook.retry_count}次 / {drawerWebhook.retry_interval}s</Descriptions.Item>
              <Descriptions.Item label="超时">{drawerWebhook.timeout}s</Descriptions.Item>
              <Descriptions.Item label="状态">
                <Tag color={drawerWebhook.enabled ? 'green' : 'default'}>
                  {drawerWebhook.enabled ? '启用' : '停用'}
                </Tag>
              </Descriptions.Item>
            </Descriptions>

            <Table<DeliveryItem>
              rowKey="id"
              columns={deliveryColumns}
              dataSource={deliveries}
              loading={deliveryLoading}
              size="small"
              pagination={{
                current: deliveryPage,
                pageSize: 20,
                total: deliveryTotal,
                showTotal: (t) => `共 ${t} 条`,
                onChange: (p) => {
                  setDeliveryPage(p);
                  if (drawerWebhook) fetchDeliveries(drawerWebhook.id, p);
                },
              }}
              expandable={{
                expandedRowRender: (record) => (
                  <div style={{ padding: '8px 0' }}>
                    {record.payload && (
                      <div style={{ marginBottom: 8 }}>
                        <strong>请求体:</strong>
                        <pre style={{ background: '#f5f5f5', padding: 8, borderRadius: 4, fontSize: 12, maxHeight: 200, overflow: 'auto' }}>
                          {JSON.stringify(record.payload, null, 2)}
                        </pre>
                      </div>
                    )}
                    {record.response_body && (
                      <div>
                        <strong>响应内容:</strong>
                        <pre style={{ background: '#f5f5f5', padding: 8, borderRadius: 4, fontSize: 12, maxHeight: 200, overflow: 'auto' }}>
                          {record.response_body}
                        </pre>
                      </div>
                    )}
                  </div>
                ),
              }}
            />
          </>
        )}
      </Drawer>
    </div>
  );
};

export default WebhooksPage;
