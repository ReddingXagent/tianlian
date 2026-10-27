/**
 * 站点收益排行 — 站点营收/充电量/利用率/收益每桩
 */
import React, { useEffect, useState, useCallback } from 'react';
import { Card, Table, Select, Spin, Empty, Tag, Input } from 'antd';
import { SearchOutlined } from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import api from '../../../api';

const StationRank: React.FC = () => {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [range, setRange] = useState<'day' | 'week' | 'month' | 'year'>('day');
  const [search, setSearch] = useState('');

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get('/analytics/station-rank', { params: { range, limit: 50 } });
      setData(res.data?.data);
    } catch { setData(null); }
    finally { setLoading(false); }
  }, [range]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const getBarOption = () => {
    if (!data?.ranking?.length) return {};
    const ranking = data.ranking.slice(0, 10);
    return {
      tooltip: { trigger: 'axis' },
      legend: { data: ['营收(元)', '充电量(kWh)'] },
      grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
      xAxis: { type: 'category', data: ranking.map((r: any) => r.station_name), axisLabel: { rotate: 30 } },
      yAxis: { type: 'value' },
      series: [
        { name: '营收(元)', type: 'bar', data: ranking.map((r: any) => r.revenue), itemStyle: { color: '#1890ff' } },
        { name: '充电量(kWh)', type: 'bar', data: ranking.map((r: any) => r.kwh), itemStyle: { color: '#52c41a' } },
      ],
    };
  };

  const columns = [
    { title: '排名', key: 'rank', width: 60, render: (_: any, __: any, idx: number) => idx + 1 },
    { title: '站点', dataIndex: 'station_name', key: 'station_name' },
    { title: '编码', dataIndex: 'station_code', key: 'station_code', width: 100 },
    { title: '营收(元)', dataIndex: 'revenue', key: 'revenue', align: 'right' as const, sorter: (a: any, b: any) => a.revenue - b.revenue, render: (v: number) => <span style={{ fontWeight: 600 }}>¥{v.toFixed(2)}</span> },
    { title: '充电量(kWh)', dataIndex: 'kwh', key: 'kwh', align: 'right' as const, render: (v: number) => v.toFixed(2) },
    { title: '订单数', dataIndex: 'orders', key: 'orders', align: 'right' as const },
    {
      title: '利用率', dataIndex: 'utilization_rate', key: 'utilization_rate', align: 'right' as const,
      render: (v: number) => <Tag color={v > 50 ? 'green' : v > 20 ? 'orange' : 'red'}>{v.toFixed(1)}%</Tag>,
    },
    { title: '收益/桩(元)', dataIndex: 'revenue_per_pile', key: 'revenue_per_pile', align: 'right' as const, render: (v: number) => `¥${v.toFixed(2)}` },
    { title: '单均(元)', dataIndex: 'avg_revenue_per_order', key: 'avg_revenue_per_order', align: 'right' as const, render: (v: number) => `¥${v.toFixed(2)}` },
  ];

  const filtered = data?.ranking?.filter((r: any) =>
    !search || r.station_name?.includes(search) || r.station_code?.includes(search)
  ) || [];

  if (loading) return <Card><div style={{ textAlign: 'center', padding: 60 }}><Spin size="large" /></div></Card>;

  return (
    <Card title="站点收益排行" extra={
      <div style={{ display: 'flex', gap: 8 }}>
        <Input placeholder="搜索站点" prefix={<SearchOutlined />} value={search} onChange={e => setSearch(e.target.value)} style={{ width: 150 }} allowClear />
        <Select value={range} onChange={(v) => setRange(v)} size="small" style={{ width: 100 }}
          options={[
            { label: '按日', value: 'day' }, { label: '按周', value: 'week' },
            { label: '按月', value: 'month' }, { label: '按年', value: 'year' },
          ]} />
      </div>
    }>
      {filtered.length > 0 ? (
        <>
          <ReactECharts option={getBarOption()} style={{ height: 300, marginBottom: 16 }} />
          <Table columns={columns} dataSource={filtered} rowKey="station_id" pagination={{ pageSize: 15, showSizeChanger: true }} size="small" />
        </>
      ) : <Empty description="暂无站点排行数据" />}
    </Card>
  );
};

export default StationRank;
