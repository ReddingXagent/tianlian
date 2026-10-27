/**
 * 天链 V3 - 值班排班管理页面（Phase9 #52）
 *
 * 功能:
 * - 值班规则管理（CRUD + 自动生成排班）
 * - 排班表查看 & 手动调整
 * - 当前值班人员
 * - 交接班管理
 * - 值班日志
 * - 值班统计报表
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
  Tabs, Card, Button, Table, Tag, Space, Modal, Form, Input, Select, message,
  Descriptions, Row, Col, Statistic, Popconfirm, DatePicker, InputNumber, Switch,
  Typography, Timeline, Divider, Tooltip
} from 'antd';
import {
  PlusOutlined, ReloadOutlined, DeleteOutlined, EditOutlined,
  SearchOutlined, SwapOutlined, FileTextOutlined, BarChartOutlined,
  ClockCircleOutlined, TeamOutlined, UserOutlined, ThunderboltOutlined,
} from '@ant-design/icons';
import { onCallAPI, teamAPI } from '../../api';
import type { OnCallRule, OnCallShift, OnCallLog, OnCallStats, CurrentShiftInfo, Team } from '../../types';
import dayjs from 'dayjs';

const { Text } = Typography;

const OnCallPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState('rules');

  return (
    <div className="page-container">
      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        items={[
          { key: 'rules', label: <><SwapOutlined /> 值班规则</> },
          { key: 'shifts', label: <><ClockCircleOutlined /> 排班表</> },
          { key: 'current', label: <><UserOutlined /> 当前值班</> },
          { key: 'logs', label: <><FileTextOutlined /> 值班日志</> },
          { key: 'stats', label: <><BarChartOutlined /> 统计报表</> },
        ]}
      />

      {activeTab === 'rules' && <RulesTab />}
      {activeTab === 'shifts' && <ShiftsTab />}
      {activeTab === 'current' && <CurrentTab />}
      {activeTab === 'logs' && <LogsTab />}
      {activeTab === 'stats' && <StatsTab />}
    </div>
  );
};

// ============ 值班规则 Tab ============

const RulesTab: React.FC = () => {
  const [rules, setRules] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalVisible, setModalVisible] = useState(false);
  const [editing, setEditing] = useState<any>(null);
  const [form] = Form.useForm();
  const [teams, setTeams] = useState<any[]>([]);
  const [regenerating, setRegenerating] = useState<number | null>(null);

  const loadRules = async () => {
    setLoading(true);
    try {
      const res: any = await onCallAPI.rules.list({ enabled_only: false });
      setRules(res?.data?.rules || res?.rules || []);
    } catch {
      message.error('加载规则失败');
    }
    setLoading(false);
  };

  const loadTeams = async () => {
    try {
      const res: any = await teamAPI.list();
      setTeams(res?.data?.items || res?.items || []);
    } catch { /* ignore */ }
  };

  useEffect(() => { loadRules(); loadTeams(); }, []);

  const handleSave = async () => {
    try {
      const values = await form.validateFields();
      if (editing) {
        await onCallAPI.rules.update(editing.id, values);
        message.success('规则已更新');
      } else {
        const result: any = await onCallAPI.rules.create(values);
        message.success(`规则创建成功，已生成 ${result?.data?.shifts_generated || result?.shifts_generated || 0} 个班次`);
      }
      setModalVisible(false);
      form.resetFields();
      loadRules();
    } catch { /* validation error */ }
  };

  const handleRegenerate = async (ruleId: number) => {
    setRegenerating(ruleId);
    try {
      const res: any = await onCallAPI.rules.generateShifts(ruleId, { num_cycles: 4 });
      message.success(`已重新生成排班，删除 ${res?.data?.deleted ?? res?.deleted ?? 0}，创建 ${res?.data?.created ?? res?.created ?? 0} 个班次`);
      loadRules();
    } catch {
      message.error('重新生成失败');
    }
    setRegenerating(null);
  };

  const handleDelete = async (id: number) => {
    try {
      await onCallAPI.rules.delete(id);
      message.success('规则已删除');
      loadRules();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '删除失败';
      message.error(msg);
    }
  };

  const columns = [
    { title: '规则名称', dataIndex: 'name', key: 'name', width: 180 },
    {
      title: '轮换类型',
      dataIndex: 'schedule_type',
      key: 'schedule_type',
      width: 100,
      render: (v: string) => {
        const map: Record<string, string> = { daily: '每日', weekly: '每周', monthly: '每月', custom: '自定义' };
        return <Tag>{map[v] || v}</Tag>;
      },
    },
    { title: '每班时长', dataIndex: 'shift_duration_hours', key: 'shift_duration_hours', width: 100, render: (h: number) => `${h}h` },
    {
      title: '当前值班',
      dataIndex: 'current_oncall',
      key: 'current_oncall',
      width: 120,
      render: (u: { name: string } | undefined) => u ? <Tag color="green">{u.name}</Tag> : <Tag color="default">无人</Tag>,
    },
    { title: '总班次', dataIndex: 'total_shifts', key: 'total_shifts', width: 80 },
    { title: '待值班', dataIndex: 'upcoming_shifts', key: 'upcoming_shifts', width: 80 },
    {
      title: '状态',
      dataIndex: 'enabled',
      key: 'enabled',
      width: 80,
      render: (v: boolean) => <Tag color={v ? 'green' : 'default'}>{v ? '启用' : '停用'}</Tag>,
    },
    {
      title: '操作',
      key: 'action',
      width: 200,
      render: (record: OnCallRule) => (
        <Space size="small">
          <Button icon={<EditOutlined />} size="small" onClick={() => {
            setEditing(record);
            form.setFieldsValue({
              ...record,
              rotation_order: record.rotation_order,
              notify_methods: record.notify_methods,
            });
            setModalVisible(true);
          }} />
          <Tooltip title="重新生成排班">
            <Button icon={<ReloadOutlined />} size="small" loading={regenerating === record.id} onClick={() => handleRegenerate(record.id)} />
          </Tooltip>
          <Popconfirm title="确认删除?" onConfirm={() => handleDelete(record.id)}>
            <Button icon={<DeleteOutlined />} size="small" danger />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <Card
      title="值班规则管理"
      extra={
        <Space>
          <Button icon={<ReloadOutlined />} onClick={loadRules}>刷新</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => {
            setEditing(null);
            form.resetFields();
            setModalVisible(true);
          }}>
            新增规则
          </Button>
        </Space>
      }
    >
      <Table dataSource={Array.isArray(rules) ? rules : []} columns={columns} rowKey="id" loading={loading} scroll={{ x: 960 }} pagination={{ pageSize: 10, showTotal: (t: number) => `共 ${t} 条` }} />

      <Modal title={editing ? '编辑规则' : '新增值班规则'} open={modalVisible} onCancel={() => setModalVisible(false)} onOk={handleSave} width="min(700px, calc(100vw - 24px))">
        <Form form={form} layout="vertical">
          <Row gutter={16}>
            <Col xs={24} sm={12}>
              <Form.Item name="name" label="规则名称" rules={[{ required: true, message: '请输入规则名称' }]}>
                <Input placeholder="如: 一线工程师轮值" />
              </Form.Item>
            </Col>
            <Col xs={24} sm={12}>
              <Form.Item name="team_id" label="所属团队" rules={[{ required: true, message: '请选择团队' }]}>
                <Select placeholder="选择团队">
                  {(Array.isArray(teams) ? teams : []).map((t: Team) => <Select.Option key={t.id} value={t.id}>{t.name}</Select.Option>)}
                </Select>
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col xs={24} sm={8}>
              <Form.Item name="schedule_type" label="轮换类型" initialValue="weekly">
                <Select>
                  <Select.Option value="daily">每日轮换</Select.Option>
                  <Select.Option value="weekly">每周轮换</Select.Option>
                  <Select.Option value="monthly">每月轮换</Select.Option>
                  <Select.Option value="custom">自定义</Select.Option>
                </Select>
              </Form.Item>
            </Col>
            <Col xs={24} sm={8}>
              <Form.Item name="shift_duration_hours" label="每班时长(小时)" initialValue={168}>
                <InputNumber min={1} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col xs={24} sm={8}>
              <Form.Item name="overlap_minutes" label="交接重叠(分钟)" initialValue={30}>
                <InputNumber min={0} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="rotation_order" label="轮换顺序（用户ID列表）" rules={[{ required: true, message: '请输入轮换顺序' }]}>
            <Input placeholder="如: [1,2,3] - 用JSON数组格式" />
          </Form.Item>
          <Row gutter={16}>
            <Col xs={24} sm={12}>
              <Form.Item name="escalation_level" label="升级级别" initialValue={2}>
                <InputNumber min={1} max={5} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col xs={24} sm={12}>
              <Form.Item name="escalation_timeout_minutes" label="升级超时(分钟)" initialValue={30}>
                <InputNumber min={5} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="auto_assign_workorders" label="自动分配告警工单" valuePropName="checked" initialValue={true}>
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  );
};

