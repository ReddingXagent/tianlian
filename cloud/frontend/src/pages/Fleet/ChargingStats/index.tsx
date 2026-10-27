/**
 * 车队 - 充电统计页面（独立模块）
 *
 * 功能：
 *  - 车队级汇总：总电量/总费用/充电次数/活跃车辆 + 车辆排行(充电量 Top N) + 场站分布
 *  - 单车统计：充电次数/总电量/总费用/平均单次电量 + 月度充电趋势(电量+费用双轴折线)
 *  - 企业选择 + 日期范围筛选（联动车队与单车两个视图）
 *
 * API（响应拦截器已剥离 success_response 外层，r.data 即业务对象）：
 *   GET /enterprises/{eid}/charging-stats                 车队级汇总
 *   GET /enterprises/{eid}/vehicles/{vid}/charging-stats  单车统计
 *   GET /fleet/enterprises ; GET /enterprises/{eid}/vehicles
 */
import React, { useEffect, useState, useCallback } from 'react';
import {
  Card, Table, Select, DatePicker, Button, Space, Statistic, Row, Col, Empty, Tabs,
} from 'antd';
import {
  ThunderboltOutlined, ReloadOutlined, CarOutlined,
} from '@ant-design/icons';
import type { Dayjs } from 'dayjs';
import ReactECharts from 'echarts-for-react';
import api from '../../../api';
import PageWrapper from '../../../components/PageWrapper';

const { RangePicker } = DatePicker;

/* ── 类型 ── */
interface EnterpriseLite { id: number; name: string; }
interface VehicleLite { id: number; plate_number: string; }
interface Summary {
  total_orders: number; total_kwh: number; total_amount: number;
  avg_kwh_per_order: number; avg_amount_per_order: number;
}
interface TopVehicle {
  vehicle_id: number; plate_number: string;
  charged_kwh: number; total_amount: number; order_count: number;
}
interface StationItem {
  station_id: number; station_name: string;
  charged_kwh: number; order_count: number;
}
interface FleetStats {
  enterprise_id: number;
  summary: Summary;
  active_vehicles: number;
  top_vehicles: TopVehicle[];
  station_distribution: StationItem[];
}
interface TrendPoint { month: string; charged_kwh: number; total_amount: number; }
interface VehicleStats {
  vehicle: { id: number; plate_number: string; vin?: string };
  summary: Summary;
  monthly_trend: TrendPoint[];
}

