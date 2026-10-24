/**
 * 消息通知管理中心 - P1功能
 * 
 * 三大功能模块：
 * 1. 消息发送 - 选择模板/手动编辑/选择渠道/发送
 * 2. 消息模板 - CRUD管理
 * 3. 发送记录 - 历史记录查询
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
  Card, Tabs, Table, Button, Modal, Form, Input, Select, Tag, Space,
  message, Popconfirm, Switch, Row, Col, Statistic, Descriptions, Input as SearchInput
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import {
  MessageOutlined, SendOutlined, FileTextOutlined, HistoryOutlined,
  PlusOutlined, EditOutlined, DeleteOutlined, MailOutlined,
  MobileOutlined, WechatOutlined, BellOutlined, LinkOutlined,
} from '@ant-design/icons';
import api from '../../api';
import { fetchAllPages } from '../../api/fetchAll';

const { TabPane } = Tabs;
const { TextArea } = Input;

// ─── 类型定义 ────────────────────────────────────

interface NotificationTemplate {
  id: number;
  name: string;
  template_type: string;
  title: string;
  content: string;
  channels: string[];
  variables: any;
  enabled: boolean;
  created_at?: string;
}

interface NotificationMessage {
  id: number;
  template_id: number | null;
  template_name: string | null;
  title: string;
  content: string;
  channel: string;
  receivers: string[];
  sender: string;
  status: string;
  result_message: string | null;
  sent_at: string | null;
  created_at?: string;
}

interface MessageStats {
  total_templates: number;
  total_messages: number;
  sent_today: number;
  failed_count: number;
  channel_distribution: Record<string, number>;
}

// ─── 渠道配置 ────────────────────────────────────

const CHANNEL_OPTIONS = [
  { label: '短信', value: 'sms', icon: <MobileOutlined />, color: 'green' },
  { label: '邮件', value: 'email', icon: <MailOutlined />, color: 'blue' },
  { label: 'IM-B', value: 'im_b', icon: <WechatOutlined />, color: 'cyan' },
  { label: 'IM', value: 'im', icon: <BellOutlined />, color: 'purple' },
  { label: 'App推送', value: 'app_push', icon: <SendOutlined />, color: 'orange' },
  { label: 'Webhook', value: 'webhook', icon: <LinkOutlined />, color: 'geekblue' },
];

const CHANNEL_MAP: Record<string, { icon: React.ReactNode; color: string }> = {};
CHANNEL_OPTIONS.forEach(c => { CHANNEL_MAP[c.value] = { icon: c.icon, color: c.color }; });

const TEMPLATE_TYPES = [
  { label: '系统通知', value: 'system' },
  { label: '充电通知', value: 'charging' },
  { label: '维护通知', value: 'maintenance' },
  { label: '营销消息', value: 'marketing' },
  { label: '自定义', value: 'custom' },
];

const STATUS_MAP: Record<string, string> = {
  pending: 'orange', sent: 'green', failed: 'red', delivered: 'blue', read: 'cyan',
};

// ─── 主组件 ─────────────────────────────────────────

const MessageCenter: React.FC = () => {
  const [activeTab, setActiveTab] = useState('send');
  const [stats, setStats] = useState<MessageStats | null>(null);

  // 消息发送
  const [sendForm] = Form.useForm();
  const [sending, setSending] = useState(false);

  // 模板管理
  const [templates, setTemplates] = useState<NotificationTemplate[]>([]);
  const [tplLoading, setTplLoading] = useState(false);
  const [tplModalVisible, setTplModalVisible] = useState(false);
  const [editingTpl, setEditingTpl] = useState<NotificationTemplate | null>(null);
  const [tplForm] = Form.useForm();

  // 发送记录
  const [messages, setMessages] = useState<NotificationMessage[]>([]);
  const [msgLoading, setMsgLoading] = useState(false);
  const [msgPage, setMsgPage] = useState(1);
  const [msgTotal, setMsgTotal] = useState(0);
  const [msgFilter, setMsgFilter] = useState<{ status?: string; channel?: string }>({});

  // ─── 统计数据 ───
  const fetchStats = useCallback(async () => {
    try {
      const res = await api.get('/notifications/stats');
      setStats(res.data as any);
    } catch (e) {
      // 静默失败
    }
  }, []);

  useEffect(() => {
    fetchStats();
  }, [fetchStats]);

  // ─── 消息发送 ───
  const handleSend = async (values: any) => {
    setSending(true);
    try {
      await api.post('/notifications/send', values);
      message.success('消息发送成功');
      sendForm.resetFields();
      fetchStats();
      // 切换到记录页
      fetchMessages(msgPage);
    } catch (e: any) {
      message.error(e?.response?.data?.message || '发送失败');
    } finally {
      setSending(false);
    }
  };

  // ─── 模板管理 ───
  const fetchTemplates = useCallback(async () => {
    setTplLoading(true);
    try {
      const items = await fetchAllPages<any>((params) => api.get('/notifications/templates', { params }));
      setTemplates(items);
    } catch (e) {
      message.error('加载消息模板失败');
      setTemplates([]);
    } finally {
      setTplLoading(false);
    }
  }, []);

  useEffect(() => {
    if (activeTab === 'templates') fetchTemplates();
  }, [activeTab, fetchTemplates]);

  const handleCreateTpl = async (values: any) => {
    try {
      if (editingTpl) {
        await api.put(`/notifications/templates/${editingTpl.id}`, values);
        message.success('模板更新成功');
      } else {
        await api.post('/notifications/templates', values);
        message.success('模板创建成功');
      }
      setTplModalVisible(false);
      setEditingTpl(null);
      tplForm.resetFields();
      fetchTemplates();
    } catch (e: any) {
      message.error(e?.response?.data?.message || '操作失败');
    }
  };

  const handleDeleteTpl = async (id: number) => {
    try {
      await api.delete(`/notifications/templates/${id}`);
      message.success('模板已删除');
      fetchTemplates();
    } catch (e) {
      message.error('删除失败');
    }
  };

  // ─── 发送记录 ───
  const fetchMessages = useCallback(async (page: number = 1) => {
    setMsgLoading(true);
    try {
      const params: any = { page, page_size: 20 };
      if (msgFilter.status) params.status = msgFilter.status;
      if (msgFilter.channel) params.channel = msgFilter.channel;
      const res = await api.get('/notifications/messages', { params });
      const data = res.data as any;
      setMessages(data?.items || []);
      setMsgTotal(data?.total || 0);
      setMsgPage(page);
    } catch (e) {
      // 静默
    } finally {
      setMsgLoading(false);
    }
  }, [msgFilter]);

  useEffect(() => {
    if (activeTab === 'records') fetchMessages();
  }, [activeTab, fetchMessages, msgFilter]);

  // ─── 模板表格列 ───
  const tplColumns: ColumnsType<NotificationTemplate> = [
    { title: 'ID', dataIndex: 'id', width: 60 },
    { title: '模板名称', dataIndex: 'name', width: 160 },
    { title: '类型', dataIndex: 'template_type', width: 100,
      render: (v: string) => <Tag>{TEMPLATE_TYPES.find(t => t.value === v)?.label || v}</Tag> },
    { title: '标题', dataIndex: 'title', width: 200, ellipsis: true },
    { title: '渠道', dataIndex: 'channels', width: 180,
      render: (chs: string[]) => (
        <Space size="small">{chs?.map(c => {
          const ch = CHANNEL_MAP[c];
          return ch ? <Tag icon={ch.icon} color={ch.color} key={c}>{c}</Tag> : <Tag key={c}>{c}</Tag>;
        })}</Space>
      )},
    { title: '状态', dataIndex: 'enabled', width: 80,
      render: (v: boolean) => <Tag color={v ? 'green' : 'default'}>{v ? '启用' : '禁用'}</Tag> },
    { title: '创建时间', dataIndex: 'created_at', width: 150,
      render: (v: string) => v?.slice(0, 19) || '-' },
    { title: '操作', width: 120, fixed: 'right',
      render: (_: any, r: NotificationTemplate) => (
        <Space size="small">
          <Button size="small" icon={<EditOutlined />} onClick={() => {
            setEditingTpl(r);
            tplForm.setFieldsValue(r);
            setTplModalVisible(true);
          }}>编辑</Button>
          <Popconfirm title="确认删除？" onConfirm={() => handleDeleteTpl(r.id)}>
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      )},
  ];

  // ─── 消息记录表格列 ───
  const msgColumns: ColumnsType<NotificationMessage> = [
    { title: 'ID', dataIndex: 'id', width: 60 },
    { title: '标题', dataIndex: 'title', width: 200, ellipsis: true },
    { title: '渠道', dataIndex: 'channel', width: 100,
      render: (v: string) => {
        const ch = CHANNEL_MAP[v];
        return ch ? <Tag icon={ch.icon} color={ch.color}>{v}</Tag> : <Tag>{v}</Tag>;
      }},
    { title: '模板', dataIndex: 'template_name', width: 120,
      render: (v: string) => v ? <Tag>{v}</Tag> : '-' },
    { title: '接收人', dataIndex: 'receivers', width: 150,
      render: (rcs: string[]) => (
        <Space size="small">{rcs?.slice(0, 3).map(r => <Tag key={r}>{r}</Tag>)}
          {rcs?.length > 3 && <span>+{rcs.length - 3}</span>}
        </Space>
      )},
    { title: '状态', dataIndex: 'status', width: 80,
      render: (v: string) => <Tag color={STATUS_MAP[v] || 'default'}>{v}</Tag> },
    { title: '发送人', dataIndex: 'sender', width: 80 },
    { title: '发送时间', dataIndex: 'sent_at', width: 150,
      render: (v: string) => v?.slice(0, 19) || v?.slice(0, 19) || '-' },
    { title: '操作', width: 60, fixed: 'right',
      render: (_: any, r: NotificationMessage) => (
        <Popconfirm title="确认删除？" onConfirm={async () => {
          try {
            await api.delete(`/notifications/messages/${r.id}`);
            message.success('已删除');
            fetchMessages(msgPage);
          } catch (e) { message.error('删除失败'); }
        }}>
          <Button size="small" danger icon={<DeleteOutlined />} />
        </Popconfirm>
      )},
  ];

  return (
    <Card title={<><MessageOutlined /> 消息通知管理</>}>
      {/* 统计概览 */}
      {stats && (
        <Row gutter={16} style={{ marginBottom: 16 }}>
          <Col span={4}><Statistic title="消息模板" value={stats.total_templates} prefix={<FileTextOutlined />} /></Col>
          <Col span={4}><Statistic title="总消息数" value={stats.total_messages} prefix={<HistoryOutlined />} /></Col>
          <Col span={4}><Statistic title="今日发送" value={stats.sent_today} prefix={<SendOutlined />} valueStyle={{ color: '#3f8600' }} /></Col>
          <Col span={4}><Statistic title="失败数" value={stats.failed_count} prefix={<DeleteOutlined />} valueStyle={{ color: '#cf1322' }} /></Col>
          <Col span={8}>
            <Space size="small">
              {Object.entries(stats.channel_distribution || {}).map(([ch, count]) => {
                const channelInfo = CHANNEL_MAP[ch];
                return <Tag key={ch} icon={channelInfo?.icon} color={channelInfo?.color}>{ch}: {count as number}</Tag>;
              })}
            </Space>
          </Col>
        </Row>
      )}

      <Tabs activeKey={activeTab} onChange={setActiveTab}>
        <TabPane tab={<><SendOutlined /> 消息发送</>} key="send">
          <Card size="small">
            <Form form={sendForm} layout="vertical" onFinish={handleSend} style={{ maxWidth: 600 }}>
              <Form.Item name="template_id" label="选择模板（可选）">
                <Select
                  allowClear
                  placeholder="选择消息模板（不选则手动填写内容）"
                  onChange={(templateId) => {
                    if (templateId) {
                      const tpl = templates.find(t => t.id === templateId);
                      if (tpl) {
                        sendForm.setFieldsValue({
                          title: tpl.title,
                          content: tpl.content,
                          channels: tpl.channels,
                        });
                      }
                    }
                  }}
                  options={templates.map(t => ({ label: t.name, value: t.id }))}
                />
              </Form.Item>
              <Form.Item name="title" label="消息标题">
                <Input placeholder="消息标题" />
              </Form.Item>
              <Form.Item name="content" label="消息内容" rules={[{ required: true, message: '请输入消息内容' }]}>
                <TextArea rows={4} placeholder="请输入消息内容，支持变量替换如 {user_name}" />
              </Form.Item>
              <Form.Item name="channel" label="发送渠道" rules={[{ required: true }]}
                initialValue="app_push">
                <Select options={CHANNEL_OPTIONS.map(c => ({
                  label: <Space>{c.icon} {c.label}</Space>,
                  value: c.value,
                }))} />
              </Form.Item>
              <Form.Item name="receivers" label="接收人" rules={[{ required: true, message: '请选择接收人' }]}
                initialValue={['all']}>
                <Select mode="tags" placeholder="输入接收人标识: user:xxx, team:xxx, role:xxx, all" />
              </Form.Item>
              <Form.Item>
                <Button type="primary" htmlType="submit" loading={sending} icon={<SendOutlined />} block>
                  发送消息
                </Button>
              </Form.Item>
            </Form>
          </Card>
        </TabPane>

        <TabPane tab={<><FileTextOutlined /> 消息模板</>} key="templates">
          <div style={{ marginBottom: 16, textAlign: 'right' }}>
            <Button type="primary" icon={<PlusOutlined />} onClick={() => {
              setEditingTpl(null);
              tplForm.resetFields();
              setTplModalVisible(true);
            }}>创建模板</Button>
          </div>
          <Table dataSource={templates} columns={tplColumns} rowKey="id"
            loading={tplLoading} scroll={{ x: 1000 }} size="small" />

          {/* 模板编辑弹窗 */}
          <Modal
            title={editingTpl ? '编辑模板' : '创建模板'}
            open={tplModalVisible}
            onCancel={() => { setTplModalVisible(false); setEditingTpl(null); }}
            footer={null}
            width={600}
          >
            <Form form={tplForm} onFinish={handleCreateTpl} layout="vertical"
              initialValues={{ template_type: 'system', channels: [], enabled: true }}>
              <Form.Item name="name" label="模板名称" rules={[{ required: true }]}>
                <Input placeholder="如：充电完成通知" />
              </Form.Item>
              <Form.Item name="template_type" label="模板类型" rules={[{ required: true }]}>
                <Select options={TEMPLATE_TYPES} />
              </Form.Item>
              <Form.Item name="title" label="消息标题模板">
                <Input placeholder="如：{station_name} 充电完成通知" />
              </Form.Item>
              <Form.Item name="content" label="内容模板">
                <TextArea rows={4} placeholder="消息内容模板，支持 {user_name}, {amount} 等变量" />
              </Form.Item>
              <Form.Item name="channels" label="默认渠道">
                <Select mode="multiple" options={CHANNEL_OPTIONS.map(c => ({
                  label: <Space>{c.icon} {c.label}</Space>, value: c.value,
                }))} />
              </Form.Item>
              <Form.Item name="enabled" label="启用" valuePropName="checked">
                <Switch />
              </Form.Item>
              <Button type="primary" htmlType="submit" block>
                {editingTpl ? '更新模板' : '创建模板'}
              </Button>
            </Form>
          </Modal>
        </TabPane>

        <TabPane tab={<><HistoryOutlined /> 发送记录</>} key="records">
          <div style={{ marginBottom: 16, display: 'flex', gap: 8 }}>
            <Select allowClear placeholder="状态筛选" style={{ width: 120 }}
              onChange={(v) => setMsgFilter(prev => ({ ...prev, status: v }))}
              options={[
                { label: '待发送', value: 'pending' },
                { label: '已发送', value: 'sent' },
                { label: '发送失败', value: 'failed' },
                { label: '已送达', value: 'delivered' },
              ]} />
            <Select allowClear placeholder="渠道筛选" style={{ width: 120 }}
              onChange={(v) => setMsgFilter(prev => ({ ...prev, channel: v }))}
              options={CHANNEL_OPTIONS.map(c => ({ label: c.label, value: c.value }))} />
          </div>
          <Table dataSource={messages} columns={msgColumns} rowKey="id"
            loading={msgLoading} scroll={{ x: 1000 }} size="small"
            pagination={{
              current: msgPage,
              total: msgTotal,
              pageSize: 20,
              onChange: fetchMessages,
              showTotal: (total) => `共 ${total} 条`,
            }} />
        </TabPane>
      </Tabs>
    </Card>
  );
};

export default MessageCenter;