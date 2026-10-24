/**
 * 车队 - 企业充电策略管理页面
 *
 * 功能：策略列表(企业维度) / 新增 / 编辑 / 删除 / 策略校验(站点+时段+日限额)
 * API:
 *   GET    /fleet/policies?enterprise_id=
 *   POST   /fleet/policies
 *   PUT    /fleet/policies/{id}
 *   DELETE /fleet/policies/{id}
 *   GET    /fleet/policies/check?enterprise_id=&station_id=&time_slot=
 */
import React, { useEffect, useState, useCallback } from 'react';
import {
  Card, Table, Tag, Button, Modal, Form, Input, Select, Space, message,
  Popconfirm, Statistic, Row, Col, Switch, InputNumber, Result,
} from 'antd';
import {
  PlusOutlined, EditOutlined, DeleteOutlined, ReloadOutlined,
  ThunderboltOutlined, SafetyCertificateOutlined,
} from '@ant-design/icons';
import api from '../../../api';
import PageWrapper from '../../../components/PageWrapper';

/* ── 类型 ── */
interface Policy {
  id: number;
  enterprise_id: number;
  daily_kwh_limit: number;
  allowed_time_slots: string[];
  allowed_station_ids: number[];
  enable: boolean;
  created_at?: string;
  updated_at?: string;
}
interface EnterpriseLite { id: number; name: string; }

/* ── 常量 ── */
const TIME_SLOTS = ['尖', '峰', '平', '谷'];

