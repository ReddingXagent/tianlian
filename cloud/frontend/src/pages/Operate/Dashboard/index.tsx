/**
 * 天链 V3 — 运营看板 Dashboard
 * SPEC §3 营销看板首页
 *
 * 聚合展示:
 *   1. 4项 KPI (总营收 / 总充电量 / 总订单数 / 客单价)
 *   2. 营收·充电量·订单趋势图 (日/周/月/年)
 *   3. 五项费用占比饼图
 *   4. 站点收益排行 Top10
 *
 * 数据来源: /api/v1/analytics/revenue | /fee-breakdown | /station-rank
 */
import React, { useEffect, useState, useCallback } from 'react';
import {
  Card, Row, Col, Statistic, Select, Spin, Empty, Table, Tag,
} from 'antd';
import {
  DollarOutlined, ThunderboltOutlined, ShoppingCartOutlined, CalculatorOutlined,
} from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import api from '../../../api';

type Range = 'day' | 'week' | 'month' | 'year';

const RANGE_OPTIONS = [
  { label: '按日', value: 'day' as Range },
  { label: '按周', value: 'week' as Range },
  { label: '按月', value: 'month' as Range },
  { label: '按年', value: 'year' as Range },
];

const FEE_COLORS: Record<string, string> = {
  electricity: '#1890ff',
  service: '#52c41a',
  parking: '#faad14',
  occupancy: '#ff4d4f',
  reservation: '#722ed1',
};

