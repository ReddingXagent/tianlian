/**
 * 告警规则配置组件
 */
import React, { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Card, Table, Button, Space, Tag, Modal, Form, Input, Select, InputNumber, Switch, message, Popconfirm, Alert, Badge, Tooltip, Descriptions } from 'antd';
import {
  PlusOutlined, EditOutlined, DeleteOutlined, PlayCircleOutlined,
  StopOutlined, CheckCircleOutlined, ExclamationCircleOutlined,
  WarningOutlined, InfoCircleOutlined, ThunderboltOutlined, HistoryOutlined,
  SyncOutlined
} from '@ant-design/icons';
import { alarmAPI } from '../../api';
import { fetchAllPages } from '../../api/fetchAll';

const { Option } = Select;
const { TextArea } = Input;

interface Rule {
  id: number;
  name: string;
  description?: string;
  device_type?: string;
  device_ids?: number[];
  station_ids?: number[];
  metric: string;
  operator: string;
  threshold: number;
  duration: number;
  level: string;
  alarm_template?: string;
  notify_users?: number[];
  auto_create_workorder: boolean;
  workorder_priority: string;
  enabled: boolean;
  silence_minutes: number;
  created_at?: string;
  updated_at?: string;
}

// 按设备类型分组的指标选项
const METRIC_OPTIONS_BY_DEVICE: Record<string, { label: string; value: string }[]> = {
  inverter: [
    { label: '光伏总功率 (kW)', value: 'pv_power_total' },
    { label: '光伏电流 (A)', value: 'pv_current' },
    { label: '光伏电压 (V)', value: 'pv_voltage' },
    { label: '逆变器温度 (℃)', value: 'inv_temperature' },
    { label: '环境温度 (℃)', value: 'ambient_temperature' },
    { label: '机内温度 (℃)', value: 'internal_temperature' },
  ],
  pcs: [
    { label: 'PCS功率 (kW)', value: 'pcs_power' },
    { label: 'PCS电流 (A)', value: 'pcs_current' },
    { label: 'PCS电压 (V)', value: 'pcs_voltage' },
    { label: 'PCS温度 (℃)', value: 'pcs_temperature' },
  ],
  battery: [
    { label: '电池电压 (V)', value: 'battery_voltage' },
    { label: '电池电流 (A)', value: 'battery_current' },
    { label: '电池功率 (kW)', value: 'battery_power' },
    { label: '电池SOC (%)', value: 'battery_soc' },
    { label: '电池SOH (%)', value: 'battery_soh' },
    { label: '电池温度 (℃)', value: 'battery_temperature' },
  ],
  charger: [
    { label: '充电桩输出电流 (A)', value: 'charger_current' },
    { label: '充电桩输出功率 (kW)', value: 'charger_power' },
    { label: '充电桩电压 (V)', value: 'charger_voltage' },
    { label: '充电枪温度 (℃)', value: 'gun_temperature' },
  ],
};

// 通用指标（适用所有设备类型）
const COMMON_METRICS = [
  { label: '电网频率 (Hz)', value: 'grid_frequency' },
  { label: 'A相电压 (V)', value: 'grid_voltage_a' },
  { label: 'B相电压 (V)', value: 'grid_voltage_b' },
  { label: 'C相电压 (V)', value: 'grid_voltage_c' },
  { label: '总功率 (kW)', value: 'grid_power_total' },
  { label: '功率因数', value: 'grid_power_factor' },
]

const getDeviceTypeOptions = (t: (k: string) => string) => [
  { value: '', label: t('pages.alarms.all_types') },
  { value: 'inverter', label: t('pages.devices.type_pv_inverter') },
  { value: 'pcs', label: t('pages.devices.type_pcs') },
  { value: 'battery', label: t('pages.devices.type_battery') },
  { value: 'charger', label: t('pages.devices.type_charger_dc') },
]

const OPERATOR_MAP: Record<string, string> = {
  '>': '大于',
  '>=': '大于等于',
  '<': '小于',
  '<=': '小于等于',
  '==': '等于',
  '!=': '不等于',
};

