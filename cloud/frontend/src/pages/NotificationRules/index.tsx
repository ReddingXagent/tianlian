/**
 * 通知规则管理页面
 */
import React, { useState, useEffect } from 'react';
import {
  Card, Table, Button, Modal, Form, Input, Select, Tag, Space, message,
  Popconfirm, Switch, Descriptions, Row, Col, Statistic
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import {
  NotificationOutlined, PlusOutlined, EditOutlined, DeleteOutlined,
  SettingOutlined, BellOutlined
} from '@ant-design/icons';
import api from '../../api';

interface NotificationRule {
  id: number;
  name: string;
  level: string;
  channels: string[];
  receivers: string[];
  enabled: boolean;
  created_at?: string;
  updated_at?: string;
}

const NotificationRulesPage: React.FC = () => {
  const [rules, setRules] = useState<NotificationRule[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalVisible, setModalVisible] = useState(false);
  const [editingRule, setEditingRule] = useState<NotificationRule | null>(null);
  const [form] = Form.useForm();

  const levels = ['critical', 'warning', 'info', 'debug'];
  const channels = ['email', 'sms', 'im_b', 'im', 'webhook', 'phone'];
  const receiverOptions = [
    { label: '运维组', value: 'team:ops' },
    { label: '管理层', value: 'team:manager' },
    { label: '管理员', value: 'user:admin' },
    { label: '值班人员', value: 'oncall' },
  ];

  const fetchRules = async () => {
    setLoading(true);
    try {
      const res = await api.get('/notification-rules');
      const data = res.data as any;
      setRules(data || []);
    } catch (error) {
      message.error('获取通知规则失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchRules();
  }, []);

  const handleCreate = async (values: any) => {
    try {
      await api.post('/notification-rules', values);
      message.success('规则创建成功');
      setModalVisible(false);
      form.resetFields();
      fetchRules();
    } catch (error) {
      message.error('创建失败');
    }
  };

  const handleUpdate = async (values: any) => {
    if (!editingRule) return;
    try {
      await api.put(`/notification-rules/${editingRule.id}`, values);
      message.success('规则更新成功');
      setModalVisible(false);
      setEditingRule(null);
      form.resetFields();
      fetchRules();
    } catch (error) {
      message.error('更新失败');
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await api.delete(`/notification-rules/${id}`);
      message.success('规则已删除');
      fetchRules();
    } catch (error) {
      message.error('删除失败');
    }
  };

  const handleToggle = async (id: number) => {
    try {
      await api.put(`/notification-rules/${id}/toggle`);
      message.success('状态已切换');
      fetchRules();
    } catch (error) {
      message.error('切换失败');
    }
  };

  const openEditModal = (rule: NotificationRule) => {
    setEditingRule(rule);
    form.setFieldsValue(rule);
    setModalVisible(true);
  };

  const getLevelTag = (level: string) => {
    const map: Record<string, string> = {
      critical: 'red', warning: 'orange', info: 'blue', debug: 'default',
    };
    return <Tag color={map[level] || 'default'}>{level}</Tag>;
  };

  const getChannelTag = (channel: string) => {
    const map: Record<string, string> = {
      email: 'blue', sms: 'green', im_b: 'cyan', im: 'purple',
      webhook: 'geekblue', phone: 'magenta',
    };
    return <Tag color={map[channel] || 'default'}>{channel}</Tag>;
  };

  const columns: ColumnsType<NotificationRule> = [
    { title: 'ID', dataIndex: 'id', width: 60 },
    { title: '规则名称', dataIndex: 'name', width: 200 },
    { title: '告警级别', dataIndex: 'level', width: 100, render: getLevelTag },
    { title: '通知渠道', dataIndex: 'channels', width: 200, render: (chs: string[]) => (
      <Space size="small">{chs?.map(c => getChannelTag(c))}</Space>
    )},
    { title: '接收人', dataIndex: 'receivers', width: 200, render: (rcs: string[]) => (
      <Space size="small">{rcs?.map(r => <Tag key={r}>{r}</Tag>)}</Space>
    )},
    { title: '状态', dataIndex: 'enabled', width: 100, render: (v: boolean, r: NotificationRule) => (
      <Switch checked={v} onChange={() => handleToggle(r.id)} checkedChildren="启用" unCheckedChildren="禁用" />
    )},
    { title: '创建时间', dataIndex: 'created_at', width: 160, render: (v: string) => v?.slice(0, 19) || '-' },
    { title: '操作', width: 150, fixed: 'right', render: (_: any, r: NotificationRule) => (
      <Space size="small">
        <Button size="small" icon={<EditOutlined />} onClick={() => openEditModal(r)}>编辑</Button>
        <Popconfirm title="确认删除该规则？" onConfirm={() => handleDelete(r.id)}>
          <Button size="small" danger icon={<DeleteOutlined />} />
        </Popconfirm>
      </Space>
    )},
  ];

  return (
    <Card title={<><NotificationOutlined /> 通知规则管理</>} extra={
      <Button type="primary" icon={<PlusOutlined />} onClick={() => { setEditingRule(null); form.resetFields(); setModalVisible(true); }}>
        创建规则
      </Button>
    }>
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={4}><Statistic title="总规则数" value={rules.length} /></Col>
        <Col span={4}><Statistic title="已启用" value={rules.filter(r => r.enabled).length} /></Col>
        <Col span={4}><Statistic title="已禁用" value={rules.filter(r => !r.enabled).length} /></Col>
        <Col span={4}><Statistic title="紧急级别" value={rules.filter(r => r.level === 'critical').length} /></Col>
      </Row>

      <Table dataSource={rules} columns={columns} rowKey="id" loading={loading} scroll={{ x: 1100 }} />

      {/* 创建/编辑弹窗 */}
      <Modal
        title={editingRule ? '编辑通知规则' : '创建通知规则'}
        open={modalVisible}
        onCancel={() => { setModalVisible(false); setEditingRule(null); }}
        footer={null}
        width={600}
      >
        <Form form={form} onFinish={editingRule ? handleUpdate : handleCreate} layout="vertical">
          <Form.Item name="name" label="规则名称" rules={[{ required: true, message: '请输入规则名称' }]}>
            <Input placeholder="如：紧急告警通知" />
          </Form.Item>
          <Form.Item name="level" label="告警级别" rules={[{ required: true }]}>
            <Select placeholder="选择级别" options={levels.map(l => ({ label: l, value: l }))} />
          </Form.Item>
          <Form.Item name="channels" label="通知渠道" rules={[{ required: true, message: '请选择至少一个渠道' }]}>
            <Select mode="multiple" placeholder="选择通知渠道" options={channels.map(c => ({ label: c, value: c }))} />
          </Form.Item>
          <Form.Item name="receivers" label="接收人" rules={[{ required: true, message: '请选择至少一个接收人' }]}>
            <Select mode="multiple" placeholder="选择接收人" options={receiverOptions} />
          </Form.Item>
          <Form.Item name="enabled" label="启用状态" valuePropName="checked" initialValue={true}>
            <Switch checkedChildren="启用" unCheckedChildren="禁用" />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" block>
              {editingRule ? '更新' : '创建'}
            </Button>
          </Form.Item>
        </Form>
      </Modal>

      {/* 规则说明 */}
      <Card size="small" title={<><BellOutlined /> 规则说明</>} style={{ marginTop: 16 }}>
        <Descriptions column={1} size="small">
          <Descriptions.Item label="级别匹配">告警级别 &gt;= 规则级别时触发通知</Descriptions.Item>
          <Descriptions.Item label="渠道说明">email: 邮件, sms: 短信, im_b: IM-B, im: IM, webhook: 自定义接口</Descriptions.Item>
          <Descriptions.Item label="接收人格式">team:组名 / user:用户名 / oncall: 当前值班人员</Descriptions.Item>
        </Descriptions>
      </Card>
    </Card>
  );
};

export default NotificationRulesPage;