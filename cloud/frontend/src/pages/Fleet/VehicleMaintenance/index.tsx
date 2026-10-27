/**
 * 车队 - 车辆维保/保险档案页面
 *
 * 功能：企业+车辆选择 / Tabs(维保记录/保险记录/聚合档案) / 维保&保险 CRUD / 到期提醒
 * API:
 *   GET/POST/DELETE /fleet/vehicles/{vid}/maintenance
 *   GET/POST/DELETE /fleet/vehicles/{vid}/insurance
 *   GET             /fleet/vehicles/{vid}/profile   聚合档案
 *   GET /fleet/enterprises ; GET /enterprises/{eid}/vehicles
 */
import React, { useEffect, useState, useCallback } from 'react';
import {
  Card, Table, Tag, Button, Modal, Form, Input, Select, Space, message,
  Popconfirm, Statistic, Row, Col, Tabs, InputNumber, DatePicker, Descriptions, Empty,
} from 'antd';
import {
  PlusOutlined, DeleteOutlined, ReloadOutlined, ToolOutlined, SafetyOutlined,
  FileProtectOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import api from '../../../api';
import PageWrapper from '../../../components/PageWrapper';

/* ── 类型 ── */
interface EnterpriseLite { id: number; name: string; }
interface VehicleLite { id: number; plate_number: string; }
interface Maintenance {
  id: number; vehicle_id: number; type: string;
  start_at?: string | null; end_at?: string | null;
  cost: number; mileage: number; description?: string; status: string;
  created_at?: string;
}
interface Insurance {
  id: number; vehicle_id: number; insurance_type: string;
  company: string; policy_no: string; start_date?: string; end_date?: string;
  premium: number; attachment_url?: string;
}
interface VehicleProfile {
  vehicle_id: number;
  maintenance: { total_count: number; total_cost: number; by_status: Record<string, number>; recent: Maintenance[] };
  insurance: { total_count: number; active_count: number; total_premium: number; current: Insurance[] };
  expiry_reminders: { id: number; insurance_type: string; company: string; policy_no: string; end_date: string; days_remaining: number; status: string }[];
}

/* ── 常量 ── */
const MAINT_TYPES = [
  { value: 'maintenance', label: '保养' },
  { value: 'repair', label: '维修' },
  { value: 'inspection', label: '年检' },
];
const MAINT_STATUS = [
  { value: 'pending', label: '待处理' },
  { value: 'in_progress', label: '进行中' },
  { value: 'completed', label: '已完成' },
  { value: 'cancelled', label: '已取消' },
];
const INS_TYPES = [
  { value: 'compulsory', label: '交强险' },
  { value: 'commercial', label: '商业险' },
  { value: 'third_party', label: '第三者责任险' },
];
const MAINT_TYPE_TEXT: Record<string, string> = { maintenance: '保养', repair: '维修', inspection: '年检' };
const MAINT_STATUS_COLOR: Record<string, string> = { pending: 'default', in_progress: 'processing', completed: 'success', cancelled: 'error' };
const MAINT_STATUS_TEXT: Record<string, string> = { pending: '待处理', in_progress: '进行中', completed: '已完成', cancelled: '已取消' };
const INS_TYPE_TEXT: Record<string, string> = { compulsory: '交强险', commercial: '商业险', third_party: '第三者责任险' };
const REMINDER_COLOR: Record<string, string> = { expired: 'red', expiring_soon: 'orange' };

/* ── 组件 ── */
const FleetVehicleMaintenancePage: React.FC = () => {
  const [activeTab, setActiveTab] = useState('maintenance');
  const [enterprises, setEnterprises] = useState<EnterpriseLite[]>([]);
  const [vehicles, setVehicles] = useState<VehicleLite[]>([]);
  const [currentEid, setCurrentEid] = useState<number | null>(null);
  const [vehicleId, setVehicleId] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);

  const [maintenances, setMaintenances] = useState<Maintenance[]>([]);
  const [insurances, setInsurances] = useState<Insurance[]>([]);
  const [profile, setProfile] = useState<VehicleProfile | null>(null);

  const [maintModalOpen, setMaintModalOpen] = useState(false);
  const [insModalOpen, setInsModalOpen] = useState(false);
  const [maintForm] = Form.useForm();
  const [insForm] = Form.useForm();

  /* ── 加载企业/车辆 ── */
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

  const loadVehicles = useCallback(async () => {
    if (!currentEid) { setVehicles([]); return; }
    try {
      const { data } = await api.get(`/enterprises/${currentEid}/vehicles`);
      const items: VehicleLite[] = (Array.isArray(data) ? data : (data as any)?.items || []).map((v: any) => ({ id: v.id, plate_number: v.plate_number }));
      setVehicles(items);
      if (items.length && vehicleId === null) setVehicleId(items[0].id);
      else if (items.length && vehicleId && !items.find(v => v.id === vehicleId)) setVehicleId(items[0].id);
      else if (!items.length) setVehicleId(null);
    } catch {
      setVehicles([]);
    }
  }, [currentEid, vehicleId]);

  const loadData = useCallback(async () => {
    if (!vehicleId) { setMaintenances([]); setInsurances([]); setProfile(null); return; }
    setLoading(true);
    try {
      if (activeTab === 'maintenance') {
        const { data } = await api.get(`/fleet/vehicles/${vehicleId}/maintenance`);
        setMaintenances(Array.isArray(data) ? data : (data as any)?.items || []);
      } else if (activeTab === 'insurance') {
        const { data } = await api.get(`/fleet/vehicles/${vehicleId}/insurance`);
        setInsurances(Array.isArray(data) ? data : (data as any)?.items || []);
      } else {
        const { data } = await api.get(`/fleet/vehicles/${vehicleId}/profile`);
        setProfile(data || null);
      }
    } catch {
      if (activeTab === 'maintenance') setMaintenances([]);
      else if (activeTab === 'insurance') setInsurances([]);
      else setProfile(null);
    } finally {
      setLoading(false);
    }
  }, [vehicleId, activeTab]);

  useEffect(() => { loadEnterprises(); }, [loadEnterprises]);
  useEffect(() => { if (currentEid) loadVehicles(); }, [currentEid, loadVehicles]);
  useEffect(() => { if (vehicleId) loadData(); }, [vehicleId, activeTab, loadData]);

  /* ── 维保 CRUD ── */
  const handleMaintSubmit = async () => {
    if (!vehicleId) return;
    try {
      const values = await maintForm.validateFields();
      const payload = {
        type: values.type,
        start_at: values.start_at ? values.start_at.format('YYYY-MM-DD') : undefined,
        end_at: values.end_at ? values.end_at.format('YYYY-MM-DD') : undefined,
        cost: Number(values.cost) || 0,
        mileage: Number(values.mileage) || 0,
        description: values.description,
        status: values.status,
      };
      await api.post(`/fleet/vehicles/${vehicleId}/maintenance`, payload);
      message.success('维保记录已创建');
      setMaintModalOpen(false);
      maintForm.resetFields();
      loadData();
    } catch (err: any) {
      if (err?.errorFields) return;
      message.error('创建失败：' + (err?.response?.data?.detail || err?.message));
    }
  };

  const handleDeleteMaint = async (id: number) => {
    if (!vehicleId) return;
    try {
      await api.delete(`/fleet/vehicles/${vehicleId}/maintenance/${id}`);
      message.success('已删除');
      loadData();
    } catch (err: any) {
      message.error('删除失败：' + (err?.response?.data?.detail || err?.message));
    }
  };

  /* ── 保险 CRUD ── */
  const handleInsSubmit = async () => {
    if (!vehicleId) return;
    try {
      const values = await insForm.validateFields();
      const payload = {
        insurance_type: values.insurance_type,
        company: values.company,
        policy_no: values.policy_no,
        start_date: values.start_date.format('YYYY-MM-DD'),
        end_date: values.end_date.format('YYYY-MM-DD'),
        premium: Number(values.premium) || 0,
        attachment_url: values.attachment_url,
      };
      await api.post(`/fleet/vehicles/${vehicleId}/insurance`, payload);
      message.success('保险记录已创建');
      setInsModalOpen(false);
      insForm.resetFields();
      loadData();
    } catch (err: any) {
      if (err?.errorFields) return;
      message.error('创建失败：' + (err?.response?.data?.detail || err?.message));
    }
  };

  const handleDeleteIns = async (id: number) => {
    if (!vehicleId) return;
    try {
      await api.delete(`/fleet/vehicles/${vehicleId}/insurance/${id}`);
      message.success('已删除');
      loadData();
    } catch (err: any) {
      message.error('删除失败：' + (err?.response?.data?.detail || err?.message));
    }
  };

  /* ── 表格列 ── */
  const maintColumns = [
    { title: '类型', dataIndex: 'type', key: 'type', width: 90, render: (v: string) => <Tag color="cyan">{MAINT_TYPE_TEXT[v] || v}</Tag> },
    { title: '开始', dataIndex: 'start_at', key: 'start_at', width: 120, render: (v: string) => v?.split('T')[0] || '-' },
    { title: '结束', dataIndex: 'end_at', key: 'end_at', width: 120, render: (v: string) => v?.split('T')[0] || '-' },
    { title: '里程(km)', dataIndex: 'mileage', key: 'mileage', width: 100, align: 'right' as const, render: (v: number) => v?.toFixed(0) || '0' },
    { title: '费用(¥)', dataIndex: 'cost', key: 'cost', width: 100, align: 'right' as const, render: (v: number) => (v || 0).toFixed(2) },
    { title: '状态', dataIndex: 'status', key: 'status', width: 90, render: (v: string) => <Tag color={MAINT_STATUS_COLOR[v] || 'default'}>{MAINT_STATUS_TEXT[v] || v}</Tag> },
    { title: '描述', dataIndex: 'description', key: 'description', ellipsis: true, render: (v: string) => v || '-' },
    {
      title: '操作', key: 'action', width: 90,
      render: (_: unknown, r: Maintenance) => (
        <Popconfirm title="确认删除？" onConfirm={() => handleDeleteMaint(r.id)}>
          <Button size="small" danger icon={<DeleteOutlined />}>删除</Button>
        </Popconfirm>
      ),
    },
  ];

  const insColumns = [
    { title: '险种', dataIndex: 'insurance_type', key: 'insurance_type', width: 120, render: (v: string) => <Tag color="geekblue">{INS_TYPE_TEXT[v] || v}</Tag> },
    { title: '保险公司', dataIndex: 'company', key: 'company', width: 140, ellipsis: true },
    { title: '保单号', dataIndex: 'policy_no', key: 'policy_no', width: 150, render: (v: string) => v ? <code style={{ fontSize: 11 }}>{v}</code> : '-' },
    { title: '起保', dataIndex: 'start_date', key: 'start_date', width: 120, render: (v: string) => v?.split('T')[0] || '-' },
    { title: '到期', dataIndex: 'end_date', key: 'end_date', width: 120, render: (v: string) => v?.split('T')[0] || '-' },
    { title: '保费(¥)', dataIndex: 'premium', key: 'premium', width: 110, align: 'right' as const, render: (v: number) => (v || 0).toFixed(2) },
    {
      title: '操作', key: 'action', width: 90,
      render: (_: unknown, r: Insurance) => (
        <Popconfirm title="确认删除？" onConfirm={() => handleDeleteIns(r.id)}>
          <Button size="small" danger icon={<DeleteOutlined />}>删除</Button>
        </Popconfirm>
      ),
    },
  ];

  const reminderColumns = [
    { title: '险种', dataIndex: 'insurance_type', key: 'insurance_type', width: 130, render: (v: string) => INS_TYPE_TEXT[v] || v },
    { title: '保险公司', dataIndex: 'company', key: 'company', width: 150 },
    { title: '保单号', dataIndex: 'policy_no', key: 'policy_no', width: 160 },
    { title: '到期日', dataIndex: 'end_date', key: 'end_date', width: 120, render: (v: string) => v?.split('T')[0] || '-' },
    { title: '剩余天数', dataIndex: 'days_remaining', key: 'days_remaining', width: 100, align: 'right' as const, render: (v: number) => v < 0 ? `已过期 ${-v} 天` : `${v} 天` },
    { title: '状态', dataIndex: 'status', key: 'status', width: 110, render: (v: string) => <Tag color={REMINDER_COLOR[v] || 'default'}>{v === 'expired' ? '已过期' : '即将到期'}</Tag> },
  ];

  const curVehicle = vehicles.find(v => v.id === vehicleId);

  /* ── 空态：无企业/车辆 ── */
  if (currentEid === null && enterprises.length === 0 && !loading) {
    return (
      <PageWrapper loading={false} hasData={false} transition="slide-up">
        <Card><div style={{ padding: 24, textAlign: 'center', color: '#999' }}>暂无企业，请先在「车队企业」中创建企业。</div></Card>
      </PageWrapper>
    );
  }

  return (
    <PageWrapper
      loading={loading && activeTab === 'maintenance' && maintenances.length === 0}
      skeletonType="table"
      hasData={activeTab === 'maintenance' ? maintenances.length > 0 : activeTab === 'insurance' ? insurances.length > 0 : !!profile}
      transition="slide-up"
    >
      <div className="page-container">
        <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
          <Col xs={12} sm={6}><Card><Statistic title="维保次数" value={profile?.maintenance?.total_count ?? maintenances.length} prefix={<ToolOutlined />} /></Card></Col>
          <Col xs={12} sm={6}><Card><Statistic title="维保总费用" value={profile?.maintenance?.total_cost ?? 0} prefix="¥" precision={2} /></Card></Col>
          <Col xs={12} sm={6}><Card><Statistic title="保单数" value={profile?.insurance?.total_count ?? insurances.length} prefix={<SafetyOutlined />} /></Card></Col>
          <Col xs={12} sm={6}><Card><Statistic title="生效保单" value={profile?.insurance?.active_count ?? 0} valueStyle={{ color: '#52c41a' }} /></Card></Col>
        </Row>

        <Card extra={
          <Space wrap>
            <Select placeholder="选择企业" value={currentEid ?? undefined} onChange={(v) => { setCurrentEid(v); setVehicleId(null); }}
              style={{ width: 180 }} showSearch optionFilterProp="label"
              options={enterprises.map(e => ({ value: e.id, label: e.name }))} />
            <Select placeholder="选择车辆" value={vehicleId ?? undefined} onChange={setVehicleId}
              style={{ width: 160 }} showSearch optionFilterProp="label" disabled={!vehicles.length}
              options={vehicles.map(v => ({ value: v.id, label: v.plate_number }))} />
            <Button icon={<ReloadOutlined />} onClick={loadData}>刷新</Button>
          </Space>
        }>
          {!vehicleId ? (
            <Empty description="请选择企业并选择车辆以查看维保/保险档案" style={{ padding: 48 }} />
          ) : (
            <Tabs
              activeKey={activeTab}
              onChange={setActiveTab}
              items={[
                {
                  key: 'maintenance',
                  label: <span><ToolOutlined /> 维保记录</span>,
                  children: (
                    <>
                      <Space style={{ marginBottom: 12 }}>
                        <Button type="primary" icon={<PlusOutlined />} onClick={() => { maintForm.resetFields(); maintForm.setFieldsValue({ type: 'maintenance', status: 'pending', cost: 0, mileage: 0 }); setMaintModalOpen(true); }}>新增维保</Button>
                      </Space>
                      <Table columns={maintColumns} dataSource={maintenances} rowKey="id" loading={loading}
                        pagination={{ pageSize: 10, showSizeChanger: true, showTotal: (t: number) => `共 ${t} 条` }} />
                    </>
                  ),
                },
                {
                  key: 'insurance',
                  label: <span><SafetyOutlined /> 保险记录</span>,
                  children: (
                    <>
                      <Space style={{ marginBottom: 12 }}>
                        <Button type="primary" icon={<PlusOutlined />} onClick={() => { insForm.resetFields(); insForm.setFieldsValue({ insurance_type: 'compulsory', premium: 0 }); setInsModalOpen(true); }}>新增保险</Button>
                      </Space>
                      <Table columns={insColumns} dataSource={insurances} rowKey="id" loading={loading}
                        pagination={{ pageSize: 10, showSizeChanger: true, showTotal: (t: number) => `共 ${t} 条` }} />
                    </>
                  ),
                },
                {
                  key: 'profile',
                  label: <span><FileProtectOutlined /> 聚合档案</span>,
                  children: profile ? (
                    <Space direction="vertical" style={{ width: '100%' }} size="middle">
                      <Card size="small" title={`车辆档案 - ${curVehicle?.plate_number || ''}`}>
                        <Descriptions column={2} size="small" bordered>
                          <Descriptions.Item label="维保次数">{profile.maintenance.total_count}</Descriptions.Item>
                          <Descriptions.Item label="维保总费用">¥ {profile.maintenance.total_cost?.toFixed(2)}</Descriptions.Item>
                          <Descriptions.Item label="保单总数">{profile.insurance.total_count}</Descriptions.Item>
                          <Descriptions.Item label="生效保单">{profile.insurance.active_count}</Descriptions.Item>
                          <Descriptions.Item label="保费合计" span={2}>¥ {profile.insurance.total_premium?.toFixed(2)}</Descriptions.Item>
                          <Descriptions.Item label="维保状态分布" span={2}>
                            {Object.keys(profile.maintenance.by_status || {}).length
                              ? Object.entries(profile.maintenance.by_status).map(([k, v]) => <Tag key={k}>{MAINT_STATUS_TEXT[k] || k}: {v as any}</Tag>)
                              : '-'}
                          </Descriptions.Item>
                        </Descriptions>
                      </Card>
                      <Card size="small" title="保险到期提醒">
                        <Table columns={reminderColumns} dataSource={profile.expiry_reminders || []} rowKey="id" size="small"
                          pagination={false} locale={{ emptyText: '暂无到期/即将到期保单' }} />
                      </Card>
                    </Space>
                  ) : <Empty description="暂无聚合档案数据" style={{ padding: 48 }} />,
                },
              ]}
            />
          )}
        </Card>

        {/* 维保 Modal */}
        <Modal title="新增维保记录" open={maintModalOpen} onOk={handleMaintSubmit}
          onCancel={() => { setMaintModalOpen(false); maintForm.resetFields(); }}
          width={560} destroyOnHidden
        >
          <Form form={maintForm} layout="vertical">
            <Row gutter={16}>
              <Col span={12}>
                <Form.Item name="type" label="维保类型" rules={[{ required: true, message: '请选择类型' }]}>
                  <Select options={MAINT_TYPES} />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="status" label="状态" rules={[{ required: true }]}>
                  <Select options={MAINT_STATUS} />
                </Form.Item>
              </Col>
            </Row>
            <Row gutter={16}>
              <Col span={12}><Form.Item name="start_at" label="开始日期"><DatePicker style={{ width: '100%' }} /></Form.Item></Col>
              <Col span={12}><Form.Item name="end_at" label="结束日期"><DatePicker style={{ width: '100%' }} /></Form.Item></Col>
            </Row>
            <Row gutter={16}>
              <Col span={12}><Form.Item name="mileage" label="里程(km)" initialValue={0}><InputNumber style={{ width: '100%' }} min={0} step={100} /></Form.Item></Col>
              <Col span={12}><Form.Item name="cost" label="费用(¥)" initialValue={0}><InputNumber style={{ width: '100%' }} min={0} step={100} precision={2} /></Form.Item></Col>
            </Row>
            <Form.Item name="description" label="描述"><Input.TextArea rows={2} placeholder="维保内容描述" /></Form.Item>
          </Form>
        </Modal>

        {/* 保险 Modal */}
        <Modal title="新增保险记录" open={insModalOpen} onOk={handleInsSubmit}
          onCancel={() => { setInsModalOpen(false); insForm.resetFields(); }}
          width={560} destroyOnHidden
        >
          <Form form={insForm} layout="vertical">
            <Row gutter={16}>
              <Col span={12}>
                <Form.Item name="insurance_type" label="险种" rules={[{ required: true, message: '请选择险种' }]}>
                  <Select options={INS_TYPES} />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="company" label="保险公司" rules={[{ required: true, message: '请输入保险公司' }]}>
                  <Input placeholder="保险公司" />
                </Form.Item>
              </Col>
            </Row>
            <Form.Item name="policy_no" label="保单号" rules={[{ required: true, message: '请输入保单号' }]}>
              <Input placeholder="保单号" />
            </Form.Item>
            <Row gutter={16}>
              <Col span={12}><Form.Item name="start_date" label="起保日期" rules={[{ required: true, message: '请选择起保日期' }]}><DatePicker style={{ width: '100%' }} /></Form.Item></Col>
              <Col span={12}><Form.Item name="end_date" label="到期日期" rules={[{ required: true, message: '请选择到期日期' }]}><DatePicker style={{ width: '100%' }} /></Form.Item></Col>
            </Row>
            <Form.Item name="premium" label="保费(¥)" initialValue={0}><InputNumber style={{ width: '100%' }} min={0} step={100} precision={2} /></Form.Item>
          </Form>
        </Modal>
      </div>
    </PageWrapper>
  );
};

export default FleetVehicleMaintenancePage;
