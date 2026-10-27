/**
 * 能耗分析报表页面 (卡 d44db94a)
 *
 * 消费真实数据 API (后端契约 commit 62cc447cf):
 * - /trend: 空库返回 [] → 空态 UI
 * - /summary: price_info.source=default 表示回退系统默认电价(打角标);
 *   yoy 上期为 0 时为 null → 占位符
 * - /station-compare: 无数据站点不输出、按收益降序
 * 不做 mock 降级: 请求失败仅提示错误并保持空态。
 */
import { energyReportAPI } from '../../api';
import React, { useState, useEffect, useCallback } from 'react';
import {
  Card, Row, Col, Statistic, Select, Space, Spin, Tabs,
  Typography, Table, Tag, Empty, message, Divider, Button
} from 'antd';
import AutoHeightTable from '../../components/AutoHeightTable';
import {
  ThunderboltOutlined, RiseOutlined, FallOutlined,
  BarChartOutlined, DollarOutlined, ArrowUpOutlined, ArrowDownOutlined,
  ReloadOutlined
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import ReactEChartsCore from 'echarts-for-react/lib/core';
import * as echarts from 'echarts/core';
import { LineChart, BarChart } from 'echarts/charts';
import { GridComponent, TooltipComponent, LegendComponent, DataZoomComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';

echarts.use([LineChart, BarChart, GridComponent, TooltipComponent, LegendComponent, DataZoomComponent, CanvasRenderer]);

const { Text } = Typography;

const CHART_COLORS = ['#ff5a36', '#34a853', '#f5a623', '#ea4335', '#722ed1', '#13c2c2'];

interface TrendPoint {
  date: string;
  pv_generation: number;
  charging_amount: number;
  discharge_amount: number;
  pv_revenue: number;
  charging_revenue: number;
  discharge_revenue: number;
  total_revenue: number;
}

interface SummaryData {
  pv_generation: number;
  charging_amount: number;
  discharge_amount: number;
  total_revenue: number;
  yoy?: {
    pv_generation_yoy?: number | null;
    charging_amount_yoy?: number | null;
    discharge_amount_yoy?: number | null;
    total_revenue_yoy?: number | null;
  } | null;
  price_info?: {
    feed_in_tariff?: number;
    charging_price?: number;
    discharge_price?: number;
    source?: string;
  } | null;
}

interface StationRow {
  station_id: number;
  name: string;
  pv_gen: number;
  charge: number;
  discharge: number;
  revenue: number;
}

interface StationTotals {
  pv_generation: number;
  charging_amount: number;
  discharge_amount: number;
  total_revenue: number;
}

const EnergyReportPage: React.FC = () => {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(false);
  const [granularity, setGranularity] = useState<'day' | 'week' | 'month'>('day');
  const [trendData, setTrendData] = useState<TrendPoint[]>([]);
  const [summary, setSummary] = useState<SummaryData | null>(null);
  const [stationCompare, setStationCompare] = useState<StationRow[]>([]);
  const [stationTotals, setStationTotals] = useState<StationTotals | null>(null);

  // ========= 数据加载 (失败提示+空态, 不造数) =========

  const loadTrend = useCallback(async (g: 'day' | 'week' | 'month') => {
    setLoading(true);
    try {
      const res = await energyReportAPI.trend({ granularity: g });
      setTrendData(res.data?.trend || []);
    } catch {
      message.error(t('energyReport.load_trend_failed'));
      setTrendData([]);
    } finally {
      setLoading(false);
    }
  }, [t]);

  const loadSummary = useCallback(async () => {
    try {
      const res = await energyReportAPI.summary({ period: 'month' });
      setSummary(res.data || null);
    } catch {
      message.error(t('energyReport.load_summary_failed'));
      setSummary(null);
    }
  }, [t]);

  const loadStationCompare = useCallback(async () => {
    try {
      const res = await energyReportAPI.stationCompare();
      setStationCompare(res.data?.stations || []);
      setStationTotals(res.data?.totals || null);
    } catch {
      message.error(t('energyReport.load_station_failed'));
      setStationCompare([]);
      setStationTotals(null);
    }
  }, [t]);

  useEffect(() => { loadTrend(granularity); }, [loadTrend, granularity]);
  useEffect(() => { loadSummary(); }, [loadSummary]);
  useEffect(() => { loadStationCompare(); }, [loadStationCompare]);

  // ========= ECharts =========

  const energyTrendOption = {
    color: CHART_COLORS,
    tooltip: { trigger: 'axis' as const },
    legend: { data: [t('energyReport.pv_generation'), t('energyReport.charging_amount'), t('energyReport.discharge_amount')], top: 0 },
    grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true, top: 30 },
    xAxis: { type: 'category' as const, data: trendData.map(d => d.date || ''), boundaryGap: false },
    yAxis: { type: 'value' as const, name: 'kWh' },
    series: [
      { name: t('energyReport.pv_generation'), type: 'line', smooth: true, data: trendData.map(d => d.pv_generation), areaStyle: { opacity: 0.1 } },
      { name: t('energyReport.charging_amount'), type: 'line', smooth: true, data: trendData.map(d => d.charging_amount), areaStyle: { opacity: 0.1 } },
      { name: t('energyReport.discharge_amount'), type: 'line', smooth: true, data: trendData.map(d => d.discharge_amount), areaStyle: { opacity: 0.1 } },
    ],
  };

  const revenueTrendOption = {
    color: ['#34a853', '#f5a623', '#722ed1'],
    tooltip: { trigger: 'axis' as const },
    legend: { data: [t('energyReport.pv_revenue'), t('energyReport.charging_revenue'), t('energyReport.discharge_revenue')], top: 0 },
    grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true, top: 30 },
    xAxis: { type: 'category' as const, data: trendData.map(d => d.date || ''), boundaryGap: false },
    yAxis: { type: 'value' as const, name: '¥' },
    series: [
      { name: t('energyReport.pv_revenue'), type: 'bar', data: trendData.map(d => d.pv_revenue) },
      { name: t('energyReport.charging_revenue'), type: 'bar', data: trendData.map(d => d.charging_revenue) },
      { name: t('energyReport.discharge_revenue'), type: 'bar', data: trendData.map(d => d.discharge_revenue) },
    ],
  };

  const stationCompareOption = {
    color: CHART_COLORS,
    tooltip: { trigger: 'axis' as const, axisPointer: { type: 'shadow' as const } },
    grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
    xAxis: { type: 'value' as const, name: 'kWh' },
    yAxis: { type: 'category' as const, data: stationCompare.map(s => s.name).reverse(), axisLabel: { width: 80, overflow: 'truncate', ellipsis: '...' } },
    series: [
      { name: t('energyReport.pv_generation'), type: 'bar', stack: 'total', data: stationCompare.map(s => s.pv_gen).reverse() },
      { name: t('energyReport.charging_amount'), type: 'bar', stack: 'total', data: stationCompare.map(s => s.charge).reverse() },
      { name: t('energyReport.discharge_amount'), type: 'bar', stack: 'total', data: stationCompare.map(s => s.discharge).reverse() },
    ],
  };

  // ========= 汇总卡 / 站点表 =========

  const yoyTag = (val: number | null | undefined) => {
    if (val == null) return <Text type="secondary">--</Text>;
    return val >= 0
      ? <Tag color="success" icon={<ArrowUpOutlined />}>+{val}%</Tag>
      : <Tag color="error" icon={<ArrowDownOutlined />}>{val}%</Tag>;
  };

  const stationColumns = [
    { title: t('energyReport.station'), dataIndex: 'name', key: 'name', fixed: 'left' as const },
    { title: `${t('energyReport.pv_generation')}(kWh)`, dataIndex: 'pv_gen', key: 'pv_gen', sorter: (a: StationRow, b: StationRow) => a.pv_gen - b.pv_gen, render: (v: number) => v.toLocaleString() },
    { title: `${t('energyReport.charging_amount')}(kWh)`, dataIndex: 'charge', key: 'charge', sorter: (a: StationRow, b: StationRow) => a.charge - b.charge, render: (v: number) => v.toLocaleString() },
    { title: `${t('energyReport.discharge_amount')}(kWh)`, dataIndex: 'discharge', key: 'discharge', sorter: (a: StationRow, b: StationRow) => a.discharge - b.discharge, render: (v: number) => v.toLocaleString() },
    { title: `${t('energyReport.revenue')}(¥)`, dataIndex: 'revenue', key: 'revenue', sorter: (a: StationRow, b: StationRow) => a.revenue - b.revenue, render: (v: number) => `¥${v.toLocaleString()}` },
  ];

  const trendEmpty = trendData.length === 0;
  const stationEmpty = stationCompare.length === 0;
  const isDefaultPrice = summary?.price_info?.source === 'default';

  return (
    <Spin spinning={loading}>
      {/* 顶部汇总卡片 */}
      {summary && (
        <Row gutter={16} style={{ marginBottom: 16 }}>
          <Col xs={24} sm={12} lg={6}>
            <Card>
              <Statistic
                title={t('energyReport.pv_generation_month')}
                value={summary.pv_generation}
                suffix="kWh"
                prefix={<ThunderboltOutlined />}
              />
              <Text type="secondary" style={{ fontSize: 12 }}>
                {t('energyReport.yoy')} {yoyTag(summary.yoy?.pv_generation_yoy)}
              </Text>
            </Card>
          </Col>
          <Col xs={24} sm={12} lg={6}>
            <Card>
              <Statistic
                title={t('energyReport.charging_amount')}
                value={summary.charging_amount}
                suffix="kWh"
                prefix={<RiseOutlined />}
              />
              <Text type="secondary" style={{ fontSize: 12 }}>
                {t('energyReport.yoy')} {yoyTag(summary.yoy?.charging_amount_yoy)}
              </Text>
            </Card>
          </Col>
          <Col xs={24} sm={12} lg={6}>
            <Card>
              <Statistic
                title={t('energyReport.discharge_amount')}
                value={summary.discharge_amount}
                suffix="kWh"
                prefix={<FallOutlined />}
              />
              <Text type="secondary" style={{ fontSize: 12 }}>
                {t('energyReport.yoy')} {yoyTag(summary.yoy?.discharge_amount_yoy)}
              </Text>
            </Card>
          </Col>
          <Col xs={24} sm={12} lg={6}>
            <Card>
              <Statistic
                title={t('energyReport.total_revenue')}
                value={summary.total_revenue}
                precision={2}
                prefix={<DollarOutlined />}
                valueStyle={{ color: '#3f8600' }}
              />
              <Text type="secondary" style={{ fontSize: 12 }}>
                {t('energyReport.yoy')} {yoyTag(summary.yoy?.total_revenue_yoy)}
              </Text>
            </Card>
          </Col>
        </Row>
      )}

      {/* 控制栏 */}
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={24} md={12}>
          <Space wrap>
            <Text strong>{t('energyReport.granularity')}</Text>
            <Select
              value={granularity}
              onChange={(v: 'day' | 'week' | 'month') => setGranularity(v)}
              style={{ width: 120 }}
              options={[
                { label: t('energyReport.by_day'), value: 'day' },
                { label: t('energyReport.by_week'), value: 'week' },
                { label: t('energyReport.by_month'), value: 'month' },
              ]}
            />
          </Space>
        </Col>
        <Col xs={24} md={12} style={{ textAlign: 'right' }}>
          <Space wrap>
            <Space>
              <Text type="secondary">{t('energyReport.price')}:</Text>
              {isDefaultPrice && (
                <Tag color="orange">{t('energyReport.default_price')}</Tag>
              )}
              <Tag>{t('energyReport.pv')} ¥{summary?.price_info?.feed_in_tariff ?? '--'}/kWh</Tag>
              <Tag>{t('energyReport.charging')} ¥{summary?.price_info?.charging_price ?? '--'}/kWh</Tag>
              <Tag>{t('energyReport.discharging')} ¥{summary?.price_info?.discharge_price ?? '--'}/kWh</Tag>
            </Space>
            <Button icon={<ReloadOutlined />} onClick={() => { loadTrend(granularity); loadSummary(); loadStationCompare(); }}>
              {t('energyReport.refresh')}
            </Button>
          </Space>
        </Col>
      </Row>

      {/* 图表区域 */}
      <Tabs items={[
        {
          key: 'trend',
          label: <span><BarChartOutlined /> {t('energyReport.trend_tab')}</span>,
          children: trendEmpty ? (
            <Card><Empty description={t('energyReport.no_trend_data')} /></Card>
          ) : (
            <Row gutter={16}>
              <Col span={24}>
                <Card title={t('energyReport.energy_trend_title')} size="small" style={{ marginBottom: 16 }}>
                  <ReactEChartsCore echarts={echarts} option={energyTrendOption} style={{ height: 350 }} />
                </Card>
              </Col>
              <Col span={24}>
                <Card title={t('energyReport.revenue_trend_title')} size="small">
                  <ReactEChartsCore echarts={echarts} option={revenueTrendOption} style={{ height: 300 }} />
                </Card>
              </Col>
            </Row>
          ),
        },
        {
          key: 'station',
          label: <span><BarChartOutlined /> {t('energyReport.station_tab')}</span>,
          children: stationEmpty ? (
            <Card><Empty description={t('energyReport.no_station_data')} /></Card>
          ) : (
            <>
              <Card title={t('energyReport.station_compare_title')} size="small" style={{ marginBottom: 16 }}>
                <ReactEChartsCore echarts={echarts} option={stationCompareOption} style={{ height: 350 }} />
              </Card>
              <Card title={t('energyReport.station_detail_title')} size="small">
                {stationTotals && (
                  <Row gutter={16} style={{ marginBottom: 12 }}>
                    <Col xs={12} md={6}><Text type="secondary">{t('energyReport.total_pv')}:</Text> <Text strong>{stationTotals.pv_generation.toLocaleString()} kWh</Text></Col>
                    <Col xs={12} md={6}><Text type="secondary">{t('energyReport.total_charging')}:</Text> <Text strong>{stationTotals.charging_amount.toLocaleString()} kWh</Text></Col>
                    <Col xs={12} md={6}><Text type="secondary">{t('energyReport.total_discharging')}:</Text> <Text strong>{stationTotals.discharge_amount.toLocaleString()} kWh</Text></Col>
                    <Col xs={12} md={6}><Text type="secondary">{t('energyReport.total_revenue')}:</Text> <Text strong type="success">¥{stationTotals.total_revenue.toLocaleString()}</Text></Col>
                  </Row>
                )}
                <Divider style={{ margin: '8px 0' }} />
                <AutoHeightTable
                  scroll={{ x: 'max-content', y: 'calc(100vh - 420px)' }}
                  columns={stationColumns}
                  dataSource={stationCompare}
                  rowKey="station_id"
                  pagination={false}
                  size="small"
                />
              </Card>
            </>
          ),
        },
      ]} />
    </Spin>
  );
};

export default EnergyReportPage;