// ============ 排班表 Tab ============

const ShiftsTab: React.FC = () => {
  const [shifts, setShifts] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [rules, setRules] = useState<any[]>([]);
  const [filterRule, setFilterRule] = useState<number | undefined>(undefined);
  const [filterStatus, setFilterStatus] = useState<string>('');

  const load = async () => {
    setLoading(true);
    try {
      const params: Record<string, unknown> = { page: 1, page_size: 50 };
      if (filterRule) params.rule_id = filterRule;
      if (filterStatus) params.status = filterStatus;
      const res: any = await onCallAPI.shifts.list(params);
      const rawShifts = res?.data?.items || res?.data?.shifts || res?.items || res?.shifts || [];
      setShifts(Array.isArray(rawShifts) ? rawShifts : []);
    } catch { message.error('加载排班失败'); }
    setLoading(false);
  };

  const loadRules = async () => {
    try {
      const res: any = await onCallAPI.rules.list();
      setRules(res?.data?.rules || res?.rules || []);
    } catch { /* ignore */ }
  };

  useEffect(() => { load(); loadRules(); }, []);

  const statusColor: Record<string, string> = {
    scheduled: 'blue',
    active: 'green',
    completed: 'default',
    cancelled: 'orange',
    missed: 'red',
  };

  const statusText: Record<string, string> = {
    scheduled: '待值班',
    active: '值班中',
    completed: '已完成',
    cancelled: '已取消',
    missed: '已错过',
  };

  const handleStatusChange = async (shiftId: number, status: string) => {
    try {
      await onCallAPI.shifts.updateStatus(shiftId, status);
      message.success('状态已更新');
      load();
    } catch { message.error('更新失败'); }
  };

  const columns = [
    { title: '规则', dataIndex: 'rule_name', key: 'rule_name', width: 150 },
    { title: '值班人', dataIndex: ['user', 'name'], key: 'user_name', width: 100 },
    { title: '备份人', dataIndex: ['backup_user', 'name'], key: 'backup_name', width: 100, render: (v: string) => v || '-' },
    { title: '开始时间', dataIndex: 'start_time', key: 'start_time', width: 180, render: (v: string) => dayjs(v).format('YYYY-MM-DD HH:mm') },
    { title: '结束时间', dataIndex: 'end_time', key: 'end_time', width: 180, render: (v: string) => dayjs(v).format('YYYY-MM-DD HH:mm') },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 90,
      render: (v: string) => <Tag color={statusColor[v]}>{statusText[v] || v}</Tag>,
    },
    {
      title: '交接',
      dataIndex: 'handover_completed',
      key: 'handover',
      width: 70,
      render: (v: boolean) => v ? <Tag color="green">✅</Tag> : <Tag color="default">❌</Tag>,
    },
    {
      title: '操作',
      key: 'action',
      width: 150,
      render: (record: OnCallShift) => (
        <Space size="small">
          {record.status === 'scheduled' && (
            <Button size="small" onClick={() => handleStatusChange(record.id, 'active')}>开始</Button>
          )}
          {record.status === 'active' && (
            <Button size="small" type="primary" onClick={() => handleStatusChange(record.id, 'completed')}>完成</Button>
          )}
          {record.status === 'scheduled' && (
            <Button size="small" danger onClick={() => handleStatusChange(record.id, 'cancelled')}>取消</Button>
          )}
        </Space>
      ),
    },
  ];

  return (
    <Card
      title="排班表"
      extra={
        <Space>
          <Select placeholder="筛选规则" allowClear value={filterRule} onChange={setFilterRule} style={{ width: 180 }} loading={!rules.length}>
            {(Array.isArray(rules) ? rules : []).map((r: OnCallRule) => <Select.Option key={r.id} value={r.id}>{r.name}</Select.Option>)}
          </Select>
          <Select placeholder="筛选状态" allowClear value={filterStatus} onChange={setFilterStatus} style={{ width: 120 }}>
            {Object.entries(statusText).map(([k, v]) => <Select.Option key={k} value={k}>{v}</Select.Option>)}
          </Select>
          <Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>
        </Space>
      }
    >
      <Table dataSource={Array.isArray(shifts) ? shifts : []} columns={columns} rowKey="id" loading={loading} scroll={{ x: 1040 }} pagination={{ pageSize: 20, showTotal: (t: number) => `共 ${t} 条` }} />
    </Card>
  );
};

