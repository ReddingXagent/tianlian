/**
 * 车队 - 充电排序队列页面
 *
 * 功能：实时队列 / 入队 / 优先级调整 / 规则管理
 * API: /api/v1/fleet/charging/queue, /api/v1/fleet/charging/rules
 */
import React, { useEffect, useState, useCallback } from 'react';
import {
  Card, Table, Tag, Button, Modal, Form, Input, Select, Space, message,
  Popconfirm, Statistic, Row, Col, Tabs, InputNumber, Badge,
} from 'antd';
import {
  PlusOutlined, ReloadOutlined, ThunderboltOutlined,
  ArrowUpOutlined, DeleteOutlined, SettingOutlined,
  FieldTimeOutlined, CarOutlined,
} from '@ant-design/icons';
import api from '../../../api';
import { WS_ENDPOINTS } from '../../../config/websocket';
import { useFleetRealtime } from '../../../hooks/useFleetRealtime';
import PageWrapper from '../../../components/PageWrapper';

/* ── 常量 ── */
const QUEUE_STATUS_COLORS: Record<string, string> = {
  waiting: 'blue', charging: 'green', completed: 'default', cancelled: 'red',
};
const QUEUE_STATUS_TEXT: Record<string, string> = {
  waiting: '等待中', charging: '充电中', completed: '已完成', cancelled: '已取消',
};

