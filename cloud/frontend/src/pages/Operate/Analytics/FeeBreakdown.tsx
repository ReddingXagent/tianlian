/**
 * 费用占比分析 — 5项费用(充电/服务/停车/占桩/预约) 饼图 + 趋势
 */
import React, { useEffect, useState, useCallback } from 'react';
import { Card, Select, Spin, Empty, Row, Col, Statistic } from 'antd';
import ReactECharts from 'echarts-for-react';
import api from '../../../api';

const FEE_COLORS: Record<string, string> = {
  electricity: '#1890ff',
  service: '#52c41a',
  parking: '#faad14',
  occupancy: '#ff4d4f',
  reservation: '#722ed1',
};

const FeeBreakdown: React.FC = () => {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [range, setRange] = useState<'day' | 'week' | 'month' | 'year'>('day');

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get('/analytics/fee-breakdown', { params: { range } });
      setData(res.data?.data);
    } catch {
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [range]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const getPieOption = () => {
    if (!data?.breakdown?.length) return {};
    const chartData = data.breakdown
      .filter((b: any) => b.amount > 0)
      .map((b: any) => ({
        name: b.fee_name,
        value: b.amount,
        itemStyle: { color: FEE_COLORS[b.fee_type] || '#8c8c8c' },
      }));
    return {
      tooltip: { trigger: 'item', formatter: '{b}: ¥{c} ({d}%)' },
      legend: { orient: 'vertical', right: 10, top: 'center' },
      series: [{
        type: 'pie', radius: ['40%', '70%'], center: ['40%', '50%'],
        label: { formatter: '{b}\n{d}%', fontSize: 11 },
        emphasis: { label: { fontSize: 16, fontWeight: 'bold' } },
        data: chartData,
      }],
    };
  };

  const getTrendOption = () => {
    if (!data?.trend?.length) return {};
    const trend = data.trend;
    const feeKeys = ['electricity', 'service', 'parking', 'occupancy', 'reservation'];
    const feeNames: Record<string, string> = { electricity: '充电费', service: '服务费', parking: '停车费', occupancy: '占桩费', reservation: '预约费' };
    return {
      tooltip: { trigger: 'axis' },
      legend: { data: feeKeys.map(k => feeNames[k]) },
      grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
      xAxis: { type: 'category', data: trend.map((t: any) => t.period) },
      yAxis: { type: 'value', name: '元' },
      series: feeKeys.map(key => ({
        name: feeNames[key], type: 'bar', stack: 'total',
        data: trend.map((t: any) => t[key]),
        itemStyle: { color: FEE_COLORS[key] },
      })),
    };
  };

  if (loading) return <Card><div style={{ textAlign: 'center', padding: 60 }}><Spin size="large" /></div></Card>;

  return (
    <Card
      title="五项费用占比分析"
      extra={
        <Select value={range} onChange={(v) => setRange(v)} size="small" style={{ width: 100 }}
          options={[
            { label: '按日', value: 'day' }, { label: '按周', value: 'week' },
            { label: '按月', value: 'month' }, { label: '按年', value: 'year' },
          ]} />
      }
    >
      {data?.total > 0 ? (
        <>
          <Row gutter={16} style={{ marginBottom: 16 }}>
            <Col span={6}><Statistic title="费用总额(元)" value={data.total} precision={2} /></Col>
            {data.breakdown?.map((b: any) => (
              <Col span={Math.floor(18 / data.breakdown.length)} key={b.fee_type}>
                <Statistic title={`${b.fee_name}占比`} value={b.percentage} suffix="%" precision={1}
                  valueStyle={{ color: FEE_COLORS[b.fee_type] }} />
              </Col>
            ))}
          </Row>
          <Row gutter={16}>
            <Col span={12}>
              <ReactECharts option={getPieOption()} style={{ height: 320 }} />
            </Col>
            <Col span={12}>
              <ReactECharts option={getTrendOption()} style={{ height: 320 }} />
            </Col>
          </Row>
        </>
      ) : <Empty description="暂无费用数据" />}
    </Card>
  );
};

export default FeeBreakdown;
