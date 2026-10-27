/**
 * 车队 - 车辆保险档案页面（独立模块）
 *
 * 功能：企业+车辆选择 / 保险列表 / 类型筛选(交强/商业/三者) / 新增+编辑+删除 / 到期状态
 * API:
 *   GET    /fleet/vehicles/{vid}/insurance?insurance_type=X   列表(类型筛选)
 *   POST   /fleet/vehicles/{vid}/insurance                     创建
 *   PUT    /fleet/vehicles/{vid}/insurance/{iid}              更新
 *   DELETE /fleet/vehicles/{vid}/insurance/{iid}              删除
 *   GET /fleet/enterprises ; GET /enterprises/{eid}/vehicles
 */
import React, { useEffect, useState, useCallback } from 'react';
import {
  Card, Table, Tag, Button, Modal, Form, Input, Select, Space, message,
  Popconfirm, Statistic, Row, Col, InputNumber, DatePicker, Empty,
} from 'antd';
import {
  PlusOutlined, EditOutlined, DeleteOutlined, ReloadOutlined, SafetyOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import api from '../../../api';
import PageWrapper from '../../../components/PageWrapper';

/* ── 类型 ── */
interface EnterpriseLite { id: number; name: string; }
interface VehicleLite { id: number; plate_number: string; }
interface Insurance {
  id: number; vehicle_id: number; insurance_type: string;
  company: string; policy_no: string;
  start_date?: string | null; end_date?: string | null;
  premium: number; attachment_url?: string | null;
  created_at?: string;
}

/* ── 常量 ── */
const INS_TYPES = [
  { value: 'compulsory', label: '交强险' },
  { value: 'commercial', label: '商业险' },
  { value: 'third_party', label: '第三者责任险' },
];
const FILTER_OPTIONS = [{ value: '', label: '全部险种' }, ...INS_TYPES];
const INS_TYPE_TEXT: Record<string, string> = { compulsory: '交强险', commercial: '商业险', third_party: '第三者责任险' };
const INS_TYPE_COLOR: Record<string, string> = { compulsory: 'volcano', commercial: 'gold', third_party: 'purple' };

/** 到期阈值(天)：剩余天数 ≤ 此值视为「即将到期」 */
const EXPIRING_SOON_DAYS = 30;

/** 计算保单到期状态 */
function computeExpiry(end?: string | null): { label: string; color: string; days: number | null } {
  if (!end) return { label: '-', color: 'default', days: null };
  const days = dayjs(end).startOf('day').diff(dayjs().startOf('day'), 'day');
  if (days < 0) return { label: `已过期 ${-days} 天`, color: 'red', days };
  if (days <= EXPIRING_SOON_DAYS) return { label: `${days} 天后到期`, color: 'orange', days };
  return { label: '生效中', color: 'green', days };
}

/* ── 组件 ── */
const FleetVehicleInsurancePage: React.FC = () => {
  const [enterprises, setEnterprises] = useState<EnterpriseLite[]>([]);
  const [vehicles, setVehicles] = useState<VehicleLite[]>([]);
  const [currentEid, setCurrentEid] = useState<number | null>(null);
  const [vehicleId, setVehicleId] = useState<number | null>(null);
  const [filterType, setFilterType] = useState<string>('');
  const [loading, setLoading] = useState(false);

  const [insurances, setInsurances] = useState<Insurance[]>([]);
  const [editingIns, setEditingIns] = useState<Insurance | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [form] = Form.useForm();

  /* ── 加载企业 ── */
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

  /* ── 加载车辆(企业联动) ── */
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

  /* ── 加载保险列表(类型筛选) ── */
  const loadInsurances = useCallback(async () => {
    if (!vehicleId) { setInsurances([]); return; }
    setLoading(true);
    try {
      const params: Record<string, string> = {};
      if (filterType) params.insurance_type = filterType;
      const { data } = await api.get(`/fleet/vehicles/${vehicleId}/insurance`, { params });
      setInsurances(Array.isArray(data) ? data : (data as any)?.items || []);
    } catch {
      setInsurances([]);
    } finally {
      setLoading(false);
    }
  }, [vehicleId, filterType]);

  useEffect(() => { loadEnterprises(); }, [loadEnterprises]);
  useEffect(() => { if (currentEid) loadVehicles(); }, [currentEid, loadVehicles]);
  useEffect(() => { if (vehicleId) loadInsurances(); else setInsurances([]); }, [vehicleId, filterType, loadInsurances]);

  /* ── 打开新增 ── */
  // 注：Modal destroyOnHidden 已保证每次打开为全新表单，此处不再调 form.resetFields()
  // （Form 尚未挂载时 resetFields 会抛错中断，setModalOpen 不执行）。
  const openAdd = () => {
    setEditingIns(null);
    form.setFieldsValue({ insurance_type: 'compulsory', premium: 0 });
    setModalOpen(true);
  };

  /* ── 打开编辑 ── */
  const openEdit = (r: Insurance) => {
    setEditingIns(r);
    form.setFieldsValue({
      insurance_type: r.insurance_type,
      company: r.company,
      policy_no: r.policy_no,
      start_date: r.start_date ? dayjs(r.start_date) : undefined,
      end_date: r.end_date ? dayjs(r.end_date) : undefined,
      premium: r.premium,
      attachment_url: r.attachment_url || undefined,
    });
    setModalOpen(true);
  };

  /* ── 提交(新增/编辑) ── */
  const handleSubmit = async () => {
    if (!vehicleId) return;
    try {
      const values = await form.validateFields();
      const payload = {
        insurance_type: values.insurance_type,
        company: values.company,
        policy_no: values.policy_no,
        start_date: values.start_date.format('YYYY-MM-DD'),
        end_date: values.end_date.format('YYYY-MM-DD'),
        premium: Number(values.premium) || 0,
        attachment_url: values.attachment_url || undefined,
      };
      setSubmitting(true);
      if (editingIns) {
        await api.put(`/fleet/vehicles/${vehicleId}/insurance/${editingIns.id}`, payload);
        message.success('保险记录已更新');
      } else {
        await api.post(`/fleet/vehicles/${vehicleId}/insurance`, payload);
        message.success('保险记录已创建');
      }
      setModalOpen(false);
      form.resetFields();
      setEditingIns(null);
      loadInsurances();
    } catch (err: any) {
      if (err?.errorFields) return;
      message.error('保存失败：' + (err?.response?.data?.detail || err?.message));
    } finally {
      setSubmitting(false);
    }
  };

  /* ── 删除 ── */
  const handleDelete = async (id: number) => {
    if (!vehicleId) return;
    try {
      await api.delete(`/fleet/vehicles/${vehicleId}/insurance/${id}`);
      message.success('已删除');
      loadInsurances();
    } catch (err: any) {
      message.error('删除失败：' + (err?.response?.data?.detail || err?.message));
    }
  };

  /* ── 表格列 ── */
  const columns = [
    { title: '险种', dataIndex: 'insurance_type', key: 'insurance_type', width: 130,
      render: (v: string) => <Tag color={INS_TYPE_COLOR[v] || 'default'}>{INS_TYPE_TEXT[v] || v}</Tag> },
    { title: '保险公司', dataIndex: 'company', key: 'company', width: 150, ellipsis: true },
    { title: '保单号', dataIndex: 'policy_no', key: 'policy_no', width: 160,
      render: (v: string) => v ? <code style={{ fontSize: 11 }}>{v}</code> : '-' },
    { title: '起保', dataIndex: 'start_date', key: 'start_date', width: 120, render: (v: string) => v?.split('T')[0] || '-' },
    { title: '到期', dataIndex: 'end_date', key: 'end_date', width: 120, render: (v: string) => v?.split('T')[0] || '-' },
    { title: '保费(¥)', dataIndex: 'premium', key: 'premium', width: 110, align: 'right' as const, render: (v: number) => (v || 0).toFixed(2) },
    { title: '到期状态', dataIndex: 'end_date', key: 'expiry', width: 130,
      render: (v: string) => { const e = computeExpiry(v); return <Tag color={e.color}>{e.label}</Tag>; } },
    {
      title: '操作', key: 'action', width: 140,
      render: (_: unknown, r: Insurance) => (
        <Space>
          <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(r)}>编辑</Button>
          <Popconfirm title="确认删除该保险记录？" onConfirm={() => handleDelete(r.id)}>
            <Button size="small" danger icon={<DeleteOutlined />}>删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  /* ── 统计(基于当前列表) ── */
  const stats = {
    total: insurances.length,
    active: insurances.filter(i => (computeExpiry(i.end_date).days ?? -1) >= 0).length,
    expiringSoon: insurances.filter(i => {
      const d = computeExpiry(i.end_date).days;
      return d !== null && d >= 0 && d <= EXPIRING_SOON_DAYS;
    }).length,
    totalPremium: insurances.reduce((s, i) => s + (i.premium || 0), 0),
  };

  /* ── 空态：无企业 ── */
  if (currentEid === null && enterprises.length === 0 && !loading) {
    return (
      <PageWrapper loading={false} hasData={false} transition="slide-up">
        <Card><div style={{ padding: 24, textAlign: 'center', color: '#999' }}>暂无企业，请先在「车队企业」中创建企业。</div></Card>
      </PageWrapper>
    );
  }

  return (
    <PageWrapper
      loading={loading && insurances.length === 0}
      skeletonType="table"
      hasData={insurances.length > 0}
      transition="slide-up"
    >
      <div className="page-container">
        <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
          <Col xs={12} sm={6}><Card><Statistic title="保单总数" value={stats.total} prefix={<SafetyOutlined />} /></Card></Col>
          <Col xs={12} sm={6}><Card><Statistic title="生效保单" value={stats.active} valueStyle={{ color: '#52c41a' }} /></Card></Col>
          <Col xs={12} sm={6}><Card><Statistic title="即将到期" value={stats.expiringSoon} valueStyle={{ color: '#faad14' }} /></Card></Col>
          <Col xs={12} sm={6}><Card><Statistic title="保费合计" value={stats.totalPremium} prefix="¥" precision={2} /></Card></Col>
        </Row>

        <Card extra={
          <Space wrap>
            <Select placeholder="选择企业" value={currentEid ?? undefined} onChange={(v) => { setCurrentEid(v); setVehicleId(null); }}
              style={{ width: 180 }} showSearch optionFilterProp="label"
              options={enterprises.map(e => ({ value: e.id, label: e.name }))} />
            <Select placeholder="选择车辆" value={vehicleId ?? undefined} onChange={setVehicleId}
              style={{ width: 160 }} showSearch optionFilterProp="label" disabled={!vehicles.length}
              options={vehicles.map(v => ({ value: v.id, label: v.plate_number }))} />
            <Select value={filterType} onChange={setFilterType} style={{ width: 140 }} options={FILTER_OPTIONS} />
            <Button icon={<ReloadOutlined />} onClick={loadInsurances}>刷新</Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={openAdd} disabled={!vehicleId}>新增保险</Button>
          </Space>
        }>
          {!vehicleId ? (
            <Empty description="请选择企业并选择车辆以查看保险档案" style={{ padding: 48 }} />
          ) : (
            <Table columns={columns} dataSource={insurances} rowKey="id" loading={loading}
              pagination={{ pageSize: 10, showSizeChanger: true, showTotal: (t: number) => `共 ${t} 条` }} />
          )}
        </Card>

        {/* 新增/编辑 Modal */}
        <Modal
          title={editingIns ? '编辑保险记录' : '新增保险记录'}
          open={modalOpen}
          onOk={handleSubmit}
          confirmLoading={submitting}
          onCancel={() => { setModalOpen(false); form.resetFields(); setEditingIns(null); }}
          width={560}
          destroyOnHidden
        >
          <Form form={form} layout="vertical">
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
            <Form.Item name="attachment_url" label="保单附件URL"><Input placeholder="https://..." /></Form.Item>
          </Form>
        </Modal>
      </div>
    </PageWrapper>
  );
};

export default FleetVehicleInsurancePage;