/* ── 组件 ── */
const FleetChargingPoliciesPage: React.FC = () => {
  const [policies, setPolicies] = useState<Policy[]>([]);
  const [enterprises, setEnterprises] = useState<EnterpriseLite[]>([]);
  const [currentEid, setCurrentEid] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);

  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<Policy | null>(null);
  const [checkOpen, setCheckOpen] = useState(false);
  const [checkResult, setCheckResult] = useState<{ allowed: boolean; reason: string } | null>(null);
  const [checking, setChecking] = useState(false);
  const [form] = Form.useForm();
  const [checkForm] = Form.useForm();

  /* ── 数据加载 ── */
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

  const loadPolicies = useCallback(async () => {
    if (!currentEid) { setPolicies([]); return; }
    setLoading(true);
    try {
      const { data } = await api.get('/fleet/policies', { params: { enterprise_id: currentEid } });
      setPolicies(Array.isArray(data) ? data : (data as any)?.items || []);
    } catch {
      setPolicies([]);
    } finally {
      setLoading(false);
    }
  }, [currentEid]);

  useEffect(() => { loadEnterprises(); }, [loadEnterprises]);
  useEffect(() => { if (currentEid) loadPolicies(); }, [currentEid, loadPolicies]);

  /* ── CRUD ── */
  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      const payload = {
        enterprise_id: values.enterprise_id,
        daily_kwh_limit: Number(values.daily_kwh_limit) || 0,
        allowed_time_slots: values.allowed_time_slots || [],
        allowed_station_ids: (values.allowed_station_ids || []).map((s: string | number) => Number(s)).filter((n: number) => !Number.isNaN(n)),
        enable: values.enable,
      };
      if (editing) {
        await api.put(`/fleet/policies/${editing.id}`, payload);
        message.success('充电策略已更新');
      } else {
        await api.post('/fleet/policies', payload);
        message.success('充电策略已创建');
      }
      setModalOpen(false);
      form.resetFields();
      setEditing(null);
      loadPolicies();
    } catch (err: any) {
      if (err?.errorFields) return;
      message.error('操作失败：' + (err?.response?.data?.detail || err?.message));
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await api.delete(`/fleet/policies/${id}`);
      message.success('已删除');
      loadPolicies();
    } catch (err: any) {
      message.error('删除失败：' + (err?.response?.data?.detail || err?.message));
    }
  };

  const openAdd = () => {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({
      enterprise_id: currentEid || undefined,
      daily_kwh_limit: 0,
      allowed_time_slots: [],
      allowed_station_ids: [],
      enable: true,
    });
    setModalOpen(true);
  };

  const openEdit = (p: Policy) => {
    setEditing(p);
    form.setFieldsValue({
      enterprise_id: p.enterprise_id,
      daily_kwh_limit: p.daily_kwh_limit,
      allowed_time_slots: p.allowed_time_slots || [],
      allowed_station_ids: (p.allowed_station_ids || []).map(String),
      enable: p.enable,
    });
    setModalOpen(true);
  };

  /* ── 策略校验 ── */
  const runCheck = async () => {
    try {
      const values = await checkForm.validateFields();
      setChecking(true);
      const { data } = await api.get('/fleet/policies/check', {
        params: {
          enterprise_id: values.enterprise_id,
          station_id: values.station_id,
          time_slot: values.time_slot,
        },
      });
      setCheckResult({ allowed: !!data?.allowed, reason: data?.reason || '-' });
    } catch (err: any) {
      if (err?.errorFields) return;
      message.error('校验失败：' + (err?.response?.data?.detail || err?.message));
    } finally {
      setChecking(false);
    }
  };

  /* ── 统计 ── */
  const stats = {
    total: policies.length,
    enabled: policies.filter(p => p.enable).length,
    limitSlot: policies.filter(p => (p.allowed_time_slots || []).length > 0).length,
    limitStation: policies.filter(p => (p.allowed_station_ids || []).length > 0).length,
  };

  const entName = (eid: number) => enterprises.find(e => e.id === eid)?.name || `企业#${eid}`;

  const columns = [
    { title: '所属企业', key: 'enterprise', width: 160, ellipsis: true, render: (_: unknown, r: Policy) => entName(r.enterprise_id) },
    {
      title: '日限额(kWh)', dataIndex: 'daily_kwh_limit', key: 'daily_kwh_limit', width: 130, align: 'right' as const,
      render: (v: number) => v > 0 ? <span style={{ fontWeight: 600 }}>{v}</span> : <Tag>不限</Tag>,
    },
    {
      title: '允许时段', dataIndex: 'allowed_time_slots', key: 'allowed_time_slots', width: 150,
      render: (v: string[]) => v?.length ? v.map(s => <Tag color="blue" key={s}>{s}</Tag>) : <Tag>不限</Tag>,
    },
    {
      title: '站点白名单', dataIndex: 'allowed_station_ids', key: 'allowed_station_ids',
      render: (v: number[]) => v?.length ? v.join('、') : <Tag>不限</Tag>,
    },
    {
      title: '状态', dataIndex: 'enable', key: 'enable', width: 90,
      render: (v: boolean) => <Tag color={v ? 'green' : 'default'}>{v ? '启用' : '停用'}</Tag>,
    },
    {
      title: '操作', key: 'action', width: 150,
      render: (_: unknown, r: Policy) => (
        <Space>
          <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(r)}>编辑</Button>
          <Popconfirm title="确认删除该策略？" onConfirm={() => handleDelete(r.id)}>
            <Button size="small" danger icon={<DeleteOutlined />}>删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
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
      loading={loading && policies.length === 0}
      skeletonType="table"
      hasData={policies.length > 0}
      empty={{ type: 'default', title: '暂无充电策略', description: '点击「新增策略」配置企业充电限额/时段/站点白名单', actionText: '新增策略', onAction: openAdd }}
      transition="slide-up"
    >
      <div className="page-container">
        <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
          <Col xs={12} sm={6}><Card><Statistic title="策略总数" value={stats.total} prefix={<ThunderboltOutlined />} /></Card></Col>
          <Col xs={12} sm={6}><Card><Statistic title="启用中" value={stats.enabled} valueStyle={{ color: '#52c41a' }} /></Card></Col>
          <Col xs={12} sm={6}><Card><Statistic title="限时段" value={stats.limitSlot} /></Card></Col>
          <Col xs={12} sm={6}><Card><Statistic title="限站点" value={stats.limitStation} /></Card></Col>
        </Row>

        <Card extra={
          <Space wrap>
            <Select placeholder="选择企业" value={currentEid ?? undefined} onChange={setCurrentEid}
              style={{ width: 200 }} showSearch optionFilterProp="label"
              options={enterprises.map(e => ({ value: e.id, label: e.name }))} />
            <Button icon={<ReloadOutlined />} onClick={loadPolicies}>刷新</Button>
            <Button icon={<SafetyCertificateOutlined />} onClick={() => { checkForm.resetFields(); checkForm.setFieldsValue({ enterprise_id: currentEid ?? undefined, time_slot: '平' }); setCheckResult(null); setCheckOpen(true); }}>策略校验</Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={openAdd}>新增策略</Button>
          </Space>
        }>
          <Table columns={columns} dataSource={policies} rowKey="id" loading={loading}
            pagination={{ pageSize: 10, showSizeChanger: true, showTotal: (t: number) => `共 ${t} 条` }}
          />
        </Card>

        {/* 新增/编辑 Modal */}
        <Modal title={editing ? '编辑充电策略' : '新增充电策略'} open={modalOpen} onOk={handleSubmit}
          onCancel={() => { setModalOpen(false); form.resetFields(); setEditing(null); }}
          width={560} destroyOnHidden
        >
          <Form form={form} layout="vertical">
            <Form.Item name="enterprise_id" label="所属企业" rules={[{ required: true, message: '请选择企业' }]}>
              <Select placeholder="选择企业" showSearch optionFilterProp="label" disabled={!!editing}
                options={enterprises.map(e => ({ value: e.id, label: e.name }))} />
            </Form.Item>
            <Row gutter={16}>
              <Col span={12}>
                <Form.Item name="daily_kwh_limit" label="日充电限额(kWh)" initialValue={0}
                  tooltip="0 表示不限">
                  <InputNumber style={{ width: '100%' }} min={0} step={100} precision={1} placeholder="0 表示不限" />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="enable" label="启用" valuePropName="checked" initialValue={true}>
                  <Switch checkedChildren="启用" unCheckedChildren="停用" />
                </Form.Item>
              </Col>
            </Row>
            <Form.Item name="allowed_time_slots" label="允许时段" tooltip="不选表示不限">
              <Select mode="multiple" placeholder="选择允许时段（可多选）" allowClear options={TIME_SLOTS.map(s => ({ value: s, label: s }))} />
            </Form.Item>
            <Form.Item name="allowed_station_ids" label="站点白名单" tooltip="输入站点ID（回车添加），留空表示不限">
              <Select mode="tags" placeholder="输入站点ID后回车" tokenSeparators={[',', ' ']} allowClear />
            </Form.Item>
          </Form>
        </Modal>

        {/* 策略校验 Modal */}
        <Modal title="策略校验" open={checkOpen} confirmLoading={checking}
          onOk={runCheck} okText="执行校验"
          onCancel={() => { setCheckOpen(false); setCheckResult(null); checkForm.resetFields(); }}
          width={480} destroyOnHidden
        >
          <Form form={checkForm} layout="vertical">
            <Form.Item name="enterprise_id" label="企业" rules={[{ required: true, message: '请选择企业' }]}>
              <Select placeholder="选择企业" options={enterprises.map(e => ({ value: e.id, label: e.name }))} />
            </Form.Item>
            <Row gutter={16}>
              <Col span={12}>
                <Form.Item name="station_id" label="站点ID" rules={[{ required: true, message: '请输入站点ID' }]}>
                  <InputNumber style={{ width: '100%' }} min={1} placeholder="如 1" />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="time_slot" label="时段" rules={[{ required: true, message: '请选择时段' }]}>
                  <Select options={TIME_SLOTS.map(s => ({ value: s, label: s }))} />
                </Form.Item>
              </Col>
            </Row>
          </Form>
          {checkResult && (
            <Result
              status={checkResult.allowed ? 'success' : 'error'}
              title={checkResult.allowed ? '允许充电' : '不允许充电'}
              subTitle={checkResult.reason}
              style={{ padding: '12px 0' }}
            />
          )}
        </Modal>
      </div>
    </PageWrapper>
  );
};

export default FleetChargingPoliciesPage;
