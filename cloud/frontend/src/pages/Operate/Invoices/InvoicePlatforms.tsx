/**
 * 天链 V3 — 开票平台设置页 (百旺/航信/诺诺)
 * 团队级配置: CRUD + 设默认 + 启用/禁用
 */
import React, { useEffect, useState, useCallback } from 'react';
import { Table, Tag, Button, Space, Modal, Form, Input, Select, Switch, Popconfirm, message, Tooltip, Collapse } from 'antd';
import { ReloadOutlined, PlusOutlined, EditOutlined, DeleteOutlined, StarOutlined, StarFilled, EyeOutlined, EyeInvisibleOutlined } from '@ant-design/icons';
import { invoicePlatformAPI } from '../../../api/settlement';
import { getCurrentTeamId } from '../../../utils/team';

interface PlatformItem {
  id: number;
  team_id: number;
  platform_type: string;
  platform_name: string;
  api_url: string | null;
  app_key: string | null;
  app_secret: string | null;
  taxpayer_id: string | null;
  tax_classification_code: string | null;
  is_default: boolean;
  enabled: boolean;
  remark: string | null;
  access_token_url: string | null;
  private_key_enc: string | null;
  device_no: string | null;
  callback_url: string | null;
  ext_config_json: string | null;
  created_at: string | null;
  updated_at: string | null;
}

const PLATFORM_TYPE_LABELS: Record<string, string> = {
  baiwang: '百旺',
  hangxin: '航信',
  nuonuo: '诺诺',
  other: '其他',
};

const PLATFORM_COLORS: Record<string, string> = {
  baiwang: 'blue',
  hangxin: 'green',
  nuonuo: 'orange',
  other: 'default',
};

/** 校验扩展配置 JSON 合法性, 失败提示并返回 false */
const validateExtConfig = (raw: string): boolean => {
  if (!raw || !raw.trim()) return true; // 空值允许
  try {
    JSON.parse(raw);
    return true;
  } catch {
    message.error('扩展配置(JSON) 格式不合法');
    return false;
  }
};

