/**
 * 车队 - 告警规则引擎页面
 *
 * 功能：规则管理(列表/新增/编辑/删除/启用切换/模拟触发) + 告警记录列表
 * API:
 *   GET/POST/PUT/DELETE /fleet/alert-rules
 *   POST /fleet/alert-rules/{id}/test      模拟触发
 *   GET  /fleet/alert-records              告警记录
 */
import React, { useEffect, useState, useCallback } from 'react';
import {
  Card, Table, Tag, Button, Modal, Form, Select, Space, message,
  Popconfirm, Statistic, Row, Col, Switch, InputNumber, Tabs,
} from 'antd';
import {
  PlusOutlined, EditOutlined, DeleteOutlined, ReloadOutlined,
  AlertOutlined, ThunderboltOutlined,
} from '@ant-design/icons';
import api from '../../../api';
import PageWrapper from '../../../components/PageWrapper';

/* ── 类型 ── */
interface AlertRule {
  id: number;
  enterprise_id: number;
  rule_type: string;
  threshold: Record<string, any>;
  notify_channels: string[];
  enable: boolean;
  created_at?: string;
}
interface AlertRecord {
  id: number;
  rule_id: number;
  enterprise_id: number;
  vehicle_id?: number | null;
  plate_number?: string;
  triggered_at?: string;
  alert_value?: string;
  notified: boolean;
  status: string;
}
interface EnterpriseLite { id: number; name: string; }

/* ── 常量 ── */
const RULE_TYPES: { value: string; label: string; thresholdKey: string; thresholdLabel: string; unit: string }[] = [
  { value: 'low_battery', label: '低电量', thresholdKey: 'soc_below', thresholdLabel: 'SOC低于(%)', unit: '%' },
  { value: 'abnormal_charging', label: '异常充电', thresholdKey: 'power_delta', thresholdLabel: '功率突变(kW)', unit: 'kW' },
  { value: 'overtime_parking', label: '超时未离桩', thresholdKey: 'hours', thresholdLabel: '停留超时(小时)', unit: 'h' },
];
const NOTIFY_CHANNELS = ['im', 'sms', 'email', 'webhook'];
const RECORD_STATUS_COLOR: Record<string, string> = { active: 'red', acknowledged: 'orange', resolved: 'green' };
const RECORD_STATUS_TEXT: Record<string, string> = { active: '未处理', acknowledged: '已确认', resolved: '已解决' };

const ruleLabel = (t: string) => RULE_TYPES.find(r => r.value === t)?.label || t;
const thresholdText = (t: string, th: Record<string, any>) => {
  const conf = RULE_TYPES.find(r => r.value === t);
  if (!conf || !th) return '-';
  const v = th[conf.thresholdKey];
  return v != null ? `${conf.thresholdLabel}=${v}${conf.unit}` : '-';
};

