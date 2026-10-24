/**
 * 告警自愈引擎 - 规则配置页面
 *
 * 功能：
 * 1. 自愈规则列表（CRUD）
 * 2. 规则启用/禁用
 * 3. 告警匹配条件可视化配置
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
  Card, Table, Button, Space, Modal, Form, Input, Switch,
  Select, InputNumber, Tag, Popconfirm, message, Drawer,
  Descriptions, Alert, Typography, Divider, Row, Col, Tooltip,
} from 'antd';
import {
  PlusOutlined, EditOutlined, DeleteOutlined, ReloadOutlined,
  SafetyCertificateOutlined, ThunderboltOutlined, QuestionCircleOutlined,
} from '@ant-design/icons';
import healingApi, { HealingRule } from '../../api/healing';

const { TextArea } = Input;
const { Text } = Typography;

// 状态颜色
const statusColor: Record<string, string> = {
  pending_approval: 'orange',
  approved: 'blue',
  running: 'processing',
  success: 'success',
  partial_success: 'warning',
  failed: 'error',
  rejected: 'default',
  timeout: 'default',
  cooldown: 'default',
};

const statusText: Record<string, string> = {
  pending_approval: '待审批',
  approved: '已审批',
  running: '执行中',
  success: '成功',
  partial_success: '部分成功',
  failed: '失败',
  rejected: '已拒绝',
  timeout: '超时',
  cooldown: '冷却中',
};

const alarmLevelOptions = [
  { value: 'info', label: '提示 (info)' },
  { value: 'warning', label: '警告 (warning)' },
  { value: 'critical', label: '严重 (critical)' },
  { value: 'fatal', label: '致命 (fatal)' },
];

const deviceTypeOptions = [
  { value: 'inverter', label: '逆变器' },
  { value: 'charger', label: '充电桩' },
  { value: 'pcs', label: 'PCS' },
  { value: 'battery', label: '储能电池' },
  { value: 'meter', label: '电表' },
  { value: 'gateway', label: '网关' },
];

const runbookTemplateOptions = [
  { value: '', label: '自动匹配（根据故障类型）' },
  { value: '逆变器通讯中断', label: '逆变器通讯中断' },
  { value: '逆变器过温告警', label: '逆变器过温告警' },
  { value: '逆变器绝缘阻抗低', label: '逆变器绝缘阻抗低' },
  { value: '充电桩通讯异常', label: '充电桩通讯异常' },
  { value: '充电桩急停触发', label: '充电桩急停触发' },
  { value: '设备离线', label: '设备离线' },
];

const Rules: React.FC = () => {
  const [rules, setRules] = useState<HealingRule[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalVisible, setModalVisible] = useState(false);
  const [editingRule, setEditingRule] = useState<HealingRule | null>(null);
  const [form] = Form.useForm();

  const loadRules = useCallback(async () => {
    setLoading(true);
    try {
      const res = await healingApi.listRules();
      setRules(Array.isArray(res) ? res : []);
    } catch {
      message.error('加载自愈规则失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadRules(); }, [loadRules]);

  // 新建/编辑
  const handleEdit = (rule?: HealingRule) => {
    if (rule) {
      setEditingRule(rule);
      form.setFieldsValue({
        ...rule,
        alarm_levels: rule.alarm_pattern?.alarm_levels || [],
        alarm_types_input: (rule.alarm_pattern?.alarm_types || []).join(', '),
        device_types: rule.alarm_pattern?.device_types || [],
        content_keywords_input: (rule.alarm_pattern?.content_keywords || []).join(', '),
      });
    } else {
      setEditingRule(null);
      form.resetFields();
      form.setFieldsValue({
        auto_approve: false,
        max_retries: 1,
        cooldown_minutes: 30,
        priority: 0,
        enabled: true,
        alarm_levels: ['critical', 'warning'],
      });
    }
    setModalVisible(true);
  };

  const handleSave = async () => {
    try {
      const values = await form.validateFields();
      const alarmPattern: any = {};

      if (values.alarm_levels?.length) alarmPattern.alarm_levels = values.alarm_levels;
      if (values.alarm_types_input) {
        alarmPattern.alarm_types = values.alarm_types_input.split(/[,，]/).map((s: string) => s.trim()).filter(Boolean);
      }
      if (values.device_types?.length) alarmPattern.device_types = values.device_types;
      if (values.content_keywords_input) {
        alarmPattern.content_keywords = values.content_keywords_input.split(/[,，]/).map((s: string) => s.trim()).filter(Boolean);
      }

      const data = {
        name: values.name,
        description: values.description || '',
        alarm_pattern: alarmPattern,
        runbook_template: values.runbook_template || null,
        auto_approve: values.auto_approve || false,
        max_retries: values.max_retries || 1,
        cooldown_minutes: values.cooldown_minutes || 30,
        priority: values.priority || 0,
        enabled: values.enabled !== false,
      };

      if (editingRule) {
        await healingApi.updateRule(editingRule.id, data);
        message.success('更新成功');
      } else {
        await healingApi.createRule(data);
        message.success('创建成功');
      }
      setModalVisible(false);
      loadRules();
    } catch (err: any) {
      if (err?.response?.data?.message) {
        message.error(err.response.data.message);
      }
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await healingApi.deleteRule(id);
      message.success('删除成功');
      loadRules();
    } catch (err: any) {
      message.error(err?.response?.data?.message || '删除失败');
    }
  };

  const handleToggle = async (rule: HealingRule) => {
    try {
      await healingApi.updateRule(rule.id, { enabled: !rule.enabled });
      message.success(rule.enabled ? '已禁用' : '已启用');
      loadRules();
    } catch (err: any) {
      message.error(err?.response?.data?.message || '操作失败');
    }
  };

  const columns = [
    {
      title: '规则名称',
      dataIndex: 'name',
      key: 'name',
      render: (name: string, record: HealingRule) => (
        <Space>
          <ThunderboltOutlined style={{ color: record.enabled ? '#ff5a36' : '#ccc' }} />
          <Text strong={record.enabled}>{name}</Text>
          {!record.enabled && <Tag>已禁用</Tag>}
        </Space>
      ),
    },
    {
      title: '告警条件',
      key: 'pattern',
      width: 280,
      render: (_: any, record: HealingRule) => {
        const p = record.alarm_pattern || {};
        return (
          <Space direction="vertical" size={2}>
            {p.alarm_levels?.length > 0 && (
              <div>{p.alarm_levels.map((l: string) => <Tag key={l} color={l === 'critical' || l === 'fatal' ? 'red' : l === 'warning' ? 'orange' : 'blue'}>{l}</Tag>)}</div>
            )}
            {p.alarm_types?.length > 0 && <Text type="secondary" style={{ fontSize: 12 }}>类型: {p.alarm_types.join(', ')}</Text>}
            {p.device_types?.length > 0 && <Text type="secondary" style={{ fontSize: 12 }}>设备: {p.device_types.join(', ')}</Text>}
          </Space>
        );
      },
    },
    {
      title: 'Runbook',
      dataIndex: 'runbook_template',
      key: 'runbook_template',
      width: 150,
      render: (template: string | null) => template ? <Tag color="blue">{template}</Tag> : <Text type="secondary">自动匹配</Text>,
    },
    {
      title: '自动审批',
      dataIndex: 'auto_approve',
      key: 'auto_approve',
      width: 90,
      render: (v: boolean) => v ? <Tag color="green">自动</Tag> : <Tag color="orange">人工</Tag>,
    },
    {
      title: '冷却',
      dataIndex: 'cooldown_minutes',
      key: 'cooldown_minutes',
      width: 80,
      render: (v: number) => `${v}分钟`,
    },
    {
      title: '优先级',
      dataIndex: 'priority',
      key: 'priority',
      width: 70,
      render: (v: number) => <Tag color={v >= 10 ? 'red' : v > 0 ? 'orange' : 'default'}>{v}</Tag>,
    },
    {
      title: '操作',
      key: 'action',
      width: 200,
      render: (_: any, record: HealingRule) => (
        <Space>
          <Tooltip title={record.enabled ? '禁用' : '启用'}>
            <Switch size="small" checked={record.enabled} onChange={() => handleToggle(record)} />
          </Tooltip>
          <Button type="link" size="small" icon={<EditOutlined />} onClick={() => handleEdit(record)}>
            编辑
          </Button>
          <Popconfirm
            title="确认删除此规则？"
            onConfirm={() => handleDelete(record.id)}
            okText="删除"
            cancelText="取消"
            okButtonProps={{ danger: true }}
          >
            <Button type="link" size="small" danger icon={<DeleteOutlined />}>删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <Card
        title={
          <Space>
            <SafetyCertificateOutlined />
            <span>自愈规则配置</span>
          </Space>
        }
        extra={
          <Space>
            <Button icon={<ReloadOutlined />} onClick={loadRules}>刷新</Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={() => handleEdit()}>
              新建规则
            </Button>
          </Space>
        }
      >
        <Alert
          message="自愈规则说明"
          description="当告警触发时，系统自动匹配自愈规则并执行关联的Runbook修复步骤。低风险操作可设置自动审批，高风险操作需人工确认。"
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
        />

        <Table
          columns={columns}
          dataSource={rules}
          rowKey="id"
          loading={loading}
          pagination={false}
          size="middle"
        />
      </Card>

      {/* 新建/编辑规则弹窗 */}
      <Modal
        title={editingRule ? '编辑自愈规则' : '新建自愈规则'}
        open={modalVisible}
        onCancel={() => setModalVisible(false)}
        onOk={handleSave}
        okText="保存"
        width={720}
        destroyOnHidden
      >
        <Form form={form} layout="vertical">
          <Row gutter={16}>
            <Col span={16}>
              <Form.Item name="name" label="规则名称" rules={[{ required: true, message: '请输入规则名称' }]}>
                <Input placeholder="如：逆变器通讯中断自愈" />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="priority" label="优先级" tooltip="数值越大越优先">
                <InputNumber min={0} max={100} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>

          <Form.Item name="description" label="规则描述">
            <TextArea rows={2} placeholder="描述此规则的用途和适用场景" />
          </Form.Item>

          <Divider>告警匹配条件</Divider>

          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="alarm_levels" label="告警级别">
                <Select mode="multiple" options={alarmLevelOptions} placeholder="选择告警级别" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="device_types" label="设备类型">
                <Select mode="multiple" options={deviceTypeOptions} placeholder="选择设备类型" />
              </Form.Item>
            </Col>
          </Row>

          <Form.Item name="alarm_types_input" label="告警类型关键词" tooltip="多个用逗号分隔，模糊匹配">
            <Input placeholder="如：通讯中断, 过温, 离线" />
          </Form.Item>

          <Form.Item name="content_keywords_input" label="告警内容关键词" tooltip="多个用逗号分隔，模糊匹配">
            <Input placeholder="如：绝缘, 通讯, 温度" />
          </Form.Item>

          <Divider>执行策略</Divider>

          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="runbook_template" label="Runbook模板">
                <Select options={runbookTemplateOptions} placeholder="选择Runbook模板" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="cooldown_minutes" label="冷却时间（分钟）" tooltip="同一规则对同一设备的最小触发间隔">
                <InputNumber min={0} max={1440} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>

          <Row gutter={16}>
            <Col span={8}>
              <Form.Item name="auto_approve" label="自动审批" valuePropName="checked" tooltip="开启后低风险步骤自动执行">
                <Switch />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="max_retries" label="最大重试次数">
                <InputNumber min={0} max={10} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="enabled" label="启用" valuePropName="checked">
                <Switch />
              </Form.Item>
            </Col>
          </Row>
        </Form>
      </Modal>
    </div>
  );
};

export default Rules;