/* ── 组件 ── */
const FleetChargingQueuePage: React.FC = () => {
  const [activeTab, setActiveTab] = useState('queue');
  const [loading, setLoading] = useState(false);
  const [stationId, setStationId] = useState(1);

  // 队列
  const [queue, setQueue] = useState<any[]>([]);
  const [enqueueModalOpen, setEnqueueModalOpen] = useState(false);
  const [enqueueForm] = Form.useForm();

  // 规则
  const [rules, setRules] = useState<any[]>([]);
  const [ruleModalOpen, setRuleModalOpen] = useState(false);
  const [editingRule, setEditingRule] = useState<any>(null);
  const [ruleForm] = Form.useForm();

  const loadQueue = useCallback(async () => {
    try {
      const { data } = await api.get('/fleet/charging/queue', { params: { station_id: stationId } });
      setQueue(Array.isArray(data) ? data : []);
    } catch { setQueue([]); }
  }, [stationId]);

  const loadRules = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get('/fleet/charging/rules');
      setRules(Array.isArray(data) ? data : []);
    } catch { setRules([]); }
    finally { setLoading(false); }
  }, []);

  // WebSocket 实时推送 + 断连降级轮询 (仅队列 Tab 激活时)
  const { mode: queueMode } = useFleetRealtime({
    endpoint: WS_ENDPOINTS.fleetQueue(stationId),
    enabled: activeTab === 'queue',
    onData: () => loadQueue(),
    pollFn: loadQueue,
    pollIntervalMs: 15000,
  });

  useEffect(() => {
    if (activeTab === 'queue') loadQueue();
  }, [activeTab, loadQueue]);

  useEffect(() => {
    if (activeTab === 'rules') loadRules();
  }, [activeTab, loadRules]);

  /* ── 队列操作 ── */
  const handleEnqueue = async () => {
    try {
      const values = await enqueueForm.validateFields();
      await api.post('/fleet/charging/queue/enqueue', { ...values, station_id: stationId });
      message.success('入队成功');
      setEnqueueModalOpen(false);
      enqueueForm.resetFields();
      loadQueue();
    } catch (err: any) {
      if (err?.errorFields) return;
      message.error('入队失败：' + (err?.response?.data?.detail || err?.message));
    }
  };

  const handleDequeue = async (id: number, reason: string = 'manual') => {
    try {
      await api.delete(`/fleet/charging/queue/${id}/dequeue`, { params: { reason } });
      message.success('已离队');
      loadQueue();
    } catch (err: any) {
      message.error('操作失败：' + (err?.response?.data?.detail || err?.message));
    }
  };

  const handlePriorityChange = async (id: number, priority: number) => {
    try {
      await api.patch(`/fleet/charging/queue/${id}/priority`, { priority });
      message.success('优先级已调整');
      loadQueue();
    } catch (err: any) {
      message.error('调整失败：' + (err?.response?.data?.detail || err?.message));
    }
  };

  /* ── 规则 CRUD ── */
  const handleRuleSubmit = async () => {
    try {
      const values = await ruleForm.validateFields();
      if (editingRule) {
        await api.put(`/fleet/charging/rules/${editingRule.id}`, values);
        message.success('规则已更新');
      } else {
        await api.post('/fleet/charging/rules', values);
        message.success('规则已创建');
      }
      setRuleModalOpen(false);
      ruleForm.resetFields();
      setEditingRule(null);
      loadRules();
    } catch (err: any) {
      if (err?.errorFields) return;
      message.error('操作失败：' + (err?.response?.data?.detail || err?.message));
    }
  };

  const handleDeleteRule = async (id: number) => {
    try {
      await api.delete(`/fleet/charging/rules/${id}`);
      message.success('规则已删除');
      loadRules();
    } catch (err: any) {
      message.error('删除失败：' + (err?.response?.data?.detail || err?.message));
    }
  };

  /* ── 统计 ── */
  const qStats = {
    total: queue.length,
    waiting: queue.filter(e => e.status === 'waiting').length,
    charging: queue.filter(e => e.status === 'charging').length,
    avgWait: queue.length ? Math.round(queue.reduce((s, e) => s + (e.estimated_wait_minutes || 0), 0) / queue.length) : 0,
  };

  const queueColumns = [
    { title: '#', key: 'seq', width: 50, render: (_: unknown, __: any, idx: number) => idx + 1 },
    { title: '车辆ID', dataIndex: 'vehicle_id', key: 'vehicle_id', width: 80 },
    { title: '优先级', dataIndex: 'priority', key: 'priority', width: 80, align: 'right' as const, render: (v: number) => <Tag color={v < 50 ? 'red' : v < 100 ? 'orange' : 'blue'}>{v}</Tag> },
    { title: '需电量(kWh)', dataIndex: 'required_energy_kwh', key: 'required_energy_kwh', width: 110, align: 'right' as const, render: (v: number) => v?.toFixed(1) || '0.0' },
    { title: '当前SOC', dataIndex: 'current_soc', key: 'current_soc', width: 90, align: 'right' as const, render: (v: number) => v != null ? `${(v * 100).toFixed(0)}%` : '-' },
    { title: '目标SOC', dataIndex: 'target_soc', key: 'target_soc', width: 90, align: 'right' as const, render: (v: number) => v != null ? `${(v * 100).toFixed(0)}%` : '-' },
    { title: '预计等待(min)', dataIndex: 'estimated_wait_minutes', key: 'estimated_wait_minutes', width: 110, align: 'right' as const, render: (v: number) => v || 0 },
    { title: '状态', dataIndex: 'status', key: 'status', width: 90, render: (v: string) => <Badge status={QUEUE_STATUS_COLORS[v] === 'green' ? 'processing' : QUEUE_STATUS_COLORS[v] === 'blue' ? 'warning' : 'default'} text={QUEUE_STATUS_TEXT[v] || v} /> },
    {
      title: '操作', key: 'action', width: 180,
      render: (_: unknown, r: any) => r.status === 'waiting' && (
        <Space>
          <Popconfirm title="上调优先级？" onConfirm={() => handlePriorityChange(r.id, Math.max(1, r.priority - 10))}>
            <Button size="small" icon={<ArrowUpOutlined />}>优先</Button>
          </Popconfirm>
          <Popconfirm title="确认离队？" onConfirm={() => handleDequeue(r.id, 'manual')}>
            <Button size="small" danger icon={<DeleteOutlined />}>离队</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const ruleColumns = [
    { title: '规则名称', dataIndex: 'rule_name', key: 'rule_name', width: 160 },
    { title: '企业ID', dataIndex: 'enterprise_id', key: 'enterprise_id', width: 80 },
    { title: '站点ID', dataIndex: 'station_id', key: 'station_id', width: 80, render: (v: number) => v || '全部' },
    { title: '最大队列', dataIndex: 'max_queue_length', key: 'max_queue_length', width: 90, align: 'right' as const },
    { title: '启用', dataIndex: 'enable', key: 'enable', width: 70, render: (v: boolean) => <Badge status={v ? 'success' : 'default'} text={v ? '启用' : '禁用'} /> },
    {
      title: '操作', key: 'action', width: 140,
      render: (_: unknown, r: any) => (
        <Space>
          <Button size="small" icon={<SettingOutlined />} onClick={() => { setEditingRule(r); ruleForm.setFieldsValue(r); setRuleModalOpen(true); }}>编辑</Button>
          <Popconfirm title="确认删除？" onConfirm={() => handleDeleteRule(r.id)}>
            <Button size="small" danger>删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <PageWrapper loading={loading} skeletonType="table" hasData={true} transition="slide-up">
      <div className="page-container">
        {activeTab === 'queue' && (
          <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
            <Col xs={12} sm={6}><Card><Statistic title="队列总数" value={qStats.total} prefix={<CarOutlined />} /></Card></Col>
            <Col xs={12} sm={6}><Card><Statistic title="等待中" value={qStats.waiting} valueStyle={{ color: '#1890ff' }} /></Card></Col>
            <Col xs={12} sm={6}><Card><Statistic title="充电中" value={qStats.charging} valueStyle={{ color: '#52c41a' }} /></Card></Col>
            <Col xs={12} sm={6}><Card><Statistic title="平均等待(min)" value={qStats.avgWait} prefix={<FieldTimeOutlined />} /></Card></Col>
          </Row>
        )}

        <Card extra={
          <Space>
            {activeTab === 'queue' && (
              <>
                <InputNumber placeholder="站点ID" value={stationId} min={1} onChange={v => setStationId(v || 1)} style={{ width: 100 }} />
                <Button icon={<ReloadOutlined />} onClick={loadQueue}>刷新</Button>
                <Button type="primary" icon={<PlusOutlined />} onClick={() => { enqueueForm.resetFields(); enqueueForm.setFieldsValue({ priority: 100, target_soc: 0.8, current_soc: 0.2, required_energy_kwh: 30 }); setEnqueueModalOpen(true); }}>车辆入队</Button>
              </>
            )}
            {activeTab === 'rules' && (
              <>
                <Button icon={<ReloadOutlined />} onClick={loadRules}>刷新</Button>
                <Button type="primary" icon={<PlusOutlined />} onClick={() => { setEditingRule(null); ruleForm.resetFields(); ruleForm.setFieldsValue({ enterprise_id: 0, max_queue_length: 100, enable: true }); setRuleModalOpen(true); }}>新增规则</Button>
              </>
            )}
          </Space>
        }>
          <Tabs activeKey={activeTab} onChange={setActiveTab} items={[
            { key: 'queue', label: <span><ThunderboltOutlined /> 实时队列 {queueMode === 'realtime' ? '(实时推送)' : '(15s轮询)'}</span>, children: (
              <Table columns={queueColumns} dataSource={queue} rowKey="id" loading={loading}
                pagination={{ pageSize: 15, showSizeChanger: true, showTotal: (t: number) => `共 ${t} 条` }}
              />
            )},
            { key: 'rules', label: <span><SettingOutlined /> 排序规则</span>, children: (
              <Table columns={ruleColumns} dataSource={rules} rowKey="id" loading={loading}
                pagination={{ pageSize: 10 }}
              />
            )},
          ]} />
        </Card>

        {/* 入队 Modal */}
        <Modal title="车辆入队" open={enqueueModalOpen} onOk={handleEnqueue}
          onCancel={() => { setEnqueueModalOpen(false); enqueueForm.resetFields(); }}
          width={480} destroyOnHidden
        >
          <Form form={enqueueForm} layout="vertical">
            <Form.Item name="vehicle_id" label="车辆ID" rules={[{ required: true, message: '请输入车辆ID' }]}>
              <InputNumber style={{ width: '100%' }} min={1} />
            </Form.Item>
            <Form.Item name="enterprise_id" label="企业ID" initialValue={0}>
              <InputNumber style={{ width: '100%' }} min={0} />
            </Form.Item>
            <Row gutter={16}>
              <Col span={12}><Form.Item name="required_energy_kwh" label="需电量(kWh)"><InputNumber style={{ width: '100%' }} min={0} step={5} /></Form.Item></Col>
              <Col span={12}><Form.Item name="priority" label="优先级(数字越小越优先)"><InputNumber style={{ width: '100%' }} min={1} max={999} /></Form.Item></Col>
            </Row>
            <Row gutter={16}>
              <Col span={12}><Form.Item name="current_soc" label="当前SOC"><InputNumber style={{ width: '100%' }} min={0} max={1} step={0.1} precision={2} /></Form.Item></Col>
              <Col span={12}><Form.Item name="target_soc" label="目标SOC"><InputNumber style={{ width: '100%' }} min={0} max={1} step={0.1} precision={2} /></Form.Item></Col>
            </Row>
          </Form>
        </Modal>

        {/* 规则 Modal */}
        <Modal title={editingRule ? '编辑排序规则' : '新增排序规则'} open={ruleModalOpen} onOk={handleRuleSubmit}
          onCancel={() => { setRuleModalOpen(false); ruleForm.resetFields(); setEditingRule(null); }}
          width={520} destroyOnHidden
        >
          <Form form={ruleForm} layout="vertical">
            <Form.Item name="rule_name" label="规则名称" rules={[{ required: true, message: '请输入规则名称' }]}>
              <Input placeholder="如 默认优先级规则" />
            </Form.Item>
            <Row gutter={16}>
              <Col span={12}><Form.Item name="enterprise_id" label="企业ID"><InputNumber style={{ width: '100%' }} min={0} /></Form.Item></Col>
              <Col span={12}><Form.Item name="station_id" label="站点ID (可选)"><InputNumber style={{ width: '100%' }} min={1} /></Form.Item></Col>
            </Row>
            <Form.Item name="max_queue_length" label="最大队列长度">
              <InputNumber style={{ width: '100%' }} min={1} max={9999} />
            </Form.Item>
            <Form.Item name="enable" label="启用">
              <Select><Select.Option value={true}>启用</Select.Option><Select.Option value={false}>禁用</Select.Option></Select>
            </Form.Item>
          </Form>
        </Modal>
      </div>
    </PageWrapper>
  );
};

export default FleetChargingQueuePage;
