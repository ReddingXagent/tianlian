/**
 * 车队 - 碳减排核证/交易页面
 *
 * 功能：核证列表 / 申请核证(选月度汇总) / 核证确认 / 交易登记 / 撤销
 * 状态机: pending -> verified -> traded ; pending|verified -> cancelled
 * API:
 *   POST  /fleet/carbon/certificates/apply          { summary_id }
 *   GET   /fleet/carbon/certificates?enterprise_id=&status=
 *   PATCH /fleet/carbon/certificates/{id}/verify
 *   PATCH /fleet/carbon/certificates/{id}/trade     { trade_volume, trade_price }
 *   PATCH /fleet/carbon/certificates/{id}/cancel
 *   GET   /fleet/carbon/reports?enterprise_id=       (核证申请的下拉数据源)
 */
import React, { useEffect, useState, useCallback } from 'react';
import {
  Card, Table, Tag, Button, Modal, Form, Select, Space, message,
  Popconfirm, Statistic, Row, Col, InputNumber,
} from 'antd';
import {
  PlusOutlined, ReloadOutlined, FileProtectOutlined, CheckOutlined, SwapOutlined,
} from '@ant-design/icons';
import api from '../../../api';
import PageWrapper from '../../../components/PageWrapper';

/* ── 类型 ── */
interface Certificate {
  id: number;
  enterprise_id: number;
  summary_id: number;
  certificate_no: string;
  status: string;
  verified_at?: string | null;
  trade_volume: number;
  trade_price: number;
  created_at?: string;
  updated_at?: string;
}
interface CarbonSummary {
  id: number;
  report_year: number;
  report_month: number;
  total_reduction_kg: number;
  verified: boolean;
}
interface EnterpriseLite { id: number; name: string; }

/* ── 常量 ── */
const STATUS_COLOR: Record<string, string> = { pending: 'orange', verified: 'blue', traded: 'green', cancelled: 'default' };
const STATUS_TEXT: Record<string, string> = { pending: '待核证', verified: '已核证', traded: '已交易', cancelled: '已撤销' };
const STATUS_OPTIONS = [
  { value: 'pending', label: '待核证' },
  { value: 'verified', label: '已核证' },
  { value: 'traded', label: '已交易' },
  { value: 'cancelled', label: '已撤销' },
];

