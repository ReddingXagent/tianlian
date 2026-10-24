/**
 * 车队 - 碳排放管理页面
 *
 * 功能：碳减排概览 / 明细列表 / 月度报告 / 排放因子管理
 * API: /api/v1/fleet/carbon/*
 */
import React, { useEffect, useState, useCallback } from 'react';
import {
  Card, Table, Tag, Button, Modal, Form, Input, Select, Space, message,
  Statistic, Row, Col, Tabs, InputNumber, DatePicker, Descriptions, Badge,
} from 'antd';
import {
  ReloadOutlined, ExperimentOutlined, CarOutlined, FireOutlined,
  CheckCircleOutlined, PlusOutlined, ThunderboltOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import api from '../../../api';
import PageWrapper from '../../../components/PageWrapper';

/* ── 常量 ── */
const FACTOR_TYPE_TEXT: Record<string, string> = { grid: '电网排放因子', fuel: '燃油基准' };
const FACTOR_TYPE_COLOR: Record<string, string> = { grid: 'blue', fuel: 'orange' };

/* ── 组件 ── */
const FleetCarbonPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState('overview');
  const [loading, setLoading] = useState(false);

  // 概览
  const [overview, setOverview] = useState<any>(null);
  const [overviewEnterpriseId, setOverviewEnterpriseId] = useState(1);

  // 明细
  const [details, setDetails] = useState<any[]>([]);
  const [detailsTotal, setDetailsTotal] = useState(0);
  const [detailsPage, setDetailsPage] = useState(1);

  // 报告
  const [reports, setReports] = useState<any[]>([]);

  // 因子
  const [factors, setFactors] = useState<any[]>([]);
  const [factorModalOpen, setFactorModalOpen] = useState(false);
  const [editingFactor, setEditingFactor] = useState<any>(null);
  const [factorForm] = Form.useForm();

  const loadOverview = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get('/fleet/carbon/overview', { params: { enterprise_id: overviewEnterpriseId } });
      setOverview(data);
    } catch { setOverview(null); }
    finally { setLoading(false); }
  }, [overviewEnterpriseId]);

  const loadDetails = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get('/fleet/carbon/details', { params: { enterprise_id: overviewEnterpriseId, page: detailsPage, page_size: 10 } });
      setDetails(data?.items || []);
      setDetailsTotal(data?.total || 0);
    } catch { setDetails([]); }
    finally { setLoading(false); }
  }, [overviewEnterpriseId, detailsPage]);

  const loadReports = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get('/fleet/carbon/reports', { params: { enterprise_id: overviewEnterpriseId } });
      setReports(Array.isArray(data) ? data : []);
    } catch { setReports([]); }
    finally { setLoading(false); }
  }, [overviewEnterpriseId]);

  const loadFactors = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get('/fleet/carbon/factors', { params: { page: 1, page_size: 50 } });
      setFactors(data?.items || []);
    } catch { setFactors([]); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => {
    if (activeTab === 'overview') loadOverview();
    else if (activeTab === 'details') loadDetails();
    else if (activeTab === 'reports') loadReports();
    else if (activeTab === 'factors') loadFactors();
  }, [activeTab, loadOverview, loadDetails, loadReports, loadFactors]);

  /* ── 因子 CRUD ── */
  const handleFactorSubmit = async () => {
    try {
      const values = await factorForm.validateFields();
      if (editingFactor) {
        await api.put(`/fleet/carbon/factors/${editingFactor.id}`, values);
        message.success('排放因子已更新');
      } else {
        await api.post('/fleet/carbon/factors', values);
        message.success('排放因子已创建');
      }
      setFactorModalOpen(false);
      factorForm.resetFields();
      setEditingFactor(null);
      loadFactors();
    } catch (err: any) {
      if (err?.errorFields) return;
      message.error('操作失败：' + (err?.response?.data?.detail || err?.message));
    }
  };

  const handleVerifyReport = async (id: number) => {
    try {
      await api.post(`/fleet/carbon/reports/${id}/verify`);
      message.success('报告已审核');
      loadReports();
    } catch (err: any) {
      message.error('审核失败：' + (err?.response?.data?.detail || err?.message));
    }
  };

  const refreshTab = () => {
    if (activeTab === 'overview') loadOverview();
    else if (activeTab === 'details') loadDetails();
    else if (activeTab === 'reports') loadReports();
    else loadFactors();
  };

  /* ── 概览统计 ── */
  const monthlyTrend = overview?.monthly_trend || [];

  const detailColumns = [
    { title: '日期', dataIndex: 'record_date', key: 'record_date', width: 110, render: (v: string) => v || '-' },
    { title: '车辆ID', dataIndex: 'vehicle_id', key: 'vehicle_id', width: 80 },
    { title: '充电量(kWh)', dataIndex: 'charge_energy_kwh', key: 'charge_energy_kwh', width: 120, align: 'right' as const, render: (v: number) => v?.toFixed(2) || '0.00' },
    { title: '电网因子', dataIndex: 'grid_factor', key: 'grid_factor', width: 100, align: 'right' as const, render: (v: number) => v?.toFixed(4) || '-' },
    { title: '减排量(kg)', dataIndex: 'carbon_reduction_kg', key: 'carbon_reduction_kg', width: 110, align: 'right' as const, render: (v: number) => <span style={{ color: '#52c41a', fontWeight: 600 }}>{v?.toFixed(2) || '0.00'}</span> },
    { title: '等效节油(L)', dataIndex: 'equivalent_fuel_saved_liters', key: 'equivalent_fuel_saved_liters', width: 110, align: 'right' as const, render: (v: number) => v?.toFixed(2) || '0.00' },
  ];

  const reportColumns = [
    { title: '月份', dataIndex: 'report_month', key: 'report_month', width: 80, render: (v: number) => `${v}月` },
    { title: '充电量(kWh)', dataIndex: 'total_charge_kwh', key: 'total_charge_kwh', width: 120, align: 'right' as const, render: (v: number) => v?.toFixed(2) || '0.00' },
    { title: '减排量(kg)', dataIndex: 'total_reduction_kg', key: 'total_reduction_kg', width: 120, align: 'right' as const, render: (v: number) => <span style={{ color: '#52c41a', fontWeight: 600 }}>{v?.toFixed(2) || '0.00'}</span> },
    { title: '节油量(L)', dataIndex: 'total_fuel_saved_liters', key: 'total_fuel_saved_liters', width: 110, align: 'right' as const, render: (v: number) => v?.toFixed(2) || '0.00' },
    { title: '车辆数', dataIndex: 'vehicle_count', key: 'vehicle_count', width: 80, align: 'right' as const },
    { title: '状态', dataIndex: 'verified', key: 'verified', width: 100, render: (v: boolean) => v ? <Badge status="success" text="已审核" /> : <Badge status="warning" text="待审核" /> },
    { title: '操作', key: 'action', width: 100, render: (_: unknown, r: any) => !r.verified && <Button size="small" type="link" icon={<CheckCircleOutlined />} onClick={() => handleVerifyReport(r.id)}>审核</Button> },
  ];

  const factorColumns = [
    { title: '年份', dataIndex: 'year', key: 'year', width: 80 },
    { title: '区域', dataIndex: 'region', key: 'region', width: 100 },
    { title: '类型', dataIndex: 'factor_type', key: 'factor_type', width: 120, render: (v: string) => <Tag color={FACTOR_TYPE_COLOR[v] || 'default'}>{FACTOR_TYPE_TEXT[v] || v}</Tag> },
    { title: '排放因子', dataIndex: 'emission_factor', key: 'emission_factor', width: 120, align: 'right' as const, render: (v: number) => v?.toFixed(6) || '-' },
    { title: '来源', dataIndex: 'source', key: 'source', ellipsis: true },
    {
      title: '操作', key: 'action', width: 120,
      render: (_: unknown, r: any) => (
        <Space>
          <Button size="small" onClick={() => { setEditingFactor(r); factorForm.setFieldsValue(r); setFactorModalOpen(true); }}>编辑</Button>
        </Space>
      ),
    },
  ];

  return (
    <PageWrapper loading={loading} skeletonType="table" hasData={true} transition="slide-up">
      <div className="page-container">
        {/* 统计卡片 */}
        {activeTab === 'overview' && overview && (
          <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
            <Col xs={12} sm={6}><Card><Statistic title="年度充电量(kWh)" value={overview.total_charge_kwh || 0} precision={2} prefix={<ThunderboltOutlined />} valueStyle={{ color: '#1890ff' }} /></Card></Col>
            <Col xs={12} sm={6}><Card><Statistic title="碳减排量(kg)" value={overview.total_reduction_kg || 0} precision={2} prefix={<ExperimentOutlined />} valueStyle={{ color: '#52c41a' }} /></Card></Col>
            <Col xs={12} sm={6}><Card><Statistic title="等效节油(L)" value={overview.total_fuel_saved_liters || 0} precision={2} prefix={<FireOutlined />} valueStyle={{ color: '#fa8c16' }} /></Card></Col>
            <Col xs={12} sm={6}><Card><Statistic title="车辆数" value={overview.vehicle_count || 0} prefix={<CarOutlined />} /></Card></Col>
          </Row>
        )}

        <Card extra={
          <Space>
            <InputNumber placeholder="企业ID" value={overviewEnterpriseId} min={1} onChange={v => setOverviewEnterpriseId(v || 1)} style={{ width: 100 }} />
            <Button icon={<ReloadOutlined />} onClick={refreshTab}>刷新</Button>
            {activeTab === 'factors' && <Button type="primary" icon={<PlusOutlined />} onClick={() => { setEditingFactor(null); factorForm.resetFields(); factorForm.setFieldsValue({ year: new Date().getFullYear(), region: '全国' }); setFactorModalOpen(true); }}>新增因子</Button>}
          </Space>
        }>
          <Tabs activeKey={activeTab} onChange={setActiveTab} items={[
            { key: 'overview', label: <span><ExperimentOutlined /> 碳减排概览</span>, children: (
              <Card title={`碳减排概览 - ${overview?.enterprise?.name || '...'}`} size="small">
                {monthlyTrend.length > 0 && (
                  <Table dataSource={monthlyTrend} rowKey="month" size="small" pagination={false}
                    columns={[
                      { title: '月份', dataIndex: 'month', key: 'month', width: 80, render: (m: number) => `${m}月` },
                      { title: '充电量(kWh)', dataIndex: 'charge_kwh', key: 'charge_kwh', align: 'right' as const, render: (v: number) => v?.toFixed(2) || '0.00' },
                      { title: '减排量(kg)', dataIndex: 'reduction_kg', key: 'reduction_kg', align: 'right' as const, render: (v: number) => <span style={{ color: '#52c41a' }}>{v?.toFixed(2) || '0.00'}</span> },
                    ]}
                  />
                )}
              </Card>
            )},
            { key: 'details', label: <span><CarOutlined /> 减排明细</span>, children: (
              <Table columns={detailColumns} dataSource={details} rowKey="id" loading={loading}
                pagination={{ current: detailsPage, pageSize: 10, total: detailsTotal, onChange: setDetailsPage, showTotal: (t: number) => `共 ${t} 条` }}
              />
            )},
            { key: 'reports', label: <span><CheckCircleOutlined /> 月度报告</span>, children: (
              <Table columns={reportColumns} dataSource={reports} rowKey="id" loading={loading}
                pagination={{ pageSize: 12 }}
              />
            )},
            { key: 'factors', label: <span><ThunderboltOutlined /> 排放因子</span>, children: (
              <Table columns={factorColumns} dataSource={factors} rowKey="id" loading={loading}
                pagination={{ pageSize: 10 }}
              />
            )},
          ]} />
        </Card>

        {/* 因子 Modal */}
        <Modal title={editingFactor ? '编辑排放因子' : '新增排放因子'} open={factorModalOpen} onOk={handleFactorSubmit}
          onCancel={() => { setFactorModalOpen(false); factorForm.resetFields(); setEditingFactor(null); }}
          width={480} destroyOnHidden
        >
          <Form form={factorForm} layout="vertical">
            <Row gutter={16}>
              <Col span={12}><Form.Item name="year" label="年份" rules={[{ required: true }]}><InputNumber style={{ width: '100%' }} min={2000} max={2100} /></Form.Item></Col>
              <Col span={12}><Form.Item name="region" label="区域" rules={[{ required: true }]}><Input placeholder="如 全国" /></Form.Item></Col>
            </Row>
            <Row gutter={16}>
              <Col span={12}><Form.Item name="factor_type" label="类型" rules={[{ required: true }]}><Select><Select.Option value="grid">电网排放因子</Select.Option><Select.Option value="fuel">燃油基准</Select.Option></Select></Form.Item></Col>
              <Col span={12}><Form.Item name="emission_factor" label="排放因子值" rules={[{ required: true }]}><InputNumber style={{ width: '100%' }} min={0} step={0.0001} precision={6} /></Form.Item></Col>
            </Row>
            <Form.Item name="source" label="数据来源"><Input placeholder="如 GB/T 32150" /></Form.Item>
          </Form>
        </Modal>
      </div>
    </PageWrapper>
  );
};

export default FleetCarbonPage;