// ============ 当前值班 Tab ============

const CurrentTab: React.FC = () => {
  const [currentShifts, setCurrentShifts] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const res: any = await onCallAPI.shifts.getCurrent();
      const raw = res?.data?.current_shifts || res?.current_shifts || [];
      setCurrentShifts(Array.isArray(raw) ? raw : []);
    } catch { message.error('加载当前值班失败'); }
    setLoading(false);
  };

  useEffect(() => { load(); }, []);

  return (
    <Card
      title="当前值班人员"
      extra={<Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>}
    >
      {loading ? <Text>加载中...</Text> : currentShifts.length === 0 ? (
        <Text type="secondary">当前无值班人员</Text>
      ) : (
        <Row gutter={16}>
          {(Array.isArray(currentShifts) ? currentShifts : []).map((s: CurrentShiftInfo) => (
            <Col xs={24} sm={12} md={8} key={s.shift_id}>
              <Card size="small" style={{ marginBottom: 16 }}>
                <Descriptions column={1} size="small">
                  <Descriptions.Item label="规则">{s.rule_name}</Descriptions.Item>
                  <Descriptions.Item label="值班人">
                    <Tag color="blue">{s.primary?.name}</Tag>
                  </Descriptions.Item>
                  <Descriptions.Item label="备份人">
                    {s.backup ? <Tag color="orange">{s.backup.name}</Tag> : <Text type="secondary">无</Text>}
                  </Descriptions.Item>
                  <Descriptions.Item label="剩余时间">
                    <Text strong style={{ color: '#ff5a36' }}>{s.remaining_hours} 小时</Text>
                  </Descriptions.Item>
                  <Descriptions.Item label="交接">
                    {s.handover_completed ? <Tag color="green">已完成</Tag> : <Tag color="default">未完成</Tag>}
                  </Descriptions.Item>
                </Descriptions>
              </Card>
            </Col>
          ))}
        </Row>
      )}
    </Card>
  );
};