/* ── 组件 ── */
const FleetAlertRulesPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState('rules');
  const [rules, setRules] = useState<AlertRule[]>([]);
  const [records, setRecords] = useState<AlertRecord[]>([]);
  const [enterprises, setEnterprises] = useState<EnterpriseLite[]>([]);
  const [currentEid, setCurrentEid] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);

  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<AlertRule | null>(null);
  const [ruleType, setRuleType] = useState<string>('low_battery');
  const [form] = Form.useForm();

  /* ── 加载 ── */
  const loadEnterprises = useCallback(async () => {
    try {
      const { data } = await api.get('/fleet/enterprises');
      const items: EnterpriseLite[] = Array.isArray(data) ? data : (data as any)?.items || [];
      setEnterprises(items);
      if (items.length && currentEid === null) setCurrentEid(items[0].id);
    } catch {
      setEnterprises([]);
    }
  }, [currentEid]);

  const loadRules = useCallback(async () => {
    if (!currentEid) { setRules([]); return; }
    setLoading(true);
    try {
      const { data } = await api.get('/fleet/alert-rules', { params: { enterprise_id: currentEid } });
      setRules(Array.isArray(data) ? data : (data as any)?.items || []);
    } catch {
      setRules([]);
    } finally {
      setLoading(false);
    }
  }, [currentEid]);

  const loadRecords = useCallback(async () => {
    if (!currentEid) { setRecords([]); return; }
    try {
      const { data } = await api.get('/fleet/alert-records', { params: { enterprise_id: currentEid } });
      setRecords(Array.isArray(data) ? data : (data as any)?.items || []);
    } catch {
      setRecords([]);
    }
  }, [currentEid]);

  useEffect(() => { loadEnterprises(); }, [loadEnterprises]);
  useEffect(() => {
    if (!currentEid) return;
    if (activeTab === 'rules') loadRules();
    else loadRecords();
  }, [currentEid, activeTab, loadRules, loadRecords]);

  /* ── CRUD ── */
  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      const conf = RULE_TYPES.find(r => r.value === values.rule_type)!;
      const threshold = { [conf.thresholdKey]: Number(values.threshold_value) };
      const payload = {
        enterprise_id: values.enterprise_id,
        rule_type: values.rule_type,
        threshold,
        notify_channels: values.notify_channels || [],
        enable: values.enable,
      };
      if (editing) {
        await api.put(`/fleet/alert-rules/${editing.id}`, payload);
        message.success('告警规则已更新');
      } else {
        await api.post('/fleet/alert-rules', payload);
        message.success('告警规则已创建');
      }
      setModalOpen(false);
      form.resetFields();
      setEditing(null);
      loadRules();
    } catch (err: any) {
      if (err?.errorFields) return;
      message.error('操作失败：' + (err?.response?.data?.detail || err?.message));
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await api.delete(`/fleet/alert-rules/${id}`);
      message.success('已删除');
      loadRules();
    } catch (err: any) {
      message.error('删除失败：' + (err?.response?.data?.detail || err?.message));
    }
  };

  const toggleEnable = async (r: AlertRule, enable: boolean) => {
    try {
      await api.put(`/fleet/alert-rules/${r.id}`, { enable });
      message.success(enable ? '已启用' : '已停用');
      loadRules();
    } catch (err: any) {
      message.error('操作失败：' + (err?.response?.data?.detail || err?.message));
    }
  };

  const triggerTest = async (id: number) => {
    try {
      await api.post(`/fleet/alert-rules/${id}/test`);
      message.success('已模拟触发一条告警记录');
    } catch (err: any) {
      message.error('触发失败：' + (err?.response?.data?.detail || err?.message));
    }
  };

  const openAdd = () => {
    setEditing(null);
    setRuleType('low_battery');
    form.resetFields();
    form.setFieldsValue({ enterprise_id: currentEid ?? undefined, rule_type: 'low_battery', threshold_value: 20, notify_channels: ['im'], enable: true });
    setModalOpen(true);
  };

  const openEdit = (r: AlertRule) => {
    setEditing(r);
    const conf = RULE_TYPES.find(x => x.value === r.rule_type);
    setRuleType(r.rule_type);
    form.setFieldsValue({
      enterprise_id: r.enterprise_id,
      rule_type: r.rule_type,
      threshold_value: conf ? r.threshold?.[conf.thresholdKey] : undefined,
      notify_channels: r.notify_channels || [],
      enable: r.enable,
    });
    setModalOpen(true);
  };

  /* ── 统计 ── */
  const stats = {
    total: rules.length,
    enabled: rules.filter(r => r.enable).length,
    lowBattery: rules.filter(r => r.rule_type === 'low_battery').length,
    activeRecords: records.filter(r => r.status === 'active').length,
  };

  const fmtTime = (v?: string) => (v ? v.replace('T', ' ').slice(0, 16) : '-');

  const ruleColumns = [
    { title: '规则类型', dataIndex: 'rule_type', key: 'rule_type', width: 120, render: (v: string) => <Tag color="volcano">{ruleLabel(v)}</Tag> },
    { title: '阈值', key: 'threshold', render: (_: unknown, r: AlertRule) => thresholdText(r.rule_type, r.threshold) },
    { title: '通知渠道', dataIndex: 'notify_channels', key: 'notify_channels', width: 180, render: (v: string[]) => v?.length ? v.map(c => <Tag key={c}>{c}</Tag>) : '-' },
    {
      title: '启用', dataIndex: 'enable', key: 'enable', width: 90,
      render: (v: boolean, r: AlertRule) => <Switch size="small" checked={v} onChange={(checked) => toggleEnable(r, checked)} />,
    },
    {
      title: '操作', key: 'action', width: 210,
      render: (_: unknown, r: AlertRule) => (
        <Space size={4} wrap>
          <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(r)}>编辑</Button>
          <Button size="small" icon={<ThunderboltOutlined />} onClick={() => triggerTest(r.id)}>测试</Button>
          <Popconfirm title="确认删除该规则？" onConfirm={() => handleDelete(r.id)}>
            <Button size="small" danger icon={<DeleteOutlined />}>删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const recordColumns = [
    { title: '触发时间', dataIndex: 'triggered_at', key: 'triggered_at', width: 150, render: (v: string) => fmtTime(v) },
    { title: '车牌', dataIndex: 'plate_number', key: 'plate_number', width: 110, render: (v: string) => v ? <Tag color="blue">{v}</Tag> : '-' },
    { title: '告警值', dataIndex: 'alert_value', key: 'alert_value', ellipsis: true, render: (v: string) => v || '-' },
    { title: '规则ID', dataIndex: 'rule_id', key: 'rule_id', width: 80, align: 'right' as const },
    { title: '已通知', dataIndex: 'notified', key: 'notified', width: 80, render: (v: boolean) => <Tag color={v ? 'green' : 'default'}>{v ? '是' : '否'}</Tag> },
    { title: '状态', dataIndex: 'status', key: 'status', width: 90, render: (v: string) => <Tag color={RECORD_STATUS_COLOR[v] || 'default'}>{RECORD_STATUS_TEXT[v] || v}</Tag> },
  ];

  if (currentEid === null && enterprises.length === 0 && !loading) {
    return (
      <PageWrapper loading={false} hasData={false} transition="slide-up">
        <Card><div style={{ padding: 24, textAlign: 'center', color: '#999' }}>暂无企业，请先在「车队企业」中创建企业。</div></Card>
      </PageWrapper>
    );
  }

  return (
    <PageWrapper
      loading={loading && activeTab === 'rules' && rules.length === 0}
      skeletonType="table"
      hasData={activeTab === 'rules' ? rules.length > 0 : records.length > 0}
      empty={{ type: 'default', title: activeTab === 'rules' ? '暂无告警规则' : '暂无告警记录', description: activeTab === 'rules' ? '点击「新增规则」配置低电量/异常充电/超时未离桩告警' : '当前企业暂无告警记录', actionText: activeTab === 'rules' ? '新增规则' : undefined, onAction: activeTab === 'rules' ? openAdd : undefined }}
      transition="slide-up"
    >
      <div className="page-container">
        <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
          <Col xs={12} sm={6}><Card><Statistic title="规则总数" value={stats.total} prefix={<AlertOutlined />} /></Card></Col>
          <Col xs={12} sm={6}><Card><Statistic title="启用中" value={stats.enabled} valueStyle={{ color: '#52c41a' }} /></Card></Col>
          <Col xs={12} sm={6}><Card><Statistic title="低电量规则" value={stats.lowBattery} /></Card></Col>
          <Col xs={12} sm={6}><Card><Statistic title="未处理告警" value={stats.activeRecords} valueStyle={{ color: '#ea4335' }} /></Card></Col>
        </Row>

        <Card extra={
          <Space wrap>
            <Select placeholder="选择企业" value={currentEid ?? undefined} onChange={setCurrentEid}
              style={{ width: 200 }} showSearch optionFilterProp="label"
              options={enterprises.map(e => ({ value: e.id, label: e.name }))} />
            <Button icon={<ReloadOutlined />} onClick={() => (activeTab === 'rules' ? loadRules() : loadRecords())}>刷新</Button>
            {activeTab === 'rules' && <Button type="primary" icon={<PlusOutlined />} onClick={openAdd}>新增规则</Button>}
          </Space>
        }>
          <Tabs
            activeKey={activeTab}
            onChange={setActiveTab}
            items={[
              {
                key: 'rules',
                label: <span><AlertOutlined /> 规则管理</span>,
                children: <Table columns={ruleColumns} dataSource={rules} rowKey="id" loading={loading}
                  pagination={{ pageSize: 10, showSizeChanger: true, showTotal: (t: number) => `共 ${t} 条` }} />,
              },
              {
                key: 'records',
                label: <span><ThunderboltOutlined /> 告警记录</span>,
                children: <Table columns={recordColumns} dataSource={records} rowKey="id"
                  pagination={{ pageSize: 10, showSizeChanger: true, showTotal: (t: number) => `共 ${t} 条` }} />,
              },
            ]}
          />
        </Card>

        {/* 新增/编辑 Modal */}
        <Modal title={editing ? '编辑告警规则' : '新增告警规则'} open={modalOpen} onOk={handleSubmit}
          onCancel={() => { setModalOpen(false); form.resetFields(); setEditing(null); }}
          width={520} destroyOnHidden
        >
          <Form form={form} layout="vertical">
            <Form.Item name="enterprise_id" label="所属企业" rules={[{ required: true, message: '请选择企业' }]}>
              <Select placeholder="选择企业" showSearch optionFilterProp="label" disabled={!!editing}
                options={enterprises.map(e => ({ value: e.id, label: e.name }))} />
            </Form.Item>
            <Row gutter={16}>
              <Col span={12}>
                <Form.Item name="rule_type" label="规则类型" rules={[{ required: true, message: '请选择类型' }]}>
                  <Select options={RULE_TYPES.map(r => ({ value: r.value, label: r.label }))} onChange={(v) => setRuleType(v)} />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="threshold_value" label={RULE_TYPES.find(r => r.value === ruleType)?.thresholdLabel || '阈值'}
                  rules={[{ required: true, message: '请输入阈值' }]}>
                  <InputNumber style={{ width: '100%' }} min={0} step={1} placeholder="阈值" />
                </Form.Item>
              </Col>
            </Row>
            <Form.Item name="notify_channels" label="通知渠道">
              <Select mode="multiple" placeholder="选择通知渠道" allowClear options={NOTIFY_CHANNELS.map(c => ({ value: c, label: c }))} />
            </Form.Item>
            <Form.Item name="enable" label="启用" valuePropName="checked" initialValue={true}>
              <Switch checkedChildren="启用" unCheckedChildren="停用" />
            </Form.Item>
          </Form>
        </Modal>
      </div>
    </PageWrapper>
  );
};

export default FleetAlertRulesPage;
