/**
 * 模型 Provider 编辑/新增表单弹窗
 */
import React, { useState, useEffect } from 'react';
import { Modal, Input, Radio, Space, Typography, message } from 'antd';
import type { ModelProvider } from '../types';

const { Text } = Typography;

interface ProviderFormModalProps {
  open: boolean;
  provider?: ModelProvider | null;
  onCancel: () => void;
  onSave: (p: ModelProvider) => void;
}

function ProviderFormModal({
  open,
  provider,
  onCancel,
  onSave,
}: ProviderFormModalProps) {
  const [form, setForm] = useState<ModelProvider>(
    provider || {
      provider: '',
      model_id: '',
      name: '',
      base_url: '',
      api_key: '',
      enabled: true,
    }
  );

  useEffect(() => {
    if (open) {
      setForm(
        provider || {
          provider: '',
          model_id: '',
          name: '',
          base_url: '',
          api_key: '',
          enabled: true,
        }
      );
    }
  }, [open, provider]);

  return (
    <Modal
      title={provider ? '编辑模型 Provider' : '新增模型 Provider'}
      open={open}
      onCancel={onCancel}
      width={600}
      onOk={() => {
        if (!form.name || !form.model_id) {
          message.warning('名称和模型ID不能为空');
          return;
        }
        onSave(form);
      }}
    >
      <Space direction="vertical" style={{ width: '100%' }} size="middle">
        <div>
          <Text>名称</Text>
          <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="如 TP/ModelB5.1" />
        </div>
        <div>
          <Text>Provider</Text>
          <Input value={form.provider} onChange={(e) => setForm({ ...form, provider: e.target.value })} placeholder="如 cloud_provider-token" />
        </div>
        <div>
          <Text>模型ID</Text>
          <Input value={form.model_id} onChange={(e) => setForm({ ...form, model_id: e.target.value })} placeholder="如 llm-b" />
        </div>
        <div>
          <Text>API地址</Text>
          <Input value={form.base_url} onChange={(e) => setForm({ ...form, base_url: e.target.value })} placeholder="https://..." />
        </div>
        <div>
          <Text>API Key（留空则不修改）</Text>
          <Input.Password value={form.api_key} onChange={(e) => setForm({ ...form, api_key: e.target.value })} placeholder="输入 API Key" />
        </div>
        <div>
          <Text>状态</Text>
          <Radio.Group value={form.enabled} onChange={(e) => setForm({ ...form, enabled: e.target.value })}>
            <Radio value={true}>启用</Radio>
            <Radio value={false}>禁用</Radio>
          </Radio.Group>
        </div>
      </Space>
    </Modal>
  );
}

export default ProviderFormModal;
