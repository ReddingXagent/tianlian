/**
 * 车队 - V2G 调度管理页面
 *
 * 功能：状态概览 / 充放电计划 / 放电收益 / 调度记录
 * API: /api/v1/fleet/v2g/*
 */
import React, { useEffect, useState, useCallback } from 'react';
import {
  Card, Table, Tag, Button, Modal, Form, Input, Select, Space, message,
  Statistic, Row, Col, Tabs, InputNumber, DatePicker, Descriptions,
} from 'antd';
import {
  ReloadOutlined, ThunderboltOutlined, DollarOutlined,
  CalendarOutlined, BarChartOutlined, HistoryOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import api from '../../../api';
import { WS_ENDPOINTS } from '../../../config/websocket';
import { useFleetRealtime } from '../../../hooks/useFleetRealtime';
import PageWrapper from '../../../components/PageWrapper';

/* ── 常量 ── */
const PLAN_STATUS_COLORS: Record<string, string> = {
  scheduled: 'blue', charging: 'green', discharging: 'purple',
  completed: 'default', cancelled: 'red', failed: 'red',
};
const PLAN_STATUS_TEXT: Record<string, string> = {
  scheduled: '已排期', charging: '充电中', discharging: '放电中',
  completed: '已完成', cancelled: '已取消', failed: '失败',
};

/* ── 组件 ── */
const FleetV2GPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState('status');
  const [loading, setLoading] = useState(false);
  const [enterpriseId, setEnterpriseId] = useState(1);

  // 状态
  const [status, setStatus] = useState<any>(null);
  // 计划
  const [plans, setPlans] = useState<any[]>([]);
  const [plansTotal, setPlansTotal] = useState(0);
  const [plansPage, setPlansPage] = useState(1);
  // 收益
  const [revenue, setRevenue] = useState<any[]>([]);
  const [revenueTotal, setRevenueTotal] = useState(0);
  const [revenuePage, setRevenuePage] = useState(1);
  // 记录
  const [records, setRecords] = useState<any[]>([]);
  const [recordsTotal, setRecordsTotal] = useState(0);
  const [recordsPage, setRecordsPage] = useState(1);

  const loadStatus = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get('/fleet/v2g/status', { params: { enterprise_id: enterpriseId } });
      setStatus(data);
    } catch { setStatus(null); }
    finally { setLoading(false); }
  }, [enterpriseId]);

  const loadPlans = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get('/fleet/v2g/plans', { params: { enterprise_id: enterpriseId, page: plansPage, page_size: 10 } });
      setPlans(data?.items || []);
      setPlansTotal(data?.total || 0);
    } catch { setPlans([]); }
    finally { setLoading(false); }
  }, [enterpriseId, plansPage]);

  const loadRevenue = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get('/fleet/v2g/revenue', { params: { enterprise_id: enterpriseId, page: revenuePage, page_size: 10 } });
      setRevenue(data?.items || []);
      setRevenueTotal(data?.total || 0);
    } catch { setRevenue([]); }
    finally { setLoading(false); }
  }, [enterpriseId, revenuePage]);

  const loadRecords = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get('/fleet/v2g/records', { params: { enterprise_id: enterpriseId, page: recordsPage, page_size: 10 } });
      setRecords(data?.items || []);
      setRecordsTotal(data?.total || 0);
    } catch { setRecords([]); }
    finally { setLoading(false); }
  }, [enterpriseId, recordsPage]);

  useEffect(() => {
    if (activeTab === 'status') loadStatus();
    else if (activeTab === 'plans') loadPlans();
    else if (activeTab === 'revenue') loadRevenue();
    else if (activeTab === 'records') loadRecords();
  }, [activeTab, loadStatus, loadPlans, loadRevenue, loadRecords]);

  const handleStatusChange = async (planId: number, newStatus: string) => {
    try {
      await api.put(`/fleet/v2g/plans/${planId}/status`, null, { params: { new_status: newStatus } });
      message.success(`状态已更新为 ${PLAN_STATUS_TEXT[newStatus] || newStatus}`);
      loadPlans();
    } catch (err: any) {
      message.error('操作失败：' + (err?.response?.data?.detail || err?.message));
    }
  };

  const refreshTab = useCallback(() => {
    if (activeTab === 'status') loadStatus();
    else if (activeTab === 'plans') loadPlans();
    else if (activeTab === 'revenue') loadRevenue();
    else loadRecords();
  }, [activeTab, loadStatus, loadPlans, loadRevenue, loadRecords]);

  // WebSocket 实时推送 (计划状态变更) + 断连降级轮询
  const { mode: realtimeMode } = useFleetRealtime({
    endpoint: WS_ENDPOINTS.fleetV2G(enterpriseId),
    enabled: true,
    onData: refreshTab,
    pollFn: refreshTab,
    pollIntervalMs: 30000,
  });

  const planStatusCounts = status?.plan_status_counts || {};
  const revenueSummary = status?.revenue_summary || {};

  const planColumns = [
    { title: '计划日期', dataIndex: 'plan_date', key: 'plan_date', width: 110, render: (v: string) => v || '-' },
    { title: '车辆ID', dataIndex: 'vehicle_id', key: 'vehicle_id', width: 80 },
    { title: '充电时段', key: 'charge', width: 200, render: (_: unknown, r: any) => {
      const s = r.planned_charge_start?.split('T')[1]?.substring(0, 5) || '-';
      const e = r.planned_charge_end?.split('T')[1]?.substring(0, 5) || '-';
      return `${s} - ${e}`;
    }},
    { title: '放电时段', key: 'discharge', width: 200, render: (_: unknown, r: any) => {
      const s = r.planned_discharge_start?.split('T')[1]?.substring(0, 5) || '-';
      const e = r.planned_discharge_end?.split('T')[1]?.substring(0, 5) || '-';
      return r.planned_discharge_start ? `${s} - ${e}` : '-';
    }},
    { title: 'SOC范围', key: 'soc', width: 100, render: (_: unknown, r: any) => `${(r.target_soc_min || 0) * 100}% - ${(r.target_soc_max || 0) * 100}%` },
    { title: '状态', dataIndex: 'status', key: 'status', width: 90, render: (v: string) => <Tag color={PLAN_STATUS_COLORS[v] || 'default'}>{PLAN_STATUS_TEXT[v] || v}</Tag> },
    {
      title: '操作', key: 'action', width: 150, render: (_: unknown, r: any) => r.status === 'scheduled' && (
        <Select size="small" placeholder="更新状态" style={{ width: 120 }}
          onChange={v => handleStatusChange(r.id, v)}
          options={[
            { label: '开始充电', value: 'charging' },
            { label: '开始放电', value: 'discharging' },
            { label: '完成', value: 'completed' },
            { label: '取消', value: 'cancelled' },
          ]}
        />
      ),
    },
  ];

  const revenueColumns = [
    { title: '日期', dataIndex: 'record_date', key: 'record_date', width: 110, render: (v: string) => v || '-' },
    { title: '车辆ID', dataIndex: 'vehicle_id', key: 'vehicle_id', width: 80 },
    { title: '放电量(kWh)', dataIndex: 'discharge_energy_kwh', key: 'discharge_energy_kwh', width: 120, align: 'right' as const, render: (v: number) => v?.toFixed(2) || '0.00' },
    { title: '放电收益(¥)', dataIndex: 'discharge_revenue', key: 'discharge_revenue', width: 120, align: 'right' as const, render: (v: number) => <span style={{ color: '#52c41a' }}>{v?.toFixed(2) || '0.00'}</span> },
    { title: '削峰(kWh)', dataIndex: 'peak_shaving_kwh', key: 'peak_shaving_kwh', width: 100, align: 'right' as const, render: (v: number) => v?.toFixed(2) || '0.00' },
    { title: '填谷(kWh)', dataIndex: 'valley_filling_kwh', key: 'valley_filling_kwh', width: 100, align: 'right' as const, render: (v: number) => v?.toFixed(2) || '0.00' },
    { title: '电网响应', dataIndex: 'grid_response_count', key: 'grid_response_count', width: 90, align: 'right' as const },
    { title: '总收益(¥)', dataIndex: 'total_revenue', key: 'total_revenue', width: 120, align: 'right' as const, render: (v: number) => <span style={{ fontWeight: 600, color: '#52c41a' }}>{v?.toFixed(2) || '0.00'}</span> },
  ];

  const recordColumns = [
    { title: '设备ID', dataIndex: 'device_id', key: 'device_id', width: 80 },
    { title: '调度类型', dataIndex: 'dispatch_type', key: 'dispatch_type', width: 100, render: (v: string) => <Tag color={v === 'charge' ? 'blue' : v === 'discharge' ? 'purple' : 'default'}>{v || '-'}</Tag> },
    { title: '目标功率(kW)', dataIndex: 'target_power_kw', key: 'target_power_kw', width: 120, align: 'right' as const, render: (v: number) => v?.toFixed(1) || '0.0' },
    { title: '实际功率(kW)', dataIndex: 'actual_power_kw', key: 'actual_power_kw', width: 120, align: 'right' as const, render: (v: number) => v?.toFixed(1) || '-' },
    { title: '状态', dataIndex: 'status', key: 'status', width: 90, render: (v: string) => <Tag>{v || '-'}</Tag> },
    { title: '开始时间', dataIndex: 'start_at', key: 'start_at', width: 150, render: (v: string) => v?.replace('T', ' ').substring(0, 19) || '-' },
    { title: '结束时间', dataIndex: 'end_at', key: 'end_at', width: 150, render: (v: string) => v?.replace('T', ' ').substring(0, 19) || '-' },
  ];

  return (
    <PageWrapper loading={loading} skeletonType="table" hasData={true} transition="slide-up">
      <div className="page-container">
        {activeTab === 'status' && status && (
          <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
            <Col xs={12} sm={6}><Card><Statistic title="计划总数" value={Object.values(planStatusCounts).reduce<number>((a, b) => a + Number(b), 0)} prefix={<CalendarOutlined />} /></Card></Col>
            <Col xs={12} sm={6}><Card><Statistic title="总收益(¥)" value={revenueSummary.total_revenue || 0} precision={2} prefix={<DollarOutlined />} valueStyle={{ color: '#52c41a' }} /></Card></Col>
            <Col xs={12} sm={6}><Card><Statistic title="总放电量(kWh)" value={revenueSummary.total_discharge_energy_kwh || 0} precision={2} prefix={<ThunderboltOutlined />} /></Card></Col>
            <Col xs={12} sm={6}><Card><Statistic title="收益记录数" value={revenueSummary.total_records || 0} prefix={<BarChartOutlined />} /></Card></Col>
          </Row>
        )}

        <Card extra={
          <Space>
            <Tag color={realtimeMode === 'realtime' ? 'green' : 'orange'}>{realtimeMode === 'realtime' ? '实时推送' : '轮询降级'}</Tag>
            <InputNumber placeholder="企业ID" value={enterpriseId} min={1} onChange={v => setEnterpriseId(v || 1)} style={{ width: 100 }} />
            <Button icon={<ReloadOutlined />} onClick={refreshTab}>刷新</Button>
          </Space>
        }>
          <Tabs activeKey={activeTab} onChange={setActiveTab} items={[
            { key: 'status', label: <span><BarChartOutlined /> 状态概览</span>, children: (
              <div>
                <Card title="计划状态分布" size="small" style={{ marginBottom: 16 }}>
                  <Row gutter={16}>
                    {Object.entries(planStatusCounts).map(([k, v]: [string, any]) => (
                      <Col key={k} span={4}>
                        <Statistic title={PLAN_STATUS_TEXT[k] || k} value={Number(v)} valueStyle={{ color: PLAN_STATUS_COLORS[k] === 'green' ? '#52c41a' : '#1890ff' }} />
                      </Col>
                    ))}
                    {Object.keys(planStatusCounts).length === 0 && <Col><span style={{ color: '#999' }}>暂无数据</span></Col>}
                  </Row>
                </Card>
                <Card title="最近计划" size="small">
                  <Table dataSource={status?.recent_plans || []} rowKey="id" size="small" pagination={false}
                    columns={planColumns.slice(0, -1)}
                  />
                </Card>
              </div>
            )},
            { key: 'plans', label: <span><CalendarOutlined /> 充放电计划</span>, children: (
              <Table columns={planColumns} dataSource={plans} rowKey="id" loading={loading}
                pagination={{ current: plansPage, pageSize: 10, total: plansTotal, onChange: setPlansPage, showTotal: (t: number) => `共 ${t} 条` }}
              />
            )},
            { key: 'revenue', label: <span><DollarOutlined /> 放电收益</span>, children: (
              <Table columns={revenueColumns} dataSource={revenue} rowKey="id" loading={loading}
                pagination={{ current: revenuePage, pageSize: 10, total: revenueTotal, onChange: setRevenuePage, showTotal: (t: number) => `共 ${t} 条` }}
              />
            )},
            { key: 'records', label: <span><HistoryOutlined /> 调度记录</span>, children: (
              <Table columns={recordColumns} dataSource={records} rowKey="id" loading={loading}
                pagination={{ current: recordsPage, pageSize: 10, total: recordsTotal, onChange: setRecordsPage, showTotal: (t: number) => `共 ${t} 条` }}
              />
            )},
          ]} />
        </Card>
      </div>
    </PageWrapper>
  );
};

export default FleetV2GPage;
