/**
 * 车队 - 智能充电调度页面
 *
 * 功能: 计划列表/筛选 + 当前方案甘特图 + 生成计划 + 动态调整
 * API: /api/v1/fleet/charging/schedule/*
 */
import React, { useEffect, useState, useCallback } from 'react';
import {
  Card, Table, Tag, Button, Space, Statistic, Row, Col, Tabs, InputNumber, Radio,
} from 'antd';
import {
  PlusOutlined, ReloadOutlined, ThunderboltOutlined, ScheduleOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import api from '../../../api';
import PageWrapper from '../../../components/PageWrapper';
import ScheduleGantt from './ScheduleGantt';
import GeneratePlanModal from './GeneratePlanModal';
import AdjustPanel from './AdjustPanel';
import { PLAN_STATUS_COLORS, PLAN_STATUS_TEXT } from './types';
import type { SchedulePlan, ScheduleEntry, PlanStatus } from './types';

const STATUS_OPTIONS = [
  { label: '全部', value: '' },
  { label: '待执行', value: 'planned' },
  { label: '执行中', value: 'active' },
  { label: '已完成', value: 'completed' },
  { label: '已取消', value: 'cancelled' },
];

const FleetChargingSchedulePage: React.FC = () => {
  const [activeTab, setActiveTab] = useState('list');
  const [loading, setLoading] = useState(false);
  const [enterpriseId, setEnterpriseId] = useState(1);
  const [statusFilter, setStatusFilter] = useState('');
  const [page, setPage] = useState(1);

  const [plans, setPlans] = useState<SchedulePlan[]>([]);
  const [total, setTotal] = useState(0);
  const [entryCounts, setEntryCounts] = useState<Record<number, number>>({});

  // 当前方案
  const [currentPlan, setCurrentPlan] = useState<SchedulePlan | null>(null);
  const [currentEntries, setCurrentEntries] = useState<ScheduleEntry[]>([]);

  // 弹窗
  const [genOpen, setGenOpen] = useState(false);
  const [adjustOpen, setAdjustOpen] = useState(false);
  const [adjustPlan, setAdjustPlan] = useState<SchedulePlan | null>(null);

  const loadList = useCallback(async (statusOverride?: string) => {
    const st = statusOverride !== undefined ? statusOverride : statusFilter;
    setLoading(true);
    try {
      const { data } = await api.get('/fleet/charging/schedule', {
        params: { enterprise_id: enterpriseId, status: st || undefined, page, page_size: 10 },
      });
      const items: SchedulePlan[] = data?.items || [];
      setPlans(items);
      setTotal(data?.total || 0);
      // 并发补全车辆数(列表接口不含条目数, 按 plan 详情聚合)
      items.forEach(async (p) => {
        try {
          const r = await api.get(`/fleet/charging/schedule/${p.id}`);
          setEntryCounts(prev => ({ ...prev, [p.id]: r.data?.entries?.length || 0 }));
        } catch { /* best-effort */ }
      });
    } catch {
      setPlans([]);
    } finally {
      setLoading(false);
    }
  }, [enterpriseId, statusFilter, page]);

  const loadCurrent = useCallback(async () => {
    try {
      const { data } = await api.get('/fleet/charging/schedule/current', { params: { enterprise_id: enterpriseId } });
      setCurrentPlan(data?.plan || null);
      setCurrentEntries(data?.entries || []);
    } catch {
      setCurrentPlan(null);
      setCurrentEntries([]);
    }
  }, [enterpriseId]);

  useEffect(() => { loadList(); }, [enterpriseId]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { loadCurrent(); }, [enterpriseId]);

  const handleStatusChange = (v: string) => {
    setStatusFilter(v);
    setPage(1);
    loadList(v);
  };

  const handleGenSuccess = () => {
    setGenOpen(false);
    loadList();
    loadCurrent();
  };

  const fmtTime = (iso?: string | null) => (iso ? dayjs(iso).format('HH:mm') : '-');

  const columns = [
    { title: '计划日期', dataIndex: 'plan_date', key: 'plan_date', width: 110,
      render: (v: string) => (v ? dayjs(v).format('YYYY-MM-DD') : '-') },
    { title: '企业', dataIndex: 'enterprise_id', key: 'enterprise_id', width: 70 },
    { title: '车辆数', key: 'vehicle_count', width: 80, align: 'right' as const,
      render: (_: unknown, r: SchedulePlan) => (entryCounts[r.id] ?? '-') },
    { title: '总功率', key: 'power', width: 100, align: 'right' as const,
      render: (_: unknown, r: SchedulePlan) => `${r.total_available_power_kw} kW` },
    { title: '时间窗口', key: 'window', width: 150,
      render: (_: unknown, r: SchedulePlan) => `${fmtTime(r.time_window_start)} - ${fmtTime(r.time_window_end)}` },
    { title: '状态', dataIndex: 'status', key: 'status', width: 90,
      render: (v: PlanStatus) => <Tag color={PLAN_STATUS_COLORS[v] || 'default'}>{PLAN_STATUS_TEXT[v] || v}</Tag> },
    {
      title: '操作', key: 'action', width: 100,
      render: (_: unknown, r: SchedulePlan) => (
        <Button size="small" type="link" onClick={() => { setAdjustPlan(r); setAdjustOpen(true); }}>调整</Button>
      ),
    },
  ];

  const chargingCount = currentEntries.filter(e => e.charge_mode === 'charge').length;
  const v2gCount = currentEntries.filter(e => e.charge_mode === 'discharge').length;

  return (
    <PageWrapper loading={loading} skeletonType="table" hasData transition="slide-up">
      <div className="page-container">
        <Card extra={
          <Space wrap>
            <InputNumber placeholder="企业ID" value={enterpriseId} min={1}
              onChange={v => setEnterpriseId(v || 1)} style={{ width: 100 }} />
            <div data-testid="status-filter">
              <Radio.Group value={statusFilter} onChange={e => handleStatusChange(e.target.value)}
                size="small" optionType="button" buttonStyle="solid" options={STATUS_OPTIONS} />
            </div>
            <Button icon={<ReloadOutlined />} onClick={() => { loadList(); loadCurrent(); }}>刷新</Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={() => setGenOpen(true)}>新建调度计划</Button>
          </Space>
        }>
          <Tabs activeKey={activeTab} onChange={setActiveTab} items={[
            { key: 'list', label: <span><ScheduleOutlined /> 调度计划</span>, children: (
              <Table columns={columns} dataSource={plans} rowKey="id" loading={loading}
                pagination={{ current: page, pageSize: 10, total, onChange: setPage, showTotal: (t: number) => `共 ${t} 条` }}
              />
            )},
            { key: 'current', label: <span><ThunderboltOutlined /> 当前方案</span>, children: (
              <div>
                {currentPlan && (
                  <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
                    <Col xs={12} sm={6}><Card><Statistic title="可用总功率(kW)" value={currentPlan.total_available_power_kw} /></Card></Col>
                    <Col xs={12} sm={6}><Card><Statistic title="调度车辆数" value={currentEntries.length} /></Card></Col>
                    <Col xs={12} sm={6}><Card><Statistic title="充电中" value={chargingCount} valueStyle={{ color: '#1890ff' }} /></Card></Col>
                    <Col xs={12} sm={6}><Card><Statistic title="V2G放电" value={v2gCount} valueStyle={{ color: '#f5222d' }} /></Card></Col>
                  </Row>
                )}
                <ScheduleGantt entries={currentEntries} availablePowerKw={currentPlan?.total_available_power_kw} />
              </div>
            )},
          ]} />
        </Card>

        <GeneratePlanModal open={genOpen} enterpriseId={enterpriseId}
          onCancel={() => setGenOpen(false)} onSuccess={handleGenSuccess} />
        <AdjustPanel open={adjustOpen} plan={adjustPlan}
          onClose={() => setAdjustOpen(false)} onSuccess={() => { setAdjustOpen(false); loadCurrent(); }} />
      </div>
    </PageWrapper>
  );
};

export default FleetChargingSchedulePage;