const LEVEL_TAG: Record<string, { color: string; icon: React.ReactNode }> = {
  info: { color: 'blue', icon: <InfoCircleOutlined /> },
  warning: { color: 'orange', icon: <WarningOutlined /> },
  critical: { color: 'red', icon: <ExclamationCircleOutlined /> },
  fatal: { color: 'red', icon: <ExclamationCircleOutlined /> },
};

export const getLevelName = (lvl: string) => {
  const names: Record<string, string> = { info: '提示', warning: '警告', critical: '紧急', fatal: '致命' };
  return names[lvl] || lvl;
};

const AlarmRulesTab: React.FC = () => {
  const { t } = useTranslation();
  const [rules, setRules] = useState<Rule[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalVisible, setModalVisible] = useState(false);
  const [editingRule, setEditingRule] = useState<Rule | null>(null);
  const [logModalVisible, setLogModalVisible] = useState(false);
  const [ruleLogs, setRuleLogs] = useState<any[]>([]);
  const [logLoading, setLogLoading] = useState(false);
  const [form] = Form.useForm();

  const fetchRules = async () => {
    setLoading(true);
    try {
      const res: any = await alarmAPI.rules.list();
      setRules(Array.isArray(res.data) ? res.data : []);
    } catch {
      message.error('获取告警规则失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchRules(); }, []);

  const handleCreate = () => {
    setEditingRule(null);
    form.resetFields();
    form.setFieldsValue({ level: 'warning', operator: '>', duration: 0, silence_minutes: 0, enabled: true, auto_create_workorder: false });
    setModalVisible(true);
  };

  const handleEdit = (rule: Rule) => {
    setEditingRule(rule);
    form.setFieldsValue(rule);
    setModalVisible(true);
  };

  const handleSave = async () => {
    try {
      const values = await form.validateFields();
      if (editingRule) {
        await alarmAPI.rules.update(editingRule.id, values);
        message.success('规则已更新');
      } else {
        await alarmAPI.rules.create(values);
        message.success('规则已创建');
      }
      setModalVisible(false);
      fetchRules();
    } catch (err: any) {
      if (err?.errorFields) return;
      message.error('保存失败');
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await alarmAPI.rules.del(id);
      message.success('规则已删除');
      fetchRules();
    } catch {
      message.error('删除失败');
    }
  };

  const handleToggle = async (id: number) => {
    try {
      await alarmAPI.rules.toggle(id);
      fetchRules();
    } catch {
      message.error('切换失败');
    }
  };

  const handleEvaluate = async (id: number) => {
    try {
      const res: any = await alarmAPI.rules.evaluate(id);
      if (res.data?.triggered) {
        message.success(`规则触发成功，告警ID: ${res.data.alarm_id}`);
      } else {
        message.info(res.data?.message || '未触发');
      }
      fetchRules();
    } catch {
      message.error('评估失败');
    }
  };

  const showLogs = async () => {
    setLogLoading(true);
    setLogModalVisible(true);
    try {
      const items = await fetchAllPages<any>((params) => alarmAPI.ruleLogs(params));
      setRuleLogs(items);
    } catch {
      message.error('获取日志失败');
    } finally {
      setLogLoading(false);
    }
  };

  const columns = [
    {
      title: '规则名称',
      dataIndex: 'name',
      key: 'name',
      width: 180,
      render: (name: string, record: Rule) => (
        <Space>
          {record.enabled ? (
            <Badge status="success" />
          ) : (
            <Badge status="default" />
          )}
          <span>{name}</span>
        </Space>
      ),
    },
    {
      title: '条件',
      key: 'condition',
      width: 280,
      render: (_: any, record: Rule) => {
        const allMetrics = [...Object.values(METRIC_OPTIONS_BY_DEVICE).flat(), ...COMMON_METRICS];
        const metricLabel = allMetrics.find(m => m.value === record.metric)?.label || record.metric;
        return (
          <Tag style={{ fontSize: 13, padding: '2px 8px' }}>
            {metricLabel} {record.operator} {record.threshold}
            {record.duration > 0 ? ` (持续${record.duration}秒)` : ''}
          </Tag>
        );
      },
    },
    {
      title: '级别',
      dataIndex: 'level',
      key: 'level',
      width: 80,
      render: (lvl: string) => {
        const t = LEVEL_TAG[lvl] || LEVEL_TAG.warning;
        return (
          <Tag color={t.color}>{t.icon} {getLevelName(lvl)}</Tag>
        );
      },
    },
    {
      title: '设备类型',
      dataIndex: 'device_type',
      key: 'device_type',
      width: 120,
      render: (v: string) => v ? <Tag>{v}</Tag> : <Tag color="default">全部</Tag>,
    },
    {
      title: '静默(分钟)',
      dataIndex: 'silence_minutes',
      key: 'silence_minutes',
      width: 100,
      render: (v: number) => v > 0 ? `${v}分钟` : '无',
    },
    {
      title: '操作',
      key: 'action',
      width: 280,
      fixed: 'right' as const,
      render: (_: any, record: Rule) => (
        <Space>
          <Tooltip title={record.enabled ? '禁用' : '启用'}>
            <Button
              size="small"
              icon={record.enabled ? <StopOutlined /> : <CheckCircleOutlined />}
              onClick={() => handleToggle(record.id)}
              type={record.enabled ? 'default' : 'primary'}
            >
              {record.enabled ? '禁用' : '启用'}
            </Button>
          </Tooltip>
          <Tooltip title="手动评估">
            <Button size="small" icon={<ThunderboltOutlined />} onClick={() => handleEvaluate(record.id)}>
              触发
            </Button>
          </Tooltip>
          <Button size="small" icon={<EditOutlined />} onClick={() => handleEdit(record)}>
            编辑
          </Button>
          <Popconfirm title="确定删除此规则?" onConfirm={() => handleDelete(record.id)}>
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <Card>
        <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Space>
            <Button type="primary" icon={<PlusOutlined />} onClick={handleCreate}>
              新建规则
            </Button>
            <Button icon={<SyncOutlined />} onClick={fetchRules}>
              刷新
            </Button>
          </Space>
          <Button icon={<HistoryOutlined />} onClick={showLogs}>
            触发日志
          </Button>
        </div>

        <Alert
          message="告警规则引擎每分钟自动评估一次。新建/修改规则后约1分钟生效。可点击「触发」按钮手动评估。"
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
        />

        <Table
          columns={columns}
          dataSource={rules}
          rowKey="id"
          loading={loading}
          pagination={{ pageSize: 10, showTotal: (t) => `共 ${t} 条规则` }}
          scroll={{ x: 1000 }}
        />
      </Card>

      {/* 新建/编辑规则弹窗 */}
      <Modal
        title={editingRule ? '编辑告警规则' : '新建告警规则'}
        open={modalVisible}
        onCancel={() => setModalVisible(false)}
        onOk={handleSave}
        width={700}
        okText="保存"
        cancelText="取消"
      >
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="规则名称" rules={[{ required: true, message: '请输入规则名称' }]}>
            <Input placeholder="如：电池高温告警" />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <TextArea rows={2} placeholder="规则说明（可选）" />
          </Form.Item>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <Form.Item name="device_type" label="设备类型">
              <Select style={{ width: 150 }} placeholder="全部类型" allowClear>
                {getDeviceTypeOptions(t).filter(o => o.value).map(o => (
                  <Option key={o.value} value={o.value}>{o.label}</Option>
                ))}
              </Select>
            </Form.Item>
            <Form.Item noStyle shouldUpdate={(prev, cur) => prev.device_type !== cur.device_type}>
              {({ getFieldValue }) => {
                const deviceType = getFieldValue('device_type') || '';
                const metrics = deviceType && METRIC_OPTIONS_BY_DEVICE[deviceType]
                  ? [...METRIC_OPTIONS_BY_DEVICE[deviceType], ...COMMON_METRICS]
                  : [...Object.values(METRIC_OPTIONS_BY_DEVICE).flat(), ...COMMON_METRICS];
                const unique = metrics.filter((m, i, arr) => arr.findIndex(x => x.value === m.value) === i);
                return (
                  <Form.Item name="metric" label="指标" rules={[{ required: true, message: '请选择指标' }]} style={{ width: 200 }}>
                    <Select placeholder="选择指标" showSearch>
                      {unique.map(m => (
                        <Option key={m.value} value={m.value}>{m.label}</Option>
                      ))}
                    </Select>
                  </Form.Item>
                );
              }}
            </Form.Item>
            <Form.Item name="operator" label="操作符" rules={[{ required: true }]}>
              <Select style={{ width: 100 }}>
                {Object.entries(OPERATOR_MAP).map(([k, v]) => (
                  <Option key={k} value={k}>{v} ({k})</Option>
                ))}
              </Select>
            </Form.Item>
            <Form.Item name="threshold" label="阈值" rules={[{ required: true, message: '请输入阈值' }]}>
              <InputNumber style={{ width: 130 }} placeholder="阈值" step={0.1} />
            </Form.Item>
          </div>
          <Space style={{ width: '100%' }} align="start">
            <Form.Item name="level" label="告警级别" rules={[{ required: true }]}>
              <Select style={{ width: 120 }}>
                <Option value="info">提示</Option>
                <Option value="warning">警告</Option>
                <Option value="critical">紧急</Option>
              </Select>
            </Form.Item>
            <Form.Item name="duration" label="持续(秒)" help="连续超过阈值N秒后触发，0=立即">
              <InputNumber style={{ width: 100 }} min={0} />
            </Form.Item>
            <Form.Item name="silence_minutes" label="静默(分钟)" help="同一设备重复告警间隔">
              <InputNumber style={{ width: 100 }} min={0} />
            </Form.Item>
          </Space>
          {/* 设备类型已在上方与指标联动选择 */}
          <Form.Item name="alarm_template" label="告警内容模板">
            <TextArea rows={2} placeholder="可用变量: {metric} {value} {threshold} {operator} {device_name} {rule_name}" />
          </Form.Item>
          <Space>
            <Form.Item name="enabled" label="启用" valuePropName="checked">
              <Switch />
            </Form.Item>
            <Form.Item name="auto_create_workorder" label="自动创建工单" valuePropName="checked">
              <Switch />
            </Form.Item>
          </Space>
        </Form>
      </Modal>

      {/* 触发日志弹窗 */}
      <Modal
        title="告警规则触发日志"
        open={logModalVisible}
        onCancel={() => setLogModalVisible(false)}
        footer={<Button onClick={() => setLogModalVisible(false)}>关闭</Button>}
        width={800}
      >
        <Table
          dataSource={ruleLogs}
          rowKey="id"
          loading={logLoading}
          size="small"
          columns={[
            { title: '规则', dataIndex: 'rule_name', key: 'rule_name', width: 150 },
            { title: '设备', dataIndex: 'device_name', key: 'device_name', width: 120 },
            { title: '指标', dataIndex: 'metric', key: 'metric', width: 100 },
            {
              title: '当前值', dataIndex: 'current_value', key: 'current_value', width: 100,
              render: (v: number) => v?.toFixed(2),
            },
            {
              title: '阈值', dataIndex: 'threshold', key: 'threshold', width: 100,
              render: (v: number) => `${v}`,
            },
            {
              title: '结果', dataIndex: 'triggered', key: 'triggered', width: 80,
              render: (v: boolean) => v
                ? <Tag color="red">触发</Tag>
                : <Tag color="default">未触发</Tag>,
            },
            {
              title: '时间', dataIndex: 'checked_at', key: 'checked_at', width: 180,
              render: (v: string) => v ? new Date(v).toLocaleString() : '-',
            },
          ]}
          pagination={{ pageSize: 20, showTotal: (t) => `共 ${t} 条日志` }}
          scroll={{ x: 800 }}
        />
      </Modal>
    </div>
  );
};

export default AlarmRulesTab;
