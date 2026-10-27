/**
 * 营收总览 — 总营收/充电量/订单数/客单价 + 趋势图(日/周/月/年切换)
 */
import React, { useEffect, useState, useCallback } from 'react';
import { Card, Row, Col, Statistic, Select, Spin, Empty } from 'antd';
import {
  DollarOutlined, ThunderboltOutlined, ShoppingCartOutlined, CalculatorOutlined,
} from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import api from '../../../api';

const RevenueOverview: React.FC = () => {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [range, setRange] = useState<'day' | 'week' | 'month' | 'year'>('day');

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get('/analytics/revenue', { params: { range } });
      setData(res.data?.data);
    } catch {
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [range]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const getTrendOption = () => {
    if (!data?.trend?.length) return {};
    const trend = data.trend;
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

  if (loading) {
    return <Card><div style={{ textAlign: 'center', padding: 60 }}><Spin size="large" /></div></Card>;
  }

  const summary = data?.summary || { total_revenue: 0, total_kwh: 0, total_orders: 0, avg_per_order: 0 };

  return (
    <div>
      <Card
        extra={
          <Select value={range} onChange={(v) => setRange(v)} size="small" style={{ width: 100 }}
            options={[
              { label: '按日', value: 'day' },
              { label: '按周', value: 'week' },
              { label: '按月', value: 'month' },
              { label: '按年', value: 'year' },
            ]} />
        }
      >
        <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
          <Col xs={12} sm={6}>
            <Card><Statistic title="总营收(元)" value={summary.total_revenue} precision={2} prefix={<DollarOutlined />} valueStyle={{ color: '#1890ff' }} /></Card>
          </Col>
          <Col xs={12} sm={6}>
            <Card><Statistic title="总充电量(kWh)" value={summary.total_kwh} precision={2} prefix={<ThunderboltOutlined />} valueStyle={{ color: '#52c41a' }} /></Card>
          </Col>
          <Col xs={12} sm={6}>
            <Card><Statistic title="总订单数" value={summary.total_orders} prefix={<ShoppingCartOutlined />} /></Card>
          </Col>
          <Col xs={12} sm={6}>
            <Card><Statistic title="客单价(元)" value={summary.avg_per_order} precision={2} prefix={<CalculatorOutlined />} valueStyle={{ color: '#fa8c16' }} /></Card>
          </Col>
        </Row>

        {data?.trend?.length ? (
          <ReactECharts option={getTrendOption()} style={{ height: 360 }} />
        ) : (
          <Empty description="暂无趋势数据" />
        )}
      </Card>
    </div>
  );
};

export default RevenueOverview;
