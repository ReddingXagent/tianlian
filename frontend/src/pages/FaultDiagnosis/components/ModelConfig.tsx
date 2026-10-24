/**
 * 模型配置 Tab — Provider 列表（CRUD） + 任务→模型映射（可编辑）
 */
import React, { useState, useEffect } from 'react';
import {
  Card, Row, Col, Button, Tag, Table, Select, Space, Typography, Spin, Descriptions, Modal, message,
} from 'antd';
import AutoHeightTable from '../../../components/AutoHeightTable';
import { ReloadOutlined, SettingOutlined, RobotOutlined } from '@ant-design/icons';
import { logAnalysisAPI } from '../../../api';
import type { ModelProvider } from '../types';
import ProviderFormModal from './ProviderFormModal';

const { Text } = Typography;

function ModelConfig() {
  const [config, setConfig] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  // Provider 编辑
  const [providerModal, setProviderModal] = useState(false);
  const [editingProvider, setEditingProvider] = useState<ModelProvider | null>(null);

  // 任务映射编辑
  const [editingTask, setEditingTask] = useState<string | null>(null);

  useEffect(() => { loadConfig(); }, []);

  const loadConfig = async () => {
    setLoading(true);
    try {
      const data = await logAnalysisAPI.getModelConfig();
      setConfig(data.data);
    } catch (e) {
      message.error('加载配置失败');
    }
    setLoading(false);
  };

  const handleSaveProviders = async (providers: any[]) => {
    setSaving(true);
    try {
      await logAnalysisAPI.updateModelConfig(providers);
      message.success('Provider 列表已更新');
      loadConfig();
    } catch {
      message.error('保存失败');
    }
    setSaving(false);
  };

  const handleSaveTaskMapping = async (task: string, model: string) => {
    try {
      await logAnalysisAPI.updateTaskMapping({ task_type: task, model_name: model });
      message.success(`${task} → ${model}`);
      loadConfig();
    } catch {
      message.error('更新失败');
    }
    setEditingTask(null);
  };

  const handleDeleteProvider = async (name: string) => {
    if (!config?.providers) return;
    const remaining = config.providers.filter((p: ModelProvider) => p.name !== name);
    if (remaining.length === 0) {
      message.warning('至少保留一个 Provider');
      return;
    }
    Modal.confirm({
      title: `确认删除 ${name}？`,
      onOk: () => handleSaveProviders(remaining),
    });
  };

  const handleProviderSave = (p: ModelProvider) => {
    if (!config?.providers) return;
    const providers = [...config.providers];
    const idx = providers.findIndex((x: ModelProvider) => x.name === p.name);
    if (idx >= 0) {
      providers[idx] = p;
    } else {
      providers.push(p);
    }
    setProviderModal(false);
    setEditingProvider(null);
    handleSaveProviders(providers);
  };

  const taskNames: Record<string, string> = {
    log_analysis: '日志分析',
    fault_classify: '故障分类',
    root_cause: '根因分析',
    repair_suggest: '维修建议',
    preventive: '预防措施',
  };

  if (loading && !config) {
    return <Spin style={{ display: 'block', margin: '40px auto' }} />;
  }

  const providers = config?.providers || [];
  const taskMappings = config?.task_mappings || {};

  return (
    <div>
      <Space style={{ marginBottom: 16 }}>
        <Button icon={<ReloadOutlined />} onClick={loadConfig} loading={loading}>刷新</Button>
        <Button type="primary" icon={<SettingOutlined />} onClick={() => { setEditingProvider(null); setProviderModal(true); }}>新增 Provider</Button>
        <Text type="secondary">AI模型配置</Text>
      </Space>

      {/* Provider 卡片列表 */}
      <Row gutter={16}>
        {providers.map((p: ModelProvider, i: number) => (
          <Col span={12} key={i} style={{ marginBottom: 12 }}>
            <Card
              title={<Space><RobotOutlined /><Text strong>{p.name}</Text><Tag color={p.enabled ? 'green' : 'red'}>{p.enabled ? '启用' : '禁用'}</Tag></Space>}
              size="small"
              extra={
                <Space>
                  <Button size="small" onClick={() => { setEditingProvider(p); setProviderModal(true); }}>编辑</Button>
                  <Button size="small" danger onClick={() => handleDeleteProvider(p.name)}>删除</Button>
                </Space>
              }
            >
              <Descriptions column={1} size="small">
                <Descriptions.Item label="Provider">{p.provider}</Descriptions.Item>
                <Descriptions.Item label="模型ID">{p.model_id}</Descriptions.Item>
                <Descriptions.Item label="API地址">{p.base_url}</Descriptions.Item>
                <Descriptions.Item label="API Key">{p.api_key || '-'}</Descriptions.Item>
              </Descriptions>
            </Card>
          </Col>
        ))}
      </Row>

      {/* 任务→模型映射（可编辑） */}
      <Card title="任务→模型映射" size="small" style={{ marginTop: 16 }}>
        <AutoHeightTable
          scroll={{ x: 'max-content', y: 'calc(100vh - 420px)' }}
          dataSource={Object.entries(taskMappings).map(([task, model]) => ({
            key: task, task, model,
          }))}
          columns={[
            { title: '任务类型', dataIndex: 'task', key: 'task', render: (v: string) => taskNames[v] || v },
            {
              title: '使用模型',
              dataIndex: 'model',
              key: 'model',
              render: (model: string, r: any) => {
                if (editingTask === r.key) {
                  return (
                    <Select
                      defaultValue={model}
                      style={{ width: 180 }}
                      onChange={(v) => handleSaveTaskMapping(r.key, v)}
                      onBlur={() => setEditingTask(null)}
                      autoFocus
                    >
                      {providers
                        .filter((p: ModelProvider) => p.enabled)
                        .map((p: ModelProvider) => (
                          <Select.Option key={p.name} value={p.name}>{p.name}</Select.Option>
                        ))}
                    </Select>
                  );
                }
                return (
                  <Tag color="blue" style={{ cursor: 'pointer' }} onClick={() => setEditingTask(r.key)}>
                    {model} ✏️
                  </Tag>
                );
              },
            },
          ]}
          pagination={false}
          size="small"
        />
        <Text type="secondary" style={{ marginTop: 8, display: 'block' }}>点击模型标签可切换模型</Text>
      </Card>

      {/* Provider 编辑弹窗 */}
      <ProviderFormModal
        open={providerModal}
        provider={editingProvider}
        onCancel={() => { setProviderModal(false); setEditingProvider(null); }}
        onSave={handleProviderSave}
      />
    </div>
  );
}

export default ModelConfig;