// ============ 值班日志 Tab ============

const LogsTab: React.FC = () => {
  const [logs, setLogs] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalVisible, setModalVisible] = useState(false);
  const [form] = Form.useForm();

  const load = async () => {
    setLoading(true);
    try {
      const res: any = await onCallAPI.logs.list({ page: 1, page_size: 50 });
      setLogs(res?.data?.items || res?.data?.logs || res?.items || res?.logs || []);
    } catch { message.error('加载日志失败'); }
    setLoading(false);
  };

  useEffect(() => { load(); }, []);

  const handleSave = async () => {
    try {
      const values = await form.validateFields();
      await onCallAPI.logs.create(values);
      message.success('日志已创建');
      setModalVisible(false);
      form.resetFields();
      load();
    } catch { /* validation */ }
  };

  const eventTypeIcon: Record<string, string> = {
    note: '📝',
    alarm: '🚨',
    workorder: '🔧',
    handover: '🔄',
    escalation: '⬆️',
    incident: '⚠️',
  };

  const severityColor: Record<string, string> = { info: 'blue', warning: 'orange', critical: 'red' };
  const severityText: Record<string, string> = { info: '普通', warning: '警告', critical: '严重' };

  const columns = [
    { title: '类型', dataIndex: 'event_type', key: 'event_type', width: 100, render: (v: string) => <Tag>{eventTypeIcon[v] || ''} {v}</Tag> },
    { title: '内容', dataIndex: 'content', key: 'content', ellipsis: true },
    {
      title: '严重度',
      dataIndex: 'severity',
      key: 'severity',
      width: 80,
      render: (v: string) => <Tag color={severityColor[v]}>{severityText[v]}</Tag>,
    },
    { title: '关联告警', dataIndex: 'alarm_id', key: 'alarm_id', width: 90, render: (v: number) => v ? `#${v}` : '-' },
    { title: '关联工单', dataIndex: 'workorder_id', key: 'workorder_id', width: 120, render: (v: string) => v || '-' },
    { title: '时间', dataIndex: 'created_at', key: 'created_at', width: 160, render: (v: string) => dayjs(v).format('YYYY-MM-DD HH:mm:ss') },
  ];

  return (
    <Card
      title="值班日志"
      extra={
        <Space>
          <Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => { form.resetFields(); setModalVisible(true); }}>
            新增日志
          </Button>
        </Space>
      }
    >
      <Table dataSource={Array.isArray(logs) ? logs : []} columns={columns} rowKey="id" loading={loading} scroll={{ x: 720 }} pagination={{ pageSize: 20, showTotal: (t: number) => `共 ${t} 条` }} />

      <Modal title="新增值班日志" open={modalVisible} onCancel={() => setModalVisible(false)} onOk={handleSave}>
        <Form form={form} layout="vertical">
          <Form.Item name="shift_id" label="班次ID" rules={[{ required: true, message: '请输入班次ID' }]}>
            <InputNumber style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="user_id" label="记录人ID" rules={[{ required: true, message: '请输入记录人ID' }]}>
            <InputNumber style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="event_type" label="事件类型" initialValue="note">
            <Select>
              <Select.Option value="note">📝 备注</Select.Option>
              <Select.Option value="alarm">🚨 告警</Select.Option>
              <Select.Option value="workorder">🔧 工单</Select.Option>
              <Select.Option value="handover">🔄 交接</Select.Option>
              <Select.Option value="escalation">⬆️ 升级</Select.Option>
              <Select.Option value="incident">⚠️ 事件</Select.Option>
            </Select>
          </Form.Item>
          <Form.Item name="content" label="内容" rules={[{ required: true, message: '请输入日志内容' }]}>
            <Input.TextArea rows={4} placeholder="日志内容..." />
          </Form.Item>
          <Form.Item name="severity" label="严重级别" initialValue="info">
            <Select>
              <Select.Option value="info">普通</Select.Option>
              <Select.Option value="warning">警告</Select.Option>
              <Select.Option value="critical">严重</Select.Option>
            </Select>
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  );
};

