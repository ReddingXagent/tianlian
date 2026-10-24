/**
 * 时段收益分析 — 尖峰平谷各时段电量分布/电价贡献/服务费占比
 */
import React, { useEffect, useState, useCallback } from 'react';
import { Card, Select, Spin, Empty, Row, Col, Statistic } from 'antd';
import ReactECharts from 'echarts-for-react';
import api from '../../../api';

const SLOT_COLORS: Record<string, string> = {
  peak: '#ff4d4f', flat: '#1890ff', valley: '#52c41a', trough: '#722ed1',
};

const TimeSlotAnalysis: React.FC = () => {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [range, setRange] = useState<'day' | 'week' | 'month' | 'year'>('day');

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get('/analytics/time-slot', { params: { range } });
      setData(res.data?.data);
    } catch { setData(null); }
    finally { setLoading(false); }
  }, [range]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const getPieOption = () => {
    if (!data?.slots?.length) return {};
    const chartData = data.slots
      .filter((s: any) => s.kwh > 0)
      .map((s: any) => ({
        name: s.slot_name,
        value: s.kwh,
        itemStyle: { color: SLOT_COLORS[s.slot_key] || '#8c8c8c' },
      }));
    return {
      tooltip: { trigger: 'item', formatter: '{b}: {c} kWh ({d}%)' },
      legend: { orient: 'vertical', right: 10, top: 'center' },
      series: [{
        type: 'pie', radius: ['40%', '70%'], center: ['40%', '50%'],
        label: { formatter: '{b}\n{d}%', fontSize: 11 },
        data: chartData,
      }],
    };
  };

  const getBarOption = () => {
    if (!data?.slots?.length) return {};
    return {
      tooltip: { trigger: 'axis' },
      grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
      xAxis: { type: 'category', data: data.slots.map((s: any) => s.slot_name) },
      yAxis: [{ type: 'value', name: 'kWh' }, { type: 'value', name: '占比%' }],
      series: [
        { name: '电量(kWh)', type: 'bar', data: data.slots.map((s: any) => s.kwh), itemStyle: { color: '#1890ff' } },
        { name: '占比(%)', type: 'line', yAxisIndex: 1, data: data.slots.map((s: any) => s.kwh_percentage), itemStyle: { color: '#fa8c16' } },
      ],
    };
  };

  if (loading) return <Card><div style={{ textAlign: 'center', padding: 60 }}><Spin size="large" /></div></Card>;

  const summary = data?.summary || {};

  return (
    <Card title="时段收益分析(尖峰平谷)" extra={
      <Select value={range} onChange={(v) => setRange(v)} size="small" style={{ width: 100 }}
        options={[
          { label: '按日', value: 'day' }, { label: '按周', value: 'week' },
          { label: '按月', value: 'month' }, { label: '按年', value: 'year' },
        ]} />
    }>
      {data?.slots?.length ? (
        <>
          <Row gutter={16} style={{ marginBottom: 16 }}>
            <Col span={6}><Statistic title="总电量(kWh)" value={summary.total_kwh || 0} precision={2} /></Col>
            <Col span={6}><Statistic title="电费(元)" value={summary.total_electricity_fee || 0} precision={2} /></Col>
            <Col span={6}><Statistic title="服务费(元)" value={summary.total_service_fee || 0} precision={2} /></Col>
            <Col span={6}><Statistic title="总订单" value={summary.total_orders || 0} /></Col>
          </Row>
          <Row gutter={16}>
            <Col span={12}>
              <Card title="电量分布" size="small">
                <ReactECharts option={getPieOption()} style={{ height: 300 }} />
              </Card>
            </Col>
            <Col span={12}>
              <Card title="电量&占比" size="small">
                <ReactECharts option={getBarOption()} style={{ height: 300 }} />
              </Card>
            </Col>
          </Row>
        </>
      ) : <Empty description="暂无时段分析数据" />}
    </Card>
  );
};

export default TimeSlotAnalysis;
