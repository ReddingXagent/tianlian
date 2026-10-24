/**
 * 用户收入分析 — 按用户类型(APP/卡/VIN/互联互通/企业)营收贡献/户均消费/复充率
 */
import React, { useEffect, useState, useCallback } from 'react';
import { Card, Table, Select, Spin, Empty, Tag } from 'antd';
import ReactECharts from 'echarts-for-react';
import api from '../../../api';

const USER_COLORS: Record<string, string> = {
  app: '#1890ff', card: '#52c41a', vin: '#722ed1', interconnect: '#fa8c16', enterprise: '#eb2f96',
};

const UserRevenue: React.FC = () => {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [range, setRange] = useState<'day' | 'week' | 'month' | 'year'>('day');

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get('/analytics/user-revenue', { params: { range } });
      setData(res.data?.data);
    } catch { setData(null); }
    finally { setLoading(false); }
  }, [range]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const getBarOption = () => {
    if (!data?.breakdown?.length) return {};
    const bd = data.breakdown;
    return {
      tooltip: { trigger: 'axis' },
      legend: { data: ['营收(元)', '充电量(kWh)'] },
      grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
      xAxis: { type: 'category', data: bd.map((b: any) => b.type_label) },
      yAxis: { type: 'value' },
      series: [
        { name: '营收(元)', type: 'bar', data: bd.map((b: any) => b.revenue), itemStyle: { color: '#1890ff' } },
        { name: '充电量(kWh)', type: 'bar', data: bd.map((b: any) => b.kwh), itemStyle: { color: '#52c41a' } },
      ],
    };
  };

  const columns = [
    { title: '用户类型', dataIndex: 'type_label', key: 'type_label', render: (v: string, r: any) => <Tag color={USER_COLORS[r.user_type] || 'blue'}>{v}</Tag> },
    { title: '营收(元)', dataIndex: 'revenue', key: 'revenue', align: 'right' as const, render: (v: number) => `¥${v.toFixed(2)}` },
    { title: '充电量(kWh)', dataIndex: 'kwh', key: 'kwh', align: 'right' as const, render: (v: number) => v.toFixed(2) },
    { title: '订单数', dataIndex: 'orders', key: 'orders', align: 'right' as const },
    { title: '独立用户', dataIndex: 'unique_users', key: 'unique_users', align: 'right' as const },
    { title: '户均消费(元)', dataIndex: 'avg_per_user', key: 'avg_per_user', align: 'right' as const, render: (v: number) => `¥${v.toFixed(2)}` },
    { title: '人均订单', dataIndex: 'orders_per_user', key: 'orders_per_user', align: 'right' as const, render: (v: number) => v.toFixed(1) },
    { title: '复充率', dataIndex: 'recharge_rate', key: 'recharge_rate', align: 'right' as const, render: (v: number) => `${v}%` },
  ];

  if (loading) return <Card><div style={{ textAlign: 'center', padding: 60 }}><Spin size="large" /></div></Card>;

  return (
    <Card title="用户收入分析" extra={
      <Select value={range} onChange={(v) => setRange(v)} size="small" style={{ width: 100 }}
        options={[
          { label: '按日', value: 'day' }, { label: '按周', value: 'week' },
          { label: '按月', value: 'month' }, { label: '按年', value: 'year' },
        ]} />
    }>
      {data?.breakdown?.length ? (
        <>
          <ReactECharts option={getBarOption()} style={{ height: 300, marginBottom: 16 }} />
          <Table columns={columns} dataSource={data.breakdown} rowKey="user_type" pagination={false} size="small" />
        </>
      ) : <Empty description="暂无用户收入数据" />}
    </Card>
  );
};

export default UserRevenue;