/* ── 组件 ── */
const FleetChargingStatsPage: React.FC = () => {
  const [enterprises, setEnterprises] = useState<EnterpriseLite[]>([]);
  const [currentEid, setCurrentEid] = useState<number | null>(null);
  const [dateRange, setDateRange] = useState<[Dayjs, Dayjs] | null>(null);

  const [vehicles, setVehicles] = useState<VehicleLite[]>([]);
  const [vehicleId, setVehicleId] = useState<number | null>(null);

  const [fleetStats, setFleetStats] = useState<FleetStats | null>(null);
  const [fleetLoading, setFleetLoading] = useState(false);
  const [vehicleStats, setVehicleStats] = useState<VehicleStats | null>(null);
  const [vehicleLoading, setVehicleLoading] = useState(false);
  const [innerTab, setInnerTab] = useState<'fleet' | 'vehicle'>('fleet');

  /* ── 日期 → query 参数 ── */
  const dateParams = useCallback((range: [Dayjs, Dayjs] | null) => {
    const p: Record<string, string> = {};
    if (range?.[0]) p.start_date = range[0].format('YYYY-MM-DD');
    if (range?.[1]) p.end_date = range[1].format('YYYY-MM-DD');
    return p;
  }, []);

  /* ── 加载企业（默认选首个） ── */
  const loadEnterprises = useCallback(async () => {
    try {
      const { data } = await api.get('/fleet/enterprises');
      const items: EnterpriseLite[] = (Array.isArray(data) ? data : (data as any)?.items || [])
        .map((e: any) => ({ id: e.id, name: e.name }));
      setEnterprises(items);
      if (items.length && currentEid === null) setCurrentEid(items[0].id);
    } catch {
      setEnterprises([]);
    }
  }, [currentEid]);

  /* ── 车队级汇总 ── */
  const loadFleetStats = useCallback(async (eid: number, range: [Dayjs, Dayjs] | null) => {
    setFleetLoading(true);
    try {
      const { data } = await api.get(`/enterprises/${eid}/charging-stats`, { params: dateParams(range) });
      setFleetStats(data as FleetStats);
    } catch {
      setFleetStats(null);
    } finally {
      setFleetLoading(false);
    }
  }, [dateParams]);

  /* ── 车辆列表（企业联动，默认选首台） ── */
  const loadVehicles = useCallback(async (eid: number) => {
    try {
      const { data } = await api.get(`/enterprises/${eid}/vehicles`);
      const items: VehicleLite[] = (Array.isArray(data) ? data : (data as any)?.items || [])
        .map((v: any) => ({ id: v.id, plate_number: v.plate_number }));
      setVehicles(items);
      if (items.length && vehicleId === null) setVehicleId(items[0].id);
      else if (items.length && vehicleId && !items.find(v => v.id === vehicleId)) setVehicleId(items[0].id);
      else if (!items.length) setVehicleId(null);
    } catch {
      setVehicles([]);
    }
  }, [vehicleId]);

  /* ── 单车统计 ── */
  const loadVehicleStats = useCallback(async (eid: number, vid: number, range: [Dayjs, Dayjs] | null) => {
    setVehicleLoading(true);
    try {
      const { data } = await api.get(`/enterprises/${eid}/vehicles/${vid}/charging-stats`, { params: dateParams(range) });
      setVehicleStats(data as VehicleStats);
    } catch {
      setVehicleStats(null);
    } finally {
      setVehicleLoading(false);
    }
  }, [dateParams]);

  useEffect(() => { loadEnterprises(); }, [loadEnterprises]);
  useEffect(() => { if (currentEid != null) loadFleetStats(currentEid, dateRange); }, [currentEid, dateRange, loadFleetStats]);
  useEffect(() => { if (currentEid != null) loadVehicles(currentEid); }, [currentEid, loadVehicles]);
  useEffect(() => { if (currentEid != null && vehicleId) loadVehicleStats(currentEid, vehicleId, dateRange); }, [currentEid, vehicleId, dateRange, loadVehicleStats]);

  const refreshAll = () => {
    if (currentEid == null) return;
    loadFleetStats(currentEid, dateRange);
    if (vehicleId) loadVehicleStats(currentEid, vehicleId, dateRange);
  };

  /* ── 趋势图 option（电量 + 费用双轴折线） ── */
  const trend = vehicleStats?.monthly_trend ?? [];
  const trendOption = {
    tooltip: { trigger: 'axis' },
    legend: { data: ['充电量(kWh)', '费用(¥)'] },
    grid: { left: 48, right: 56, top: 40, bottom: 32 },
    xAxis: { type: 'category', data: trend.map((t: TrendPoint) => t.month) },
    yAxis: [
      { type: 'value', name: 'kWh' },
      { type: 'value', name: '¥' },
    ],
    series: [
      { name: '充电量(kWh)', type: 'line', smooth: true, data: trend.map((t: TrendPoint) => t.charged_kwh) },
      { name: '费用(¥)', type: 'line', smooth: true, yAxisIndex: 1, data: trend.map((t: TrendPoint) => t.total_amount) },
    ],
  };

  /* ── 表格列 ── */
  const topVehicleColumns = [
    { title: '排名', key: 'rank', width: 60, render: (_: unknown, __: unknown, idx: number) => idx + 1 },
    { title: '车牌', dataIndex: 'plate_number', key: 'plate', render: (v: string) => v || '-' },
    { title: '充电量(kWh)', dataIndex: 'charged_kwh', key: 'kwh', align: 'right' as const, render: (v: number) => Number(v || 0).toLocaleString() },
    { title: '费用(¥)', dataIndex: 'total_amount', key: 'amount', align: 'right' as const, render: (v: number) => Number(v || 0).toFixed(2) },
    { title: '充电次数', dataIndex: 'order_count', key: 'orders', align: 'right' as const },
  ];
  const stationColumns = [
    { title: '场站', dataIndex: 'station_name', key: 'station', render: (v: string) => v || '-' },
    { title: '充电量(kWh)', dataIndex: 'charged_kwh', key: 'kwh', align: 'right' as const, render: (v: number) => Number(v || 0).toLocaleString() },
    { title: '充电次数', dataIndex: 'order_count', key: 'orders', align: 'right' as const },
  ];

  const fleetSummary = fleetStats?.summary;
  const vehicleSummary = vehicleStats?.summary;

  /* ── 企业空态 ── */
  if (currentEid === null && enterprises.length === 0) {
    return (
      <PageWrapper loading={false} hasData transition="slide-up">
        <Card><div style={{ padding: 24, textAlign: 'center', color: '#999' }}>暂无企业，请先在「车队企业」中创建企业。</div></Card>
      </PageWrapper>
    );
  }

  return (
    <PageWrapper
      loading={fleetLoading && !fleetStats && innerTab === 'fleet'}
      skeletonType="table"
      hasData
      transition="slide-up"
    >
      <div className="page-container">
        <Card extra={
          <Space wrap>
            <Select
              placeholder="选择企业"
              value={currentEid ?? undefined}
              onChange={(v) => { setCurrentEid(v); setVehicleId(null); }}
              style={{ width: 200 }}
              showSearch
              optionFilterProp="label"
              options={enterprises.map(e => ({ value: e.id, label: e.name }))}
            />
            <RangePicker
              value={dateRange ?? undefined}
              onChange={(dates) => setDateRange(dates as [Dayjs, Dayjs] | null)}
              placeholder={['开始日期', '结束日期']}
            />
            <Button icon={<ReloadOutlined />} onClick={refreshAll}>刷新</Button>
          </Space>
        }>
          <Tabs
            activeKey={innerTab}
            onChange={(k) => setInnerTab(k as 'fleet' | 'vehicle')}
            items={[
              {
                key: 'fleet',
                label: '车队汇总',
                children: (
                  <>
                    <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
                      <Col xs={12} sm={6}><Card><Statistic title="总电量(kWh)" value={fleetSummary?.total_kwh ?? 0} prefix={<ThunderboltOutlined />} /></Card></Col>
                      <Col xs={12} sm={6}><Card><Statistic title="总费用(¥)" value={fleetSummary?.total_amount ?? 0} prefix="¥" precision={2} valueStyle={{ color: '#34a853' }} /></Card></Col>
                      <Col xs={12} sm={6}><Card><Statistic title="充电次数" value={fleetSummary?.total_orders ?? 0} /></Card></Col>
                      <Col xs={12} sm={6}><Card><Statistic title="活跃车辆" value={fleetStats?.active_vehicles ?? 0} prefix={<CarOutlined />} /></Card></Col>
                    </Row>
                    <Row gutter={[16, 16]}>
                      <Col xs={24} lg={12}>
                        <Card title="车辆排行（充电量 Top）" size="small">
                          <Table
                            columns={topVehicleColumns}
                            dataSource={fleetStats?.top_vehicles ?? []}
                            rowKey="vehicle_id"
                            loading={fleetLoading}
                            size="small"
                            pagination={false}
                            locale={{ emptyText: <Empty description="暂无排行数据" /> }}
                          />
                        </Card>
                      </Col>
                      <Col xs={24} lg={12}>
                        <Card title="场站分布" size="small">
                          <Table
                            columns={stationColumns}
                            dataSource={fleetStats?.station_distribution ?? []}
                            rowKey="station_id"
                            loading={fleetLoading}
                            size="small"
                            pagination={false}
                            locale={{ emptyText: <Empty description="暂无场站数据" /> }}
                          />
                        </Card>
                      </Col>
                    </Row>
                  </>
                ),
              },
              {
                key: 'vehicle',
                label: '单车统计',
                children: (
                  <>
                    <Space style={{ marginBottom: 16 }}>
                      <Select
                        placeholder="选择车辆"
                        value={vehicleId ?? undefined}
                        onChange={setVehicleId}
                        style={{ width: 200 }}
                        showSearch
                        optionFilterProp="label"
                        disabled={!vehicles.length}
                        options={vehicles.map(v => ({ value: v.id, label: v.plate_number }))}
                      />
                    </Space>
                    <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
                      <Col xs={12} sm={6}><Card><Statistic title="充电次数" value={vehicleSummary?.total_orders ?? 0} /></Card></Col>
                      <Col xs={12} sm={6}><Card><Statistic title="总电量(kWh)" value={vehicleSummary?.total_kwh ?? 0} prefix={<ThunderboltOutlined />} /></Card></Col>
                      <Col xs={12} sm={6}><Card><Statistic title="总费用(¥)" value={vehicleSummary?.total_amount ?? 0} prefix="¥" precision={2} valueStyle={{ color: '#34a853' }} /></Card></Col>
                      <Col xs={12} sm={6}><Card><Statistic title="平均单次电量(kWh)" value={vehicleSummary?.avg_kwh_per_order ?? 0} /></Card></Col>
                    </Row>
                    <Card title="月度充电趋势" size="small">
                      {vehicleId ? (
                        <ReactECharts option={trendOption} style={{ height: 300 }} />
                      ) : (
                        <Empty description="请选择车辆以查看充电趋势" style={{ padding: 48 }} />
                      )}
                    </Card>
                  </>
                ),
              },
            ]}
          />
        </Card>
      </div>
    </PageWrapper>
  );
};

export default FleetChargingStatsPage;