const OperateDashboard: React.FC = () => {
  const [range, setRange] = useState<Range>('day');
  const [loading, setLoading] = useState(false);
  const [revenue, setRevenue] = useState<any>(null);
  const [fee, setFee] = useState<any>(null);
  const [rank, setRank] = useState<any>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [revRes, feeRes, rankRes] = await Promise.all([
        api.get('/analytics/revenue', { params: { range } }).catch(() => null),
        api.get('/analytics/fee-breakdown', { params: { range } }).catch(() => null),
        api.get('/analytics/station-rank', { params: { range, limit: 10 } }).catch(() => null),
      ]);
      setRevenue(revRes?.data?.data ?? null);
      setFee(feeRes?.data?.data ?? null);
      setRank(rankRes?.data?.data ?? null);
    } finally {
      setLoading(false);
    }
  }, [range]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const summary = revenue?.summary || { total_revenue: 0, total_kwh: 0, total_orders: 0, avg_per_order: 0 };

  const getTrendOption = () => {
    const trend = revenue?.trend || [];
    if (!trend.length) return {};
    return {
      tooltip: { trigger: 'axis' },
      legend: { data: ['营收(元)', '充电量(kWh)', '订单数'] },
      grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
      xAxis: { type: 'category', data: trend.map((t: any) => t.period) },
      yAxis: [
        { type: 'value', name: '元/kWh' },
        { type: 'value', name: '订单' },
      ],
      series: [
        { name: '营收(元)', type: 'line', smooth: true, data: trend.map((t: any) => t.revenue), itemStyle: { color: '#1890ff' } },
        { name: '充电量(kWh)', type: 'line', smooth: true, data: trend.map((t: any) => t.kwh), itemStyle: { color: '#52c41a' } },
        { name: '订单数', type: 'bar', yAxisIndex: 1, data: trend.map((t: any) => t.orders), itemStyle: { color: '#faad14', opacity: 0.6 } },
      ],
    };
  };

  const getPieOption = () => {
    const breakdown = fee?.breakdown || [];
    const chartData = breakdown
      .filter((b: any) => b.amount > 0)
      .map((b: any) => ({
        name: b.fee_name,
        value: b.amount,
        itemStyle: { color: FEE_COLORS[b.fee_type] || '#8c8c8c' },
      }));
    if (!chartData.length) return {};
    return {
      tooltip: { trigger: 'item', formatter: '{b}: ¥{c} ({d}%)' },
      legend: { orient: 'vertical', right: 10, top: 'center' },
      series: [{
        type: 'pie', radius: ['40%', '70%'], center: ['40%', '50%'],
        label: { formatter: '{b}\n{d}%', fontSize: 11 },
        data: chartData,
      }],
    };
  };

  const ranking = (rank?.ranking || []).slice(0, 10);

  const rankColumns = [
    { title: '排名', key: 'rank', width: 60, render: (_: any, __: any, idx: number) => idx + 1 },
    { title: '站点', dataIndex: 'station_name', key: 'station_name' },
    { title: '营收(元)', dataIndex: 'revenue', key: 'revenue', align: 'right' as const,
      render: (v: number) => <span style={{ fontWeight: 600 }}>¥{(v || 0).toFixed(2)}</span> },
    { title: '充电量(kWh)', dataIndex: 'kwh', key: 'kwh', align: 'right' as const,
      render: (v: number) => (v || 0).toFixed(2) },
    { title: '订单数', dataIndex: 'orders', key: 'orders', align: 'right' as const },
    { title: '利用率', dataIndex: 'utilization_rate', key: 'utilization_rate', align: 'right' as const,
      render: (v: number) => <Tag color={(v || 0) > 50 ? 'green' : (v || 0) > 20 ? 'orange' : 'red'}>{(v || 0).toFixed(1)}%</Tag> },
  ];

  return (
    <Card
      title="运营看板"
      extra={
        <Select
          value={range}
          onChange={(v) => setRange(v)}
          style={{ width: 100 }}
          options={RANGE_OPTIONS}
        />
      }
    >
      {loading ? (
        <div style={{ textAlign: 'center', padding: 60 }}><Spin size="large" /></div>
      ) : (
        <>
          {/* KPI 概览 */}
          <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
            <Col xs={12} sm={6}>
              <Card><Statistic title="总营收" value={summary.total_revenue || 0} precision={2} prefix={<DollarOutlined />} valueStyle={{ color: '#1890ff' }} /></Card>
            </Col>
            <Col xs={12} sm={6}>
              <Card><Statistic title="总充电量" value={summary.total_kwh || 0} precision={2} prefix={<ThunderboltOutlined />} valueStyle={{ color: '#52c41a' }} suffix="kWh" /></Card>
            </Col>
            <Col xs={12} sm={6}>
              <Card><Statistic title="总订单数" value={summary.total_orders || 0} prefix={<ShoppingCartOutlined />} /></Card>
            </Col>
            <Col xs={12} sm={6}>
              <Card><Statistic title="客单价" value={summary.avg_per_order || 0} precision={2} prefix={<CalculatorOutlined />} valueStyle={{ color: '#fa8c16' }} suffix="元" /></Card>
            </Col>
          </Row>

          {/* 趋势图 + 费用饼图 */}
          <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
            <Col xs={24} lg={14}>
              <Card title="营收 · 充电量 · 订单趋势" size="small">
                {revenue?.trend?.length ? (
                  <ReactECharts option={getTrendOption()} style={{ height: 300 }} />
                ) : (
                  <Empty description="暂无趋势数据" style={{ padding: 40 }} />
                )}
              </Card>
            </Col>
            <Col xs={24} lg={10}>
              <Card title="五项费用占比" size="small">
                {fee?.breakdown?.length ? (
                  <ReactECharts option={getPieOption()} style={{ height: 300 }} />
                ) : (
                  <Empty description="暂无费用数据" style={{ padding: 40 }} />
                )}
              </Card>
            </Col>
          </Row>

          {/* 站点收益排行 Top10 */}
          <Card title="站点收益排行 Top10" size="small">
            {ranking.length ? (
              <Table
                columns={rankColumns}
                dataSource={ranking}
                rowKey="station_id"
                pagination={false}
                size="small"
              />
            ) : (
              <Empty description="暂无站点排行数据" style={{ padding: 40 }} />
            )}
          </Card>
        </>
      )}
    </Card>
  );
};

export default OperateDashboard;