const InvoicePlatformPage: React.FC = () => {
  const [data, setData] = useState<PlatformItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [keyVisible, setKeyVisible] = useState(false);
  const [editing, setEditing] = useState<PlatformItem | null>(null);
  const [form] = Form.useForm();
  const teamId = getCurrentTeamId();

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const { data: res } = await invoicePlatformAPI.list({ team_id: teamId });
      const d = (res as any)?.data ?? res;
      setData(d?.items ?? []);
    } catch {
      setData([]);
    } finally {
      setLoading(false);
    }
  }, [teamId]);

  useEffect(() => { loadData(); }, [loadData]);

  const handleAdd = () => {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({
      platform_type: 'baiwang',
      enabled: true,
      is_default: false,
    });
    setModalOpen(true);
  };

  const handleEdit = (record: PlatformItem) => {
    setEditing(record);
    form.setFieldsValue(record);
    setModalOpen(true);
  };

  const handleDelete = async (id: number) => {
    try {
      await invoicePlatformAPI.delete(id);
      message.success('删除成功');
      loadData();
    } catch {
      message.error('删除失败');
    }
  };

  const handleSetDefault = async (id: number) => {
    try {
      await invoicePlatformAPI.setDefault(id);
      message.success('已设为团队默认');
      loadData();
    } catch {
      message.error('设置失败');
    }
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      if (editing) {
        await invoicePlatformAPI.update(editing.id, values);
        message.success('更新成功');
      } else {
        await invoicePlatformAPI.create({ team_id: teamId, ...values });
        message.success('创建成功');
      }
      setModalOpen(false);
      loadData();
    } catch (err: any) {
      if (err?.errorFields) return; // 表单校验错误
      message.error(editing ? '更新失败' : '创建失败');
    }
  };

  const columns = [
    {
      title: '默认',
      dataIndex: 'is_default',
      width: 60,
      render: (isDefault: boolean, record: PlatformItem) =>
        isDefault ? (
          <Tag color="gold" icon={<StarFilled />}>默认</Tag>
        ) : (
          <Tooltip title="设为默认">
            <Button type="text" size="small" icon={<StarOutlined />} onClick={() => handleSetDefault(record.id)} />
          </Tooltip>
        ),
    },
    {
      title: '平台类型',
      dataIndex: 'platform_type',
      width: 100,
      render: (t: string) => <Tag color={PLATFORM_COLORS[t] || 'default'}>{PLATFORM_TYPE_LABELS[t] || t}</Tag>,
    },
    { title: '平台名称', dataIndex: 'platform_name', width: 180 },
    { title: 'API地址', dataIndex: 'api_url', ellipsis: true },
    { title: 'AppKey', dataIndex: 'app_key', ellipsis: true },
    { title: '纳税人识别号', dataIndex: 'taxpayer_id', width: 180 },
    {
      title: '状态',
      dataIndex: 'enabled',
      width: 80,
      render: (enabled: boolean) =>
        enabled ? <Tag color="success">启用</Tag> : <Tag color="error">禁用</Tag>,
    },
    {
      title: '操作',
      width: 120,
      render: (_: any, record: PlatformItem) => (
        <Space size="small">
          <Button type="link" size="small" icon={<EditOutlined />} onClick={() => handleEdit(record)} />
          <Popconfirm title="确定删除该平台配置?" onConfirm={() => handleDelete(record.id)}>
            <Button type="link" size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h3 style={{ margin: 0 }}>开票平台设置</h3>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={loadData} loading={loading}>刷新</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={handleAdd}>新增平台</Button>
        </Space>
      </div>

      <Table
        columns={columns}
        dataSource={data}
        rowKey="id"
        loading={loading}
        pagination={false}
        size="middle"
      />

      <Modal
        title={editing ? '编辑开票平台' : '新增开票平台'}
        open={modalOpen}
        onOk={handleSubmit}
        onCancel={() => setModalOpen(false)}
        width={640}
        destroyOnHidden
      >
        <Form form={form} layout="vertical">
          <Form.Item name="platform_type" label="平台类型" rules={[{ required: true }]}>
            <Select>
              {Object.entries(PLATFORM_TYPE_LABELS).map(([k, v]) => (
                <Select.Option key={k} value={k}>{v}</Select.Option>
              ))}
            </Select>
          </Form.Item>
          <Form.Item name="platform_name" label="平台名称" rules={[{ required: true, message: '请输入平台名称' }]}>
            <Input placeholder="如：百旺生产环境" />
          </Form.Item>
          <Form.Item name="api_url" label="API地址">
            <Input placeholder="https://api.baiwang.com" />
          </Form.Item>
          <Form.Item name="access_token_url" label="Token换取地址">
            <Input placeholder="https://api.baiwang.com/oauth/token" />
          </Form.Item>
          <Space style={{ display: 'flex' }}>
            <Form.Item name="app_key" label="AppKey" style={{ flex: 1 }}>
              <Input />
            </Form.Item>
            <Form.Item name="app_secret" label="AppSecret" style={{ flex: 1 }}>
              <Input.Password />
            </Form.Item>
          </Space>
          <Space style={{ display: 'flex' }}>
            <Form.Item name="taxpayer_id" label="纳税人识别号" style={{ flex: 1 }}>
              <Input />
            </Form.Item>
            <Form.Item name="tax_classification_code" label="税收分类编码" style={{ flex: 1 }}>
              <Input />
            </Form.Item>
          </Space>
          {/* 按平台类型条件渲染: 设备编号(百旺/航信) */}
          <Form.Item
            noStyle
            shouldUpdate={(prev, cur) => prev.platform_type !== cur.platform_type}
          >
            {({ getFieldValue }) =>
              ['baiwang', 'hangxin'].includes(getFieldValue('platform_type')) ? (
                <Form.Item name="device_no" label="设备/终端编号">
                  <Input placeholder="如：01234567890" />
                </Form.Item>
              ) : null
            }
          </Form.Item>
          {/* 按平台类型条件渲染: RSA私钥(诺诺) */}
          <Form.Item
            noStyle
            shouldUpdate={(prev, cur) => prev.platform_type !== cur.platform_type}
          >
            {({ getFieldValue }) =>
              getFieldValue('platform_type') === 'nuonuo' ? (
                <Form.Item name="private_key_enc" label={<Space size="small">RSA私钥<Button type="text" size="small" icon={keyVisible ? <EyeInvisibleOutlined /> : <EyeOutlined />} onClick={() => setKeyVisible(v => !v)} /></Space>}>
                <Input.TextArea rows={4} placeholder={"-----BEGIN RSA PRIVATE KEY-----\nMII...\n-----END RSA PRIVATE KEY-----"} autoComplete="off" style={{ fontFamily: "monospace", fontSize: 12, ...(keyVisible ? {} : { color: "transparent", textShadow: "0 0 6px rgba(0,0,0,0.6)" }) }} />
                </Form.Item>
              ) : null
            }
          </Form.Item>
          <Form.Item name="remark" label="备注">
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item name="callback_url" label="开票回调地址">
            <Input placeholder="https://your-domain.com/api/invoice/callback" />
          </Form.Item>
          {/* 高级配置: 扩展JSON */}
          <Collapse
            items={[{
              key: 'advanced',
              label: '高级配置',
              children: (
                <Form.Item name="ext_config_json" label="扩展配置(JSON)">
                  <Input.TextArea
                    rows={3}
                    placeholder='{"seller_bank":"XX银行"}'
                    onBlur={(e) => validateExtConfig(e.target.value)}
                  />
                </Form.Item>
              ),
            }]}
          />
          <Space>
            <Form.Item name="is_default" label="设为团队默认" valuePropName="checked">
              <Switch />
            </Form.Item>
            <Form.Item name="enabled" label="启用" valuePropName="checked">
              <Switch />
            </Form.Item>
          </Space>
        </Form>
      </Modal>
    </div>
  );
};

export default InvoicePlatformPage;