// ============ 统计报表 Tab ============

const StatsTab: React.FC = () => {
  const [stats, setStats] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [days, setDays] = useState(30);

  const load = async (d: number = days) => {
    setLoading(true);
    try {
      const res: any = await onCallAPI.stats.getStats(d);
      setStats(res?.data || res);
    } catch { message.error('加载统计失败'); }
    setLoading(false);
  };

  useEffect(() => { load(); }, []);

  if (loading || !stats) return <Card><Text type="secondary">{loading ? '加载中...' : '暂无数据'}</Text></Card>;

  return (
    <Card
      title="值班统计报表"
      extra={
        <Space>
          <Select value={days} onChange={(v) => { setDays(v); load(v); }} style={{ width: 120 }}>
            <Select.Option value={7}>最近7天</Select.Option>
            <Select.Option value={30}>最近30天</Select.Option>
            <Select.Option value={90}>最近90天</Select.Option>
            <Select.Option value={365}>最近一年</Select.Option>
          </Select>
          <Button icon={<ReloadOutlined />} onClick={() => load()}>刷新</Button>
        </Space>
      }
    >
      {/* 班次完成概览 */}
      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col xs={12} sm={6}>
          <Card><Statistic title="总班次" value={stats.shifts.total} suffix="个" /></Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card><Statistic title="完成班次" value={stats.shifts.completed} valueStyle={{ color: '#34a853' }} suffix="个" /></Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card><Statistic title="错过班次" value={stats.shifts.missed} valueStyle={{ color: '#ea4335' }} suffix="个" /></Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card><Statistic title="完成率" value={stats.shifts.completion_rate} suffix="%" valueStyle={{ color: '#ff5a36' }} /></Card>
        </Col>
      </Row>

      {/* 交接统计 */}
      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col xs={24} md={12}>
          <Card title="交接班统计">
            <Descriptions column={2}>
              <Descriptions.Item label="完成交接">{stats.handover.completed}</Descriptions.Item>
              <Descriptions.Item label="交接率">
                <Text strong style={{ color: '#34a853' }}>{stats.handover.rate}%</Text>
              </Descriptions.Item>
            </Descriptions>
          </Card>
        </Col>
        <Col xs={24} md={12}>
          <Card title="日志统计">
            <Descriptions column={2}>
              <Descriptions.Item label="总日志数">{stats.logs.total}</Descriptions.Item>
              <Descriptions.Item label="事件类型分布">
                {Object.entries(stats.logs.by_event_type || {}).map(([k, v]) => (
                  <Tag key={k}>{k}: {v as number}</Tag>
                ))}
              </Descriptions.Item>
            </Descriptions>
          </Card>
        </Col>
      </Row>

      {/* 按人员统计 */}
      <Card title="按人员班次统计">
        <Table
          dataSource={stats.by_user || []}
          columns={[
            { title: '人员', dataIndex: 'name', key: 'name', width: 120, render: (n: string) => <Tag icon={<UserOutlined />}>{n}</Tag> },
            { title: '班次数', dataIndex: 'shift_count', key: 'shift_count', width: 100, sorter: (a: { shift_count: number }, b: { shift_count: number }) => a.shift_count - b.shift_count },
          ]}
          rowKey="user_id"
          pagination={false}
          size="small"
        />
      </Card>
    </Card>
  );
};

export default OnCallPage;
