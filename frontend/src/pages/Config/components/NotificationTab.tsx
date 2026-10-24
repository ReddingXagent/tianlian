/**
 * 天链 V3 - 系统配置：通知配置 Tab
 */
import React, { useState } from 'react';
import {
  Card, Table, Button, Space, Tag, Modal, Form, Input, Select,
  Row, Col, Statistic, Switch, Descriptions, Popconfirm,
} from 'antd';
import {
  PlusOutlined, ReloadOutlined, EditOutlined, DeleteOutlined, BellOutlined,
  MailOutlined, MessageOutlined, MobileOutlined, ApartmentOutlined,
} from '@ant-design/icons';
import { useNotificationRules } from '../hooks/useNotificationRules';
import type { NotificationRule } from '../types';

const NotificationTab: React.FC = () => {
  const {
    rules, rulesLoading, ruleModalVisible, setRuleModalVisible,
    editingRule, setEditingRule, ruleForm,
    fetchRules, openCreateRule, openEditRule, handleRuleSubmit,
    handleDeleteRule, handleToggleRule,
  } = useNotificationRules();

  const [notifyToggles, setNotifyToggles] = useState({
    sms: true, email: true, app: true, im_b: false, im: true, webhook: false,
  });

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

  const ruleColumns = [
    { title: 'ID', dataIndex: 'id', width: 60 },
    { title: '规则名称', dataIndex: 'name', width: 200 },
    { title: '告警级别', dataIndex: 'level', width: 100, render: getLevelTag },
    {
      title: '通知渠道', dataIndex: 'channels', width: 200,
      render: (chs: string[]) => <Space size="small">{chs?.map(c => getChannelTag(c))}</Space>,
    },
    {
      title: '接收人', dataIndex: 'receivers', width: 200,
      render: (rcs: string[]) => <Space size="small">{rcs?.map(r => <Tag key={r}>{r}</Tag>)}</Space>,
    },
    {
      title: '状态', dataIndex: 'enabled', width: 100,
      render: (v: boolean, r: NotificationRule) => (
        <Switch checked={v} onChange={() => handleToggleRule(r.id)}
          checkedChildren="启用" unCheckedChildren="禁用" />
      ),
    },
    { title: '创建时间', dataIndex: 'created_at', width: 160, render: (v: string) => v?.slice(0, 19) || '-' },
    {
      title: '操作', width: 150, fixed: 'right' as const,
      render: (_: any, r: NotificationRule) => (
        <Space size="small">
          <Button size="small" icon={<EditOutlined />} onClick={() => openEditRule(r)}>编辑</Button>
          <Popconfirm title="确认删除该规则？" onConfirm={() => handleDeleteRule(r.id)}>
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <>
      <Card title={<Space><BellOutlined />通知渠道开关</Space>} style={{ marginBottom: 16 }}>
        <Row gutter={[24, 16]}>
          <Col span={8}>
            <Card size="small" hoverable>
              <Space>
                <MessageOutlined style={{ fontSize: 24, color: '#1890ff' }} />
                <div>
                  <div style={{ fontWeight: 'bold' }}>短信通知</div>
                  <Switch
                    checked={notifyToggles.sms}
                    onChange={(v) => setNotifyToggles(t => ({ ...t, sms: v }))}
                    checkedChildren="开" unCheckedChildren="关"
                  />
                </div>
              </Space>
            </Card>
          </Col>
          <Col span={8}>
            <Card size="small" hoverable>
              <Space>
                <MailOutlined style={{ fontSize: 24, color: '#52c41a' }} />
                <div>
                  <div style={{ fontWeight: 'bold' }}>邮件通知</div>
                  <Switch
                    checked={notifyToggles.email}
                    onChange={(v) => setNotifyToggles(t => ({ ...t, email: v }))}
                    checkedChildren="开" unCheckedChildren="关"
                  />
                </div>
              </Space>
            </Card>
          </Col>
          <Col span={8}>
            <Card size="small" hoverable>
              <Space>
                <MobileOutlined style={{ fontSize: 24, color: '#722ed1' }} />
                <div>
                  <div style={{ fontWeight: 'bold' }}>APP推送</div>
                  <Switch
                    checked={notifyToggles.app}
                    onChange={(v) => setNotifyToggles(t => ({ ...t, app: v }))}
                    checkedChildren="开" unCheckedChildren="关"
                  />
                </div>
              </Space>
            </Card>
          </Col>
          <Col span={8}>
            <Card size="small" hoverable>
              <Space>
                <BellOutlined style={{ fontSize: 24, color: '#13c2c2' }} />
                <div>
                  <div style={{ fontWeight: 'bold' }}>IM-B通知</div>
                  <Switch
                    checked={notifyToggles.im_b}
                    onChange={(v) => setNotifyToggles(t => ({ ...t, im_b: v }))}
                    checkedChildren="开" unCheckedChildren="关"
                  />
                </div>
              </Space>
            </Card>
          </Col>
          <Col span={8}>
            <Card size="small" hoverable>
              <Space>
                <BellOutlined style={{ fontSize: 24, color: '#fa8c16' }} />
                <div>
                  <div style={{ fontWeight: 'bold' }}>IM通知</div>
                  <Switch
                    checked={notifyToggles.im}
                    onChange={(v) => setNotifyToggles(t => ({ ...t, im: v }))}
                    checkedChildren="开" unCheckedChildren="关"
                  />
                </div>
              </Space>
            </Card>
          </Col>
          <Col span={8}>
            <Card size="small" hoverable>
              <Space>
                <ApartmentOutlined style={{ fontSize: 24, color: '#eb2f96' }} />
                <div>
                  <div style={{ fontWeight: 'bold' }}>Webhook</div>
                  <Switch
                    checked={notifyToggles.webhook}
                    onChange={(v) => setNotifyToggles(t => ({ ...t, webhook: v }))}
                    checkedChildren="开" unCheckedChildren="关"
                  />
                </div>
              </Space>
            </Card>
          </Col>
        </Row>
      </Card>

      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}><Statistic title="总规则数" value={rules.length} /></Col>
        <Col span={6}><Statistic title="已启用" value={rules.filter(r => r.enabled).length} /></Col>
        <Col span={6}><Statistic title="已禁用" value={rules.filter(r => !r.enabled).length} /></Col>
        <Col span={6}><Statistic title="紧急级别" value={rules.filter(r => r.level === 'critical').length} /></Col>
      </Row>

      <Card
        title={<Space><BellOutlined />通知规则管理</Space>}
        extra={
          <Space>
            <Button type="primary" icon={<PlusOutlined />} onClick={openCreateRule}>创建规则</Button>
            <Button icon={<ReloadOutlined />} onClick={fetchRules}>刷新</Button>
          </Space>
        }
        style={{ marginBottom: 16 }}
      >
        <Table
          dataSource={rules}
          columns={ruleColumns}
          rowKey="id"
          loading={rulesLoading}
          scroll={{ x: 1100 }}
          pagination={false}
        />
      </Card>

      <Card size="small" title={<><BellOutlined /> 规则说明</>}>
        <Descriptions column={1} size="small">
          <Descriptions.Item label="级别匹配">告警级别 &gt;= 规则级别时触发通知</Descriptions.Item>
          <Descriptions.Item label="渠道说明">email: 邮件, sms: 短信, im_b: IM-B, im: IM, webhook: 自定义接口</Descriptions.Item>
          <Descriptions.Item label="接收人格式">team:组名 / user:用户名 / oncall: 当前值班人员</Descriptions.Item>
        </Descriptions>
      </Card>

      {/* 规则弹窗 */}
      <Modal
        title={editingRule ? '编辑通知规则' : '创建通知规则'}
        open={ruleModalVisible}
        onCancel={() => { setRuleModalVisible(false); setEditingRule(null); }}
        footer={null}
        width={600}
      >
        <Form form={ruleForm} onFinish={handleRuleSubmit} layout="vertical">
          <Form.Item name="name" label="规则名称" rules={[{ required: true, message: '请输入规则名称' }]}>
            <Input placeholder="如：紧急告警通知" />
          </Form.Item>
          <Form.Item name="level" label="告警级别" rules={[{ required: true }]}>
            <Select placeholder="选择级别"
              options={['critical', 'warning', 'info', 'debug'].map(l => ({ label: l, value: l }))} />
          </Form.Item>
          <Form.Item name="channels" label="通知渠道" rules={[{ required: true, message: '请选择至少一个渠道' }]}>
            <Select mode="multiple" placeholder="选择通知渠道"
              options={['email', 'sms', 'im_b', 'im', 'webhook', 'phone'].map(c => ({ label: c, value: c }))} />
          </Form.Item>
          <Form.Item name="receivers" label="接收人" rules={[{ required: true, message: '请选择至少一个接收人' }]}>
            <Select mode="multiple" placeholder="选择接收人"
              options={[
                { label: '运维组', value: 'team:ops' },
                { label: '管理层', value: 'team:manager' },
                { label: '管理员', value: 'user:admin' },
                { label: '值班人员', value: 'oncall' },
              ]} />
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
    </>
  );
};

export default NotificationTab;
