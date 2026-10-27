/**
 * AI模型配置页面
 * 
 * 功能：
 *   1. Provider 管理 — 表格 CRUD（新增/编辑/删除）
 *   2. 任务映射 — 每个任务类型 → 下拉选择模型
 *   3. 保存回调
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
  Card, Table, Button, Space, Tag, Modal, Form, Input, InputNumber,
  Switch, message, Popconfirm, Tooltip, Select, Descriptions, Row, Col,
} from 'antd';
import {
  RobotOutlined, PlusOutlined, ReloadOutlined, EditOutlined,
  DeleteOutlined, ApiOutlined, KeyOutlined, LinkOutlined,
  SettingOutlined, ThunderboltOutlined, SafetyOutlined,
  ToolOutlined, BulbOutlined, MessageOutlined,
} from '@ant-design/icons';
import { aiModelConfigAPI, getTaskLabel, type ProviderConfig, type AIModelFullConfig } from '../../api/aiModelConfig';

// ─── 常量 ───

const SYSTEM_BUILTIN_NAMES = ['TP/DS4P', 'TP/DS4F', 'TP/ModelB5.1', 'TP/ModelD', 'TP/Q3P'];

const TASK_ICONS: Record<string, React.ReactNode> = {
  log_analysis: <ApiOutlined />,
  fault_classify: <ThunderboltOutlined />,
  root_cause: <BulbOutlined />,
  repair_suggest: <ToolOutlined />,
  preventive: <SafetyOutlined />,
  chat_general: <MessageOutlined />,
};

const TASK_ORDER = ['log_analysis', 'fault_classify', 'root_cause', 'repair_suggest', 'preventive', 'chat_general'];

const PROVIDER_OPTIONS = [
  { label: 'cloud_provider-token (云服务商百炼Token)', value: 'cloud_provider-token' },
  { label: 'llm_generic (LlmGeneric)', value: 'llm_generic' },
  { label: 'model_a (ModelA)', value: 'model_a' },
  { label: 'custom (自定义)', value: 'custom' },
];

const ENV_KEY_HINTS: Record<string, string> = {
  'cloud_provider-token': 'ALIYUN_TOKEN_API_KEY',
  'llm_generic': 'LLM_GENERIC_API_KEY',
  'model_a': 'MODELA_API_KEY',
  'custom': 'CUSTOM_API_KEY',
};

const PAGE_SIZE = 20;

const AIModelConfigPage: React.FC = () => {
  // ─── State ───
  const [config, setConfig] = useState<AIModelFullConfig>({
    providers: [],
    task_mappings: {},
    fallback_strategy: 'next_available',
  });
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  // Modal
  const [modalVisible, setModalVisible] = useState(false);
  const [editingProvider, setEditingProvider] = useState<ProviderConfig | null>(null);
  const [providerForm] = Form.useForm();

  // ─── 数据加载 ───
  const fetchConfig = useCallback(async () => {
    setLoading(true);
    try {
      const res: any = await aiModelConfigAPI.getConfig();
      const data = res?.data || res;
      setConfig(data);
    } catch {
      message.error('获取AI模型配置失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchConfig();
  }, [fetchConfig]);

  // ─── 保存 ───
  const handleSave = async () => {
    setSaving(true);
    try {
      await aiModelConfigAPI.updateConfig(config);
      message.success('AI模型配置保存成功');
      await fetchConfig();
    } catch (err: any) {
      message.error(err?.response?.data?.detail || '保存失败');
    } finally {
      setSaving(false);
    }
  };

  // ─── Provider CRUD ───
  const openAddProvider = () => {
    setEditingProvider(null);
    providerForm.resetFields();
    providerForm.setFieldsValue({
      provider: 'cloud_provider-token',
      base_url: 'https://token-plan.cn-beijing.maas.cloud_providercs.com/compatible-mode/v1',
      context_window: 128000,
      max_tokens: 16384,
      enabled: true,
    });
    setModalVisible(true);
  };

  const openEditProvider = (record: ProviderConfig) => {
    setEditingProvider(record);
    providerForm.setFieldsValue(record);
    setModalVisible(true);
  };

  const handleProviderSubmit = async () => {
    try {
      const values = await providerForm.validateFields();
      let updated: ProviderConfig[];
      if (editingProvider) {
        updated = config.providers.map(p =>
          p.name === editingProvider.name ? { ...p, ...values } : p
        );
      } else {
        const newProvider: ProviderConfig = {
          ...values,
          api_key: values.api_key || '',
        };
        updated = [...config.providers, newProvider];
      }
      setConfig(prev => ({ ...prev, providers: updated }));
      message.success(editingProvider ? 'Provider 已更新' : 'Provider 已添加');
      setModalVisible(false);
    } catch {
      // validation error, form will show
    }
  };

  const handleDeleteProvider = (record: ProviderConfig) => {
    setConfig(prev => ({
      ...prev,
      providers: prev.providers.filter(p => p.name !== record.name),
    }));
    message.success(`Provider "${record.name}" 已移除`);
  };

  const handleToggleProvider = (record: ProviderConfig, checked: boolean) => {
    setConfig(prev => ({
      ...prev,
      providers: prev.providers.map(p =>
        p.name === record.name ? { ...p, enabled: checked } : p
      ),
    }));
  };

  // ─── Task Mapping ───
  const handleMappingChange = (taskType: string, modelName: string) => {
    setConfig(prev => ({
      ...prev,
      task_mappings: { ...prev.task_mappings, [taskType]: modelName },
    }));
  };

  // ─── 表格列 ───
  const providerColumns = [
    {
      title: '显示名称', dataIndex: 'name', key: 'name', width: 120,
      render: (name: string) => <Tag color={SYSTEM_BUILTIN_NAMES.includes(name) ? 'blue' : 'purple'}>{name}</Tag>,
    },
    {
      title: 'Provider', dataIndex: 'provider', key: 'provider', width: 120,
      render: (p: string) => <Tag>{p}</Tag>,
    },
    { title: 'Model ID', dataIndex: 'model_id', key: 'model_id', width: 160 },
    {
      title: 'Base URL', dataIndex: 'base_url', key: 'base_url', ellipsis: true,
      render: (url: string) => (
        <Tooltip title={url}>
          <span style={{ color: '#999', fontSize: 13 }}>{url}</span>
        </Tooltip>
      ),
    },
    {
      title: 'API Key', dataIndex: 'api_key', key: 'api_key', width: 140,
      render: (key: string) => {
        if (!key) return <Tag color="default">未设置</Tag>;
        // 可能已部分隐藏
        if (key.includes('***')) return <Tag color="orange">{key}</Tag>;
        if (key.length > 12) return <Tag color="green">{key.slice(0, 12)}***</Tag>;
        return <Tag color="green">***</Tag>;
      },
    },
    { title: '上下文窗口', dataIndex: 'context_window', key: 'context_window', width: 110,
      render: (v: number) => v?.toLocaleString() },
    { title: '最大Tokens', dataIndex: 'max_tokens', key: 'max_tokens', width: 100,
      render: (v: number) => v?.toLocaleString() },
    {
      title: '启用', dataIndex: 'enabled', key: 'enabled', width: 70,
      render: (v: boolean, record: ProviderConfig) => (
        <Switch size="small" checked={v} onChange={(checked) => handleToggleProvider(record, checked)} />
      ),
    },
    {
      title: '操作', key: 'action', width: 150, fixed: 'right' as const,
      render: (_: any, record: ProviderConfig) => (
        <Space size="small">
          <Button size="small" icon={<EditOutlined />} onClick={() => openEditProvider(record)}>
            编辑
          </Button>
          {!SYSTEM_BUILTIN_NAMES.includes(record.name) && (
            <Popconfirm
              title={`确定删除 Provider "${record.name}"？`}
              onConfirm={() => handleDeleteProvider(record)}
              okText="删除" cancelText="取消"
            >
              <Button size="small" danger icon={<DeleteOutlined />} />
            </Popconfirm>
          )}
          {SYSTEM_BUILTIN_NAMES.includes(record.name) && (
            <Tooltip title="系统内置 Provider 不可删除，但可编辑">
              <Button size="small" danger icon={<DeleteOutlined />} disabled />
            </Tooltip>
          )}
        </Space>
      ),
    },
  ];

  // ─── 可选的模型列表（用于任务映射） ───
  const enabledModels = config.providers.filter(p => p.enabled);
  const modelOptions = enabledModels.map(p => ({
    label: `${p.name} (${p.model_id})`,
    value: p.name,
  }));

  return (
    <div className="page-container">
      {/* ── 顶部操作栏 ── */}
      <Card style={{ marginBottom: 16 }}>
        <Row justify="space-between" align="middle">
          <Col>
            <Space size="middle">
              <RobotOutlined style={{ fontSize: 20, color: '#1890ff' }} />
              <span style={{ fontSize: 18, fontWeight: 600 }}>AI模型配置</span>
            </Space>
          </Col>
          <Col>
            <Space>
              <Button icon={<ReloadOutlined />} onClick={fetchConfig} loading={loading}>
                刷新
              </Button>
              <Button type="primary" icon={<SettingOutlined />} onClick={handleSave} loading={saving}>
                保存全部配置
              </Button>
            </Space>
          </Col>
        </Row>
        <Row style={{ marginTop: 12 }}>
          <Col span={24}>
            <Descriptions size="small" column={3}>
              <Descriptions.Item label="Provider 数量">
                <Tag color="blue">{config.providers.length}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="已启用">
                <Tag color="green">{config.providers.filter(p => p.enabled).length}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="Fallback 策略">
                <Tag color="orange">{config.fallback_strategy}</Tag>
              </Descriptions.Item>
            </Descriptions>
          </Col>
        </Row>
      </Card>

      {/* ── Provider 管理 ── */}
      <Card
        title={<Space><ApiOutlined />Provider 管理</Space>}
        extra={
          <Button type="primary" icon={<PlusOutlined />} onClick={openAddProvider}>
            新增 Provider
          </Button>
        }
        style={{ marginBottom: 16 }}
      >
        <Table
          columns={providerColumns}
          dataSource={config.providers}
          rowKey="name"
          loading={loading}
          pagination={config.providers.length > PAGE_SIZE ? { pageSize: PAGE_SIZE } : false}
          scroll={{ x: 1100 }}
          size="middle"
        />
        <div style={{ marginTop: 8, color: '#999', fontSize: 13 }}>
          <KeyOutlined /> 提示：API Key 优先从环境变量读取（MODELA_API_KEY / LLM_GENERIC_API_KEY / ALIYUN_TOKEN_API_KEY），
          此处仅作为备用配置。系统内置 Provider 可编辑但不可删除。
        </div>
      </Card>

      {/* ── 任务映射 ── */}
      <Card
        title={<Space><LinkOutlined />任务模型映射</Space>}
        style={{ marginBottom: 16 }}
      >
        <Row gutter={[16, 16]}>
          {TASK_ORDER.map(taskType => (
            <Col xs={24} sm={12} md={8} key={taskType}>
              <Card
                size="small"
                hoverable
                title={
                  <Space>
                    {TASK_ICONS[taskType]}
                    <span>{getTaskLabel(taskType)}</span>
                    <Tag style={{ fontSize: 10 }}>{taskType}</Tag>
                  </Space>
                }
              >
                <Select
                  style={{ width: '100%' }}
                  placeholder="选择模型"
                  value={config.task_mappings[taskType] || undefined}
                  onChange={(value) => handleMappingChange(taskType, value)}
                  options={modelOptions}
                  allowClear
                  notFoundContent="暂无可用模型，请先启用 Provider"
                />
              </Card>
            </Col>
          ))}
        </Row>
      </Card>

      {/* ── Provider 编辑/新增弹窗 ── */}
      <Modal
        title={editingProvider ? `编辑 Provider: ${editingProvider.name}` : '新增 Provider'}
        open={modalVisible}
        onOk={handleProviderSubmit}
        onCancel={() => setModalVisible(false)}
        okText="保存"
        cancelText="取消"
        width={640}
        destroyOnHidden
      >
        <Form form={providerForm} layout="vertical" style={{ marginTop: 12 }}>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item
                name="provider"
                label="Provider 类型"
                rules={[{ required: true, message: '请选择 Provider 类型' }]}
              >
                <Select options={PROVIDER_OPTIONS} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item
                name="model_id"
                label="Model ID"
                rules={[{ required: true, message: '请输入 Model ID' }]}
              >
                <Input placeholder="例如: llm-pro-a" />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item
                name="name"
                label="显示名称"
                rules={[{ required: true, message: '请输入显示名称' }]}
                tooltip="用于任务映射下拉选择，建议简短易懂"
                extra={editingProvider && SYSTEM_BUILTIN_NAMES.includes(editingProvider.name)
                  ? '⚠️ 修改显示名称会影响任务映射，请谨慎操作'
                  : undefined}
              >
                <Input placeholder="例如: TP/DS4P" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item
                name="base_url"
                label="Base URL"
                rules={[{ required: true, message: '请输入 Base URL' }]}
              >
                <Input placeholder="https://api.llm_generic.com/v1" />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item
            name="api_key"
            label="API Key"
            extra={
              providerForm.getFieldValue('provider')
                ? `如已设置环境变量 ${ENV_KEY_HINTS[providerForm.getFieldValue('provider')] || ENV_KEY_HINTS.custom}，此处可留空`
                : '如已设置环境变量，此处可留空'
            }
          >
            <Input.Password
              placeholder="输入 API Key，也可通过环境变量设置"
              iconRender={(visible) => (visible ? <span>隐藏</span> : <span>显示</span>)}
            />
          </Form.Item>
          <Row gutter={16}>
            <Col span={8}>
              <Form.Item name="context_window" label="Context Window">
                <InputNumber
                  style={{ width: '100%' }}
                  min={1}
                  step={1000}
                  placeholder="128000"
                  formatter={(v) => `${v}`.replace(/\B(?=(\d{3})+(?!\d))/g, ',')}
                  parser={(v) => Number(v?.replace(/,/g, '') || 0) as any}
                />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="max_tokens" label="Max Tokens">
                <InputNumber
                  style={{ width: '100%' }}
                  min={1}
                  step={1000}
                  placeholder="16384"
                  formatter={(v) => `${v}`.replace(/\B(?=(\d{3})+(?!\d))/g, ',')}
                  parser={(v) => Number(v?.replace(/,/g, '') || 0) as any}
                />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="enabled" label="启用" valuePropName="checked">
                <Switch checkedChildren="启用" unCheckedChildren="禁用" />
              </Form.Item>
            </Col>
          </Row>
        </Form>
      </Modal>
    </div>
  );
};

export default AIModelConfigPage;