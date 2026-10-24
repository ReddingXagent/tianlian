import { copyToClipboard } from '../../utils/clipboard';
/**
 * API密钥管理页面
 */
import React, { useState, useEffect } from 'react';
import {
  Card, Table, Button, Modal, Form, Input, Select, Tag, Space, message,
  Popconfirm, Descriptions, Statistic, Row, Col, Switch, InputNumber, Tooltip
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import {
  KeyOutlined, PlusOutlined, DeleteOutlined, SyncOutlined,
  EyeOutlined, BarChartOutlined, CopyOutlined, SafetyOutlined
} from '@ant-design/icons';
import api from '../../api';

const { TextArea } = Input;

interface ApiKey {
  id: number;
  name: string;
  key_prefix: string;
  description?: string;
  scopes: string[];
  rate_limit: number;
  is_active: boolean;
  is_revoked: boolean;
  created_at: string;
  expires_at?: string;
  last_used_at?: string;
}

const ApiKeyPage: React.FC = () => {
  const [keys, setKeys] = useState<ApiKey[]>([]);
  const [loading, setLoading] = useState(false);
  const [createModalVisible, setCreateModalVisible] = useState(false);
  const [usageModalVisible, setUsageModalVisible] = useState(false);
  const [selectedKey, setSelectedKey] = useState<ApiKey | null>(null);
  const [usageStats, setUsageStats] = useState<any>(null);
  const [newKey, setNewKey] = useState<string>('');
  const [form] = Form.useForm();

  const availableScopes = [
    'devices:read', 'devices:write',
    'alarms:read', 'alarms:write',
    'stations:read', 'stations:write',
    'reports:read', 'reports:write',
    'telemetry:read', 'telemetry:write',
    'health:read',
  ];

  const fetchKeys = async () => {
    setLoading(true);
    try {
      const res = await api.get('/api-keys');
      const data = res.data as any;
      setKeys(data.items || data || []);
    } catch (error) {
      message.error('获取API密钥列表失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchKeys();
  }, []);

  const handleCreate = async (values: any) => {
    try {
      const res = await api.post('/api-keys', values);
      const data = res.data as any;
      message.success('API密钥创建成功');
      setNewKey(data.api_key || '');
      setCreateModalVisible(false);
      form.resetFields();
      fetchKeys();
    } catch (error) {
      message.error('创建失败');
    }
  };

  const handleRevoke = async (id: number) => {
    try {
      await api.delete(`/api-keys/${id}`);
      message.success('密钥已撤销');
      fetchKeys();
    } catch (error) {
      message.error('撤销失败');
    }
  };

  const handleRotate = async (id: number) => {
    try {
      const res = await api.post(`/api-keys/${id}/rotate`);
      const data = res.data as any;
      message.success('密钥已轮换');
      setNewKey(data.api_key || '');
      setSelectedKey(keys.find(k => k.id === id) || null);
      setUsageModalVisible(true);
      fetchKeys();
    } catch (error) {
      message.error('轮换失败');
    }
  };

  const handleViewUsage = async (key: ApiKey) => {
    setSelectedKey(key);
    try {
      const res = await api.get(`/api-keys/${key.id}/usage`, { params: { days: 7 } });
      setUsageStats(res.data);
      setUsageModalVisible(true);
    } catch (error) {
      message.error('获取使用统计失败');
    }
  };

  const copyKey = (key: string) => {
    copyToClipboard(key);
    message.success('密钥已复制到剪贴板');
  };

  const columns: ColumnsType<ApiKey> = [
    { title: 'ID', dataIndex: 'id', width: 60 },
    { title: '名称', dataIndex: 'name', width: 150 },
    { title: '密钥前缀', dataIndex: 'key_prefix', width: 120, render: (v: string) => <Tag>{v}...</Tag> },
    { title: '权限范围', dataIndex: 'scopes', width: 130, render: (scopes: string[]) => (
      <Space size="small" wrap>
        {scopes?.map(s => <Tag color="blue" key={s} style={{ marginInlineEnd: 0 }}>{s}</Tag>)}
      </Space>
    )},
    { title: '速率限制', dataIndex: 'rate_limit', width: 100, render: (v: number) => `${v}/min` },
    { title: '状态', width: 100, render: (_: any, r: ApiKey) => (
      r.is_revoked ? <Tag color="red">已撤销</Tag> :
      r.is_active ? <Tag color="green">活跃</Tag> : <Tag color="orange">禁用</Tag>
    )},
    { title: '创建时间', dataIndex: 'created_at', width: 160, render: (v: string) => v?.slice(0, 19) },
    { title: '过期时间', dataIndex: 'expires_at', width: 160, render: (v: string) => v?.slice(0, 19) || '永久' },
    { title: '最后使用', dataIndex: 'last_used_at', width: 160, render: (v: string) => v?.slice(0, 19) || '从未' },
    { title: '操作', width: 180, fixed: 'right', render: (_: any, r: ApiKey) => (
      <Space size="small">
        <Tooltip title="使用统计">
          <Button size="small" icon={<BarChartOutlined />} onClick={() => handleViewUsage(r)} />
        </Tooltip>
        <Tooltip title="轮换密钥">
          <Button size="small" icon={<SyncOutlined />} onClick={() => handleRotate(r.id)} disabled={r.is_revoked} />
        </Tooltip>
        <Popconfirm title="确认撤销该密钥？" onConfirm={() => handleRevoke(r.id)}>
          <Button size="small" danger icon={<DeleteOutlined />} disabled={r.is_revoked} />
        </Popconfirm>
      </Space>
    )},
  ];

  return (
    <Card title={<><KeyOutlined /> API密钥管理</>} extra={
      <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateModalVisible(true)}>创建密钥</Button>
    }>
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}><Statistic title="总密钥数" value={keys.length} /></Col>
        <Col span={6}><Statistic title="活跃密钥" value={keys.filter(k => k.is_active && !k.is_revoked).length} /></Col>
        <Col span={6}><Statistic title="已撤销" value={keys.filter(k => k.is_revoked).length} /></Col>
        <Col span={6}><Statistic title="最近使用" value={keys.filter(k => k.last_used_at).length} /></Col>
      </Row>

      <Table dataSource={keys} columns={columns} rowKey="id" loading={loading} scroll={{ x: 1320 }} />

      {/* 创建密钥弹窗 */}
      <Modal title="创建API密钥" open={createModalVisible} onCancel={() => setCreateModalVisible(false)} footer={null} width={600}>
        <Form form={form} onFinish={handleCreate} layout="vertical">
          <Form.Item name="name" label="密钥名称" rules={[{ required: true }]}>
            <Input placeholder="如：数据上报服务" />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <TextArea rows={2} placeholder="用途说明" />
          </Form.Item>
          <Form.Item name="scopes" label="权限范围">
            <Select mode="multiple" placeholder="选择权限" options={availableScopes.map(s => ({ label: s, value: s }))} />
          </Form.Item>
          <Form.Item name="ip_whitelist" label="IP白名单">
            <Select mode="tags" placeholder="输入IP地址" />
          </Form.Item>
          <Form.Item name="rate_limit" label="速率限制(次/分钟)" initialValue={1000}>
            <InputNumber min={1} max={10000} />
          </Form.Item>
          <Form.Item name="expires_days" label="有效期(天)">
            <InputNumber min={1} max={365} placeholder="永久有效" />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" block>创建</Button>
          </Form.Item>
        </Form>
      </Modal>

      {/* 使用统计弹窗 */}
      <Modal title="密钥详情与使用统计" open={usageModalVisible} onCancel={() => { setUsageModalVisible(false); setNewKey(''); }} width={700} footer={null}>
        {selectedKey && (
          <Descriptions bordered size="small" column={2}>
            <Descriptions.Item label="名称">{selectedKey.name}</Descriptions.Item>
            <Descriptions.Item label="密钥前缀">{selectedKey.key_prefix}</Descriptions.Item>
            <Descriptions.Item label="权限">{selectedKey.scopes?.join(', ')}</Descriptions.Item>
            <Descriptions.Item label="速率限制">{selectedKey.rate_limit}/min</Descriptions.Item>
          </Descriptions>
        )}
        {newKey && (
          <Card size="small" style={{ marginTop: 16, background: '#fffbe6' }}>
            <Space>
              <SafetyOutlined style={{ color: '#faad14' }} />
              <span>新生成的密钥（仅显示一次）：</span>
              <Tag color="orange">{newKey}</Tag>
              <Button size="small" icon={<CopyOutlined />} onClick={() => copyKey(newKey)}>复制</Button>
            </Space>
          </Card>
        )}
        {usageStats && (
          <Card size="small" title="近7天使用统计" style={{ marginTop: 16 }}>
            <Row gutter={16}>
              <Col span={6}><Statistic title="总请求" value={usageStats.total_requests || 0} /></Col>
              <Col span={6}><Statistic title="平均耗时" value={usageStats.avg_duration_ms || 0} suffix="ms" /></Col>
            </Row>
            <div style={{ marginTop: 12 }}>
              <strong>状态码分布：</strong>
              <Space style={{ marginLeft: 8 }}>
                {usageStats.status_distribution?.map((s: any) => (
                  <Tag key={s.status} color={s.status < 300 ? 'green' : 'red'}>{s.status}: {s.count}</Tag>
                ))}
              </Space>
            </div>
            <div style={{ marginTop: 12 }}>
              <strong>Top 10 路径：</strong>
              <ul style={{ margin: 8, paddingLeft: 20 }}>
                {usageStats.top_paths?.map((p: any) => (
                  <li key={p.path}>{p.path} - {p.count}次, 平均{p.avg_duration}ms</li>
                ))}
              </ul>
            </div>
          </Card>
        )}
      </Modal>
    </Card>
  );
};

export default ApiKeyPage;