/* ── 组件 ── */
const FleetCarbonCertificatesPage: React.FC = () => {
  const [certs, setCerts] = useState<Certificate[]>([]);
  const [enterprises, setEnterprises] = useState<EnterpriseLite[]>([]);
  const [summaries, setSummaries] = useState<CarbonSummary[]>([]);
  const [currentEid, setCurrentEid] = useState<number | null>(null);
  const [statusFilter, setStatusFilter] = useState<string | undefined>(undefined);
  const [loading, setLoading] = useState(false);

  const [applyOpen, setApplyOpen] = useState(false);
  const [tradeTarget, setTradeTarget] = useState<Certificate | null>(null);
  const [applyForm] = Form.useForm();
  const [tradeForm] = Form.useForm();

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

  const loadCerts = useCallback(async () => {
    if (!currentEid) { setCerts([]); return; }
    setLoading(true);
    try {
      const params: any = { enterprise_id: currentEid };
      if (statusFilter) params.status = statusFilter;
      const { data } = await api.get('/fleet/carbon/certificates', { params });
      setCerts(Array.isArray(data) ? data : (data as any)?.items || []);
    } catch {
      setCerts([]);
    } finally {
      setLoading(false);
    }
  }, [currentEid, statusFilter]);

  const loadSummaries = useCallback(async () => {
    if (!currentEid) { setSummaries([]); return; }
    try {
      const { data } = await api.get('/fleet/carbon/reports', { params: { enterprise_id: currentEid } });
      const items: CarbonSummary[] = Array.isArray(data) ? data : (data as any)?.items || [];
      setSummaries(items);
    } catch {
      setSummaries([]);
    }
  }, [currentEid]);

  useEffect(() => { loadEnterprises(); }, [loadEnterprises]);
  useEffect(() => { if (currentEid) loadCerts(); }, [currentEid, loadCerts]);

  /* ── 操作 ── */
  const handleApply = async () => {
    try {
      const values = await applyForm.validateFields();
      await api.post('/fleet/carbon/certificates/apply', { summary_id: values.summary_id });
      message.success('核证申请已提交');
      setApplyOpen(false);
      applyForm.resetFields();
      loadCerts();
    } catch (err: any) {
      if (err?.errorFields) return;
      message.error('申请失败：' + (err?.response?.data?.detail || err?.message));
    }
  };

  const handleVerify = async (id: number) => {
    try {
      await api.patch(`/fleet/carbon/certificates/${id}/verify`);
      message.success('核证确认成功');
      loadCerts();
    } catch (err: any) {
      message.error('核证失败：' + (err?.response?.data?.detail || err?.message));
    }
  };

  const handleTrade = async () => {
    if (!tradeTarget) return;
    try {
      const values = await tradeForm.validateFields();
      await api.patch(`/fleet/carbon/certificates/${tradeTarget.id}/trade`, {
        trade_volume: Number(values.trade_volume),
        trade_price: Number(values.trade_price),
      });
      message.success('交易登记成功');
      setTradeTarget(null);
      tradeForm.resetFields();
      loadCerts();
    } catch (err: any) {
      if (err?.errorFields) return;
      message.error('交易登记失败：' + (err?.response?.data?.detail || err?.message));
    }
  };

  const handleCancel = async (id: number) => {
    try {
      await api.patch(`/fleet/carbon/certificates/${id}/cancel`);
      message.success('已撤销核证');
      loadCerts();
    } catch (err: any) {
      message.error('撤销失败：' + (err?.response?.data?.detail || err?.message));
    }
  };

  const openApply = async () => {
    await loadSummaries();
    applyForm.resetFields();
    setApplyOpen(true);
  };

  /* ── 统计 ── */
  const stats = {
    total: certs.length,
    pending: certs.filter(c => c.status === 'pending').length,
    verified: certs.filter(c => c.status === 'verified').length,
    traded: certs.filter(c => c.status === 'traded').length,
  };

  const fmtTime = (v?: string | null) => (v ? v.replace('T', ' ').slice(0, 16) : '-');
  const verifiedSummaries = summaries.filter(s => s.verified);

  const columns = [
    { title: '核证编号', dataIndex: 'certificate_no', key: 'certificate_no', width: 220, render: (v: string) => <code style={{ fontSize: 11 }}>{v || '-'}</code> },
    { title: '汇总ID', dataIndex: 'summary_id', key: 'summary_id', width: 80, align: 'right' as const },
    { title: '状态', dataIndex: 'status', key: 'status', width: 90, render: (v: string) => <Tag color={STATUS_COLOR[v] || 'default'}>{STATUS_TEXT[v] || v}</Tag> },
    { title: '交易量(吨)', dataIndex: 'trade_volume', key: 'trade_volume', width: 110, align: 'right' as const, render: (v: number, r: Certificate) => r.status === 'traded' ? (v || 0).toFixed(2) : '-' },
    { title: '单价(元/吨)', dataIndex: 'trade_price', key: 'trade_price', width: 110, align: 'right' as const, render: (v: number, r: Certificate) => r.status === 'traded' ? (v || 0).toFixed(2) : '-' },
    { title: '核证时间', dataIndex: 'verified_at', key: 'verified_at', width: 150, render: (v: string) => fmtTime(v) },
    { title: '申请时间', dataIndex: 'created_at', key: 'created_at', width: 150, render: (v: string) => fmtTime(v) },
    {
      title: '操作', key: 'action', width: 200,
      render: (_: unknown, r: Certificate) => (
        <Space size={4} wrap>
          {r.status === 'pending' && (
            <>
              <Popconfirm title="确认核证？" onConfirm={() => handleVerify(r.id)}>
                <Button size="small" type="primary" icon={<CheckOutlined />}>核证</Button>
              </Popconfirm>
              <Popconfirm title="确认撤销该核证？" onConfirm={() => handleCancel(r.id)}>
                <Button size="small" danger>撤销</Button>
              </Popconfirm>
            </>
          )}
          {r.status === 'verified' && (
            <>
              <Button size="small" icon={<SwapOutlined />} onClick={() => { setTradeTarget(r); tradeForm.setFieldsValue({ trade_volume: undefined, trade_price: undefined }); }}>交易登记</Button>
              <Popconfirm title="确认撤销该核证？" onConfirm={() => handleCancel(r.id)}>
                <Button size="small" danger>撤销</Button>
              </Popconfirm>
            </>
          )}
          {(r.status === 'traded' || r.status === 'cancelled') && <span style={{ color: '#999' }}>-</span>}
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
      loading={loading && certs.length === 0}
      skeletonType="table"
      hasData={certs.length > 0}
      empty={{ type: 'default', title: '暂无碳核证记录', description: '点击「申请核证」从已审核的月度碳减排汇总生成核证证书', actionText: '申请核证', onAction: openApply }}
      transition="slide-up"
    >
      <div className="page-container">
        <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
          <Col xs={12} sm={6}><Card><Statistic title="核证总数" value={stats.total} prefix={<FileProtectOutlined />} /></Card></Col>
          <Col xs={12} sm={6}><Card><Statistic title="待核证" value={stats.pending} valueStyle={{ color: '#fa8c16' }} /></Card></Col>
          <Col xs={12} sm={6}><Card><Statistic title="已核证" value={stats.verified} valueStyle={{ color: '#1677ff' }} /></Card></Col>
          <Col xs={12} sm={6}><Card><Statistic title="已交易" value={stats.traded} valueStyle={{ color: '#52c41a' }} /></Card></Col>
        </Row>

        <Card extra={
          <Space wrap>
            <Select placeholder="选择企业" value={currentEid ?? undefined} onChange={setCurrentEid}
              style={{ width: 180 }} showSearch optionFilterProp="label"
              options={enterprises.map(e => ({ value: e.id, label: e.name }))} />
            <Select placeholder="状态筛选" value={statusFilter} onChange={setStatusFilter} allowClear
              style={{ width: 130 }} options={STATUS_OPTIONS} />
            <Button icon={<ReloadOutlined />} onClick={loadCerts}>刷新</Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={openApply}>申请核证</Button>
          </Space>
        }>
          <Table columns={columns} dataSource={certs} rowKey="id" loading={loading}
            pagination={{ pageSize: 10, showSizeChanger: true, showTotal: (t: number) => `共 ${t} 条` }}
          />
        </Card>

        {/* 申请核证 Modal */}
        <Modal title="申请碳核证" open={applyOpen} onOk={handleApply}
          onCancel={() => { setApplyOpen(false); applyForm.resetFields(); }}
          width={480} destroyOnHidden
        >
          <Form form={applyForm} layout="vertical">
            <Form.Item name="summary_id" label="碳减排月度汇总" rules={[{ required: true, message: '请选择汇总' }]}
              extra={verifiedSummaries.length === 0 ? '当前企业暂无已审核的月度汇总，请先在「碳排放」中审核报告' : undefined}>
              <Select placeholder="选择已审核的月度汇总" notFoundContent="暂无已审核汇总"
                options={verifiedSummaries.map(s => ({
                  value: s.id,
                  label: `${s.report_year}-${String(s.report_month).padStart(2, '0')} (减排 ${(s.total_reduction_kg / 1000).toFixed(2)} 吨)`,
                }))}
              />
            </Form.Item>
          </Form>
        </Modal>

        {/* 交易登记 Modal */}
        <Modal title={`交易登记 - ${tradeTarget?.certificate_no || ''}`} open={!!tradeTarget} onOk={handleTrade}
          onCancel={() => { setTradeTarget(null); tradeForm.resetFields(); }}
          width={440} destroyOnHidden
        >
          <Form form={tradeForm} layout="vertical">
            <Form.Item name="trade_volume" label="交易量(吨CO₂)" rules={[{ required: true, message: '请输入交易量' }]}>
              <InputNumber style={{ width: '100%' }} min={0.01} step={0.01} precision={2} placeholder="如 12.50" />
            </Form.Item>
            <Form.Item name="trade_price" label="交易单价(元/吨)" rules={[{ required: true, message: '请输入单价' }]}>
              <InputNumber style={{ width: '100%' }} min={0.01} step={1} precision={2} placeholder="如 65.00" />
            </Form.Item>
          </Form>
        </Modal>
      </div>
    </PageWrapper>
  );
};

export default FleetCarbonCertificatesPage;
